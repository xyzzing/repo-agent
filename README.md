# repo-agent

A small CLI toolchain that onboards repositories, generates deterministic
agent instructions from a validated YAML contract, runs bounded coding
tasks through DSH with a local worker, and verifies outcomes with an
independent, protected evaluator.

Built from `docs/prd-v1.3.md` (task IDs RA-nnn). The environment record
from the build run is `discovery.md`; the honest account of what was
built, measured, and deferred is `docs/RUN-NOTES.md`. Per-RA contracts
and status live in `issues/RA-*.md`.

## Status

Working and tested (124 tests, mypy clean over 16 files, ratchet at
baseline):

- `config` — closed-schema YAML validation with stable reason codes
  (duplicate keys, unknown fields, path traversal, symlink escape,
  unsafe tags, oversized input); inert parsing; `effective-config.json`
  with provenance.
- `render --check|--write` — byte-stable AGENTS.md projection from the
  validated config and project notes; refuses to overwrite an unowned
  file; `--check` exits 1 on drift without writing.
- `inspect` — read-only inventory whose findings cite evidence and
  confidence; conflicting discoveries are exposed, never resolved;
  nothing is executed.
- `state` — SQLite run journal: code-controlled transitions (no
  `running -> accepted`), append-only events with idempotency keys,
  atomic checkpoints, per-run owner lock.
- `verifier` + `containment` — protected verification: freezes a patch
  digest, rebuilds its own environment from trusted base + patch,
  injects graders after the worker, fails closed on grader tampering,
  and binds verdicts to the digest so later mutation voids them. When
  rootless podman and the pinned image are present, verify-phase
  commands run in a container with no network and a read-only root
  filesystem, and each verdict binds the containment level it ran at;
  without them it is a named skip to `isolation_by_construction`.
  Generated artifacts (__pycache__ etc.) never enter a patch; binary
  files travel base64 under a size cap.
- `adapters/dsh` — the pinned dsh 0.2.1-rc.2 headless interface
  (`--json` run events, `--session-id` resume, process-group
  cancellation); parser pinned to captured live-event fixtures; per-step
  usage deltas summed and verified against live dispatches.
- `doctor [--live]` — readiness checks with honest skips: dsh binary and
  profile, endpoint health through the minder proxy, containment probes,
  journal writability, and (live) one harmless model ping.
- `task validate|run|resume|cancel` — the full lifecycle: a §10 worker
  packet drives a real worker in a staged workspace; preflight refuses a
  moved base or a dirty repo; a FAIL re-dispatches with the
  verification-evidence tail, bounded by the packet's `max_attempts`
  (the budget carries across resumes); runs land in the journal with
  handoff.json + events.jsonl evidence files; acceptance comes only from
  the protected verifier. First live run: PASS, accepted, ~2 minutes.
- `bootstrap --mode new|mature [--apply]` — plan-then-apply onboarding:
  the proposal is recorded with the content hashes it reviewed, and
  --apply refuses on any drift since. Mature mode backs up a
  hand-written AGENTS.md byte-identical before the renderer takes over.

Honest stubs (exit 3 `unimplemented`): `eval run|compare`,
`lesson propose`.

## Usage

```sh
repo-agent inspect PATH                 # read-only inventory
repo-agent render PATH --check          # drift check (exit 1 on drift)
repo-agent render PATH --write          # regenerate owned AGENTS.md
repo-agent doctor PATH --live           # readiness, including a model ping
repo-agent task validate TASK.yaml      # validate a worker packet
repo-agent task run TASK.yaml \         # full protected lifecycle
    --repo PATH --grader GRADER.sh
```

Exit codes: 0 success; 1 checks failed; 2 usage/configuration error; 3
blocked prerequisite/policy; 4 infrastructure failure. Every result is
JSON with a `reason_code`.

The task runner keeps its journal and work areas in
`~/.local/state/repo-agent` (override `REPO_AGENT_STATE_DIR`), never
inside the target repository.

## Layout

- `repo_agent/` — the package; `adapters/dsh.py` is the only module that
  may invoke dsh, `adapters/http.py` the only one that may touch urllib,
  `state.py` the only one that opens SQLite (grep-gated in
  `tests/test_gates.py`).
- `scripts/proven-red.sh`, `scripts/ratchet.sh` — the P2/C7 gates.
- `AGENTS.md` — portable agent-contract core; `AGENTS.project.md` — this
  repo's contracts and verification commands.

## Related work

- [minder](https://github.com/xyzzing/minder) — the supervisor runtime
  repo-agent is built to govern: local-first failure escalation,
  second-opinion budgets, append-only evidence.
- [dsh-minder-hooks](https://github.com/xyzzing/dsh-minder-hooks) — the
  capture-first hooks bridge for driving dsh sessions.

## License

MIT — see [LICENSE](LICENSE).

## Verification

```sh
make gates          # pytest + ruff + ratchet
scripts/proven-red.sh <base> HEAD   # every changed test was red before
mypy repo_agent --ignore-missing-imports
```
