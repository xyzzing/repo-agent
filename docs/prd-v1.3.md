# Agent Repo Automation: Frontier-to-Local DSH Implementation PRD

Version: 1.3 | Date: 21 October 2026 (Singapore)

Revision 1.3: adds conditional UI/UX planning, optional Intent/Impeccable integration, curated design references, frontier-to-local design contracts, rendered review and RA-031–035. Design-system preservation and task proportionality are explicit.

Revision 1.2: adds validated CLM-style context editing, exact-first engine reuse, performance evaluation and RA-024–029; RA-030 is an optional CML markup experiment. No implementation or speedup is claimed by this specification.

Revision 1.1: adds portable long-term memory, event-driven extraction, model-switch qualification, memory evaluation and RA-016–023. Existing task IDs are retained; dependencies determine execution order.

Status: implementation specification; no deployment has been performed by this document.

Primary implementers: a frontier supervisor and the user's local approximately 3.5-bit Qwen 3.8 Flash Next deployment, executed through DeepSeek Harness (DSH). The exact model artifact, engine and capabilities must be discovered, not inferred from this label.

## 1. Outcome and product decision

Build a small CLI toolchain, provisionally `repo-agent`, that onboards new and mature repositories, generates consistent agent instructions, runs bounded coding tasks through DSH, verifies outcomes independently, and records evidence for supervised improvement.

The user should be able to give a frontier supervisor this document and a target repository. The supervisor inspects the environment, turns the work into local-model packets, dispatches one packet at a time, reviews the evidence, and delivers a working installation with rollback instructions.

Core decisions:

- YAML is the validated project configuration source. Generated AGENTS.md is the human/model-readable projection.
- DSH remains the execution harness. Do not build another conversational agent loop.
- Minder retains evidence, escalation and budget policy. Do not duplicate its policy in a second autonomous supervisor.
- Evaluation runs independently of the implementation worker and independently of Minder's runtime.
- Frontier supervision owns ambiguity, interfaces, high-risk reviews and evidence-based acceptance. Local execution owns bounded implementation work.
- Reusable learning is a proposed versioned change, evaluated before promotion. No automatic production self-modification.
- Durable knowledge belongs to the user/toolchain, independently of the model that wrote it. Minder owns canonical memory and its lifecycle; search indexes and writer backends are replaceable.
- Model upgrades preserve evidence and portable knowledge, while model-specific strategies and routing are requalified. No automatic weight changes or cross-model cache reuse.
- Editable working context is a versioned projection of immutable execution evidence. DSH commits validated revisions, Minder governs knowledge/policy, and the inference engine owns state/cache validity.
- UI/UX planning is conditional on the task. Preserve existing design systems, load only relevant skills, and verify rendered results for substantive visual work. No external design site or skill is compulsory.
- CLM (Context Language Models) is the primary context-management workstream. CML (Context Mark Language) is a separate optional rendering experiment; neither is assumed to improve this deployment without measurement.

### Success scenarios

1. A new repo receives a minimal, verified setup and one working vertical slice.
2. A mature repo receives additive configuration while existing instructions, behavior and user edits are preserved.
3. A local worker fixes a scoped issue; a protected verifier accepts or rejects the resulting patch.
4. A stopped run resumes without repeating an already completed frontier consultation or losing evidence.
5. A failed task produces a useful escalation packet and, when warranted, a separately evaluated improvement proposal.
6. A new model resumes from a neutral checkpoint and scoped knowledge without inheriting unqualified prompts, permissions or performance claims.
7. A stale or contradicted memory is withheld or explicitly marked and corrected without erasing its provenance.

### Non-goals for v1

No web UI for the toolchain itself (conditional design support for downstream UI projects is in scope), general workflow DSL, plugin marketplace, multi-tenant service, model fine-tuning, automatic repository-wide cleanup, automatic merges, distributed scheduler or mandatory new vector database. No rewriting DSH or Strata. No claim that low-bit Qwen matches a frontier model until measured. No real-money trading or unrelated domain expansion.

## 2. Evidence baseline and mandatory discovery

Earlier in this conversation, Minder was inspected at commit `c8038d3924dc6ed33c8d1d3b4e061852bf81c6be`. This is a reference snapshot, not a claim about the installed machine or current remote HEAD.

Observed at that snapshot:

- `minder_core/comparator.py` exposes an independently importable comparison function with safety, comparability and regression checks.
- `minder_quality/driver.py` stages tasks and grades CLI-agent output; it explicitly leaves network isolation to an external wrapper.
- `benchmarks/coding-core-v1/manifest.json` contains two tier-3 coding repair tasks. Useful regression fixtures, insufficient coverage for this product.
- `minder_op`, `minder_decision` and memory/evidence components provide integration candidates.
- Comparator PASS means within its configured regression limits, not statistically proven improvement.

Before coding, frontier must produce `discovery.md` with:

1. Actual target paths, git status, branch and commit; applicable AGENTS.md instructions.
2. DSH version, available profiles, supported noninteractive invocation, session resume and event interfaces, established from installed help/source or pinned upstream documentation.
3. Minder installed version, active configuration and actual event/escalation integration surface.
4. Exact local model file/hash, quantisation, engine revision, endpoint, context limits, chat/tool template, streaming behavior and reasoning controls.
5. Host prerequisites: Fedora/runtime details, existing container tooling, CPU/RAM/GPU allocation and model-server ownership.
6. Existing tests, skills and scripts to reuse; baseline failures and unavailable checks.
7. Existing Minder memory schemas, ownership, retention, retrieval and migration mechanisms; DSH persistence backend and durable flush/checkpoint/injection interfaces.
8. Existing embedding/index identities, writer resource contention and candidate model-switch targets.
9. Current context compaction/revision ownership, exact model request reconstruction, engine revised-history support, prefix-cache diagnostics and state/checkpoint ownership.
10. For downstream UI work: existing design documents/tokens/components, browser test tools, available design skills, screenshot access and reviewer vision capability. Skip this discovery for tasks with no UI relevance.
11. Any departure from this PRD with reason and impact.

Do not guess a DSH profile named `tui`, invent a CLI flag, or assume an OpenAI-compatible endpoint supports every tool/reasoning feature. Never replace active model or systemd configuration during discovery.

If no workspace is supplied, discover plausible project roots read-only and ask only if multiple targets remain ambiguous. The historical `~/projects` convention is a hint, not verified state.

## 3. Architecture and ownership

Implement one small Python CLI package unless the discovered repo already has a better established stack. Prefer its existing dependency manager. Use a safe YAML parser and schema validation; declare and pin necessary dependencies. Avoid introducing a framework for straightforward state transitions.

| Component | Owns | Must not own |
|---|---|---|
| repo-agent core | Config, rendering, lifecycle, workspace and artifact references | Model chat loop or hidden policy decisions |
| DSH adapter | Start/resume/cancel, session identity, normalized tool/run events | Acceptance grading |
| Minder adapter | Evidence, canonical memory access and policy requests | Independent outcome oracle |
| Memory writer | Evidence-linked candidate extraction | Promotion authority or policy changes |
| Retrieval backend | Derived search indexes and bounded candidate retrieval | Canonical knowledge ownership |
| Execution boundary | Filesystem/process/network containment and credential exposure | Declaring correctness |
| Evaluator | Trusted checks, held-out cases, result production | Editing worker implementation |
| Frontier supervisor | Task contracts, review, exceptional diagnosis and release recommendation | Weakening graders to make a patch pass |
| Local worker | Scoped implementation and evidence-backed handoff | Editing protected policy, budgets or hidden evaluation |
| CI/operator | Merge/release enforcement and deployment configuration | Treating model claims as verification |

Suggested modules: `config`, `inspect`, `render`, `state`, `workspace`, `events`, `evaluate`, `cli`, and `adapters/dsh` plus `adapters/minder`. Add modules only when there is a concrete responsibility. Do not mandate one file per abstract noun.

Keep this package separate from Minder's core runtime. A separate repo is reasonable after discovery; a clearly bounded package in an existing toolchain repo is also acceptable. Document the decision. Avoid a broad extraction of Minder internals before a working adapter exists.

## 4. Configuration contract

The following YAML and CLI are proposed interfaces to implement. They are not native DSH or Minder APIs.

```yaml
schema_version: 1
project:
  name: sample-project
  maturity: mature
  architecture: docs/architecture.md

environment:
  setup: [uv, sync, --frozen]
  required_tools: [git, uv]

commands:
  lint: [uv, run, ruff, check, .]
  test: [uv, run, pytest, -q]
  verify: [lint, test]

instructions:
  policy_version: '1.0.0'
  project_notes: AGENTS.project.md
  scoped: []

boundaries:
  generated: [generated/**, vendor/**]
  sensitive: [migrations/**, auth/**]
  preserve: [public_api, stored_data_compatibility, user_changes]

skills:
  required: [code-quality-guard]
  conditional: []
  lock_file: agent-skills.lock.json

execution:
  adapter: dsh
  profile: local-worker
  sandbox_profile: worker-local
  max_attempts: 3
  max_attempts_without_new_evidence: 2
  timeout_seconds: 1800

routing:
  default: local
  frontier_when: [ambiguous_acceptance, sensitive_change, repeated_failure]

evaluation:
  suite: coding-project-v1
  verifier_profile: protected

learning:
  capture: true
  propose_lessons: true
  auto_promote: false

memory:
  schema_version: 1
  canonical_owner: minder
  default_scope: repository
  cross_project: reviewed_export_only
  writer:
    backend: existing_model_endpoint
    schedule: idle_priority
    debounce_seconds: 45
    max_pending_batches: 100
  retrieval:
    initial_backend: keyword_and_metadata
    context_budget_tokens: 1500
    triggers: [task_start, unexpected_failure, subsystem_change, correction]
  promotion:
    facts: evidence_checked
    procedures: independent_verification
    reusable_rules: reviewed_evaluation
  model_specific_default: unqualified_on_switch

model_switch:
  require_checkpoint: true
  require_qualification: true
  transfer_inference_cache: false
  rollback_profile: previous_qualified

context_management:
  mode: observe_only
  editable_regions: [working_notes, completed_tool_output, retrieved_evidence]
  triggers: [phase_boundary, context_pressure, repeated_redundancy]
  max_edit_attempts_per_checkpoint: 1
  archive_before_edit: true
  require_revision_match: true
  reserve_output_tokens: 4096
  engine_reuse: exact_if_supported
  recompute_fallback: true
  approximate_suffix_reuse: false
  rendering: markdown

design:
  mode: auto_when_relevant
  preference_questions: ask_when_material
  preserve_existing_system: true
  planning:
    backend_only: skip
    routine_ui_change: lightweight
    new_interface: full
    substantial_redesign: full
  references:
    max_per_decision: 3
    verify_before_use: true
    auto_install: false
  skills:
    router: design-resource-router
    optional_candidates: [design-with-intent, impeccable]
  review:
    rendered_ui: when_visual_change
    responsive: when_applicable
    interaction_states: when_applicable
    keyboard_and_focus: when_applicable
    reduced_motion: when_motion_changes
```

Example commands above are appropriate only for a repo actually using uv/pytest/ruff. Bootstrap must discover alternatives, and never install a new language stack just to match this example. `local-worker` is a proposed profile to provision only after confirming supported DSH configuration.

Design fields are proposed configuration to implement, not current DSH APIs; resolve skill aliases to actual installed/pinned identifiers. Design modes are auto_when_relevant, off and required. The off mode skips optional planning/reference exploration, not explicit acceptance, accessibility or functional requirements. Record overrides and rationale. Context modes are off, observe_only and validated_edits; unknown modes fail validation. Protected regions are controller-defined, never removable through project configuration. Output reservation is a tunable example and must fit the discovered model limit. Memory debounce and retrieval budgets are tunable starting defaults, not measured optima. Operator-owned retention, credentials and model registry live outside the worker-controlled repo. Validate all new fields and include them in the effective config.

### Validation requirements

- Reject unknown fields, duplicate YAML keys, unsupported versions, unsafe tags, excessive nesting and oversized input.
- Commands are nonempty argv arrays. `verify` references named commands, with cycle detection if composition is later supported.
- All path fields are repo-relative unless their field explicitly allows an operator-owned external location. Resolve symlinks and reject traversal outside authorized roots.
- Configuration is inert during inspection, validation and rendering. Executing setup or verification is a distinct, visible operation.
- A worker cannot override trusted sandbox profiles, frontier credentials, budgets, protected graders or promotion policy by editing repo YAML.
- Produce `effective-config.json` recording validated values, defaults, provenance and content hashes. Keep secrets out.
- Lock skills to actual revisions/content digests. Record where each skill is loaded and how loading was verified. Missing skills yield an explicit capability gap, not fabricated compliance.
- Initial precedence: operator security/budget policy constrains project configuration; task packets may narrow permitted scope and budgets, not widen them. Normal harness instruction precedence still applies.

## 5. Repository onboarding and generated instructions

### CLI contract

| Command | Required behavior |
|---|---|
| `repo-agent inspect PATH --json` | Read-only inventory with evidence paths and confidence |
| `repo-agent bootstrap PATH --mode MODE` (new or mature) | Produce a proposed patch; no install or execution by default |
| `repo-agent bootstrap PATH --apply` | Apply an already reviewed proposal with source-hash checks |
| `repo-agent doctor PATH` | Check prerequisites and report operational readiness |
| `repo-agent render PATH --check` | Non-mutating drift check |
| `repo-agent render PATH --write` | Deterministic generation of owned instruction files |
| `repo-agent task validate TASK.yaml` | Validate task and policy references |
| `repo-agent task run TASK.yaml` | Run one authorized task with durable state |
| `repo-agent task resume RUN_ID` | Reconcile and resume a paused/interrupted run |
| `repo-agent task cancel RUN_ID` | Stop tracked execution and preserve evidence |
| `repo-agent eval run PLAN.yaml` | Execute a versioned evaluation plan |
| `repo-agent eval compare BASE CANDIDATE` | Compare compatibility, regressions, quality and cost |
| `repo-agent lesson propose RUN_ID` | Produce an evidence-linked candidate, never activate it |

Exit codes: 0 success; 1 checks failed; 2 usage/configuration error; 3 blocked prerequisite/policy; 4 infrastructure failure. JSON results also carry specific reason codes. `--check` returns 1 on drift. A valid insufficient-sample comparison may exit 0 as an operation, but its report must explicitly deny promotion.

### Discovery sources

Inspect existing CI, manifests, lockfiles, README/CONTRIBUTING and instructions. Record the source of each inferred command. Conflicting commands become unresolved findings, not arbitrary choices. Inspection does not run package scripts.

### Mature repo behavior

Preserve existing instructions and user edits. Show a migration diff that maps retained guidance into AGENTS.project.md or scoped notes. Require a deliberate apply action for the initial migration. Existing authorization to implement the task can cover this action after review by the frontier; do not repeatedly ask the user for routine reversible work. Never stash, reset or commit unrelated changes.

### New repo behavior

Use a selected minimal project template. Establish a working example and behavioral checks before speculative architecture. Bootstrap may ask for the stack only if it cannot be inferred from the task.

### Rendering

Inputs: versioned shared policy, validated YAML, project notes and scoped notes. Output must be deterministic and include source digests and policy version. Exclude timestamps from generated content to avoid meaningless drift. Preserve scoped instruction semantics; do not flatten incompatible scopes into one file.

Generated AGENTS.md must cover project map, verified commands, inspect-before-edit, preservation of user changes, acceptance contract, reuse, error handling, relevant skills, bounded retries, verification and honest completion reporting. Keep bulky historical lessons out of the file.

Use existing harness instruction conventions discovered in phase 0. Generate alternate entry files only when necessary. A harmless instruction-loading integration fixture must demonstrate the instruction was actually supplied; a file's presence alone is insufficient.

## 6. Execution lifecycle and recovery

States: `created -> preflight -> baselined -> contracted -> running -> verifying -> reviewing -> accepted`. Alternate states: `needs_evidence`, `escalating`, `paused`, `blocked`, `failed`, `cancelled`. No direct `running -> accepted` transition.

Transitions are code-controlled. Worker messages are observations, never authoritative transition commands. Each accepted state carries the exact patch digest and verifier result digest.

### State requirements

- Persist state and append-only events outside the worker's writable mount. A single SQLite journal with transactional transitions is sufficient; avoid dual writable sources of truth.
- Use run IDs, event IDs, sequence numbers and idempotency keys. A run lock prevents two resumptions dispatching the same task.
- On resume, reconcile DSH session/process status, workspace revision and pending external actions before dispatch.
- Do not promise exactly-once external requests. If a frontier request may have completed but its response was lost, mark `consult_status_unknown`, reconcile provider/request IDs where available, and do not automatically spend again.
- Atomic checkpoints record completed work, evidence references, current hypothesis, unresolved questions and next action. Model handoff checkpoints additionally bind the patch, memory revisions, pending external actions and cumulative budgets; see Section 12B. They do not store private chain-of-thought.
- Timeout/cancellation terminates the tracked process group or container, checks for remaining children, and preserves artifacts.
- Two unsuccessful attempts without new evidence trigger escalation or stop. New evidence means a new validated observation, not different prose or a changed timestamp. Record the reason for retry eligibility.
- Budgets apply across resumes and all descendants. Include maximum attempts, wall time, frontier spend and context/output limits where measurable. Unknown spend is explicitly unknown and handled conservatively.

## 7. DSH and model adapter

Implement only the smallest verified DSH interface needed for start, resume, cancel and event collection. Prefer supported public interfaces over parsing display output. If only CLI output is available, version and test the parser against real captured fixtures; fail explicitly on unknown formats.

The doctor must probe, without modifying host services:

- Endpoint health and reported model identity.
- A harmless structured tool invocation and tool-result roundtrip.
- Relevant streaming/finish behavior and cancellation.
- Context/output limits and supported reasoning controls where discoverable.
- Session persistence and instruction loading.

Do not silently switch to another model on failure. Record exact effective inference settings per run. Avoid per-turn reasoning/template changes that could invalidate engine caches unless tested and explicitly configured.

On the user's single-GPU deployment, serialize workers by default. Frontier work can occur remotely while the GPU serves one local session. Do not start another GPU model or alter Strata/llama service ownership automatically.

Normalize DSH-specific fields into the event contract. Keep raw redacted artifacts for troubleshooting with bounded retention. Unsupported DSH versions report BLOCKED until a compatible adapter is established.

## 8. Execution containment and evaluator independence

Select one concrete containment implementation after inspecting the host, preferably its existing rootless container tooling. Do not claim a worktree or a fresh directory is a sandbox.

Worker access: writable task checkout and designated temporary directory; no evaluator assets, host home, private credentials or policy database. The model endpoint is available through an explicitly configured broker/allowlisted route. A container's loopback is not the host's loopback; demonstrate connectivity rather than assuming 127.0.0.1 works.

Worker networking: deny general outbound traffic, allow only the required model/tool broker. Dependency acquisition occurs separately through a reviewed setup step and pinned artifacts. Frontier credentials remain outside the worker, in the supervisor/broker boundary.

Verification workflow:

1. Stop worker execution and freeze its patch against the recorded base revision.
2. Create a clean verifier environment from the trusted base plus that patch.
3. Mount or inject trusted graders after worker execution; keep secret cases unavailable to the worker.
4. Run checks with time/memory/output limits and restricted network.
5. Collect results through a trusted controller. Worker stdout or a worker-created JSON report cannot declare success.
6. Bind result digests to the frozen patch. Any later patch mutation requires verification again.

Product tests may legitimately change with requirements. Record and review such changes; do not categorically forbid test edits. Evaluator-owned tests and policy remain protected. Candidate code itself is untrusted during grading: container isolation and controller-owned result handling must prevent it overwriting grader assets or forging accepted results. Hash checks are useful evidence, not a substitute for containment.

Test escape attempts against synthetic canary files and blocked network destinations. A containment failure blocks deployment. If containment cannot be provided, allow inspect/render only and clearly disable autonomous execution.

## 9. Minder boundary

Reuse the installed, supported evidence/decision surface where possible. Discover it before designing transport. If no stable API exists, begin with an explicit file/CLI bridge and a small adapter contract; do not invent an HTTP endpoint and pretend it already exists.

Minimum event:

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "event_type": "verification.failed",
  "run_id": "run-003",
  "task_id": "cache-invalidation",
  "sequence": 12,
  "attempt": 2,
  "timestamp": "2026-10-21T01:00:00Z",
  "producer": "trusted-verifier",
  "evidence_ref": "artifacts/test-results.json",
  "evidence_sha256": "actual-digest",
  "failure_signature": "cache_stale_after_config_change"
}
```

Artifact references resolve only within the trusted run artifact root; reject traversal and missing/digest-mismatched artifacts. Evidence must distinguish worker-reported, controller-observed and independently verified facts.

Decision response: `decision_id`, `run_id`, `basis_event_ids`, `action`, `reason_code`, `policy_version`, `remaining_budget`, `expires_at`. Allowed actions: `continue`, `retry_with_evidence`, `consult_frontier`, `pause`, `stop`. Validate stale/duplicate decisions and permissions before applying.

Minder is the policy authority when enabled; the runner enforces its decisions and immutable operator limits. When optional telemetry is unavailable, buffer bounded redacted events and surface degraded capture. When required policy decisions are unavailable, block new escalation/spend. Do not fail open on a budget or permission requirement.

Evaluation must also run with Minder disabled. Preserve existing comparator behavior through an adapter; introduce richer statistical and promotion results separately instead of silently redefining historical PASS.

## 10. Frontier-to-local operating protocol

### Frontier responsibilities

Inspect and pin the environment; resolve interfaces; define acceptance independently of implementation; split tasks; dispatch through DSH; review every evidence bundle; perform high-risk changes directly when justified; manage integration and final deployment.

### Local worker responsibilities

Read assigned code/instructions, implement one coherent change, run permitted focused checks, review its diff and return a structured handoff. Never modify protected acceptance, policy or budgets. Request scope changes with concrete evidence.

### Worker packet template

```yaml
task_schema_version: 1
task_id: RA-003
base_commit: '<actual commit>'
goal: 'Render deterministic AGENTS.md from validated configuration'
read_first: [src/repo_agent/config.py, tests/test_config.py]
expected_write_scope: [src/repo_agent/render.py, tests/test_render.py]
acceptance:
  - 'Repeated render with identical inputs produces identical bytes'
  - 'Project notes remain unchanged'
  - 'Check mode reports drift without writing'
invariants: ['No command execution during rendering']
non_goals: ['DSH integration', 'automatic skill installation']
verification_commands:
  - [uv, run, pytest, -q, tests/test_render.py]
budget:
  max_attempts: 3
  timeout_seconds: 1800
required_skills: [code-quality-guard]
escalate_when:
  - 'Existing scoped instruction semantics are ambiguous'
  - 'Two attempts fail without new diagnostic evidence'
```

Placeholders must be resolved before dispatch; do not hand unresolved example paths to the local worker. Frontier may adjust packet size to observed model reliability. One bounded responsibility and one writer per overlapping code path are the defaults; parallel execution is optional only for proven independent work and adequate resources.

### Handoff result

Return task ID, base/current revision, changed paths, patch digest, acceptance-by-acceptance result, commands actually executed with exit codes, evidence references, baseline failures, remaining risks and requested decisions. No unsupported claim of production readiness.

### Minimal escalation

Include the exact failing command, short error excerpt, reproduction steps, relevant code/diff, attempted hypotheses, new observations and one specific question. Exclude irrelevant conversation and secrets. Prefer the registered `escalate-minimal-questions` skill when available; verify its loading.

### Skills

Use code-quality-guard for substantive coding and final review. Use evidence-led-execution if installed and applicable; otherwise record its absence without blocking ordinary work. Use port-strata-hip/analyze-strata-moe only for actual engine/kernel work, not this generic CLI. Do not install skills simply because their names appear in this PRD. Pin reviewed dependencies and skills before execution.

## 11. Evaluation and promotion

Separate three levels:

1. Software tests: parser, renderer, state transitions, adapters, isolation and recovery.
2. Agent-task evals: actual tasks under fixed model/harness configurations.
3. Improvement evals: baseline versus candidate skill/instruction/routing change.

Pilot: 30 distinct tasks, with 20 development tasks and 10 held-out tasks grouped by issue family. Suggested mix: bounded bug fixes, cross-file features, mature compatibility, instruction interpretation, tool-call/recovery, verification integrity, and environment failure recognition. Use repeated runs for stochastic configurations when affordable; repetitions do not substitute for task diversity.

The small held-out pilot is a smoke check, not enough to prove a small improvement. Keep holdouts inaccessible to the worker and improver, refresh after repeated consultation, and never call public shipped fixtures secret holdouts.

Compare frontier-only, local-only, frontier-plan/local-execute, and local-plus-Minder. Then test individual additions. Hold task/environment/limits constant where feasible; log unavoidable differences. Do not compare different model artifacts or task revisions as if only the harness changed.

Metrics: independently verified completion; critical failures; false completion; tampering; human rework minutes; total wall time; p50/p95 where sample supports them; frontier tokens/cost; local execution time; total cost per verified completion. Include planner, reviewer, retries and failed runs in cost. Report energy only if measured; do not estimate it from token counts without a documented model.

Report outcomes: `NON_COMPARABLE`, `INSUFFICIENT_EVIDENCE`, `REGRESSION`, `NO_MATERIAL_CHANGE`, `IMPROVEMENT_CANDIDATE`. Critical integrity/permission failures block promotion regardless of aggregate scores. Report task-level paired results and uncertainty; cluster by task when repeated runs exist. Predeclare the tolerated quality loss and desired cost improvement before running comparisons. A 20-run minimum is not statistical proof.

An evaluator can use existing Minder comparison logic for compatibility and add a separate promotion report. Harbor is a candidate external execution adapter, not a prerequisite for the first working vertical slice. Mini-SWE-agent is an optional simple baseline; do not add it to production routing merely for benchmarking.

## 12. Learning and maintenance

Candidate lesson fields: ID, source run/evidence digests, failure family, proposed change, applicable repo/model/engine versions, contraindications, owner, evaluation plan/results, expiry or invalidation condition, review state and rollback revision.

Choose the smallest correction: a missing repo fact, a test, a tool adapter fix, a relevant skill, or a routing adjustment. Do not convert every transient incident into global instructions. Retrieve only applicable lessons within a bounded context budget.

Candidate states: proposed, evaluated, reviewed, promoted, rejected, expired, rolled_back. Changes to graders or policy require separate review and cannot be smuggled into a worker implementation patch.

Optional maintenance CLI emits a reviewable report for stale instructions, repeated failures and pinned dependency updates. Schedule only when requested/configured by the operator. No silent auto-install, fleet-wide policy update or production routing change.


## 12A. Portable long-term memory

### Ownership and storage

Implement logical collections in the existing Minder-owned store where feasible; do not create four new services. Keep the repo-agent lifecycle journal authoritative for run transitions, DSH authoritative for session events, and Minder authoritative for memory revisions. Link them by immutable IDs/digests rather than duplicating editable transcripts. Independent evals use an exported frozen memory snapshot or memory-off mode and do not require a live Minder daemon.

| Collection | Contents | Validity and retention |
|---|---|---|
| Execution evidence | Redacted tool outputs, patches, verification and source event references | Bounded retention with evidence-availability state |
| Working state | Current task, decisions, failures, pending actions and next step | Task-scoped; checkpoint at meaningful boundaries |
| Durable knowledge | Project facts, user constraints, decisions and verified procedures | Revalidate on relevant changes, contradictions or expiry |
| Capability profiles | Exact model/engine/template/tool qualification and measured routing performance | Specific to a versioned execution profile |

Producer identity is provenance, not an automatic scope restriction. A build command discovered by Qwen may be valid for DeepSeek. A Qwen-specific prompt workaround must be withheld from another model until qualified. Treat future Qwen/DeepSeek names as user intentions, not proof of available artifacts or capabilities.

### Canonical memory contract

```yaml
memory_schema_version: 1
memory_id: mem-cache-017
revision: 1
kind: verified_procedure
claim: 'Invalidate cached results when configuration changes.'
scope:
  repository_id: '<stable registered repository identity>'
  branch_context: '<source branch; not the sole validity check>'
  component: configuration_cache
  relevant_files:
    - path: src/cache.py
      content_hash: '<hash at verification>'
applicability:
  prerequisites: ['Cache key omits the configuration revision']
  model_specific: false
provenance:
  source_run: run-003
  source_event_ids: [event-021, event-034]
  producer_profile: qwen-local-profile-v1
  writer_profile: writer-profile-v1
  evidence_digest: '<actual digest>'
verification:
  state: locally_verified
  tested_commit: '<commit>'
  command_argv: [uv, run, pytest, -q, tests/test_cache.py]
  outcome_ref: artifacts/regression-results.json
lifecycle:
  last_validated_at: '<timestamp>'
  supersedes: []
  contradicted_by: []
  invalidation_triggers: [relevant_code_changed, regression_test_changed]
```

Add authority/source type, sensitivity/egress classification, owner and expiry where applicable. Repository IDs survive path moves; forks and unrelated repos require explicit mappings. A branch name or HEAD change alone must not invalidate the whole bank. Relevant file/interface/dependency changes mark affected claims for revalidation. Missing evidence lowers the supported verification state; never silently report it as independently verified.

Memory lifecycle: `candidate -> evidence_checked -> locally_verified -> reusable`; not every kind needs every transition. Direct facts may become retrievable at evidence_checked. Procedures require verified outcomes; general rules require wider evaluation and review. Parallel states include stale, contradicted, superseded and retired. Keep revision links; do not resolve conflicting claims by latest timestamp alone. Preserve uncertainty and surface material contradictions.

A test pass supports its tested behavior, not every proposed causal explanation. Separate observed results from root-cause hypotheses. Retrieval frequency and user silence are not verification. Memory cannot change permissions, budgets, sandbox policy or evaluator criteria. Existing authorization remains authoritative; a model-generated memory never creates new authority.

### Event-driven writer

Consume committed DSH evidence with a durable cursor. Do not launch extraction for every message/token/tool call. Normalize supported events through the pinned DSH adapter; event names in this PRD are product concepts, not assumed native API names.

| Trigger | Immediate durable action | Extraction work |
|---|---|---|
| Tool completion | Persist/identify evidence | Usually none |
| Phase boundary | Save working checkpoint | Batch candidate facts if useful |
| Independently verified fix | Bind patch and test evidence | Candidate repair procedure |
| User correction | Apply active constraint and mark affected claims | Append correction with source provenance |
| Before model switch/compaction | Freeze handoff and pending actions | Optional extraction, never required to preserve raw checkpoint |
| Task completion | Final evidence bundle | Decisions and candidate reusable lessons |
| Repeated failure | Error signature and attempts | Retrieve similar experience; propose bounded diagnosis |

Default debounce 45 seconds within a configurable 30–60 second starting range. Coalesce nearby triggers, with idempotency based on source event range/digest plus extractor version. Recover after crashes without duplicate promotions. Store cursor progress transactionally with queued extraction work. Detect source-log gaps/rotation and report capture degradation.

Use the existing endpoint at idle priority. One GPU worker by default; background extraction must not evict the active coding model or monopolize its request queue. Cap batch size/output, queue depth, retries and writer spend. At the queue limit, coalesce or pause extraction and expose backlog; never silently discard critical corrections or checkpoints. Coding continues with explicit memory-degraded status if optional extraction fails. Corrections apply immediately, even while durable distillation is pending.

Writer output is schema-validated untrusted proposal data. Reject invented citations, invalid event references, unsupported verification labels, secrets and instruction/policy overrides. No direct writer access to promotion flags or protected policy. Do not store private chain-of-thought.

### Retrieval and injection

Begin with metadata filters, exact error signatures and keyword search. Embeddings are optional after measured need. Filter repository/access scope and lifecycle before ranking. Cross-project transfer defaults to reviewed export of a generalized procedure, excluding source-project secrets and accidental identifiers.

Retrieve at task start, unexpected failure, subsystem change and material correction. Default budget 1,500 tokens with target-model tokenizer accounting where available; otherwise use a conservative documented estimate. Budget is configurable. Retrieve record IDs, short claims, applicability and evidence pointers; fetch details on demand. Deduplicate by memory ID and revision. Include updated corrections even if an older revision was already injected.

Inject through the verified DSH session mechanism and retain reconstructable memory IDs, revisions, rendered content digest and source snapshot in durable events. Memory is quoted evidence with explicit provenance and authority limits, even if the transport uses a user-role message. Do not continuously rewrite the system prompt or AGENTS.md. Stable prefixes are a design aim, not a guarantee of engine cache reuse.

If current instructions conflict with recalled content, current applicable authority wins and the conflict is recorded. Unresolved material factual contradictions trigger rechecking, not silent selection. Retrieval failure falls back to ordinary repository inspection; it never manufactures remembered facts.

### Portability, indexes and data lifecycle

Provide schema-versioned JSONL export/import with record/revision IDs, scopes, provenance and a digest manifest. Validate size, types, paths and references; imported content is untrusted and cannot promote itself. Default imported procedures to unqualified until source provenance and applicable verification are established. Deduplicate IDs/revisions and reject conflicting content under the same identity.

Changing the coding model does not require changing the embedding model. For an embedding-model change, rebuild a separate index from canonical records, validate retrieval, then atomically switch the index pointer; retain rollback. Never mix incompatible vector spaces. Include embedding version, dimensions, preprocessing and index schema in its fingerprint. Index corruption must not destroy canonical records.

Configure retention and deletion explicitly. Secret removal must reach raw evidence, memories, exports under toolchain control and derived indexes; prevent future retrieval immediately with tombstones while purge completes. Append-only operational history does not justify retaining exposed secrets forever: retain non-sensitive audit metadata after an authorized purge. Apply appropriate filesystem access controls and minimize content sent to any remote writer/frontier endpoint under existing egress policy.

### Hy-Memory option

Implement a narrow writer/retrieval backend interface, not a mandatory Hy-Memory dependency. First establish a structured extraction baseline with the current model. Evaluate Hy-Memory only against that baseline using the same canonical format and protected tasks. Evaluate a dedicated memory writer only if extraction quality is a measured bottleneck and its total latency/resource cost is acceptable. No second large model deployment by default. Confirm backend license, interfaces and storage/egress behavior before adoption.

## 12B. Model-switch qualification and handoff

Use a versioned profile identity covering model artifact/provider revision, quantisation, engine build, tokenizer/chat/tool template, context/output limits, reasoning controls and relevant sampling parameters. An alias alone is insufficient. For providers without immutable revisions, record the advertised identity and date and explicitly limit reproducibility claims.

Model-switch states: `requested -> quiescing -> checkpointed -> probing -> qualified -> activated`. On failure: blocked or rolled_back. Switching is distinct from arbitrary per-request routing. Only one controller may activate a profile; retain an auditable switch transaction ID.

1. Stop admitting new worker actions and reach a safe tool boundary. Finish/cancel pending tools and reconcile unknown external requests. Never replay side effects merely because the model changed.
2. Freeze a neutral checkpoint: task contract, repo/base revision, current patch/digest, completed verification, unresolved hypotheses, next action, memory snapshot/revisions, cumulative budgets and pending action ledger.
3. Register the candidate profile and probe endpoint health, instruction loading, tool roundtrip, structured output, cancellation and context fit.
4. Construct fresh compatible context from stable instructions, checkpoint and applicable memories. Do not blindly copy provider-specific reasoning blocks, malformed tool history or model-specific control tokens.
5. Run a predefined representative qualification suite and integrity gates. Mark model-specific lessons/routing unqualified until tested; retain them as historical evidence.
6. Activate only after policy/review gates pass. Record old/new profiles and handoff digest. Start a new DSH session lineage if in-place switching is not demonstrably compatible.
7. Confirm first-task health, preserve the previous qualified profile and support explicit rollback. Rollback preserves new evidence but does not activate unqualified candidate-specific memories.

Never transfer KV caches, recurrent model state or engine checkpoints between different model profiles unless a separately implemented exact-compatibility gate proves support. Default to cache rebuild. Do not claim that architectural similarity makes caches portable.

The initial transfer pilot requires two actual available profiles. If only one is available, complete deterministic adapter tests and mark live cross-model qualification BLOCKED; do not fake a future model or claim cross-family readiness. Do not download huge models or stop unrelated services without existing authorization and capacity checks.

New CLI proposals: `memory query`, `memory inspect ID`, `memory export`, `memory import --dry-run`, `memory revalidate`, `model register PROFILE`, `model qualify PROFILE`, `model switch PROFILE --run RUN_ID`, and `model rollback SWITCH_ID`. Specify argument/error contracts during RA-016/021. Imports, activation and rollback are separate deliberate actions. Tools expose only scoped memory to the worker; admin operations remain outside its authority.

## 12C. Memory and transfer evaluation

Extend Section 11 with paired memory conditions: no cross-session memory; facts/checkpoints only; verified procedures; and optional candidate backend. Use fixed snapshots for offline comparisons. During a comparison, do not let one arm contaminate another through writes; use per-run branches or read-only snapshots. Separate online sequential-learning experiments from static retrieval tests.

Cross-model matrix: old model memory-off/on; new model memory-off; new model with portable knowledge; new model with explicitly tested old model-specific strategies; new model with newly qualified strategies. The old-strategy arm is an isolated experiment, never default production activation. Record model differences as intentional variables rather than labeling all reports non-comparable; require identical tasks, grading and memory snapshots for the intended contrast, and clearly distinguish transfer studies from same-model harness studies.

Use held-out variants from recurring real failures, split by issue family. Include stale facts, contradictory instructions, malicious retrieved text, missing evidence, project-scope collisions, repo renames/forks, changed embeddings, extraction crashes and live model-switch interruptions. Improvement claims require task-level evidence and uncertainty; small pilots can remain inconclusive.

Metrics: verified completion, recurrence of known errors, stale-memory-caused failures, unsupported claims, scope leakage, retrieval relevance on a labeled subset, correction propagation, extraction latency, injected tokens, total writer/retrieval/worker/frontier cost, and cost per verified task. Preserve negative outcomes. No causal claim merely because a memory was retrieved on a successful run.

Promotion requires no critical integrity or scope leakage, no unacceptable quality regression and a predeclared benefit target supported by the sample. The memory store records evidence; the independent evaluator assesses benefit; authorized review decides deployment.


## 12D. CLM-style working-context management

### Goal and terminology

Improve end-to-end verified task completion time and cost by controlling what the next model invocation reads. CLM means Context Language Models: the agent participates in editing its next working input. This PRD specifies a bounded, validated adaptation rather than unrestricted edits to all instructions. CML means Context Mark Language, a separate markup syntax; it is optional under RA-030.

Context editing is neither model weight training nor a raw decode-kernel optimisation. Benefits may come from reduced repeated input processing, less irrelevant context and fewer lost requirements. Costs include edit generation, validation, archive access and cache invalidation. All are measured.

### Layers and authority

| Layer | Owner | Contract |
|---|---|---|
| Session evidence | DSH persistence | Preserve original actions and results under retention policy |
| Working-context revisions | DSH adapter/controller | Commit the exact validated projection used for model invocation |
| Durable knowledge | Minder | Facts, procedures, lifecycle and policy; unchanged by a mere context edit |
| Inference state/cache | Strata or selected engine | Execute full revised input correctly and reuse only compatible state |
| Evaluation | Independent runner | Assess correctness, retained requirements and net performance |

Do not implement hidden truncation or rewriting solely in a proxy: the harness record must reconstruct the actual model-visible request. Trace one real request through projection, rendering, tokenization and engine admission during discovery. Support one context-revision authority per session; disable conflicting compaction writers or serialize them through the same revision transaction.

### Editable context contract

Use typed sections/messages with stable IDs; Markdown may be the model-facing view. Protect applicable system/developer instructions, permission rules, current user requirements, acceptance criteria, active constraints, unresolved tool-call/result structure, pending external actions and budget state. These references remain protected when task state legitimately changes through its controller. The worker cannot designate protected material as ordinary notes.

Editable regions include completed investigation notes, redundant completed tool output, superseded hypotheses and retrieved material no longer needed. A summary preserves source references and distinguishes facts from hypotheses. A referenced artifact is not sufficient when the next action requires its actual details; support on-demand restoration with scope checks.

Proposed operations: replace an editable section, archive a completed span with an evidence-linked summary, restore an archived span, or append bounded working notes. No arbitrary filesystem execution or mutation of the canonical event log through this interface.

Every proposal carries:

```yaml
context_edit_schema_version: 1
session_id: '<session>'
base_context_revision: 12
base_input_digest: '<digest>'
operations:
  - operation: archive_with_summary
    target_ids: [completed-tool-span-17]
    source_event_ids: [event-81, event-82]
    summary: '<bounded factual summary>'
reason_code: completed_phase
producer_profile: '<qualified model profile>'
```

The controller validates scope, source existence, protected-section preservation, message/tool pairing, schema, model template constraints and token budget. Validate using actual rendered token counts where possible. An approximate estimate must be labeled and conservative; engine admission remains authoritative.

Commit an archive snapshot and accepted revision atomically before the next request. Record operation diff, base/result digests, archive IDs, model/rendering identity and validation result. Reject stale revisions via compare-and-swap. A failed validation leaves the active revision unchanged. A crash between archive and activation must recover to one unambiguous committed revision. Never edit while a conflicting generation/tool admission is in flight.

Rollback restores the context projection and recomputes/reuses valid engine state. It never reverses real external actions or replays them implicitly. Accepted code patches and task budgets retain their own authoritative state.

### Scheduling and cost control

Start in observe_only: generate bounded proposals and measure what would change without applying them. Enable validated_edits only after integrity and quality tests. Trigger at phase completion, material redundancy, or pressure against the actual input budget after reserving output/tool overhead. Do not edit every message and do not fill the entire context limit merely because it is available.

Default maximum one edit proposal per checkpoint, charged to the task budget. Use cooldown/hysteresis configured from measurements to avoid repeated shrink/restore cycles. Record why an edit was scheduled and its realized cost. Prefer bounded changes preserving a useful stable prefix, but allow earlier edits when their measured benefit exceeds replay cost.

Decision metric: expected future processing saved minus edit generation, validation, restore and replay costs. This is a scheduling hypothesis, not a promise. Keep an off switch and full-input fallback; short tasks should normally avoid unnecessary editing.

### Memory and model-switch interaction

Archiving a span does not promote it to long-term memory. Candidate lesson extraction remains subject to Sections 12A–12C. Retiring a durable memory does not erase original execution evidence; corrections propagate to the next projection and invalidate stale injected revisions.

A model handoff includes the committed context revision, archive manifest, task checkpoint, memory snapshot and pending action ledger. Re-render for the new template/tokenizer and qualify context-edit behavior separately from ordinary coding. Protect the same requirements across models, but do not transfer the previous model's preferred compression frequency or editing prompts as proven settings. Never reuse old-model KV or hybrid state by virtue of a shared context digest.

## 12E. Exact-first engine execution and cache reuse

First establish correctness using complete revised input with full recomputation. Existing standard chat APIs are preferred where sufficient. Cache diagnostics/revision extensions are optional and capability-negotiated; proposed fields are not claims about existing Strata support.

RA-028 must deliver discovery, capability negotiation, reference replay and a validated fallback. Implement new engine checkpoint optimisations only after a measured bottleneck and source audit justify them. If hardware or compatible execution is unavailable, mark engine optimisation unverified and retain the full-recomputation path; do not claim a speedup.

### Exact reuse rules

1. Render/tokenize with the actual model, tokenizer, chat template and reasoning settings. Find the first divergent token against the cached request.
2. Select a valid checkpoint at or before divergence with the same prefix and compatible execution identity. Revision labels or equal text alone are insufficient.
3. Inventory and restore every sequence-dependent component required by the loaded architecture: attention KV, recurrent/convolution history, positions, indexer/token-history state and speculative state where present. Do not hard-code assumptions from another Qwen generation.
4. Validate KV cell lifetimes and branch ownership as well as checkpoint metadata. A state snapshot pointing to overwritten shared KV is invalid.
5. Replay from the common safe boundary through the revised suffix, including text that is unchanged after an earlier edit. Commit only after successful execution.
6. On mismatch, missing state, cancellation or stale ownership, reset/recompute or restore an earlier proven checkpoint. Never silently continue with partial restored state.

Include prefill chunk plan/kernel/runtime identity where it affects numerical equivalence. Preserve safe ownership of asynchronous expert work; obsolete/cancelled activation results cannot publish into restored state. Serialize requests sharing an incompatible state arena.

Exact here means no deliberately stale representations or approximate suffix reuse. Define numerical acceptance tolerances before testing and report kernel/chunk-induced nondeterminism; do not promise bitwise equality without evidence. Compare fresh and restored execution on identical revised token inputs, checking logits/state where available and downstream outcomes.

Checkpoint memory competes with expert residency, KV and scratch space. Bound checkpoint count/bytes and measure copy/restore costs, GPU/host pressure and decode regressions. Keep the existing single-GPU ownership model. Use enable-strata-clm for engine state/reuse work and port-strata-hip only for actual HIP implementation; do not edit generated translation output outside the fork's source-of-truth process.

### Approximation exclusion

Approximate suffix-cache reuse is disabled in v1.2. Unchanged suffix text can depend on the old prefix; position correction alone is insufficient, and recurrent layers need separate treatment. Any later experiment requires opt-in, clearly labeled approximation, per-architecture validation, independent quality gates and exact-mode fallback. Do not copy another engine's cache machinery and assume compatibility.

## 12F. Context performance evaluation and optional CML

Separate two experiments:

- Context-policy experiment: compare original handling, checkpoint summarization, memory retrieval without editing, and memory plus validated edits on the same task families.
- Engine-reuse experiment: freeze identical revised token inputs and compare fresh recomputation with exact reuse. This isolates engine reuse from changes in task difficulty or context content.

Use short, medium and long tasks; multiple edit positions; repeated archive/restore; changing requirements; cancellation; session concurrency rejection; model switches; and delayed retrieval of archived evidence. Freeze memory snapshots and graders per Section 12C. Hold out issue families and report per-model results.

Metrics: independently verified completion, lost/contradicted requirements, false completion, total task time/cost, first-token latency after revision, edit/validation/archive overhead, processed versus reused tokens from actual engine counters, peak memory, checkpoint bytes/copy time, and accepted output throughput under a fixed context workload. Missing counters are unknown, not inferred cache hits. Shorter prompts or faster first-token latency do not establish faster same-context token arithmetic.

Predeclare quality tolerances and desired net benefit. Integrity violations block activation. A candidate with no defensible benefit remains off or limited to demonstrated task classes. Research benchmark gains are not acceptance targets for the user's quantised model/hardware.

RA-030 optionally compares CML markup against Markdown/JSON rendering over identical canonical content. Test escaping/parser roundtrip, actual token counts for each target tokenizer, model comprehension and verified task outcomes. Keep canonical schemas unchanged. Do not promote a custom syntax based on character count alone; retain the baseline renderer and do not require CML for v1.2 release.

### Research implementation boundary

The referenced Context Language Models repository declares CC BY-NC 4.0 in the source checked during this conversation. For commercial Minder work, do not assume its code is a permissive dependency. Recheck the actual license/NOTICE before reuse; implement the approved design independently or obtain appropriate permission. Keep provenance and attribution records. This does not block implementing the independently specified interfaces and evaluation plan here.


## 12G. Conditional UI/UX planning and aesthetic quality

### Scope and activation

Provide a reusable design workflow for UI projects handled by repo-agent. This does not add a mandatory web frontend to repo-agent or require redesigning Minder. Installing every design skill or browsing every reference is explicitly out of scope.

Evaluate task intent, affected behavior and existing conventions together. File extensions alone are insufficient: a backend change can alter a user-visible error flow, while a frontend build-file change may have no design impact. Record `design_disposition`, rationale, applicable checks and selected skill identities in the task packet.

| Task | Default disposition | Required effort |
|---|---|---|
| Backend, inference, kernel or infrastructure with no interface impact | skip | No design research or visual gate |
| UI copy correction or isolated visual bug | lightweight | Preserve conventions; inspect changed states proportionately |
| New form, table, navigation or interaction | focused | Brief flow/state contract and relevant checks |
| New application interface or substantial redesign | full | UX brief, coherent visual direction, implementation contract and rendered review |
| Landing page, portfolio or editorial site | full | Art direction, typography, composition, content and responsive review |
| Motion-only change | focused_motion | Interaction purpose, input behavior, reduced motion and performance |

A backend task must not be blocked by absent Impeccable, Intent, browser access or a design gallery. A required UI acceptance check cannot be declared passed merely because the optional design-planning mode is off. Existing user preferences and an explicit brief override default aesthetic choices.

Use ask_when_material: ask one compact question only when unresolved alternatives materially change brand expression, user flow, scope or a hard-to-reverse decision. Otherwise choose a reasonable reversible direction and continue. Do not repeatedly ask permission to use a skill. Routine changes do not require a mood board or wireframes.

### Skill and responsibility routing

- `design-resource-router`: select task-relevant guidance/references and preserve the existing system.
- `uiux-workflow`: application flows, forms, tables, navigation, responsive behavior and accessibility.
- `frontend-art-direction`: brand expression, landing pages, portfolios and major composition decisions.
- `ui-motion`: interactions, transitions and reduced-motion behavior when motion is in scope.
- Design with Intent: optional UX strategy, research framing, information architecture, content, accessibility and measurement guidance.
- Impeccable: optional visual execution, hierarchy, typography, spacing, consistency and critique guidance.

Resolve names to actual available skills; website names are not guaranteed registered identifiers. Inspect source, license and installation scope; pin the reviewed revision. Load a small relevant subset. Do not stack overlapping foundational instructions without resolving conflicts. Established project instructions and user requirements remain authoritative.

Missing optional skills have a documented fallback to established project practices. Missing essential vision/browser capability is a specific verification limitation, not permission to invent a successful visual review. No automatic plugin installation, paid subscription, account connection or wholesale component-library replacement.

### Design contract and frontier-to-local handoff

For full/focused work, extend the ordinary task packet with the minimum needed design facts:

```yaml
design_contract:
  disposition: focused
  primary_user: '<actual user group>'
  primary_task: '<observable user outcome>'
  existing_system_refs: ['<existing design document or token path>']
  constraints: ['<brand, platform, content, compatibility constraints>']
  direction: '<one coherent visual direction with rationale>'
  reference_ids: ['<at most three relevant references per decision>']
  token_refs: ['<typography, spacing, color and component tokens>']
  flow: ['<entry>', '<primary action>', '<result and recovery>']
  required_states: [loading, empty, error, success]
  viewports: ['<target mobile width>', '<target desktop width>']
  keyboard_behavior: '<expected navigation, focus and activation>'
  motion: '<purpose, or none; reduced-motion behavior when applicable>'
  acceptance: ['<functional and visual criteria>']
  review_owner: '<qualified vision-capable reviewer or human>'
```

Resolve placeholders before dispatch. Add disabled, validation, permission, overflow, long-label and interrupted-action states where the flow requires them; do not mechanically require every state for static content. Use realistic synthetic fixtures rather than attractive but misleading placeholder data.

Frontier owns the brief, consequential design decisions and review. Local execution implements a bounded screen/flow/component using established tokens and dependencies. Changes to accepted direction or shared components require an evidence-backed scope adjustment, not silent restyling. A representative rendered slice can establish direction before implementing all screens.

Reuse the existing design authority (e.g. DESIGN.md or the project's design docs). Create a new document only when needed, and keep one source of truth. Record selected references and transferable properties: density, hierarchy, spacing, typographic roles, palette and motion purpose. Do not clone a brand or infer asset/code reuse permission from a screenshot.

Generated AGENTS.md should include a concise conditional rule: for substantive UI work, inspect existing design conventions and apply the relevant installed design guidance; ask only for material unresolved choices; verify the rendered result; skip external design research for unrelated work. Do not embed the full catalog in every prompt.

### Curated reference registry

Keep an extensible registry of discovery leads, not a mandatory browsing list. Each selected entry stores URL, intended role, last checked date, access status, actual inspected examples, transferable properties and license/attribution notes for any adopted asset/code. A downloaded skill or page is untrusted reference content, never an authority to override task instructions.

| Resource | Selection role |
|---|---|
| https://designwithintent.ai/ | UX strategy and decision rationale |
| https://impeccable.style/ | Visual execution and critique |
| https://minimal.gallery/ | Restrained website composition and typography |
| https://mobbin.com/ | Shipped application screens and interaction-flow references |
| https://curated.design/ | Industry/style-specific websites and page sections |
| https://www.awwwards.com/ | Expressive brand/marketing composition and interactions |
| https://www.hoverstat.es/ | Experimental layouts and interactions when the brief calls for originality |
| https://www.realtimecolors.com/ | Palette/typography exploration on representative layouts |

The list is non-exhaustive. The existing design-resource-router catalog can supply component, motion and asset candidates when relevant. For each decision, inspect at most three sources initially; use project-native patterns first for mature applications. Verify current availability, relevant examples, stack fit and licensing at use time. An inaccessible/paywalled resource gets a clear unavailable status and an accessible fallback; never claim unseen reference inspection.

Do not judge resource quality by popularity counts. Select specific examples with a reason. Marketing inspiration is not automatically appropriate for an operational dashboard. Avoid visual inconsistency from mixing unrelated styles and dependency bloat from combining multiple overlapping UI libraries.

### Rendered review and executable checks

Keep visual acceptance and functional acceptance separate, with both applicable gates attached to the patch digest. For substantive visual changes, render the actual implementation with controlled fixtures at relevant viewport sizes. Record route, app/build revision, browser, viewport, fixture and screenshot/artifact digest. Re-render after material changes. Screenshot evidence must respect existing data/egress permissions; do not expose sensitive real-user content to a remote reviewer.

A reviewer must actually be able to inspect images. Qualify the frontier or local vision model against representative visual defects before assigning it visual acceptance. If the local coding model is text-only, it can implement and run DOM/browser tests, while a capable frontier or human reviews rendered output. Logs or source inspection do not substitute for seeing the interface.

Review proportional to the task:

- Hierarchy, legibility, spacing, alignment, density, consistent token use and fit to the chosen direction.
- Mobile overflow, long content, text resizing, focus visibility and keyboard navigation.
- Loading, empty, error and recovery flows; truthful status and clear action labels.
- Motion purpose and reduced-motion handling where applicable.
- Browser interaction tests for the primary flow and meaningful failure paths.
- Automated accessibility checks plus targeted manual review; never claim certification from a scanner or screenshot alone.
- Performance and dependency cost when adding heavy imagery, animations or component packages.

Use the existing browser/test tooling where suitable. Missing rendering prerequisites create an explicit unverified visual gate; non-UI work may continue. Visual snapshot differences are evidence to inspect, not an automatic verdict on aesthetic quality. Stabilize fonts, fixtures and animations before snapshot comparisons to reduce noise.

Review results carry criterion, location/state, observed evidence, severity and smallest useful fix. Block concrete functional/accessibility defects or failure to meet accepted design requirements. Treat subjective preferences as advisory unless grounded in the brief. Avoid invented beauty scores, generic “looks modern” judgments or unlimited polish loops. Bound review iterations; escalate unresolved tradeoffs with rendered evidence.

### Memory, context and model switching

Store adopted tokens, project-specific style decisions, reference provenance and user preferences with repository/brand scope. A successful aesthetic in one repo must not become a global style rule. Keep bulky reference galleries out of working context; provide selected properties and artifact pointers. Preserve active design acceptance criteria during CLM context edits. Recheck stale references, assets and tokens when their dependencies change.

Model-switch qualification distinguishes coding, visual inspection and UX reasoning capabilities. Do not transfer a vision-review role to a text-only model. Retain project design decisions across switches while requalifying model-specific review prompts and thresholds. A claim that a skill improves aesthetics must be evaluated using comparable briefs and rendered results, not merely whether the skill was loaded.

### Design workflow evaluation

Provide fixtures for backend skip, routine UI fix, new form flow, dense dashboard, landing page, motion change and mature design-system preservation. Include inaccessible references, absent optional skills, a text-only worker, long/localized labels, injected design instructions and a changed render after review.

Metrics: correct routing/skip decisions, preservation of the existing system, primary-flow completion, concrete accessibility defects, responsive failures, unnecessary dependency additions, review rework, latency/cost, and brief-aligned visual review. Evaluate meaningful choices with blinded comparison when feasible and record reviewer disagreement. Do not generalize an aesthetic score across unrelated brands or user groups.

The product must support this workflow; individual tasks need only their applicable gates. Intent/Impeccable adoption is optional and can be rejected when it adds cost without useful improvement.

## 13. Implementation backlog and frontier gates

Execute in dependency order. The frontier fills actual paths and revisions into each task packet before delegation.

| ID | Owner / dependency | Deliverable | Acceptance and evidence |
|---|---|---|---|
| RA-000 | Frontier / none | discovery.md, pinned compatibility record and architecture decision | Real DSH commands/profile and model probe verified; dirty work preserved; unknowns explicit |
| RA-001 | Local / 000 | Minimal package and CLI skeleton | Existing conventions reused; help/JSON/error exit contracts work; no speculative services |
| RA-002 | Local / 001 | YAML schema and effective config | Reject duplicates/unknowns/traversal/unsafe tags; valid roundtrip; no execution during parsing |
| RA-003 | Local / 002 | Deterministic renderer and drift command | Stable bytes; scoped guidance retained; check mode read-only; notes untouched |
| RA-004 | Local / 002 | Read-only inspector and bootstrap proposals | Sources cited; conflicts exposed; mature migration preserves instructions and edits |
| RA-005 | Frontier design, local implementation / 001 | Durable state/event journal | Crash/resume, locking, duplicate events and invalid transitions tested |
| RA-006 | Frontier-led / 000,005 | Contained worker and protected verifier vertical slice using a fake worker | Canary write/egress denied; forged result rejected; patch-to-result binding verified |
| RA-007 | Local with frontier review / 005,006 | Pinned DSH adapter and model doctor | Real harmless session start/resume/cancel; instruction and tool roundtrip confirmed |
| RA-008 | Local / 007 | Task packets and evidence bundles | Exact base/workspace identity; bounded retries; complete handoff; no premature accepted state |
| RA-009 | Local with frontier review / 008 | Minder adapter | Idempotent events; stale decision rejected; telemetry outage degraded; required policy outage blocks |
| RA-010 | Frontier test design, local implementation / 006,008 | Independent evaluator and integrity regressions | Works without Minder; hidden tests inaccessible; changed patch invalidates results |
| RA-011 | Local / 003,004,010 | CI checks and packaging | Fresh install outside source checkout includes schemas/templates; drift check and required tests run |
| RA-012 | Frontier / 007–011 | Live new-repo and mature-repo pilots | Both complete real tasks; resume exercised; user edits preserved; rollback demonstrated |
| RA-013 | Frontier plans, local executes / 012 | 30-task pilot and configuration comparison | Full run manifest; failures retained; cost includes all stages; uncertainty explicit |
| RA-014 | Local / 013 | Lesson proposal and paired evaluation command | Proposal cannot activate itself; held-out data protected; rollback retained |
| RA-015 | Frontier / 012–014,023,029,035 | Final v1.3 release report and rollout | G0–G7 pass; earlier partial releases labeled separately; task-specific design gates remain conditional |
| RA-016 | Frontier contract, local implementation / 002,005,009 | Canonical memory schema and Minder migrations | Producer/applicability separated; migration/rollback; scopes and revisions preserved |
| RA-017 | Local / 016,007 | Durable event cursor and checkpoint writer | Crash replay idempotent; corrections immediate; source gaps visible; queue bounded |
| RA-018 | Local / 017,010 | Candidate extraction and lifecycle | Evidence references validated; unsupported promotion rejected; idle-priority resource limits |
| RA-019 | Local with frontier review / 016,017,007 | Scoped retrieval and reconstructable injection | Budget/dedup enforced; stale claims filtered; no cross-project leak or policy override |
| RA-020 | Local / 016,019 | Export/import, invalidation and index lifecycle | Roundtrip identities; untrusted imports quarantined; purge/reindex and rollback tested |
| RA-021 | Frontier-led / 007,008,016,017 | Profile registry and neutral model handoff | Pending actions reconciled; cache transfer denied; failed switch restores qualified profile |
| RA-022 | Local executes, frontier reviews / 018–021,010 | Live memory/transfer pilots | Two real profiles tested or explicitly blocked; interruption and contradictions covered |
| RA-023 | Frontier / 013,014,022 | Paired memory and transfer evaluation | Isolated arms, frozen snapshots, full costs and honest uncertainty; promotion decision recorded |
| RA-024 | Frontier contract, local implementation / 005,008,017 | Context revisions, typed sections and protected policy | Reconstruction and compare-and-swap; protected sections immutable; atomic recovery |
| RA-025 | Local with frontier review / 024,007 | DSH context-edit adapter | Real request matches committed projection; tool pairing valid; stale/conflicting edits rejected |
| RA-026 | Local / 025,019,020 | Archive/restore and Minder references | Evidence recoverable; scope filters and correction propagation; no automatic lesson promotion |
| RA-027 | Local / 025,026 | Bounded scheduler and observe-only mode | One proposal/checkpoint default; overhead charged; no edit/restore loop; short-task bypass |
| RA-028 | Frontier-led engine review, bounded local tasks / 025,010 | Engine capability negotiation, fresh replay reference and exact reuse where supported | Actual token-prefix/state compatibility; failed restore falls back; unverified optimisations explicitly blocked |
| RA-029 | Frontier designs, local executes / 023,026–028 | Context-policy and fixed-input engine comparisons | Quality/integrity protected; total cost and cache rebuild included; per-model activation decision |
| RA-030 | Optional, frontier-reviewed / 029 | CML representation experiment | Same content, parser/escaping and tokenization tests; must beat baseline on useful outcomes |
| RA-031 | Local with frontier review / 002,004,008 | Conditional design routing and instruction generation | Backend skips; small fixes lightweight; material decisions routed; optional skill absence handled |
| RA-032 | Frontier contract, local implementation / 031 | Design-contract generator and worker packet extension | Existing tokens/docs reused; functional and visual acceptance explicit; no unresolved placeholders |
| RA-033 | Local / 031 | Curated reference registry and bounded selection | Sources/access/licensing tracked; max-three initial shortlist; unavailable source never presented as inspected |
| RA-034 | Frontier review design, local implementation / 032,033,010 | Rendered review and browser-check evidence adapter | Actual screenshots tied to build/patch; vision capability qualified; meaningful flow/state tests |
| RA-035 | Frontier designs, local executes / 031–034 | UI/UX routing, quality and proportionality evals | Backend no-op, mature-system preservation and UI fixtures pass; full costs and reviewer limits recorded |

### Milestone gates

G0 Discovery: no guessed APIs, exact local environment identified.

G1 Repo contract (RA-001–004): new/mature bootstrap and deterministic instructions work without a model.

G2 Safe execution (RA-005–008): a fake worker and one live local DSH worker complete the lifecycle with containment and recovery evidence.

G3 Supervised execution (RA-009–012): Minder integration, independent evaluator, installation and two real pilots pass.

G4 Measured improvement (RA-013–014): comparisons and candidate learning are reproducible; production promotion remains explicitly reviewed.

G5 Portable memory and model switching (RA-016–023): canonical memory, event-driven writing, scoped retrieval, export/invalidation, live qualification and transfer evaluation meet Sections 12A–12C. RA-015 closes the full v1.3 release after G7. Schedule RA-016/017/021 foundations after their dependencies, alongside the core release work; defer expensive extraction/evaluation until verification works.

G6 Context management (RA-024–029): validated revision/restore behavior, model-qualified edit policy, full-input fallback, and separate context/engine evaluations are complete. Measured optimisations may remain disabled when inconclusive; a successful release does not require inventing a speedup. RA-030 and approximate suffix reuse are not release requirements.

G7 Conditional design support (RA-031–035): routing, design contracts, reference selection, rendered review and evaluation work, including an explicit skip path for non-UI tasks. Required toolchain support does not make design research or external skills mandatory on every task. This workstream can proceed once its own dependencies are ready; it does not depend on optional CML experiments.

Do not delay G1–G3 to build a large benchmark dashboard or learning subsystem. If the evaluation pilot finds no benefit from a component, retain the simpler working configuration and report the result.

## 14. Required acceptance scenarios

| Scenario | Expected result |
|---|---|
| Dirty mature repo with an existing AGENTS.md | Proposal preserves unrelated changes and instruction content |
| Repo contains a malicious setup command | Inspect/render never execute it |
| YAML contains duplicate keys or escaping symlinks | Explicit validation rejection |
| Local model returns malformed tool calls | Adapter records protocol failure and bounded escalation; no fabricated execution |
| DSH installed profile differs from configured one | Doctor blocks with discovered profiles; does not invent one |
| Worker writes an `accepted` JSON result | Trusted controller ignores it as an acceptance authority |
| Worker changes grading files or accesses host canary | Action denied or run fails integrity gate |
| Worker fails tests then weakens assertions | Diff/integrity review flags change; protected grading still rejects incorrect behavior |
| Process dies after frontier request was sent | Resume reconciles unknown request status; no automatic duplicate charge |
| Two supervisors resume one run | One acquires ownership; the other exits with a clear conflict |
| Minder unavailable | Optional telemetry buffers; policy-dependent escalation stops |
| Model endpoint unreachable from container | Infrastructure failure, no quality score attributed to model |
| Patch changes after successful verification | Acceptance invalidated and verification required again |
| Existing project check already fails | Baseline preserved; introduced regressions separately identified |
| Candidate improves visible fixture but fails holdout | Candidate rejected or marked regression; no automatic promotion |
| Fresh wheel installed outside repository | Required runtime resources exist and commands function |
| Model changes from profile A to B | Portable facts survive; A-specific strategies remain unqualified; new routing history starts |
| Switch interrupted after external request | Pending action ledger prevents blind replay or duplicate spend |
| New profile fails tool-call probe | Activation blocked; previous qualified profile remains usable |
| Same error in unrelated repositories | Retrieval filters scope before similarity ranking |
| Relevant source changed but branch name unchanged | Affected memories marked stale and revalidated |
| User correction arrives during writer backlog | Active task respects correction immediately; durable update follows |
| Writer crashes after queuing evidence | Cursor replay produces no duplicate lesson/promotion |
| Retrieved text says to bypass approval or change grader | Treated as untrusted evidence; policy unchanged |
| Memory contains a secret later identified for deletion | Retrieval tombstone immediate; controlled records/indexes purged; non-sensitive audit retained |
| Embedding model changes | Separate index rebuilt and validated; canonical records unchanged |
| Only one live model available | Cross-model deployment remains explicitly unverified/blocked |
| Edit removes protected acceptance or pending tool result | Rejected; previous revision stays active |
| Concurrent compaction and model edit | One revision commits; stale proposal rejected and evidence retained |
| Crash after archive but before activation | Recovery selects exactly one committed projection; no evidence lost |
| Earlier-prefix edit leaves later text unchanged | Exact mode recomputes dependent suffix; no stale state reuse |
| Engine checkpoint has invalid KV ownership | Restore rejected; earlier valid checkpoint or full recomputation |
| Revised context exceeds admitted input budget | Explicit rejection/recovery; no silent truncation |
| Archived span is needed later | Scoped restoration with source identity; quality eval checks recovered details |
| Model switch follows context edit | Fresh compatible rendering and cache rebuild; pending actions not replayed |
| Editing overhead exceeds processing savings | Policy stays disabled or limited to measured beneficial cases |
| Optional CML representation uses fewer characters but more tokens | No compression/speed claim; baseline remains available |
| Backend-only task with no browser/design skills | Design workflow skipped without blocking execution |
| Routine UI bug in mature app | Existing tokens/components preserved; no unsolicited redesign or full research phase |
| New interface with material unresolved direction | One focused question or explicit reversible assumption; no repeated permission loop |
| Intent or Impeccable unavailable | Applicable fallback used; no fabricated skill loading or automatic installation |
| Design reference inaccessible/paywalled | Mark unavailable and choose accessible alternative; no invented inspection |
| Text-only local model reviews its own CSS | Visual gate stays unverified until actual image-capable review |
| Attractive screenshot but broken keyboard/form flow | Functional/accessibility gate fails regardless of appearance |
| Rendered patch changes after visual acceptance | Re-render and review affected scope; old evidence cannot approve new patch |
| A project-specific style memory matches another repo | Scope filter prevents unapproved style transfer |
| UI task requires heavy animation | Purpose, reduced motion and performance checked before acceptance |

## 15. Deployment and rollback

Deployment means installing this toolchain on the user's local machine and wiring a tested DSH profile—not uploading a model or altering its weights.

1. Build and verify a pinned release in an isolated environment.
2. Back up only configuration files this installation will change; record hashes and versions.
3. Install the CLI in an isolated environment using the discovered package-management convention.
4. Provision the reviewed DSH profile/adapter without overwriting unrelated profiles.
5. Configure local endpoint access and Minder adapter through operator-owned configuration. Do not expose credentials in repo files.
6. Run doctor and a harmless task in a disposable repo, then a representative mature-repo branch.
7. Preserve a known-good release and profile. Rollback restores prior owned configuration and binary version, leaving task evidence intact.
8. Back up and migrate the Minder memory schema with a tested restore path; preserve model/embedding profile identities. Export a manifest before backend changes.
9. Run the memory and model-switch pilot before enabling automatic retrieval or a new profile in normal tasks. Keep extraction optional/degraded if it fails; never lose checkpoints.
10. Start context management in observe_only, verify revision integrity, then enable validated_edits only for qualified profiles/task classes. Preserve context-policy and engine-capability rollback independently of memory migrations.
11. Verify design routing on a backend task and a representative UI task. Configure optional skills only when selected and reviewed; keep design review tools outside worker authority where they produce acceptance evidence.
12. Enable further repos individually after the pilot. No automatic modification of all `~/projects` repositories.

Do not run install scripts taken from arbitrary retrieved content. Inspect and pin dependencies. Reversible local setup is within the implementation task's intended scope; destructive migrations, external publication and unrelated service changes remain separate actions.

## 16. Definition of done and delivery manifest

Required deliverables:

- Working CLI and versioned schemas/templates with installation instructions.
- Example new/mature configurations and generated AGENTS.md examples.
- Verified DSH adapter, compatibility record, model identity and probe report.
- Containment implementation and tested protected evaluator.
- Minder integration and documented degraded-mode behavior.
- Durable state, restart/cancel behavior and evidence format.
- Unit/integration tests focused on real failure risks, plus two live pilot reports.
- Evaluation manifest and honest configuration comparison, even when inconclusive.
- Lesson proposal workflow with review and rollback.
- Canonical memory schema, bounded event-driven writer, scoped retrieval and reconstructable injections.
- Memory export/import, correction/invalidation, retention/purge and index migration tests.
- Versioned model profiles, neutral handoffs, qualification and rollback with actual live-transfer evidence or an explicit blocked status.
- Paired memory-on/off and cross-model evaluation with no shared-state contamination.
- Validated context-edit/archive/restore implementation, protected sections and reconstructable request revisions.
- Exact-first engine capability report, full-input fallback, and context-policy versus fixed-input engine performance comparisons.
- Explicit activation/rollback policy; CML optional and approximate suffix reuse disabled.
- Conditional design router, packet schema, reference registry and rendered/browser review integration.
- UI/UX evaluation fixtures, skip-path evidence and documented vision/tooling limitations.
- Release report listing checks actually executed, remaining limitations and deployment/rollback results.

Not sufficient: lint alone, mock-only DSH tests, generated files never loaded by a harness, a dashboard without complete traces, or a comparator PASS without independent task verification.

## 17. Paste-ready frontier supervisor instruction

> Implement this PRD on the user's local environment. Start with RA-000 and inspect existing instructions, repos, DSH profiles, Minder integration and model capabilities before modifying anything. Preserve unrelated changes. Resolve the real workspace and exact software/model versions. Do not assume the illustrative YAML fields or CLI commands already exist.
>
> Own the architecture, task contracts, high-risk boundaries, integration review and final evidence. Delegate bounded implementation tasks to the local Qwen model through the verified DSH interface. Use one local worker at a time by default. Before dispatch, replace all example paths/commits with actual values and load applicable installed skills. Keep acceptance criteria and evaluators outside the worker's control.
>
> Deliver G1–G3 as the first useful release. At each gate inspect the diff and actual test artifacts, then continue autonomously with authorized reversible work. Escalate failures using a minimal reproducer and evidence; do not repeat ineffective prompts. Do not weaken tests or policy to pass a gate. If local execution cannot be verified, mark that portion blocked and complete safe preparatory work without claiming deployment.
>
> Build portable memory and model-switch qualification under Sections 12A–12C and RA-016–023. Preserve user knowledge independently of model identity, keep model-specific strategies unqualified until tested, and never replay uncertain external actions during a switch. Use the existing model endpoint for idle-priority extraction first; Hy-Memory and dedicated writers remain optional evaluated backends. G1–G3 may ship as a clearly labeled core release; do not claim the full v1.3 release until G7 is satisfied.
>
> Implement RA-024–029 under Sections 12D–12F: preserve immutable evidence, validate model-proposed working-context edits at the DSH boundary, and keep engine execution exact-first with full recomputation fallback. Use enable-strata-clm for engine state/reuse work. Measure total task benefit including editing/cache-rebuild costs; do not equate fewer prompt tokens with faster decode kernels. RA-030 CML markup is optional, approximate suffix reuse stays disabled, and research code licensing must be respected.
>
> Implement conditional design support under Section 12G and RA-031–035. Preserve mature design systems; skip design planning for non-UI tasks and keep routine fixes lightweight. Use design-resource-router and relevant installed skills; Intent/Impeccable and external references remain optional, pinned and task-selected. Hand the local model concrete tokens, flows, states and acceptance criteria. Require actual rendered inspection by a vision-capable reviewer for substantive visual work, alongside functional browser checks. Never call unseen screenshots reviewed or impose one aesthetic on all projects.
>
> Continue through measured evaluation and reviewed lesson proposals. Report what changed, what was actually run, baseline failures, remaining limitations and rollback instructions. Never describe unexecuted checks as passing or a small benchmark as proof of general model capability.

## 18. References and implementation candidates

These references support the design and prior conversation; they are not pinned installation instructions. RA-000 must confirm current interfaces and choose tested revisions.

- Minder reference snapshot: https://github.com/xyzzing/minder/tree/c8038d3924dc6ed33c8d1d3b4e061852bf81c6be
- AGENTS.md format: https://github.com/agentsmd/agents.md
- DSH runtime: https://github.com/deepseek-ai/deepseek-harness
- Harbor evaluation framework: https://github.com/harbor-framework/harbor
- Minimal comparison agent: https://github.com/SWE-agent/mini-swe-agent
- Harness improvement research: https://github.com/google-research/harness2
- Community evidence/skill experiments, inspect before adoption: https://github.com/zhangguiping-xydt/dsh-session-lab

- DSH session/persistence model: https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/session.md
- DSH agent injection/model-selection interfaces: https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent/README.md
- Optional memory backend: https://github.com/Tencent-Hunyuan/Hy-Memory
- Optional dedicated writer: https://huggingface.co/tencent/Hy-Memory-30B-A3B

- CLM research and license/NOTICE: https://github.com/facebookresearch/context-language-models
- Context Language Models paper: https://arxiv.org/abs/2609.37725
- CML markup specification (distinct from CLM): https://doc-war.com/contextmarklanguage/

- Optional UX strategy: https://designwithintent.ai/
- Optional visual execution/critique: https://impeccable.style/
- Website references: https://minimal.gallery/ and https://curated.design/
- Application flow references: https://mobbin.com/
- Expressive/experimental references: https://www.awwwards.com/ and https://www.hoverstat.es/
- Palette/typography exploration: https://www.realtimecolors.com/

Borrow proven interfaces and focused mechanisms. Do not install every listed project or create a new dependency solely because it appears here.
