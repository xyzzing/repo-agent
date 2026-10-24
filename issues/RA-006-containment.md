# RA-006 — Contained worker and protected verifier (fake worker)

PRD acceptance lines (docs/prd-v1.3.md §13):

> RA-006 | Frontier-led / 000,005 | Contained worker and protected
> verifier vertical slice using a fake worker | Canary write/egress
> denied; forged result rejected; patch-to-result binding verified

## Containment level tonight (honest)

`isolation_by_construction` for worker and verifier execution: disposable
workspace, HOME/TMPDIR constructed inside it, env allowlist, argv-only
subprocess with process-group kill, and a verifier that rebuilds its
environment from base + a frozen patch it computed itself — worker output
is never acceptance authority. podman is present and rootless on this
host; the container level is the recorded upgrade path (RA-006b), and
podman-driven probes (egress deny, read-only mount) ship as checks a
doctor can run — they are marked with the level that actually enforced
them.

## What is enforced and tested

- Workspace construction: worker HOME/TMPDIR land inside the workspace;
  a fake worker's canary write goes to the workspace, never the host home.
- Patch binding: verdicts bind to the frozen patch digest; any later
  patch mutation invalidates them (re-verification required).
- Grader integrity: graders are injected after patch application; a
  worker-modified grader is a tampering failure, not a passing run.
- Forged results: a worker-written "accepted": true JSON is ignored as
  acceptance authority.
- Containment probes via rootless podman: network-deny and read-only
  mount checks; skipped with a named reason if podman is unavailable.

Status: done — tests/test_verify.py (9 tests incl. live podman probes); container level recorded as RA-006b upgrade path.
