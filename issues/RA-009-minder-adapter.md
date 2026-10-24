# RA-009 — Minder adapter

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-009 | Local with frontier review / 008 | Minder adapter | Idempotent
> events; stale decision rejected; telemetry outage degraded; required
> policy outage blocks

## Discovered surface (verified, not assumed — PRD §9)

Probed read-only against the local minder tree before designing
transport; every claim below was checked in source:

- The minder sink (`sink.py`) is a loopback persistence sidecar: it
  accepts `POST /persist` with `Authorization: Bearer <token>` and the
  op `append_jsonl {name, record}`; `name` must be one of
  `events.jsonl / consults.jsonl / hook-trace.jsonl`; `record` must be
  a JSON object and is appended as one line.
- `minder.report()` reads `events.jsonl` with `json.loads` per line and
  one malformed line silently discards the whole timeline, so records
  must be single-line JSON. Its intervention filter ignores unknown
  event names, so repo-agent emits namespaced `repo_agent_*` events
  that persist in the ledger without polluting minder's own timeline.
- Minder has **no out-of-process decision surface** (the sink is
  persistence + stats only). PRD §9's decision contract is therefore
  satisfied locally and fail-closed: `LocalPolicy` enforces the
  packet's own immutable budget; `RequiredMinderPolicy` exists for
  operators who require an external surface and always blocks rather
  than fail open. PRD §9: "Do not fail open on a budget or permission
  requirement."

## Design

- `repo_agent/adapters/minder.py`:
  - `MinderEvents`: emits namespaced records to the sink; unreachable
    or failing sink → bounded in-file buffer (`buffer_dir`), `degraded`
    surfaced, overflow drops oldest and counts it (never silent).
    `event_id` makes emission idempotent: a replayed id is a
    `duplicate`, not a second sink record.
  - Verification events carry the PRD §9 contract fields inside the
    minder record: `schema_version`, `event_id`, `run_id`, `attempt`,
    `producer: trusted-verifier`, `evidence_ref`, `evidence_sha256`,
    `failure_signature` (failures only).
  - `resolve_evidence`: evidence refs resolve only inside the trusted
    artifact root; traversal, symlink escape, missing files and digest
    mismatches are named rejections.
  - `Decision` / `parse_decision` / `validate_decision`: PRD §9 fields;
    rejects unknown fields, malformed types, unknown actions, expired
    and replayed decisions, and run mismatches. `consult_frontier` is a
    valid external action but the local ladder never emits it.
  - `discover_sink_url`: `REPO_AGENT_MINDER_SINK_URL` env, then
    `MINDER_SINK_URL` env, then an explicit hooks file.
- `taskrun.run_packet(policy=...)`: optional policy gate consulted
  before the first dispatch and at the `needs_evidence` retry point —
  `continue`/`retry_with_evidence` spend, `pause` blocks,
  `stop` fails the run, `consult_frontier` escalates; `PolicyBlocked`
  becomes `TaskBlocked("policy_unavailable")` (CLI exit 3). Policy off
  by default; evaluation runs with Minder disabled (PRD §9).
- HTTP POST joins the sanctioned `adapters/http.py` surface (C-N);
  the minder adapter is the only caller.

## Delivered

- `repo_agent/adapters/minder.py`: sink transport — `MinderEvents`
  (namespaced single-line records, event-id idempotency, bounded
  buffer with dropped count, `status()`/`degraded()`), URL discovery
  (env → hooks.json), token discovery (explicit → env → minder's
  `sink.token`), `telemetry_status` (wired into `doctor`), and
  `resolve_evidence` (§9 artifact validation).
- `repo_agent/adapters/minder_decisions.py`: the decision contract —
  `Decision`, `parse_decision` (untrusted-dict validation),
  `validate_decision` (run mismatch / replay / expiry),
  `RunPolicy` protocol, `LocalPolicy` (packet-budget ladder, journal
  audit), `RequiredMinderPolicy` (fail closed).
- `taskrun.run_packet(policy=..., policy_factory=...)`: the policy
  gate — consulted before the first dispatch and at every
  `needs_evidence` retry point; refusals park the run
  (`stop→failed`, `pause/other→blocked`, `consult_frontier→escalating`);
  `PolicyBlocked` becomes `TaskBlocked("policy_unavailable")` (exit 3).
  Every verdict is emitted as telemetry bound to a written
  `verdict.json` artifact (digest in the event). Off by default.
- CLI: `task run --policy {none,local,required} [--minder-sink URL]`.
- Tests: `tests/test_minder_adapter.py` (19), `tests/test_policy_gate.py` (6).

## Evidence

- tests/test_minder_adapter.py + tests/test_policy_gate.py green
  (25 tests); full suite green excluding the concurrent RA-016/017
  session's in-flight files (memory.py/test_memory*.py), which were
  not part of this work; ratchet holds; mypy clean on changed files;
  proven-red recorded in the PR.

## Remaining (recorded, not hidden)

- Buffered events are exposed, not drained: sink recovery does not
  auto-replay the backlog (drain is a deliberate follow-up).
- The seen-decision ledger is per-process; a persisted replay ledger
  lands with the memory work (RA-016+).
- `pause` maps to the `blocked` state at the retry point:
  `needs_evidence -> paused` is not a legal transition in the journal
  state machine; changing TRANSITIONS is a separate contract decision.
- `consult_frontier` is parsed and mapped (`escalating`) but no local
  policy emits it; an external decision source would arrive with the
  memory/model-switch work (RA-016+).
