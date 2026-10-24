# RA-004 — Read-only inspector and bootstrap proposals

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-004 | Local / 002 | Read-only inspector and bootstrap proposals |
> Sources cited; conflicts exposed; mature migration preserves
> instructions and edits

## Execution

- Acceptance tests written first (tests/test_inspect.py, 9 tests) by the
  supervisor; implementation DISPATCHED to the local worker (Qwen
  3.8-Flash-Next via `dsh --profile headless --json`, through the minder
  proxy) with a §10-shaped packet.
- Worker produced repo_agent/inspect.py (223 lines) and additionally wired
  the `inspect` CLI handler in repo_agent/cli.py — one file beyond the
  packet's write scope, in the direction the CLI needed. Accepted with the
  violation recorded; it is pilot data, not a passing grade.
- Supervisor verified: full gates, mypy, ruff run locally; no worker claim
  trusted without re-running.

## Bootstrap proposals

Deferred to the next RA-004 commit: `bootstrap --mode new|mature`
proposal/apply flow is a separate logical change (P5) and lands after the
inspector.

Status: inspector + packets + task-run lifecycle done; bootstrap proposals deferred as RA-004b; eval/lesson remain honest stubs.
