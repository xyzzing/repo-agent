"""RA-018: the LLM-assisted refine pass over deterministic candidates.

The refiner is injectable so tests substitute a fake; the dsh-backed
refiner is bounded (limit, idle) and simply absent when no model is
configured. A refined claim lands as a NEW revision; the model_specific
heuristic flips applicability when the refined claim names prompt- or
model-bound behavior.
"""
from repo_agent.extraction_llm import refine_candidates
from repo_agent.memory import MemoryStore
from repo_agent.state import Journal


def seed_candidate(tmp_path, claim, kind="strategy"):
    journal = Journal(tmp_path / "j.sqlite")
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    run = journal.create_run(task_id="t")
    eid = journal.record_event(run, "verifier.verdict", {"verdict": "PASS"})
    mem = store.record(
        kind=kind, claim=claim, scope={"source_run": run},
        provenance={"source_event_ids": [eid], "evidence_digest": "d" * 8},
    )
    return store, mem


def test_refine_creates_new_revision_with_sharper_claim(tmp_path):
    store, mem = seed_candidate(tmp_path, "task succeeded; approach used")
    calls = []

    def fake_refiner(claim, kind, context):
        calls.append(claim)
        return "Edit only calc.py; verify with the pinned assert before handing off"

    result = refine_candidates(store, fake_refiner, limit=5)
    assert result["refined"] == 1
    latest = store.get(mem["memory_id"])
    assert "pinned assert" in latest["claim"]
    assert latest["revision"] == mem["revision"] + 1
    assert calls == ["task succeeded; approach used"]


def test_refiner_decline_leaves_record_untouched(tmp_path):
    store, mem = seed_candidate(tmp_path, "already sharp enough")
    result = refine_candidates(store, lambda *a: None, limit=5)
    assert result["refined"] == 0
    assert store.get(mem["memory_id"])["claim"] == "already sharp enough"


def test_model_bound_refined_claim_becomes_model_specific(tmp_path):
    store, mem = seed_candidate(tmp_path, "task succeeded")
    refine_candidates(
        store,
        lambda *a: "Re-issue the thinking block; this model needs the "
        "reasoning prompt repeated per turn",
        limit=5,
    )
    latest = store.get(mem["memory_id"])
    assert latest["applicability"]["model_specific"] is True


def test_limit_bounds_the_pass(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    for i in range(4):
        run = journal.create_run(task_id=f"t{i}")
        eid = journal.record_event(run, "verifier.verdict", {"verdict": "PASS"})
        store.record(
            kind="fact", claim=f"fact {i}", scope={"source_run": run},
            provenance={"source_event_ids": [eid], "evidence_digest": "d" * 8},
        )
    result = refine_candidates(
        store, lambda claim, kind, ctx: f"refined {claim}", limit=2
    )
    assert result["refined"] == 2
