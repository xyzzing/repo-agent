# RA-011 — CI checks and packaging

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-011 | Local / 003,004,010 | CI checks and packaging | Fresh
> install outside source checkout includes schemas/templates; drift
> check and required tests run

## Design

- `scripts/packaging-smoke.sh`: build a wheel from the checkout
  (`pip wheel --no-deps`), install it into a fresh venv outside the
  source tree, and run the installed CLI from a scratch directory:
  `--version`, `inspect` on a fixture repo, `render --check` (drift
  check exits non-zero on an unrendered fixture — proving the drift
  path works from the wheel), `render --write` then `--check` exits 0,
  `task validate` on a fixture packet, and `doctor` without `--live`.
  All schemas and templates live in code modules, so the wheel needs
  no package data beyond the two packages pyproject already lists;
  the smoke proves it rather than assumes it.
- `.github/workflows/ci.yml`: one workflow, three jobs —
  `gates` (make gates + mypy --ignore-missing-imports),
  `proven-red` (scripts/proven-red.sh against the PR base), and
  `packaging` (the smoke script, python 3.11 and 3.14). Push and PR
  triggers.
- `tests/test_ci.py`: the structural gate — the workflow exists and
  names every enforced gate (pytest, ruff, ratchet, proven-red, mypy,
  packaging smoke), and the smoke script exists and is executable.
  This is the red that proves the change is testable.
- README's verification section gains the smoke command.

## Remaining (recorded, not hidden)

- The wheel smoke runs behavioral checks, not the unit suite; running
  the unit tests from the installed wheel needs the tests packaged or
  a sdist test run — deferred until RA-013 says which it wants.
- No publish/release workflow: releases remain operator-run (P8).
