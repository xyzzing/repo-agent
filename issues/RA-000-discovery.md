# RA-000 — Discovery, pinned compatibility record, architecture decision

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-000 | Frontier / none | discovery.md, pinned compatibility record and
> architecture decision | Real DSH commands/profile and model probe
> verified; dirty work preserved; unknowns explicit

## Execution

- Probed live (read-only): dsh 0.2.1-rc.2 help/interfaces, headless profile
  wiring, proxy 8390 + engine 8081 health and a real completion, podman/
  bwrap/unshare presence, minder 0.2 surfaces, GPU-stack identity.
- `systemctl --user start strata-8081` was run once at the owner's explicit
  instruction; no other host state changed.
- Dirty work preserved: the minder tree's uncommitted
  `minder_memory/lessons.py` WIP is untouched.
- Unknowns recorded in discovery.md: dsh `--json` event schema (RA-007),
  podman rootless confirmation (RA-006), dsh 0.2.1 session-layout
  re-verification (RA-007).

## Result

discovery.md committed. Architecture decision: separate repo at
~/projects/repo-agent (PRD §3); no remote during the overnight run.

Status: done.
