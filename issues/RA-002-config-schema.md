# RA-002 — YAML schema and effective config

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-002 | Local / 002 | YAML schema and effective config | Reject
> duplicates/unknowns/traversal/unsafe tags; valid roundtrip; no execution
> during parsing

## Contract

- Closed schema mirroring PRD §4 (config_schema.py holds the spec; C4).
- Reject: duplicate keys, unknown fields at any depth, schema_version
  other than 1, unsafe YAML tags, input over 256 KiB, nesting over 5
  levels, non-safe path fields (absolute, `..`, symlink escape), empty or
  non-string argv, `verify` referencing unknown commands, `verify` cycles.
- `effective_config()` returns validated values with defaults applied and
  provenance (source sha256, defaults applied, generator version); JSON
  roundtrip identical.
- Parsing is inert: validation never executes setup/verify commands.

Status: in progress.
