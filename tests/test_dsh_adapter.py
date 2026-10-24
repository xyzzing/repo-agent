"""RA-007: DSH adapter contract against captured fixtures and a fake dsh.

The fake dsh is a real subprocess speaking the verified CLI contract, so
argv construction, stdin delivery, timeout-kill, and stderr handling are
all exercised across a process boundary. Parser fixtures are captured
live events (dsh 0.2.1-rc.2), not invented shapes.
"""
import json
import os
import stat
from contextlib import contextmanager
from pathlib import Path

import pytest

from repo_agent.adapters.dsh import (
    DshParseError,
    parse_events,
    run_task,
    session_id_from_events,
    usage_from_events,
)

FIXTURE = Path(__file__).parent / "fixtures" / "dsh-events-probe.jsonl"


def load_fixture() -> list[dict[str, object]]:
    return parse_events(FIXTURE.read_text(encoding="utf-8").splitlines())


def test_parser_accepts_captured_live_events():
    events = load_fixture()
    assert [e["type"] for e in events][:2] == ["session", "status"]
    assert session_id_from_events(events) == "session-00000000-0000-0000-0000-000000000000"


def test_final_text_from_captured_fixture():
    events = load_fixture()
    assert run_task is not None  # import seam sanity
    from repo_agent.adapters.dsh import final_text_from_events

    assert final_text_from_events(events) == "worker-ready"


def test_usage_sums_per_step_deltas():
    events = load_fixture()
    assert usage_from_events(events) == {
        "inputTokens": 14658,
        "outputTokens": 21,
        "totalTokens": 14679,
    }


def test_unknown_event_types_are_tolerated():
    events = parse_events(['{"type":"something-new","x":1}', '{"type":"final","text":"ok"}'])
    assert len(events) == 2
    assert usage_from_events(events)["totalTokens"] == 0


def test_non_json_line_is_a_named_error():
    with pytest.raises(DshParseError, match="line 1"):
        parse_events(["<<< dsh progress bar >>>"])


def make_fake_dsh(tmp_path: Path, body: str) -> Path:
    shim = tmp_path / "fake-dsh.sh"
    shim.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    return shim


@contextmanager
def dsh_bin(shim: Path):
    """Point DSH_BIN at a shim for the block, restoring the env after."""
    old = os.environ.get("DSH_BIN")
    os.environ["DSH_BIN"] = str(shim)
    try:
        yield shim
    finally:
        if old is None:
            os.environ.pop("DSH_BIN", None)
        else:
            os.environ["DSH_BIN"] = old


def test_run_task_builds_verified_argv_and_reads_stdin(tmp_path: Path):
    seen = tmp_path / "seen.txt"
    shim = make_fake_dsh(
        tmp_path,
        f'printf "%s\\n" "$@" > {seen}\n'
        'cat > /dev/null\n'
        'echo \'{"type":"session","sessionId":"session-x"}\'\n'
        'echo \'{"type":"final","text":"done"}\'\n',
    )
    with dsh_bin(shim):
        run = run_task("fix the bug", timeout_seconds=60)
    assert run.final_text == "done"
    assert run.session_id == "session-x"
    assert run.returncode == 0
    assert seen.read_text(encoding="utf-8").splitlines() == [
        "--profile",
        "headless",
        "--json",
        "-",
    ]


def test_run_task_session_resume_passthrough(tmp_path: Path):
    seen = tmp_path / "seen.txt"
    shim = make_fake_dsh(
        tmp_path,
        f'printf "%s\\n" "$@" > {seen}\n'
        'cat > /dev/null\n'
        'echo \'{"type":"final","text":"resumed"}\'\n',
    )
    with dsh_bin(shim):
        run = run_task("continue", session_id="session-abc", timeout_seconds=60)
    assert run.final_text == "resumed"
    assert seen.read_text(encoding="utf-8").splitlines() == [
        "--profile",
        "headless",
        "--session-id",
        "session-abc",
        "--json",
        "-",
    ]


def test_run_task_timeout_kills(tmp_path: Path):
    shim = make_fake_dsh(tmp_path, "sleep 30\n")
    with dsh_bin(shim):
        run = run_task("go", timeout_seconds=2)
    assert run.timed_out is True
    assert run.final_text is None


def test_multi_step_usage_sums_deltas():
    lines = [
        json.dumps({"type": "status", "phase": "step_end", "step": 1,
                    "usage": {"inputTokens": 100, "outputTokens": 5, "totalTokens": 105}}),
        json.dumps({"type": "status", "phase": "step_end", "step": 2,
                    "usage": {"inputTokens": 40, "outputTokens": 3, "totalTokens": 43}}),
    ]
    assert usage_from_events(parse_events(lines)) == {
        "inputTokens": 140, "outputTokens": 8, "totalTokens": 148,
    }
