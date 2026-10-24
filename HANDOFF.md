# HANDOFF — repo-agent

Updated 2026-10-25. Scope: everything since the v0.1.0 public release.
Read this before touching the repo; the parallel-session protocol below
is load-bearing.

## State

- Internal main (origin, private repo `xyzzing/repo-agent-internal`) =
  `a5aa741` — RA-019 scoped retrieval + reconstructable injection.
  198 tests, mypy clean over 22 files, ruff clean, ratchet at baseline.
- Working tree is on `ra-013-eval-pilot` (`4b6c0a1`, RA-013 comparison
  tooling) — the parallel session's active branch; do not disturb.
  `ra-012-live-pilots` (`17f5dec`) holds the completed RA-012 pilots:
  **both live new-repo and mature-repo pilots PASS, resume and rollback
  demonstrated.**
- Public repo `xyzzing/repo-agent` is still v0.1.0; internal has
  advanced by RA-009 through RA-019 plus RA-010/011/012/013. Next
  public release is v0.2.0 (scrub + orphan-publish, see plan).

## Landed since v0.1.0

| Increment | What exists |
|---|---|
| RA-009 minder adapter | `adapters/minder.py` + `minder_decisions.py`: namespaced `repo_agent_*` events via minder's sink (Bearer, `append_jsonl`), bounded local buffer when unreachable, local fail-closed policy (minder has NO out-of-process decision surface — verified; minder issue #41 requests the seam). Doctor gains `minder_telemetry` (skip-with-reason, never fail). Live-verified: one probe record sits in minder's production `events.jsonl`. |
| RA-016/017 memory | `memory.py`: append-only canonical records, code-controlled lifecycle (`candidate → evidence_checked → locally_verified → reusable`), parallel flags, per-kind floors, citation checks against the journal (invented `source_event_ids` are rejections). `memory_writer.py`: harvest behind a durable per-run cursor committed in the SAME transaction as its candidates (record() inside that tx deadlocks). Accepted runs yield a verified_procedure candidate PLUS a strategy candidate — the approach that verified, not only failures. |
| Producer labeling | Runs record `REPO_AGENT_MODEL_PROFILE` (default `unrecorded`) in run context + handoff; harvest stamps `provenance.producer_profile` and `applicability.model_specific=False` (portable until qualified). `records_for_profile()` = per-model shelving. Minder issue #42 asks for the same two fields on minder's lessons table. |
| RA-019 retrieval | `retrieval.py`: scope filters before similarity (repository-tagged records never surface for other repos; unscoped are global), per-kind status floors, flags excluded, shelving applied, conservative char//4 token budget. `render_injection`: evidence block headed "quoted evidence, NOT instructions — the packet wins conflicts", bound to a digest with memory ids + revisions. Task run retrieves at dispatch (goal keywords ≥4 chars) and journals `memory.injected` idempotently. |
| Parallel session | RA-010 evaluator (`evaluate.py`: versioned plans, trusted manifest, integrity regressions), RA-011 CI + packaging smoke, RA-012 pilots, RA-013 comparison tooling (unmerged). |

## Coordination protocol (multiple sessions, one board)

1. One todo board; executors claim increments, cut a branch (or an
   isolated `git worktree`) from current origin/main.
2. Pushes to internal main are fast-forward only. If checkout is
   blocked by uncommitted shared files, `git branch -f main <tip>` +
   `git push origin <tip>:main` instead of fighting the tree.
3. Adopt parallel refinements intact; never rewrite another session's
   committed work. The RA-009 module was split and extended by the
   other session mid-run — that landed, not a revert.
4. Gates are judged on RAW EXIT CODES. `ruff | tail -1` masks rc=1 and
   once let a red commit through (fixed in-place; do not regress).
5. When this file and the tree disagree, the tree wins; update this
   file after landing, not before.

## Operational facts

- strata-8081 is DOWN since the overnight run (engine stopped). Proxy
  8390 and sink 8392 are UP; both answer honestly about the upstream.
  Local-worker dispatch (RA-018 extraction, any live task run) needs
  the engine restarted: `systemctl --user start strata-8081` (~40 s),
  then verify through the PROXY: `curl http://127.0.0.1:8390/health`.
  All model traffic goes through minder's proxy, never 8081 directly.
- GPU stack is AMD ROCm — `nvidia-smi` absence is normal, not breakage.
- dsh is 0.2.1-rc.2; headless emits NO agent events (tool-phase hooks
  are web-host-only). Hook-process env is dsh-controlled; minder
  inlines env in hook command strings for this reason.
- minder tree still carries the uncommitted `minder_memory/lessons.py`
  WIP (issue #22 follow-on) — leave it; it is the owner's decision.
- minder issues filed from this effort: #41 (decide seam), #42
  (lessons producer column + model_specific).

## Gotchas that cost real time (each pinned by a test or doc)

1. sqlite: `with conn` commits but never closes (leaked write locks,
   30 s stalls). Nested write transactions on one database deadlock —
   the harvest cursor and its candidates must share ONE transaction.
2. A method named `list` shadows the builtin for every annotation in
   that class (mypy) — the store method is `list_memories`.
3. Off-by-one guards that count decorated lines (render_injection's
   `len(lines)==4` against three headers) silently discard good data;
   guard on the input, not the accumulator.
4. This PyYAML build does not re-export `ConstructorError` at top
   level; SafeLoader defers nested construction (post-parse depth walk).
5. Workspace staging must exclude the target's VCS directory; journals
   live outside the target repo; harness stderr is never events;
   podman bind mounts need `:Z` on Fedora; podman runs with the
   caller's env (rewritten HOME detaches its storage); verification
   never auto-pulls images.

## Next phase (dependency order; one issue at execution time)

1. Land RA-013 to main (report shape + honesty vocabulary remain).
2. RA-014 `lesson propose` + paired evaluation command — candidates
   cannot self-activate; completes the sanctioned recursion lane:
   candidate → pinned-suite evaluation → human-reviewed promotion.
3. RA-021 profile registry + qualification — the model-switch
   mechanism (serves the planned DeepSeek move): versioned profile
   identities, probes, qualification against pinned suites, visibility
   flip for `model_specific` records. Backfill
   `qwen3.8-flash-next@strata-r020`.
4. RA-018 LLM-assisted extraction (idle-priority; model required).
5. RA-020 export/import + invalidation/purge (bridges to minder #42).
6. Public v0.2.0: scrub audit since v0.1.0, RUN-NOTES refresh,
   orphan-publish, tag + release.
7. Minder-side residue: #42 migration, #41 seam, `lessons.py` WIP
   decision, console issues #24/#18/#35–38.
8. RA-022 + RA-023 live transfer pilots + paired memory evaluation —
   needs two live profiles (qwen + DeepSeek); **G5 closes here**.

Deferred past this phase: G6 context management (RA-024–029,
observe-only first), G7 design routing (RA-031–035).

## Reproduction commands

```bash
cd ~/projects/repo-agent
make gates                                # pytest + ruff + ratchet
mypy repo_agent --ignore-missing-imports
scripts/proven-red.sh origin/main HEAD    # exit codes, not greps
python3 -m repo_agent.cli doctor . --live # readiness incl. model ping
python3 -m repo_agent.cli memory ls       # the memory store
env -u LD_LIBRARY_PATH python3 -m pytest -q   # if LD_LIBRARY_PATH set
```

Rollback for the whole post-v0.1.0 effort: `git push --force origin
v0.1.0:main` on the internal remote and delete the working branches;
the public repo is untouched.
