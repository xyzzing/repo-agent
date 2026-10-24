"""RA-017: the event-driven writer — journal cursor to memory candidates.

The writer is deterministic by design (PRD: establish the structured
extraction baseline before any model-assisted layer). It reads runs from
the journal behind a durable per-run cursor and emits candidates only:

- an accepted run becomes a verified_procedure candidate (what changed,
  bound to the verdict) plus a strategy candidate — the approach that
  verified, so learning is not failure-only;
- a run exhausted at needs_evidence becomes a failure_pattern candidate
  carrying the reason code;
- blocked/created/running runs produce nothing until they settle.

Every candidate cites its verdict event and carries the result digest as
evidence. Replaying the cursor creates nothing: idempotency is the
cursor's contract.
"""
import uuid
from datetime import UTC, datetime

from repo_agent.memory import MemoryStore

_SETTLED = ("accepted", "needs_evidence", "failed", "cancelled")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _verdict_events(journal, run_id: str) -> list[dict]:
    return [
        e for e in journal.events(run_id) if e["kind"] == "verifier.verdict"
    ]


def _procedure_claim(run: dict, verdict: dict) -> str:
    digest = str(verdict["payload"].get("patch_digest", ""))
    return (
        f"Task {run['task_id']}: completed a verified change "
        f"(patch {digest[:12]}) accepted by the protected verifier"
    )


def _strategy_claim(run: dict, verdict: dict, attempts: int) -> str:
    return (
        f"Approach that verified: {run['task_id']} succeeded under packet "
        f"discipline in {attempts} recorded attempt cycle(s); scope held "
        f"and acceptance enforced by the independent verifier"
    )


def _failure_claim(run: dict, verdict: dict) -> str:
    reason = str(verdict["payload"].get("reason_code", "unknown"))
    return f"Task {run['task_id']} exhausted retries: {reason}"


def _attempts(journal, run_id: str) -> int:
    return sum(
        1 for e in journal.events(run_id) if e["kind"] == "verifier.verdict"
    )


def harvest(store: MemoryStore, journal) -> dict[str, object]:
    """One writer pass. Returns counts; safe to call concurrently-ish
    (the cursor insert is the serialization point)."""
    created = 0
    by_kind: dict[str, int] = {}
    scanned = 0
    for run in journal.runs():
        if run["state"] not in _SETTLED:
            continue
        scanned += 1
        run_id = run["run_id"]
        verdicts = _verdict_events(journal, run_id)
        new_items: list[tuple[str, str, dict]] = []
        if run["state"] == "accepted" and verdicts:
            verdict = verdicts[-1]
            evidence = {
                "source_event_ids": [verdict["event_id"]],
                "evidence_digest": str(
                    verdict["payload"].get("result_digest", "")
                ),
            }
            new_items.append(
                ("verified_procedure", _procedure_claim(run, verdict), evidence)
            )
            new_items.append(
                ("strategy",
                 _strategy_claim(run, verdict, _attempts(journal, run_id)),
                 evidence)
            )
        elif run["state"] == "needs_evidence" and verdicts:
            verdict = verdicts[-1]
            evidence = {
                "source_event_ids": [verdict["event_id"]],
                "evidence_digest": str(
                    verdict["payload"].get("result_digest", "")
                ),
            }
            new_items.append(
                ("failure_pattern", _failure_claim(run, verdict), evidence)
            )
        if not new_items:
            continue
        # PRD §12A: producer identity is provenance, not a scope
        # restriction. Harvest candidates are portable until qualified
        # otherwise; the producer profile comes from the run context.
        try:
            ctx = journal.run_context(run_id)
            producer = str(ctx.get("model_profile") or "unrecorded")
        except Exception:
            producer = "unrecorded"
        applicability = {"model_specific": False}
        try:
            repo_path = str(journal.run_context(run_id).get("repo_path") or "")
        except Exception:
            repo_path = ""
        scope = {"source_run": run_id}
        if repo_path:
            scope["repository_id"] = repo_path
        # One write per run: the cursor row and its candidates commit
        # together, so a crash loses nothing and a replay duplicates
        # nothing. record() cannot be used here — it would open a second
        # write transaction inside this one and deadlock.
        with store._tx() as conn:  # noqa: SLF001 - batched writer path
            already = conn.execute(
                "SELECT 1 FROM harvest_cursor WHERE run_id=?", (run_id,)
            ).fetchone()
            if already:
                continue
            for kind, claim, evidence in new_items:
                store.validate_candidate(kind, claim, evidence)
                store._insert(  # noqa: SLF001
                    conn,
                    {
                        "memory_id": f"mem-{uuid.uuid4().hex}",
                        "kind": kind,
                        "claim": claim,
                        "scope": scope,
                        "applicability": applicability,
                        "provenance": {
                            **evidence,
                            "producer_profile": producer,
                        },
                        "verification": {},
                        "revision": 1,
                        "status": "candidate",
                        "flags": [],
                        "flag_reason": "",
                        "supersedes": [],
                    },
                )
                created += 1
                by_kind[kind] = by_kind.get(kind, 0) + 1
            conn.execute(
                "INSERT INTO harvest_cursor(run_id, harvested_at) VALUES(?,?)",
                (run_id, _now()),
            )
    return {"scanned": scanned, "created": created, "by_kind": by_kind}
