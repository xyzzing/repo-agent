"""RA-016: canonical memory store — schema, evidence gates, lifecycle.

Per PRD §12A: records carry kind, claim, scope, applicability,
provenance (source run + event ids + evidence digest), verification, and
lifecycle links. Transitions are code-controlled
(candidate → evidence_checked → locally_verified → reusable) with
parallel flags (stale/contradicted/superseded/retired). Invented
citations are rejected: every source_event_id must exist in the journal
the store is bound to.
"""
import sqlite3

import pytest

from repo_agent.memory import (
    KINDS,
    MemoryError,
    MemoryStore,
)
from repo_agent.state import Journal


@pytest.fixture()
def journal(tmp_path):
    return Journal(tmp_path / "j.sqlite")


@pytest.fixture()
def store(tmp_path, journal):
    return MemoryStore(tmp_path / "memory.sqlite", journal=journal)


def event_id(journal, run_task="t"):
    run = journal.create_run(task_id=run_task)
    return journal.record_event(run, "verifier.verdict", {"verdict": "PASS"})


def test_record_rejects_unknown_kind(store):
    with pytest.raises(MemoryError, match="unknown_kind"):
        store.record(kind="wisdom", claim="x", scope={}, provenance={})


def test_record_rejects_empty_claim(store):
    with pytest.raises(MemoryError, match="empty_claim"):
        store.record(kind="fact", claim="  ", scope={}, provenance={})


def test_invented_citation_rejected(store, journal):
    with pytest.raises(MemoryError, match="unknown_event"):
        store.record(
            kind="fact",
            claim="the cache key misses the revision",
            scope={"repository_id": "r", "component": "cache"},
            provenance={"source_event_ids": ["event-does-not-exist"]},
        )


def test_real_citation_accepted_and_roundtrips(store, journal):
    eid = event_id(journal)
    mem = store.record(
        kind="fact",
        claim="the cache key misses the revision",
        scope={"repository_id": "r", "component": "cache"},
        provenance={"source_event_ids": [eid], "evidence_digest": "abc"},
    )
    assert mem["status"] == "candidate"
    got = store.get(mem["memory_id"])
    assert got["provenance"]["source_event_ids"] == [eid]


def test_lifecycle_happy_path_for_procedure(store, journal):
    eid = event_id(journal)
    mem = store.record(
        kind="verified_procedure",
        claim="invalidate the cache when configuration changes",
        scope={"repository_id": "r"},
        provenance={"source_event_ids": [eid], "evidence_digest": "abc"},
    )
    store.promote(mem["memory_id"], "evidence_checked")
    with pytest.raises(MemoryError, match="verification_required"):
        store.promote(mem["memory_id"], "locally_verified")
    store.attach_verification(
        mem["memory_id"],
        {"state": "locally_verified", "tested_commit": "0" * 40,
         "command_argv": ["pytest", "-q"], "outcome_ref": "artifacts/r.json"},
    )
    store.promote(mem["memory_id"], "locally_verified")
    store.promote(mem["memory_id"], "reusable")
    assert store.get(mem["memory_id"])["status"] == "reusable"


def test_illegal_jump_refused(store):
    mem = store.record(kind="fact", claim="x", scope={}, provenance={})
    with pytest.raises(MemoryError, match="illegal_transition"):
        store.promote(mem["memory_id"], "reusable")


def test_flags_are_parallel_not_status(store, journal):
    eid = event_id(journal)
    mem = store.record(
        kind="fact", claim="x", scope={}, provenance={"source_event_ids": [eid]}
    )
    store.promote(mem["memory_id"], "evidence_checked")
    store.mark_stale(mem["memory_id"], "relevant source changed")
    got = store.get(mem["memory_id"])
    assert got["status"] == "evidence_checked"
    assert got["flags"] == ["stale"]
    assert got["flag_reason"] == "relevant source changed"
    assert [m["memory_id"] for m in store.list_memories()] == [], "stale excluded by default"
    assert len(store.list_memories(include_flagged=True)) == 1


def test_supersede_links_and_bumps_revision(store, journal):
    eid = event_id(journal)
    old = store.record(
        kind="fact", claim="use pattern A", scope={"repository_id": "r"},
        provenance={"source_event_ids": [eid]},
    )
    new = store.supersede(
        old["memory_id"],
        kind="fact", claim="use pattern B", scope={"repository_id": "r"},
        provenance={"source_event_ids": [eid]},
    )
    assert new["revision"] == old["revision"] + 1
    assert new["supersedes"] == [old["memory_id"]]
    assert "superseded" in store.get(old["memory_id"])["flags"]


def test_rows_are_append_only_at_sql_level(store):
    store.record(kind="fact", claim="x", scope={}, provenance={})
    conn = store._connect()  # noqa: SLF001 - the gate under test
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE memories SET claim = 'forged'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM memories")
    finally:
        conn.rollback()
        conn.close()


def test_query_matches_claim_keyword(store, journal):
    e1 = event_id(journal)
    store.record(
        kind="fact", claim="the retry budget refunds on success",
        scope={}, provenance={"source_event_ids": [e1]},
    )
    store.record(kind="fact", claim="cache keys include the revision",
                 scope={}, provenance={"source_event_ids": [e1]})
    hits = store.query("budget")
    assert len(hits) == 1
    assert "refund" in hits[0]["claim"]


def test_kinds_vocabulary_is_closed():
    assert set(KINDS) == {"fact", "verified_procedure", "failure_pattern", "strategy"}
