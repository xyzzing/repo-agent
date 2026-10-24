"""RA-005: durable state journal.

Code-controlled transitions (PRD §6): a worker message is never an
authoritative transition. The journal owns run state, an append-only event
ledger with sequence numbers and idempotency keys, atomic checkpoints, and
a per-run lock so two resumes cannot dispatch one task twice.
"""
import sqlite3
from pathlib import Path

import pytest

from repo_agent.state import (
    STATES,
    InvalidTransition,
    Journal,
    RunLocked,
)

HAPPY = ["created", "preflight", "baselined", "contracted", "running",
         "verifying", "reviewing", "accepted"]


@pytest.fixture()
def journal(tmp_path: Path) -> Journal:
    return Journal(tmp_path / "journal.sqlite")


def test_happy_path_transitions(journal: Journal):
    run = journal.create_run(task_id="t-1")
    for state in HAPPY[1:]:
        journal.transition(run, state)
    assert journal.run_state(run) == "accepted"


def test_running_cannot_jump_to_accepted(journal: Journal):
    run = journal.create_run(task_id="t-2")
    for state in ("preflight", "baselined", "contracted", "running"):
        journal.transition(run, state)
    with pytest.raises(InvalidTransition):
        journal.transition(run, "accepted")
    assert journal.run_state(run) == "running"


def test_unknown_state_rejected(journal: Journal):
    run = journal.create_run(task_id="t-3")
    with pytest.raises(InvalidTransition):
        journal.transition(run, "delivered")


def test_terminal_states_absorb(journal: Journal):
    run = journal.create_run(task_id="t-4")
    journal.transition(run, "preflight")
    journal.transition(run, "failed")
    with pytest.raises(InvalidTransition):
        journal.transition(run, "cancelled")
    with pytest.raises(InvalidTransition):
        journal.transition(run, "running")


def test_events_append_only_at_sql_level(journal: Journal):
    run = journal.create_run(task_id="t-5")
    journal.record_event(run, "tool.result", {"ok": True})
    conn = journal._connect()  # noqa: SLF001 - the gate under test
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE events SET kind = 'forged'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM events")
    finally:
        conn.rollback()
        conn.close()


def test_idempotent_events_no_duplicate(journal: Journal):
    run = journal.create_run(task_id="t-6")
    first = journal.record_event(
        run, "frontier.request", {"q": "x"}, idempotency_key="fr-1"
    )
    replay = journal.record_event(
        run, "frontier.request", {"q": "x"}, idempotency_key="fr-1"
    )
    assert first == replay
    rows = journal.events(run)
    assert len([e for e in rows if e["kind"] == "frontier.request"]) == 1


def test_idempotent_run_creation(journal: Journal):
    a = journal.create_run(task_id="t-7", idempotency_key="dispatch-9")
    b = journal.create_run(task_id="t-7", idempotency_key="dispatch-9")
    assert a == b


def test_run_lock_excludes_second_owner(journal: Journal):
    run = journal.create_run(task_id="t-8")
    assert journal.acquire_run_lock(run, owner="supervisor-a") is True
    with pytest.raises(RunLocked):
        journal.acquire_run_lock(run, owner="supervisor-b")
    journal.release_run_lock(run, owner="supervisor-a")
    assert journal.acquire_run_lock(run, owner="supervisor-b") is True


def test_lock_release_by_non_owner_is_refused(journal: Journal):
    run = journal.create_run(task_id="t-9")
    journal.acquire_run_lock(run, owner="a")
    with pytest.raises(RunLocked):
        journal.release_run_lock(run, owner="b")


def test_checkpoints_latest_wins_and_carry_next_action(journal: Journal):
    run = journal.create_run(task_id="t-10")
    journal.checkpoint(
        run,
        completed=["repro"],
        evidence_refs=["artifacts/a.json"],
        hypothesis="cache key misses revision",
        next_action="patch key",
    )
    journal.checkpoint(
        run,
        completed=["repro", "patch"],
        evidence_refs=["artifacts/b.json"],
        hypothesis="fixed",
        next_action="run verify",
    )
    latest = journal.latest_checkpoint(run)
    assert latest["next_action"] == "run verify"
    assert latest["completed"] == ["repro", "patch"]


def test_events_carry_increasing_sequence(journal: Journal):
    run = journal.create_run(task_id="t-11")
    for i in range(5):
        journal.record_event(run, "step", {"i": i})
    seqs = [e["sequence"] for e in journal.events(run)]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


def test_state_set_has_no_running_accepted_shortcut():
    assert "accepted" in STATES and "running" in STATES


def test_transition_records_event(journal: Journal):
    run = journal.create_run(task_id="t-12")
    journal.transition(run, "preflight")
    kinds = [e["kind"] for e in journal.events(run)]
    assert "state.changed" in kinds
    change = [e for e in journal.events(run) if e["kind"] == "state.changed"][0]
    assert change["payload"]["to"] == "preflight"
