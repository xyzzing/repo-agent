# RA-005 — Durable state/event journal

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-005 | Frontier design, local implementation / 001 | Durable
> state/event journal | Crash/resume, locking, duplicate events and
> invalid transitions tested

## Contract delivered

- repo_agent/state.py: TRANSITIONS table (no running→accepted; failed/
  cancelled/accepted absorbing), BEGIN IMMEDIATE write transactions,
  append-only events (SQL triggers), idempotency keys on runs and events,
  atomic checkpoints, per-run owner lock.
- tests/test_state.py: 13 tests including the SQL-level append-only gate,
  duplicate-dispatch idempotency, second-supervisor lock exclusion, and
  non-owner release refusal.
- Lesson recorded: sqlite3 `with conn` commits but never closes — leaked
  write locks stalled the suite 30s; every connection now closes
  explicitly.

Status: done.
