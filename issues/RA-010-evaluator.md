# RA-010 — Independent evaluator and integrity regressions

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-010 | Frontier test design, local implementation / 006,008 |
> Independent evaluator and integrity regressions | Works without
> Minder; hidden tests inaccessible; changed patch invalidates results

## Design

- `repo_agent/evaluate.py`: a versioned eval-plan loader (closed
  schema, packets.py discipline: unknown fields, duplicate keys,
  unsafe tags, nonempty task list, unique task ids, packet and grader
  files must exist and parse — all before any worker spend) and the
  trusted controller `run_plan`: each task executes through
  `taskrun.run_packet` in a fresh per-eval journal/work area, and the
  controller alone writes the manifest.
- The manifest binds what ran to what was produced: plan digest, per
  task the packet/grader digests, verdict (PASS/FAIL vocabulary),
  reason code, patch digest, result digest, attempts, token usage and
  wall time; aggregates at the end. Worker output is never acceptance
  authority — verdicts come only from the protected verifier.
- Policy stays off in the eval path (PRD §9: evaluation runs with
  minder disabled); the manifest records `policy: none`.
- Integrity regressions pin the evaluator against the known failure
  modes: a worker-forged result file is ignored; grader tamper fails
  the task as `tampered_grader`; grader content (canary) never appears
  in the worker prompt or workspace; a mutated patch after freezing is
  `verdict_invalidated`; repeated identical runs reproduce identical
  patch and result digests.
- `eval compare` remains a stub — comparison semantics are RA-013.

## Remaining (recorded, not hidden)

- Repetitions for stochastic configurations and held-out task groups
  are RA-013 (the 30-task pilot), not the RA-010 runner.
- The manifest records cost in tokens and wall time; frontier cost
  accounting arrives with RA-013's configuration comparison.
