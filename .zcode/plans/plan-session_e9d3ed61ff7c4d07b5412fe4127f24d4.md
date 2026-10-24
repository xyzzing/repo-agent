# Next phase: complete G3 — RA-009, RA-010, RA-011 (PRD v1.3 §13)

## Interpretation

You shared `docs/prd-v1.3.md` without an instruction. The repo just shipped v0.1.0 covering **RA-000–RA-008** (config/render/inspect/bootstrap/journal/verifier/DSH adapter/doctor/packets/task lifecycle, 124 tests). Following the PRD's own dependency order and its rule "deliver G1–G3 as the first useful release", the next phase is **G3: RA-009 → RA-010 → RA-011**. If you wanted something else (PRD critique, gap analysis, the memory arc), reject this plan and say so.

## Grounding (from code read)

- `taskrun.py:143-168` — the retry loop is the enforcement point where a Minder decision must be consulted before re-dispatch (spend).
- `verifier.py` — `Verifier._record()` already produces digest-bound verdicts with `result_digest`/`patch_digest`; these are the trusted evidence RA-009 emits to Minder.
- `state.py` — journal events are append-only with idempotency keys; Minder events reuse the same discipline.
- Contracts that bind this work: **C-N** (HTTP only via `adapters/http.py`, GET-only today), **C-E** (verifier independence), **C-S** (SQLite only in `state.py`), files ≤400 lines (C2), verdict vocabulary `PASS/FAIL/INSUFFICIENT_SAMPLE/NON_COMPARABLE`.
- PRD §9 rule: discover the real Minder surface before designing transport; if none, use an explicit file/CLI bridge — do not invent an HTTP endpoint.

## RA-009 — Minder adapter (PRD §9)

**New:** `repo_agent/adapters/minder.py`, `tests/test_minder.py`; issue `issues/RA-009-minder-adapter.md`.
- Evidence events per the §9 minimum JSON (`event_type` `verification.passed|failed`, producer `trusted-verifier`, `evidence_ref` + `evidence_sha256` into the run artifacts dir, `failure_signature` on failure).
- Artifact-reference validation: resolves only inside the trusted artifact root; rejects traversal, missing files, digest mismatch.
- Decision contract: validate `decision_id, run_id, basis_event_ids, action, reason_code, policy_version, remaining_budget, expires_at`; action ∈ `continue, retry_with_evidence, consult_frontier, pause, stop`. Reject expired, wrong-run, replayed, or malformed decisions with reason codes.
- Transport: read-only probe for an installed Minder surface first (record findings in `issues/RA-009-*` or `discovery.md` method notes); default to a **file bridge** — spool dirs under `~/.local/state/repo-agent/minder/` (`events/` out, `decisions/` in). No invented HTTP API.
- Degraded telemetry: bridge unavailable → bounded redacted buffer, run continues, `telemetry: degraded` + buffered count surfaced; overflow reported, never silently discarded.
- Fail closed: policy enabled but required decision unobtainable/invalid → block new escalation/spend (exit 3, `policy_unavailable`).
- Enforcement in `run_packet`: optional `policy` param consulted at the `needs_evidence` retry point — `retry_with_evidence/continue` → re-dispatch, `pause` → `paused`, `stop` → `failed`, `consult_frontier` → `escalating`. Default off (today's behavior; §9 requires evaluation to run with Minder disabled).

Acceptance mapping (§13): idempotent events → dedupe test; stale decision rejected → expired/replayed/wrong-run tests; telemetry outage degraded → bridge-failure test; required policy outage blocks → fail-closed test.

## RA-010 — Independent evaluator + integrity regressions (PRD §3 Evaluator, §11 levels 1–2)

**New:** `repo_agent/evaluate.py`, `tests/test_eval.py`; un-stub `eval run` in `cli.py`.
- Versioned eval-plan YAML (closed schema, same validation discipline as `config.py`: unknown fields/duplicates/traversal rejected).
- Runs each task packet through `run_packet` as trusted controller; emits a manifest JSON (per-task verdict, reason code, patch/result digests, attempts, token usage, wall time; aggregate counts; plan digest + config pin). Manifest written only by the controller — never by the worker.
- Works without Minder (policy off by default in the eval path — §9).
- Integrity regressions: grader tamper → `tampered_grader` FAIL recorded in manifest; forged worker JSON ignored; patch mutation between freeze and verify → `verdict_invalidated`; hidden grader content absent from the worker workspace.
- `eval compare` stays a stub — comparison semantics belong to RA-013.

## RA-011 — CI checks and packaging

- Packaging: ensure `python3 -m build` wheel carries all runtime resources; add `scripts/packaging-smoke.sh` — build, install into a fresh venv outside the checkout, run `repo-agent --version`, `render --check` and `task validate` on fixtures.
- New `.github/workflows/ci.yml`: `make gates` (pytest + ruff + ratchet), mypy on changed files, `proven-red.sh` against the PR base, drift check on a fixture repo, and the packaging-smoke job.
- Acceptance (§13): fresh install outside source checkout works; drift check and required tests run from the installed package.

## Process (per AGENTS.md / AGENTS.project.md)

1. One `issues/RA-0nn-*.md` per item **before** its first commit, quoting the PRD §13 acceptance lines; commits reference the RA ID.
2. One branch + one PR per RA (`ra-009-minder-adapter`, `ra-010-evaluator`, `ra-011-ci-packaging`); **no merge to `main` without your approval (P8)**.
3. Test-first (P2): failing tests precede each implementation; `scripts/proven-red.sh <base> HEAD` at each milestone, recording whether red was assertion or missing symbol.
4. `make gates` before every commit; mypy on changed files; full suite before push (P3).
5. Docs move with behavior (P10): README command table + claims updated per RA; AGENTS.project.md gains a C-M contract for the Minder adapter boundary (mirroring C-B).
6. Small cleanup riding the first PR: remove the stray shell lines appended to `docs/RUN-NOTES.md` (doc-only, no issue needed per P1).

## Out of scope (explicit)

- RA-012 live pilots (needs the live local model, real target repos, and your authorization — proposed as the next phase after this one).
- `eval compare`/`lesson propose` (RA-013/014), memory/model-switch surface (RA-016–023), context management (RA-024–029), design support (RA-031–035).
- Live Minder wiring beyond the probe (deferred to RA-012 pilots unless discovery finds a stable API).
- Optional: `graft build` at the end (no graph currently exists despite AGENTS.md describing one; deterministic and $0).

## Verification

Per commit: `make gates`. Per milestone: `scripts/proven-red.sh <base> HEAD` + `mypy repo_agent <changed>`. RA-011 adds the packaging smoke as the standing fresh-install check.
