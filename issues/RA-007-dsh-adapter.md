# RA-007 — Pinned DSH adapter and model doctor

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-007 | Local with frontier review / 005,006 | Pinned DSH adapter and
> model doctor | Real harmless session start/resume/cancel; instruction
> and tool roundtrip confirmed

## Contract

- adapters/dsh.py is the only module that may invoke `dsh` (C-B). It
  implements exactly the RA-000-verified interface: `dsh --profile
  headless [task|-]`, `--json` NDJSON run events, `--session-id <id>`
  resume; cancellation is process-group termination.
- The event parser is tested against events captured live from dsh
  0.2.1-rc.2 (fixtures committed); unknown event types are tolerated and
  recorded; a non-JSON line is a DshParseError quoting the offending line.
- `DSH_BIN` env override exists so tests run a fake dsh; product defaults
  to `dsh`.
- doctor reports: dsh presence/version, headless profile, model endpoint
  health (through the minder proxy), containment probes (podman level
  named), journal writability. `--live` adds a harmless model ping.
  Every check names its status and why; skips are named, never passes.

Status: done — adapter (f10c069) + doctor module via local-worker dispatch; live probe pending in dogfood.
