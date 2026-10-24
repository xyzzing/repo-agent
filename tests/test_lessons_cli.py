"""RA-014: the lesson lane — propose, human-gated promotion, paired
evaluation. A proposal is evidence-linked and CANNOT activate itself:
candidates stay candidates until a human promotes them through the
store's evidence-gated transitions, and the paired evaluation reports
in the PRD §11 vocabulary (n=1 is always flagged insufficient).
"""
import json

import pytest

from repo_agent.memory import MemoryStore
from repo_agent.memory_writer import harvest
from repo_agent.state import Journal


@pytest.fixture()
def settled_run(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    run_id = journal.create_run(
        task_id="fix-cache", idempotency_key="task:fix-cache:abc"
    )
    journal.set_run_context(
        run_id, "task.yaml", "/repos/alpha", model_profile="qwen@r020"
    )
    for state in ("preflight", "baselined", "contracted", "running",
                  "verifying", "reviewing", "accepted"):
        journal.transition(run_id, state)
    journal.record_event(
        run_id, "verifier.verdict",
        {"verdict": "PASS", "reason_code": "ok",
         "patch_digest": "a" * 16 + "0000", "result_digest": "b" * 16 + "0000"},
    )
    return journal, run_id


def seed_candidates(tmp_path, journal):
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    result = harvest(store, journal)
    assert result["created"] >= 1
    return store


def test_propose_writes_evidence_linked_proposal(tmp_path, settled_run):
    journal, run_id = settled_run
    store = seed_candidates(tmp_path, journal)
    from repo_agent.lessons_cli import propose

    proposal = propose(store, journal, run_id, evidence_dir=tmp_path / "ev")
    assert proposal["run_id"] == run_id
    assert proposal["candidates"], "proposal lists candidate records"
    for candidate in proposal["candidates"]:
        assert candidate["status"] == "candidate", "propose never activates"
    path = tmp_path / "ev" / run_id / "proposal.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["proposal_id"] == proposal["proposal_id"]


def test_propose_is_idempotent_per_run(tmp_path, settled_run):
    journal, run_id = settled_run
    store = seed_candidates(tmp_path, journal)
    from repo_agent.lessons_cli import propose

    first = propose(store, journal, run_id, evidence_dir=tmp_path / "ev")
    second = propose(store, journal, run_id, evidence_dir=tmp_path / "ev")
    assert first["proposal_id"] == second["proposal_id"]


def test_memory_promote_requires_yes(tmp_path, settled_run, capsys):
    journal, run_id = settled_run
    store = seed_candidates(tmp_path, journal)
    mem = store.list_memories()[0]
    from repo_agent.lessons_cli import promote_memory

    code = promote_memory(
        store, mem["memory_id"], "evidence_checked",
        verification_json=None, yes=False,
    )
    assert code == 2, "refuses without --yes"
    assert store.get(mem["memory_id"])["status"] == "candidate"


def test_memory_promote_honors_evidence_gates(tmp_path, settled_run):
    journal, run_id = settled_run
    store = seed_candidates(tmp_path, journal)
    mem = store.list_memories()[0]
    from repo_agent.lessons_cli import promote_memory

    assert promote_memory(
        store, mem["memory_id"], "evidence_checked",
        verification_json=None, yes=True,
    ) == 0
    assert store.get(mem["memory_id"])["status"] == "evidence_checked"
