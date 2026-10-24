"""RA-014: paired evaluation of a lesson proposal.

Two arms, identical packet and repo: baseline (no memory injection)
versus candidate (the proposal's records injected). Outcomes use the
PRD §11 vocabulary; n=1 is always flagged insufficient for promotion
claims.
"""
import subprocess
from pathlib import Path

import pytest

from repo_agent.adapters.dsh import DshRun
from repo_agent.lesson_eval import evaluate_proposal
from repo_agent.memory import MemoryStore
from repo_agent.state import Journal


def make_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True,
                   capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "b"],
        cwd=repo, check=True, capture_output=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
        check=True,
    ).stdout.strip()
    packet = tmp_path / "task.yaml"
    packet.write_text(
        "task_schema_version: 1\n"
        "task_id: pair-fixture\n"
        f"base_commit: '{head}'\n"
        "goal: 'subtract historically fails; make calc.add add'\n"
        "read_first: [calc.py]\n"
        "expected_write_scope: [calc.py]\n"
        "acceptance:\n  - 'calc.add(2, 2) returns 4'\n"
        "invariants: []\nnon_goals: []\n"
        "verification_commands:\n"
        "  - [python3, -c, \"import calc; assert calc.add(2,2)==4\"]\n"
        "budget: {max_attempts: 1, timeout_seconds: 60}\n"
        "required_skills: []\nescalate_when: []\n",
        encoding="utf-8",
    )
    grader = tmp_path / "grader.sh"
    grader.write_text(
        '#!/bin/sh\nset -e\ncd "$VERIFIER_ROOT"\n'
        'python3 -c "import calc; assert calc.add(2,2)==4"\n',
        encoding="utf-8",
    )
    grader.chmod(0o755)
    return repo, packet, grader


def dsh_run(text):
    return DshRun(
        final_text=text, session_id="s", events=[],
        usage={"inputTokens": 10, "outputTokens": 2, "totalTokens": 12},
        returncode=0,
    )


@pytest.fixture()
def proposal_fixture(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    run = journal.create_run(task_id="seed")
    eid = journal.record_event(run, "verifier.verdict", {"verdict": "PASS"})
    mem = store.record(
        kind="strategy",
        claim="subtract historically fails: add was fixed by editing calc.py only",
        scope={"repository_id": str(tmp_path / "repo")},
        provenance={"source_event_ids": [eid], "evidence_digest": "d" * 8},
    )
    store.promote(mem["memory_id"], "evidence_checked")
    store.attach_verification(
        mem["memory_id"],
        {"state": "locally_verified", "tested_commit": "0" * 40,
         "command_argv": ["pytest", "-q"], "outcome_ref": "artifacts/x.json"},
    )
    store.promote(mem["memory_id"], "locally_verified")
    proposal = {
        "proposal_id": "prop-1",
        "run_id": run,
        "records": [store.get(mem["memory_id"])],
    }
    return journal, store, proposal


def worker_that(action: str):
    def _worker(prompt, workspace):
        if action == "fix":
            (workspace / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        return dsh_run(action)

    return _worker


def test_improvement_candidate_when_only_treated_passes(tmp_path, proposal_fixture):
    journal, store, proposal = proposal_fixture
    repo, packet, grader = make_repo(tmp_path)
    actions = iter(["idle", "fix"])

    def alternating(prompt, workspace):
        return worker_that(next(actions))(prompt, workspace)

    report = evaluate_proposal(
        proposal, packet_path=packet, repo=repo,
        work_root=tmp_path / "w", journal=journal, store=store,
        grader=grader, worker=alternating,
    )
    assert report["outcome"] == "IMPROVEMENT_CANDIDATE"
    assert report["sufficient"] is False, "n=1 is never sufficient"
    assert report["arms"]["baseline"]["verdict"] == "FAIL"
    assert report["arms"]["candidate"]["verdict"] == "PASS"


def test_no_material_change_when_both_pass(tmp_path, proposal_fixture):
    journal, store, proposal = proposal_fixture
    repo, packet, grader = make_repo(tmp_path)

    report = evaluate_proposal(
        proposal, packet_path=packet, repo=repo,
        work_root=tmp_path / "w", journal=journal, store=store,
        grader=grader, worker=lambda p, w: worker_that("fix")(p, w),
    )
    assert report["outcome"] == "NO_MATERIAL_CHANGE"
    assert report["sufficient"] is False


def test_candidate_rejected_when_treated_fails(tmp_path, proposal_fixture):
    journal, store, proposal = proposal_fixture
    repo, packet, grader = make_repo(tmp_path)

    report = evaluate_proposal(
        proposal, packet_path=packet, repo=repo,
        work_root=tmp_path / "w", journal=journal, store=store,
        grader=grader, worker=lambda p, w: worker_that("idle")(p, w),
    )
    assert report["outcome"] == "CANDIDATE_REJECTED"
