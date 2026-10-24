# discovery.md — the RA-000 environment record

RA-000 (PRD §13) requires a pinned compatibility record before any code
is written: real interfaces probed, not inferred from a specification.
This file records the method and the record format. The first run's
host-specific values are deliberately not part of the public tree; fill
in your own copy when you execute RA-000 on your machine.

## Method (read-only except where stated)

Probe and record, in this order:

1. **Harness.** Harness version; every subcommand's `--help` (no
   invented flags); the non-interactive interface; the machine-readable
   event stream (capture one real run's events and pin them as parser
   fixtures); session persistence and resume semantics; cancellation
   semantics (often process-group termination, not a command).
2. **Model endpoint.** Health endpoint and reported model identity; a
   real completion through the full configured chain (proxy included)
   with usage counters; the model list the chain exposes.
3. **Containment candidates.** Container tooling present and rootless?
   (probe with a trivial run, not just `--version`.) Record the
   reference isolation pattern available in your own tooling.
4. **Governing runtime.** The supervisor's version, its event/decision
   surfaces, and which of them are safe to write from an agent context
   (sandbox rules for hooks often differ from the host).
5. **Dirty work.** Uncommitted changes in every touched repository,
   recorded and left untouched.

Every probe is read-only unless the operator explicitly authorizes the
exception; record each exception with who asked for it.

## Record format (fill this in)

- Harness: version, verified non-interactive contract, event schema
  (pinned fixture path), resume/cancel semantics, stderr characteristics
  (progress noise on stderr must never be parsed as events).
- Model: artifact identity and quantisation, engine build, context
  limits, endpoint chain (assistant → proxy → engine), per-request usage
  semantics (one live multi-step dispatch is the evidence; on one
  observed stack, `usage` fields were per-step deltas, not cumulative —
  verify, do not assume).
- Containment: container tooling, rootless confirmation, image pinned
  for verification runs.
- Supervisor surfaces: version, ledger path, decision gateway entry
  point, comparison/grading entry points.
- Findings that change default assumptions, each with the probe that
  produced it.

## Decision record

Record the placement decision (separate repository vs. package in an
existing toolchain repo) with the reason, the PRD section that allows
it, and whether a remote is configured. The default posture for a first
build: local-only, nothing pushed until the operator decides.
