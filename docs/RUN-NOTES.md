# Run notes — first build and live measurements

The reference implementation was built in one supervised overnight run,
frontier-supervisor-style: contracts and trust boundaries by the
supervisor, bounded implementation packets dispatched to the local
worker through the harness, every worker claim re-verified by the
supervisor. These notes keep what transfers to other machines; the
host-specific environment record is deliberately not part of this tree
(see discovery.md for the method).

## Measured local-worker dispatches

All dispatches ran through the standard harness headless interface with
the machine's ~3.5-bit local model; frontier-model tokens in these
loops: zero.

| dispatch | task | local tokens | steps | wall | outcome |
|---|---|---|---|---|---|
| inspect module | implement to acceptance tests | 454,814 | 19 | ~10 min | accepted after review; one-file scope violation, recorded |
| doctor module | implement doctor + http adapter | 381,692 | 12 | ~9 min | accepted as-is; scope respected |
| full lifecycle | packet → workspace → worker → protected verdict | 96,667 | 3 | ~2 min | PASS, accepted |
| doctor live probe | six readiness checks against the real stack | 14,679 | 1 | <1 min | all pass |

The binding constraint was packet precision, not model capability. The
worker's observed failure mode was scope drift (helpful edits outside
the packet); pinned write scopes plus review plus the protected
verifier caught every instance.

## Lessons pinned by tests (each was a real failure first)

1. sqlite3 `with conn` commits but never closes: leaked write locks
   stall the journal. Every connection closes explicitly.
2. YAML libraries vary in what they re-export; catch errors from their
   defining submodules, not top-level names that may not exist.
3. SafeLoader-style YAML loaders defer nested construction, so a
   during-parse depth counter reads zero; depth must be walked after
   the parse.
4. Workspace staging must exclude the target's VCS directory: binary
   objects break text patch maps, and a worker that can write history
   can rewrite it.
5. Bookkeeping (journals, work areas) lives outside the target
   repository; a journal inside the target makes every repo dirty by
   its own accounting.
6. Harness stderr is diagnostics, never events; parsers that read it
   will ingest progress noise.
7. Container verification: bind mounts need the platform's container
   label (SELinux :Z) or denials have the wrong cause; the container
   engine must run with the caller's environment (a rewritten HOME
   detaches it from its storage); verification never auto-pulls images.

## Addendum — the memory plane and the lesson lane (post-v0.1.0)

RA-009 through RA-021 landed in one coordinated multi-session push (two
agent sessions on one board; worktree isolation, fast-forward-only
pushes, adopt-don't-clobber — see HANDOFF.md):

- minder adapter: repo-agent events flow into minder's production sink;
  the supervision loop is closed on the evidence side.
- canonical memory with producer labeling and per-model shelving; the
  harvest writer learns from successes (strategy candidates) as well as
  failures; retrieval filters scope before similarity and withholds
  model-specific records from unqualified profiles.
- the lesson lane: propose (never activates) → human-gated promotion →
  paired-arms evaluation reporting PRD §11 vocabulary with n=1 always
  flagged insufficient.
- profile registry: qualification against pinned suites flips
  visibility — the mechanism that makes a model switch (e.g. serving a
  different model through the same engine) a registration rather than
  a fork.

Measured in this phase: live-sink probe verified in minder's
production ledger; both RA-012 live pilots PASS (new-repo and
mature-repo, resume and rollback demonstrated).
