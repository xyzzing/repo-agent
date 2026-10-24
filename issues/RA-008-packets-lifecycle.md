# RA-008 — Task packets and evidence bundles

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-008 | Local / 007 | Task packets and evidence bundles | Exact
> base/workspace identity; bounded retries; complete handoff; no
> premature accepted state

## Delivered

- `repo_agent/packets.py`: strict packet schema (PRD §10) with
  placeholder rejection (`unresolved_placeholder` for non-hex
  base_commits like `<actual commit>`), duplicate-key refusal, and a
  deterministic worker-prompt renderer carrying goal, scope, acceptance,
  invariants, non-goals, permitted checks, and escalation triggers.
- `repo_agent/taskrun.py`: the full lifecycle — preflight refuses
  `base_mismatch` and `dirty_repo` before the worker spends anything;
  worker dispatches into a staged workspace; the protected verifier
  freezes and grades; the journal records every transition; `accepted`
  is reachable only through `reviewing`.
- CLI: `task validate` (reason-coded), `task run --repo --grader`;
  journal and work areas in `~/.local/state/repo-agent` (outside the
  target — regression-tested after the journal-inside-repo bug).

## Evidence

- Live dogfood: PASS, accepted, ~2 min wall, 96,667 local tokens,
  changed paths exactly in scope. See docs/RUN-NOTES.md.
- tests/test_packets.py (8) + tests/test_taskrun.py (6).

## Remaining (recorded, not hidden)

- Retry loop: `needs_evidence` → bounded re-dispatch (states exist; loop
  not built). One attempt per run tonight.
- Evidence-bundle file export (handoff is JSON on stdout + journal
  events; a per-run artifacts dir is the next increment).
- `task resume` / `task cancel` stubs.

Status: core done.
