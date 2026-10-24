# RA-013 — 30-task pilot and configuration comparison

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-013 | Frontier plans, local executes / 012 | 30-task pilot and
> configuration comparison | Full run manifest; failures retained;
> cost includes all stages; uncertainty explicit

PRD §11 pilot shape: 30 distinct tasks — 20 development + 10
held-out — grouped by issue family across bounded bug fixes,
cross-file features, mature compatibility, instruction
interpretation, verification integrity, and environment failure
recognition.

## Design

- **Evaluator extensions** (test-first): plan tasks gain per-task
  `repo`, `family`, and `split` fields (a 30-task corpus spans 30
  repos — the single-plan-level repo becomes a default, not a
  requirement); plans gain a `policy` field so an arm's configuration
  is versioned in the plan digest and recorded in its manifest.
- **`eval compare` implemented** (un-stub): pairs two manifests by
  task (task set or packet digests differing → `NON_COMPARABLE`),
  classifies against **predeclared tolerances**
  (`--max-quality-loss`, `--min-cost-improvement`, `--min-paired`)
  into exactly `NON_COMPARABLE / INSUFFICIENT_EVIDENCE / REGRESSION /
  NO_MATERIAL_CHANGE / IMPROVEMENT_CANDIDATE`; critical integrity
  findings (tampered grader, invalidated verdict) block promotion
  regardless of aggregate scores. Comparison semantics preserve
  historical verdict vocabulary; an insufficient-sample comparison is
  a valid operation that explicitly denies promotion.
- **Corpus**: a deterministic generator (`eval/corpus.py`) constructs
  30 disposable target repos with packets and hidden graders under
  the state dir. Expected-failure families (environment failure
  recognition) are designed so the *correct* outcome is a bounded,
  honest failure — the metric is zero fabricated success, not PASS.
- **Arms** (PRD §11's configuration comparison, honestly scoped):
  arm A = local-only (policy none), arm B = local-plus-Minder
  (policy local: budget ladder + sink telemetry). Frontier-only and
  per-task frontier consultation are **excluded this round with
  reason**: this harness cannot measure frontier token cost, and PRD
  §11 forbids comparing configurations as if only the harness
  differed when cost cannot be included; recorded as not comparable,
  not as a result.
- **Predeclaration** (PRD §11, before running): tolerated quality
  loss = 0 PASS tasks; desired cost improvement = 0% (arm B is
  expected `NO_MATERIAL_CHANGE` on verdicts with telemetry/policy
  overhead measured in wall time — the comparison demonstrates the
  machinery and the overhead, and nothing is promoted on it).
- **Cost, all stages**: per-task worker tokens, attempts (retries
  included), wall time; planner (frontier) cost recorded as unknown
  with reason; failure manifests retained, never pruned to look
  better.

## Remaining (recorded, not hidden)

- Repeated runs per task (stochastic variance) are not affordable in
  this round; single-run results carry no distributional claims
  (PRD §11: "A 20-run minimum is not statistical proof").
- Packet-precision (planner-effort) arms are an improvement-eval
  candidate for RA-014, not this comparison.
