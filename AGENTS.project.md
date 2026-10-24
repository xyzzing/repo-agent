# Project contracts — repo-agent

Load order: `AGENTS.md` (portable core), then this file. The product
specification is `docs/prd-v1.3.md`; the pinned environment record is
`discovery.md`. Task IDs (RA-nnn) refer to PRD §13.

## Architecture contracts

- C-A Execution boundary: containment code owns filesystem/process/network
  containment and states its level honestly ("container" vs "isolation by
  construction"). A worktree or fresh directory is never called a sandbox.
  Gate: canary-write, egress-deny, and forged-result tests must pass at the
  shipped level.
- C-B DSH adapter: only `repo_agent/adapters/dsh.py` may invoke `dsh`, and
  only through interfaces recorded in `discovery.md`. Unknown output formats
  fail explicitly; parsers are tested against captured fixtures, never
  invented shapes. Gate: parser fixture tests + `doctor` probe report.
- C-E Verifier independence: worker stdout, worker-written files, and
  worker-created JSON can never be acceptance authority. Results bind to
  the frozen patch digest; later mutation invalidates them. Gate:
  forged-result and patch-mutation tests.
- C-S SQLite: `sqlite3.connect` only inside `repo_agent/state.py`. Gate:
  grep gate in `tests/test_gates.py`.
- C-N HTTP: stdlib `urllib` inside `repo_agent/adapters/http.py` only; no
  `requests`/`httpx`, no `shell=True`/`os.system`/`eval(`/`exec(`. Gate:
  grep gate.
- C-R Determinism: config parsing is inert (nothing executes during
  validate/inspect/render); rendering is byte-stable for identical inputs
  and carries no timestamps. Gate: double-render identity test.

## Verification commands

- Per commit: `make gates` = `env -u LD_LIBRARY_PATH python3 -m pytest -q`
  + `ruff check .` + `python3 scripts/ratchet.sh`.
- Before each push-equivalent checkpoint (end of an RA milestone):
  `scripts/proven-red.sh <base> HEAD` — every changed test file must be red
  against the pre-change code; the output says whether the red was an
  assertion or a missing symbol (P2, adapted from minder).
- mypy on changed files before a checkpoint: `mypy repo_agent <changed>`.

## Ratchet (C2/C7)

Baseline in `.ratchet-baseline`, measured by `scripts/ratchet.sh`. It
prints the numbers it measured (M2). `files_over_400 0`,
`bare_except_pass 0`, `runtime_deps 1` (PyYAML only),
`mocked_internal_modules 0`, `shell_true 0`. Lowering is allowed via
`--update`; raising requires a reason in the commit message.

## Issues (P1)

`issues/RA-*.md` is the ledger; one file per RA before its first commit,
quoting the PRD acceptance lines. Commits reference the RA ID. No remote
and no GitHub issues during the overnight run.

## Vocabulary

Verdicts are `PASS / FAIL / INSUFFICIENT_SAMPLE / NON_COMPARABLE`, never a
percentage alone. Containment levels: `container` or
`isolation_by_construction` — nothing else.
