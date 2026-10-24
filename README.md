# repo-agent

Give bounded coding tasks to a cheap local AI model and get results you can trust - because an independent verifier, not the model, decides what "done" means.

## The problem

Local models are nearly free to run. Capable frontier models are not.
The obvious move - hand small coding tasks to the local model - fails in
predictable ways:

- the model reports success, and its own report is the only evidence
  that anything happened;
- it fixes the task but wanders outside its scope, or quietly edits the
  checks that would have caught it;
- a crash or interruption loses everything, and nobody can say what was
  half-done.

Cheaper only helps if someone checks the work - and checking by hand
costs more than the model saved. Frontier models avoid this, at ten to a
hundred times the cost, paid on every task whether it needed that
capability or not.

## What repo-agent does

repo-agent is the boundary between the task and the verdict:

1. **A packet declares the task**: goal, files the worker may write,
   acceptance criteria, verification commands, attempt budget. A packet
   with an unresolved placeholder is rejected before anything runs.
2. **The packet drives a real worker** - your local model through the
   [dsh](https://github.com/deepseek-ai/deepseek-harness) headless
   interface - inside a disposable workspace. The worker never sees your
   home directory, credentials, or the evaluator.
3. **An independent verifier decides.** When the worker stops, the patch
   is frozen by digest; the verifier rebuilds its own environment from
   the trusted base plus that patch and runs the checks with graders
   injected after the worker. Worker-written results are never
   acceptance authority; grader tampering fails the run; container
   isolation (rootless podman, no network, read-only root) is used when
   available, and every verdict records the containment level it
   actually ran at.
4. **A journal keeps the story.** State transitions are code-controlled
   and append-only - "accepted" is unreachable except through review.
   A FAIL re-dispatches with the failure evidence attached, bounded by
   the packet budget; every run leaves handoff.json and events.jsonl.

This does not make the local model as capable as a frontier model. It
makes its failures cheap, visible, and safe to retry - so frontier
spend is reserved for tasks that genuinely need it.

Measured on the reference build: three module implementations and one
full protected lifecycle were carried by a ~3.5-bit local model, zero
frontier tokens in the worker loops. Numbers and the failures that
shaped the design: [docs/RUN-NOTES.md](docs/RUN-NOTES.md).

## Status

Working and tested (124 tests, mypy clean over 16 files, ratchet at
baseline):

- `config` — closed-schema YAML validation with stable reason codes;
  inert parsing; effective config with provenance.
- `render --check|--write` — byte-stable AGENTS.md projection from the
  validated config; refuses to overwrite an unowned file; `--check`
  exits 1 on drift without writing.
- `inspect` — read-only inventory whose findings cite evidence and
  confidence; conflicts exposed, never silently resolved.
- `state` — SQLite run journal: code-controlled transitions, append-only
  events, idempotency keys, per-run locks.
- `verifier` + `containment` — the protected verification described
  above, at the strongest containment level the host supports.
- `adapters/dsh` — the pinned dsh 0.2.1-rc.2 headless interface; parser
  tested against captured event fixtures.
- `doctor [--live]` — readiness checks with honest skips.
- `task validate|run|resume|cancel`, `bootstrap --mode new|mature
  [--apply]` — the full lifecycle with plan-then-apply onboarding.

Named stubs (exit 3, `unimplemented`): `eval run|compare`,
`lesson propose` - the evaluation pilot design is their prerequisite.

## Quick start

```bash
git clone https://github.com/xyzzing/repo-agent && cd repo-agent

# read a repository without touching it
python3 -m repo_agent.cli inspect PATH

# check whether this machine can run the full loop
python3 -m repo_agent.cli doctor PATH --live

# run one bounded task: packet + target repo + a trusted grader script
python3 -m repo_agent.cli task validate TASK.yaml
python3 -m repo_agent.cli task run TASK.yaml --repo PATH --grader GRADER.sh
```

Exit codes: 0 success; 1 checks failed; 2 usage/configuration error; 3
blocked; 4 infrastructure failure. Every result is JSON with a
`reason_code`. The task runner keeps its journal, work areas, and
evidence in `~/.local/state/repo-agent` (override
`REPO_AGENT_STATE_DIR`), never inside the target repository.

Writing a task packet: see `tests/test_packets.py` for the validated
schema and `repo_agent/packets.py:render_prompt` for what the worker
actually receives.

## Trust boundaries (where the guarantees live)

These are enforced by grep gates in `tests/test_gates.py`, so a change
that violates them cannot pass CI quietly:

- `adapters/dsh.py` is the only module that may invoke the harness;
- `adapters/http.py` is the only module that may make HTTP calls;
- `state.py` is the only module that opens the database;
- rendering is byte-stable and inert (nothing executes during
  validation or rendering);
- the verifier's environment never contains the worker's claims about
  itself.

## Related work

- [minder](https://github.com/xyzzing/minder) — the supervisor runtime
  repo-agent is built to govern: local-first failure escalation,
  second-opinion budgets, append-only evidence.
- [dsh-minder-hooks](https://github.com/xyzzing/dsh-minder-hooks) — the
  capture-first hooks bridge for driving dsh sessions.

## Verification

```bash
make gates                          # pytest + ruff + ratchet
scripts/proven-red.sh <base> HEAD   # every changed test was red before
mypy repo_agent --ignore-missing-imports
```

## License

MIT — see [LICENSE](LICENSE).
