# RA-003 — Deterministic renderer and drift command

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-003 | Local / 002 | Deterministic renderer and drift command | Stable
> bytes; scoped guidance retained; check mode read-only; notes untouched

## Contract

- `render --write` generates AGENTS.md from validated config + project
  notes: byte-stable for identical inputs across repos, no timestamps,
  source digests and policy version recorded.
- `render --check` computes without writing; exit 1 on drift.
- Project notes are inputs and are never modified.
- An existing AGENTS.md without repo-agent ownership markers is never
  overwritten (`unowned_agents_md`, exit 3) — mature-repo migration is
  RA-004's deliberate apply.
- Scoped instruction files are referenced with digests, never flattened
  into AGENTS.md.
- An instruction-loading fixture proves a harness reading the file finds
  the commands, policy version, and notes — presence alone is insufficient.

Status: done — tests/test_render.py (10 tests); proven-red carries the range red.
