"""RA-008: the task-run lifecycle — journal, packet, worker, verifier.

The full vertical: a packet drives a real (fake-binary) worker in a staged
workspace; the protected verifier freezes and grades the patch; the
journal records every transition; no direct running→accepted exists even
here. The worker is injectable so tests substitute a deterministic fake
without touching the real dsh.
"""
import json
import stat
import subprocess
from pathlib import Path

import pytest

from repo_agent import taskrun
from repo_agent.adapters.dsh import DshRun
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


GRADER = """#!/bin/sh
cd "$VERIFIER_ROOT"
python3 -c "import calc; assert calc.add(2,2)==4"
"""


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


def test_happy_path_lands_accepted(
    tmp_path: Path, repo: Path, packet_file: Path, grader: Path
):
    journal = Journal(tmp_path / "j.sqlite")
    handoff = taskrun.run_packet(
        packet_file,
        repo=repo,
        work_root=tmp_path / "work",
        journal=journal,
        worker=good_worker,
        graders=[grader],
    )
    assert handoff["verdict"] == "PASS"
    assert handoff["patch_digest"]
    assert handoff["usage"]["totalTokens"] == 12
    assert handoff["changed_paths"] == ["calc.py"]
    assert journal.run_state(handoff["run_id"]) == "accepted"
    assert handoff["acceptance"] == ["calc.add(2, 2) returns 4"]


def test_worker_that_does_nothing_fails_honestly(
    tmp_path: Path, repo: Path, packet_file: Path, grader: Path
):
    journal = Journal(tmp_path / "j.sqlite")
    handoff = taskrun.run_packet(
        packet_file,
        repo=repo,
        work_root=tmp_path / "work",
        journal=journal,
        worker=idle_worker,
        graders=[grader],
    )
    assert handoff["verdict"] == "FAIL"
    assert journal.run_state(handoff["run_id"]) != "accepted"


def test_base_commit_mismatch_is_blocked(
    tmp_path: Path, repo: Path, packet_file: Path
):
    path = tmp_path / "wrong.yaml"
    path.write_text(
        PACKET.replace("BASE", "0123456789abcdef0123456789abcdef01234567"),
        encoding="utf-8",
    )
    with pytest.raises(taskrun.TaskBlocked) as exc:
        taskrun.run_packet(
            path, repo=repo, work_root=tmp_path / "w",
            journal=Journal(tmp_path / "j.sqlite"), worker=good_worker, graders=[],
        )
    assert exc.value.reason_code == "base_mismatch"


def test_dirty_repo_is_blocked(tmp_path: Path, repo: Path, packet_file: Path):
    (repo / "calc.py").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(taskrun.TaskBlocked) as exc:
        taskrun.run_packet(
            packet_file, repo=repo, work_root=tmp_path / "w",
            journal=Journal(tmp_path / "j.sqlite"), worker=good_worker, graders=[],
        )
    assert exc.value.reason_code == "dirty_repo"


def test_worker_prompt_carries_packet_contract(
    tmp_path: Path, repo: Path, packet_file: Path
):
    seen: list[str] = []

    def spy_worker(prompt: str, workspace: Path) -> DshRun:
        seen.append(prompt)
        return good_worker(prompt, workspace)

    taskrun.run_packet(
        packet_file, repo=repo, work_root=tmp_path / "work",
        journal=Journal(tmp_path / "j.sqlite"), worker=spy_worker, graders=[],
    )
    assert "Make calc.add add instead of subtract" in seen[0]
    assert "expected write scope" in seen[0].lower()


def test_taskrun_never_writes_inside_the_repo(
    tmp_path: Path, repo: Path, packet_file: Path
):
    """The journal/work areas are caller-supplied; runs must leave the
    repo tree untouched (regression: the CLI used to journal inside the
    target and trip its own dirty_repo guard)."""
    before = sorted(
        str(x.relative_to(repo)) for x in repo.rglob("*") if ".git" not in x.parts
    )
    wrong = tmp_path / "wrong.yaml"
    wrong.write_text(
        PACKET.replace("BASE", "0123456789abcdef0123456789abcdef01234567"),
        encoding="utf-8",
    )
    with pytest.raises(taskrun.TaskBlocked):
        taskrun.run_packet(
            wrong,
            repo=repo,
            work_root=tmp_path / "work",
            journal=Journal(tmp_path / "j.sqlite"),
            worker=good_worker,
            graders=[],
        )
    after = sorted(
        str(x.relative_to(repo)) for x in repo.rglob("*") if ".git" not in x.parts
    )
    assert after == before


def test_retry_loop_recovers_after_one_failure(
    tmp_path: Path, repo: Path, packet_file: Path, grader: Path
):
    """A worker that fails once then fixes lands accepted on attempt 2,
    with the failure evidence carried into the retry prompt."""
    calls: list[str] = []

    def flaky_worker(prompt: str, workspace: Path) -> DshRun:
        calls.append(prompt)
        if len(calls) == 1:
            return idle_worker(prompt, workspace)
        return good_worker(prompt, workspace)

    handoff = taskrun.run_packet(
        packet_file,
        repo=repo,
        work_root=tmp_path / "work",
        journal=Journal(tmp_path / "j.sqlite"),
        worker=flaky_worker,
        graders=[grader],
    )
    assert handoff["verdict"] == "PASS"
    assert handoff["attempts"] == 2
    assert "did not pass verification" in calls[1]


def test_retry_budget_exhausts_honestly(
    tmp_path: Path, repo: Path, packet_file: Path, grader: Path
):
    seen: list[str] = []

    def always_idle(prompt: str, workspace: Path) -> DshRun:
        seen.append(prompt)
        return idle_worker(prompt, workspace)

    journal = Journal(tmp_path / "j.sqlite")
    handoff = taskrun.run_packet(
        packet_file,
        repo=repo,
        work_root=tmp_path / "work",
        journal=journal,
        worker=always_idle,
        graders=[grader],
    )
    assert handoff["verdict"] == "FAIL"
    assert handoff["attempts"] == 2  # packet budget max_attempts: 2
    assert len(seen) == 2
    assert journal.run_state(handoff["run_id"]) == "needs_evidence"


# --- issue #2: resume, cancel, evidence export ---


def test_runs_record_packet_and_repo_context(
    tmp_path: Path, repo: Path, packet_file: Path
):
    journal = Journal(tmp_path / "j.sqlite")
    taskrun.run_packet(
        packet_file, repo=repo, work_root=tmp_path / "work",
        journal=journal, worker=idle_worker, graders=[],
    )
    ctx = journal.run_context(journal.runs()[0]["run_id"])
    assert ctx["packet_path"] == str(packet_file)
    assert ctx["repo_path"] == str(repo)


def test_cancel_refuses_terminal_run(tmp_path: Path, repo: Path, packet_file: Path):
    journal = Journal(tmp_path / "j.sqlite")
    handoff = taskrun.run_packet(
        packet_file, repo=repo, work_root=tmp_path / "work",
        journal=journal, worker=good_worker, graders=[],
    )
    assert journal.run_state(handoff["run_id"]) == "accepted"
    with pytest.raises(taskrun.TaskBlocked) as exc:
        taskrun.cancel_run(journal, handoff["run_id"])
    assert exc.value.reason_code == "not_cancellable"


def test_cancel_parks_a_needs_evidence_run(
    tmp_path: Path, repo: Path, packet_file: Path
):
    journal = Journal(tmp_path / "j.sqlite")
    handoff = taskrun.run_packet(
        packet_file, repo=repo, work_root=tmp_path / "work",
        journal=journal, worker=idle_worker, graders=[],
    )
    assert journal.run_state(handoff["run_id"]) == "needs_evidence"
    taskrun.cancel_run(journal, handoff["run_id"])
    assert journal.run_state(handoff["run_id"]) == "cancelled"


def test_resume_from_blocked_after_preflight_fix(
    tmp_path: Path, repo: Path, packet_file: Path
):
    """Blocked by a dirty repo; clean it; resume completes the task."""
    journal = Journal(tmp_path / "j.sqlite")
    (repo / "calc.py").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(taskrun.TaskBlocked):
        taskrun.run_packet(
            packet_file, repo=repo, work_root=tmp_path / "work",
            journal=journal, worker=good_worker, graders=[],
        )
    run_id = journal.runs()[0]["run_id"]
    assert journal.run_state(run_id) == "blocked"
    (repo / "calc.py").write_text(BASE_CALC, encoding="utf-8")
    handoff = taskrun.run_packet(
        packet_file, repo=repo, work_root=tmp_path / "work",
        journal=journal, worker=good_worker, graders=[],
        resume=True,
    )
    assert handoff["run_id"] == run_id, "resume reuses the same run"
    assert handoff["verdict"] == "PASS"
    assert journal.run_state(run_id) == "accepted"


def test_resume_refused_without_flag_on_existing_run(
    tmp_path: Path, repo: Path, packet_file: Path
):
    journal = Journal(tmp_path / "j.sqlite")
    (repo / "calc.py").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(taskrun.TaskBlocked):
        taskrun.run_packet(
            packet_file, repo=repo, work_root=tmp_path / "work",
            journal=journal, worker=good_worker, graders=[],
        )
    (repo / "calc.py").write_text(BASE_CALC, encoding="utf-8")
    with pytest.raises(taskrun.TaskBlocked) as exc:
        taskrun.run_packet(
            packet_file, repo=repo, work_root=tmp_path / "work",
            journal=journal, worker=good_worker, graders=[],
        )
    assert exc.value.reason_code == "run_not_resumable"


def test_resume_refused_on_terminal_run(
    tmp_path: Path, repo: Path, packet_file: Path
):
    journal = Journal(tmp_path / "j.sqlite")
    taskrun.run_packet(
        packet_file, repo=repo, work_root=tmp_path / "work",
        journal=journal, worker=good_worker, graders=[],
    )
    with pytest.raises(taskrun.TaskBlocked) as exc:
        taskrun.run_packet(
            packet_file, repo=repo, work_root=tmp_path / "work",
            journal=journal, worker=good_worker, graders=[],
            resume=True,
        )
    assert exc.value.reason_code == "not_resumable"


def test_evidence_export_written_per_run(
    tmp_path: Path, repo: Path, packet_file: Path
):
    evidence = tmp_path / "evidence"
    handoff = taskrun.run_packet(
        packet_file, repo=repo, work_root=tmp_path / "work",
        journal=Journal(tmp_path / "j.sqlite"), worker=good_worker,
        graders=[], evidence_dir=evidence,
    )
    run_dir = evidence / handoff["run_id"]
    handoff_file = json.loads((run_dir / "handoff.json").read_text(encoding="utf-8"))
    assert handoff_file["verdict"] == "PASS"
    events = [json.loads(line) for line in
              (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    kinds = [e["kind"] for e in events]
    assert "run.created" in kinds and "state.changed" in kinds
