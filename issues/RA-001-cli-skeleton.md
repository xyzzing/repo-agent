# RA-001 — Minimal package and CLI skeleton

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-001 | Local / 000 | Minimal package and CLI skeleton | Existing
> conventions reused; help/JSON/error exit contracts work; no speculative
> services

## Contract

- CLI surface per PRD §5: `inspect`, `bootstrap`, `doctor`, `render`,
  `task {validate,run,resume,cancel}`, `eval {run,compare}`,
  `lesson propose`.
- Exit codes per PRD §5: 0 success; 1 checks failed; 2 usage/configuration
  error; 3 blocked prerequisite/policy; 4 infrastructure failure. JSON
  results carry reason codes.
- Skeleton: every command parses and dispatches; commands without an
  implementation yet exit 3 with reason `unimplemented` — they never
  fabricate success.
- No services, daemons, or network calls in the skeleton.

Status: done — tests/test_cli.py pins the contract (7 tests); proven-red
shows the test file red(missing-symbol) against the scaffold.
