"""RA-017: the event-driven writer — durable cursor, idempotent harvest,
and the strategy-from-success borrow.

The writer consumes journal events behind a cursor and emits CANDIDATES
only: accepted runs yield a verified_procedure candidate plus a strategy
candidate (what approach verified — the ReasoningBank borrow: learn
from successes, not only failures); exhausted runs yield a
failure_pattern candidate. Replaying the cursor creates nothing.
"""

import os

from repo_agent.memory import MemoryStore
from repo_agent.memory_writer import harvest
from repo_agent.retrieval import records_for_profile
from repo_agent.state import Journal


def seed_accepted_run(journal: Journal, task_id: str = "fix-cache") -> str:
    run_id = journal.create_run(
        task_id=task_id, idempotency_key=f"task:{task_id}:abc"
    )
    journal.set_run_context(
        run_id, "task.yaml", "/repo",
        model_profile=os.environ.get("REPO_AGENT_MODEL_PROFILE", "unrecorded"),
    )
    for state in ("preflight", "baselined", "contracted", "running",
                  "verifying", "reviewing", "accepted"):
        journal.transition(run_id, state)
    journal.record_event(
        run_id,
        "verifier.verdict",
        {
            "verdict": "PASS",
            "reason_code": "ok",
            "patch_digest": "12460f81f4b2dc4dd3ce9504c7352db9e"[:16] + "0000",
            "result_digest": "02768b17470052a73792e27d46b8a60c0ce367791" + "00",
        },
    )
    return run_id


def seed_exhausted_run(journal: Journal, task_id: str = "fix-worse") -> str:
    run_id = journal.create_run(
        task_id=task_id, idempotency_key=f"task:{task_id}:def"
    )
    journal.set_run_context(
        run_id, "task.yaml", "/repo",
        model_profile=os.environ.get("REPO_AGENT_MODEL_PROFILE", "unrecorded"),
    )
    for state in ("preflight", "baselined", "contracted", "running",
                  "verifying", "needs_evidence"):
        journal.transition(run_id, state)
    journal.record_event(
        run_id,
        "verifier.verdict",
        {
            "verdict": "FAIL",
            "reason_code": "grader_failed",
            "patch_digest": "ffff0000ffff0000ffff0000ffff0000",
            "result_digest": "11112222333344445555666677778888",
        },
    )
    return run_id


def test_accepted_run_yields_procedure_and_strategy(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    seed_accepted_run(journal)
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)

    result = harvest(store, journal)
    assert result["created"] == 2
    by_kind = {m["kind"] for m in store.list_memories()}
    assert by_kind == {"verified_procedure", "strategy"}

    procedure = [m for m in store.list_memories() if m["kind"] == "verified_procedure"][0]
    assert "fix-cache" in procedure["claim"]
    assert procedure["status"] == "candidate", "the writer never auto-promotes"

    strategy = [m for m in store.list_memories() if m["kind"] == "strategy"][0]
    assert "fix-cache" in strategy["claim"]
    assert strategy["status"] == "candidate"


def test_candidates_cite_their_verdict_event(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    seed_accepted_run(journal)
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    harvest(store, journal)
    verdict_events = [
        e for e in journal.events(journal.runs()[0]["run_id"])
        if e["kind"] == "verifier.verdict"
    ]
    for mem in store.list_memories():
        assert verdict_events[0]["event_id"] in mem["provenance"]["source_event_ids"]
        assert mem["provenance"]["evidence_digest"] == (
            verdict_events[0]["payload"]["result_digest"]
        )


def test_exhausted_run_yields_failure_pattern(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    seed_exhausted_run(journal)
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    harvest(store, journal)
    patterns = [m for m in store.list_memories() if m["kind"] == "failure_pattern"]
    assert len(patterns) == 1
    assert "grader_failed" in patterns[0]["claim"]
    assert "fix-worse" in patterns[0]["claim"]


def test_harvest_is_idempotent_across_instances(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    seed_accepted_run(journal)
    seed_exhausted_run(journal)
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)

    first = harvest(store, journal)
    assert first["created"] == 3
    # a fresh store instance on the same database: the cursor is durable
    store_again = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    second = harvest(store_again, journal)
    assert second["created"] == 0
    assert len(store.list_memories()) == 3


def test_blocked_runs_produce_no_candidates(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    run_id = journal.create_run(task_id="blocked-1")
    journal.transition(run_id, "preflight")
    journal.transition(run_id, "blocked")
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    result = harvest(store, journal)
    assert result["created"] == 0
    assert store.list_memories() == []


# --- producer labeling: one library, per-model shelving (PRD §12A) ---


def test_candidates_carry_producer_and_portable_default(tmp_path):
    import os

    journal = Journal(tmp_path / "j.sqlite")
    os.environ["REPO_AGENT_MODEL_PROFILE"] = "qwen3.8-flash-next@strata-r020"
    try:
        seed_accepted_run(journal)
    finally:
        os.environ.pop("REPO_AGENT_MODEL_PROFILE", None)
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)

    harvest(store, journal)
    for mem in store.list_memories():
        assert mem["provenance"]["producer_profile"] == (
            "qwen3.8-flash-next@strata-r020"
        )
        assert mem["applicability"]["model_specific"] is False, (
            "harvest candidates are portable until qualified otherwise"
        )


def test_unrecorded_producer_when_env_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("REPO_AGENT_MODEL_PROFILE", raising=False)
    journal = Journal(tmp_path / "j.sqlite")
    seed_accepted_run(journal)
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    harvest(store, journal)
    for mem in store.list_memories():
        assert mem["provenance"]["producer_profile"] == "unrecorded"


def test_records_for_profile_shelves_model_specific(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    eid = journal.create_run(task_id="t")
    eid = journal.record_event(eid, "verifier.verdict", {"verdict": "PASS"})
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)

    store.record(
        kind="fact", claim="portable repo fact", scope={},
        provenance={"source_event_ids": [eid], "producer_profile": "qwen@r020"},
        applicability={"model_specific": False},
    )
    store.record(
        kind="fact",
        claim="this model needs the thinking block re-issued",
        scope={},
        provenance={"source_event_ids": [eid], "producer_profile": "qwen@r020"},
        applicability={"model_specific": True},
    )

    deepseek = [m["claim"] for m in records_for_profile(store, "deepseek@v3")]
    qwen = [m["claim"] for m in records_for_profile(store, "qwen@r020")]
    assert any("portable repo fact" in c for c in deepseek), (
        "portable records surface for every profile"
    )
    assert not any("thinking block" in c for c in deepseek), (
        "model-specific records are withheld from other profiles"
    )
    assert any("thinking block" in c for c in qwen), (
        "model-specific records surface for their own profile"
    )


def test_harvest_records_carry_repository_scope(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    seed_accepted_run(journal)
    journal.set_run_context(
        journal.runs()[0]["run_id"], "task.yaml", "/repos/alpha",
        model_profile="qwen@r020",
    )
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    harvest(store, journal)
    for mem in store.list_memories():
        assert mem["scope"]["repository_id"] == "/repos/alpha"
