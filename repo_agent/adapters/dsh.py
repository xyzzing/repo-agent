"""DSH adapter (C-B): the only module that may invoke `dsh`.

Implements exactly the RA-000-verified interface of dsh 0.2.1-rc.2:
`dsh --profile headless --json -` (task on stdin, NDJSON run events on
stdout, diagnostics on stderr) and `--session-id <id>` for resume.
Cancellation is process-group termination — headless documents no cancel
command. Usage records on `step_end` events are per-step deltas; totals
are their sum (verified against a live multi-step dispatch, where the
values decrease on cache hits, which a cumulative counter cannot do).

`DSH_BIN` overrides the binary so tests can run a fake dsh; the parser is
pinned to captured fixtures (tests/fixtures/dsh-events-*.jsonl). Unknown
event types are tolerated and recorded — the stream is append-only
telemetry — but a non-JSON line is a DshParseError quoting the line,
because silently dropping bytes would hide protocol drift.
"""
import json
import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROFILE = "headless"
_STDIN_TASK = "-"


class DshParseError(Exception):
    pass


class DshFailed(Exception):
    def __init__(self, message: str, returncode: int, stderr_tail: str):
        super().__init__(message)
        self.returncode = returncode
        self.stderr_tail = stderr_tail


@dataclass
class DshRun:
    final_text: str | None
    session_id: str | None
    events: list[dict[str, object]]
    usage: dict[str, int]
    returncode: int
    stderr_tail: str = ""
    timed_out: bool = False


def parse_events(lines: list[str]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except ValueError as exc:
            raise DshParseError(f"line {lineno} is not JSON: {stripped[:200]!r}") from exc
        if not isinstance(event, dict):
            raise DshParseError(f"line {lineno} is not an event object: {stripped[:200]!r}")
        events.append(event)
    return events


def usage_from_events(events: list[dict[str, object]]) -> dict[str, int]:
    totals = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
    for event in events:
        if event.get("type") != "status" or event.get("phase") != "step_end":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        for key in totals:
            value = usage.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] += int(value)
    return totals


def final_text_from_events(events: list[dict[str, object]]) -> str | None:
    for event in reversed(events):
        if event.get("type") == "final" and isinstance(event.get("text"), str):
            return str(event["text"])
    return None


def session_id_from_events(events: list[dict[str, object]]) -> str | None:
    for event in events:
        if event.get("type") == "session" and isinstance(event.get("sessionId"), str):
            return str(event["sessionId"])
    return None


def _kill_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


def run_task(
    task: str,
    profile: str = DEFAULT_PROFILE,
    session_id: str | None = None,
    timeout_seconds: int = 600,
    cwd: Path | None = None,
) -> DshRun:
    dsh_bin = os.environ.get("DSH_BIN", "dsh")
    argv = [dsh_bin, "--profile", profile]
    if session_id is not None:
        argv += ["--session-id", session_id]
    argv += ["--json", _STDIN_TASK]
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    timed_out = False
    try:
        out, err = proc.communicate(task, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc)
        out, err = proc.communicate()
    stderr_tail = (err or "")[-4000:]
    if timed_out:
        return DshRun(
            final_text=None,
            session_id=None,
            events=[],
            usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
            returncode=proc.returncode if proc.returncode is not None else -9,
            stderr_tail=stderr_tail + "\n[timeout: process group killed]",
            timed_out=True,
        )
    returncode = proc.returncode if proc.returncode is not None else -1
    try:
        events = parse_events(out.splitlines())
    except DshParseError:
        raise DshFailed(
            f"dsh {profile} emitted a non-event line (rc {returncode})",
            returncode,
            stderr_tail,
        ) from None
    return DshRun(
        final_text=final_text_from_events(events),
        session_id=session_id_from_events(events),
        events=events,
        usage=usage_from_events(events),
        returncode=returncode,
        stderr_tail=stderr_tail,
    )
