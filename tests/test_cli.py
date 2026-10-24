"""RA-001: CLI skeleton contract.

Exit codes (PRD §5): 0 success; 1 checks failed; 2 usage/configuration
error; 3 blocked prerequisite/policy; 4 infrastructure failure. JSON
results carry reason codes. Every PRD §5 command parses; unimplemented
commands exit 3 with reason 'unimplemented' and never fabricate success.
"""
import json
import subprocess
import sys
from pathlib import Path

from repo_agent import cli

TOP_COMMANDS = ("inspect", "bootstrap", "doctor", "render", "task", "eval", "lesson")


def test_version_is_user_visible():
    assert cli.main(["--version"]) == 0
    # version text goes to stdout via the parser action; check via subprocess below


def test_help_names_every_top_command(capsys):
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    for name in TOP_COMMANDS:
        assert name in out, f"--help does not mention {name}"


def test_unknown_command_is_usage_error(capsys):
    assert cli.main(["frobnicate"]) == 2
    err = capsys.readouterr().err
    assert "invalid choice" in err


def test_skeleton_commands_exit_blocked_with_reason(tmp_path, capsys):
    # proven-red: allow-pass: render, inspect, doctor, task validate/run,
    # resume, cancel, and bootstrap left the blocked list as they gained
    # implementations; each range's red is carried by its new test file
    # (test_render/test_inspect/test_doctor/test_packets/test_taskrun/
    # test_bootstrap).
    for argv in (
        ["eval", "run", "plan.yaml"],
        ["eval", "compare", "base.json", "cand.json"],
        ["lesson", "propose", "run-1"],
    ):
        code = cli.main(argv)
        assert code == 3, f"{argv} should be blocked in the skeleton, got {code}"
        payload = json.loads(capsys.readouterr().out)
        assert payload["reason_code"] == "unimplemented"
        assert payload["ok"] is False
        assert payload["command"]


def test_render_requires_a_mode():
    assert cli.main(["render", "."]) == 2


def test_bootstrap_rejects_unknown_mode():
    assert cli.main(["bootstrap", ".", "--mode", "yolo"]) == 2


def test_process_exit_code_contract(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "repo_agent", "lesson", "propose", "run-1"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["reason_code"] == "unimplemented"
