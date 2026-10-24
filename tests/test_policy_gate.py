"""RA-009: the policy gate inside the task lifecycle.

Spend happens at two points — the first dispatch and each needs_evidence
retry. The policy authority (PRD §9) is consulted at both; refusals and
unavailable required decisions block further spend, and every verdict is
emitted as telemetry bound to a trusted artifact. Fixtures mirror
test_taskrun.py; the policy objects are scripted, not minder's own.
"""
import hashlib
import json
import stat
import subprocess
import uuid
from pathlib import Path

import pytest

from repo_agent import taskrun
from repo_agent.adapters.dsh import DshRun
from repo_agent.adapters.minder import MinderEvents
from repo_agent.adapters.minder_decisions import Decision, RequiredMinderPolicy
from repo_agent.state import Journal

BASE_CALC = "def add(a, b):\n    return a - b\n"
FIX_CALC = "def add(a, b):\n    return a + b\n"
PACKET = """
task_schema_version: 1
task_id: fix-add
base_commit: 'BASE'
goal: 'Make calc.add add instead of subtract'
read_first: [calc.py]
expected_write_scope: [calc.py]
acceptance:
  - 'calc.add(2, 2) returns 4'
invariants: []
non_goals: []
verification_commands:
  - [python3, -c, "import calc; assert calc.add(2,2)==4"]
budget:
  max_attempts: 2
  timeout_seconds: 600
required_skills: []
escalate_when: []
"""
GRADER = """#!/bin/sh
cd "$VERIFIER_ROOT"
python3 -c "import calc; assert calc.add(2,2)==4"
"""
DEAD_SINK = "http://127.0.0.1:1"  # nothing listens; telemetry degrades


def git(repo: Path, *argv: str) -> str:
    out = subprocess.run(
        ["git", *argv], cwd=repo, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "calc.py").write_text(BASE_CALC, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
    return root


@pytest.fixture()
def packet_file(tmp_path: Path, repo: Path) -> Path:
    head = git(repo, "rev-parse", "HEAD")
    path = tmp_path / "task.yaml"
    path.write_text(PACKET.replace("BASE", head), encoding="utf-8")
    return path


@pytest.fixture()
def grader(tmp_path: Path) -> Path:
    path = tmp_path / "grader.sh"
    path.write_text(GRADER, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def dsh_run(text: str) -> DshRun:
    return DshRun(
        final_text=text, session_id="session-fake", events=[],
        usage={"inputTokens": 10, "outputTokens": 2, "totalTokens": 12},
        returncode=0,
    )


def good_worker(prompt: str, workspace: Path) -> DshRun:
    (workspace / "calc.py").write_text(FIX_CALC, encoding="utf-8")
    return dsh_run("fixed")


def idle_worker(prompt: str, workspace: Path) -> DshRun:
    return dsh_run("did nothing")


class FakeLadder:
    """Scripted policy: pops one action per consultation, then continues."""

    events = None

    def __init__(self, actions: list[str]):
        self.actions = list(actions)
        self.consulted: list[int] = []

    def decide(self, attempt: int, basis_event_ids: list[str], run_id=None):
        self.consulted.append(attempt)
        action = self.actions.pop(0) if self.actions else "continue"
        return Decision(
            decision_id=f"decision-fake-{len(self.consulted)}-{uuid.uuid4().hex[:8]}",
            run_id=run_id or "unbound",
            basis_event_ids=tuple(basis_event_ids),
            action=action,
            reason_code="scripted",
            policy_version="fake-v1",
            remaining_budget=None,
            expires_at=None,
        )


class TelemetryPolicy:
    """Pass-through policy carrying an events emitter."""

    def __init__(self, events: MinderEvents):
        self.events = events

    def decide(self, attempt: int, basis_event_ids: list[str], run_id=None):
        return Decision(
            decision_id=f"decision-t-{attempt}-{uuid.uuid4().hex[:8]}",
            run_id=run_id or "unbound",
            basis_event_ids=tuple(basis_event_ids),
            action="continue",
            reason_code="ok",
            policy_version="telemetry-v1",
            remaining_budget=None,
            expires_at=None,
        )


def test_policy_refusal_blocks_before_any_worker_call(
    tmp_path: Path, repo: Path, packet_file: Path
):
    journal = Journal(tmp_path / "j.sqlite")
    policy = FakeLadder(["pause"])
    with pytest.raises(taskrun.TaskBlocked) as exc:
        taskrun.run_packet(
            packet_file, repo=repo, work_root=tmp_path / "work",
            journal=journal, worker=good_worker, graders=[], policy=policy,
        )
    assert exc.value.reason_code == "policy_pause"
    assert policy.consulted == [0], "consulted once, before any dispatch"
    assert journal.run_state(journal.runs()[0]["run_id"]) == "blocked"


def test_policy_stop_at_retry_fails_run_without_second_dispatch(
    tmp_path: Path, repo: Path, packet_file: Path, grader: Path
):
    journal = Journal(tmp_path / "j.sqlite")
    calls: list[str] = []

    def counting_idle(prompt: str, workspace: Path) -> DshRun:
        calls.append(prompt)
        return idle_worker(prompt, workspace)

    policy = FakeLadder(["continue", "stop"])
    handoff = taskrun.run_packet(
        packet_file, repo=repo, work_root=tmp_path / "work",
        journal=journal, worker=counting_idle, graders=[grader], policy=policy,
    )
    assert len(calls) == 1, "stop at the retry point prevents the second spend"
    assert handoff["verdict"] == "FAIL"
    assert journal.run_state(handoff["run_id"]) == "failed"
    assert handoff["policy"]["decisions"] == [
        {"attempt": 0, "action": "continue"},
        {"attempt": 1, "action": "stop"},
    ]


def test_required_policy_blocks_before_spend(
    tmp_path: Path, repo: Path, packet_file: Path
):
    journal = Journal(tmp_path / "j.sqlite")
    with pytest.raises(taskrun.TaskBlocked) as exc:
        taskrun.run_packet(
            packet_file, repo=repo, work_root=tmp_path / "work",
            journal=journal, worker=good_worker, graders=[],
            policy=RequiredMinderPolicy("no external decision surface"),
        )
    assert exc.value.reason_code == "policy_unavailable"
    assert journal.run_state(journal.runs()[0]["run_id"]) == "blocked"


def test_policy_continue_preserves_default_behavior(
    tmp_path: Path, repo: Path, packet_file: Path, grader: Path
):
    journal = Journal(tmp_path / "j.sqlite")
    policy = FakeLadder([])
    handoff = taskrun.run_packet(
        packet_file, repo=repo, work_root=tmp_path / "work",
        journal=journal, worker=idle_worker, graders=[grader], policy=policy,
    )
    assert handoff["attempts"] == 2
    assert journal.run_state(handoff["run_id"]) == "needs_evidence"
    assert policy.consulted == [0, 1]


def test_policy_telemetry_pass_event_carries_evidence(
    tmp_path: Path, repo: Path, packet_file: Path, grader: Path
):
    evidence = tmp_path / "evidence"
    buffer_dir = tmp_path / "buf"
    events = MinderEvents(
        state_dir=tmp_path / "st", sink_url=DEAD_SINK, token=None,
        buffer_dir=buffer_dir,
    )
    handoff = taskrun.run_packet(
        packet_file, repo=repo, work_root=tmp_path / "work",
        journal=Journal(tmp_path / "j.sqlite"), worker=good_worker,
        graders=[grader], policy=TelemetryPolicy(events), evidence_dir=evidence,
    )
    verdict_file = evidence / handoff["run_id"] / "verdict.json"
    verdict = json.loads(verdict_file.read_text(encoding="utf-8"))
    assert verdict["verdict"] == "PASS"
    lines = [
        json.loads(line)
        for line in (buffer_dir / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert lines[0]["event"] == "repo_agent_verification.passed"
    assert lines[0]["evidence_ref"] == f"{handoff['run_id']}/verdict.json"
    assert lines[0]["evidence_sha256"] == hashlib.sha256(
        verdict_file.read_bytes()
    ).hexdigest()
    assert "failure_signature" not in lines[0]
    assert handoff["policy"]["telemetry"]["telemetry"] == "degraded"


def test_policy_telemetry_failure_carries_signature(
    tmp_path: Path, repo: Path, packet_file: Path, grader: Path
):
    buffer_dir = tmp_path / "buf"
    events = MinderEvents(
        state_dir=tmp_path / "st", sink_url=DEAD_SINK, token=None,
        buffer_dir=buffer_dir,
    )
    taskrun.run_packet(
        packet_file, repo=repo, work_root=tmp_path / "work",
        journal=Journal(tmp_path / "j.sqlite"), worker=idle_worker,
        graders=[grader], policy=TelemetryPolicy(events),
    )
    lines = [
        json.loads(line)
        for line in (buffer_dir / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert lines[0]["event"] == "repo_agent_verification.failed"
    assert lines[0]["failure_signature"] == "check_failed"
