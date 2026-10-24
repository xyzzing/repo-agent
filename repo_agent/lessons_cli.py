"""RA-014: the lesson lane CLI helpers — propose and human-gated
promotion.

`propose` produces an evidence-linked proposal for one settled run:
the run's harvest candidates, bound to the run id by a deterministic
proposal id, written to the evidence directory. It never changes a
candidate's status. `promote_memory` is the human gate over the store's
evidence-gated transitions: without --yes it refuses (exit 2), and any
gate refusal maps to exit 2 with the store's reason code.
"""
import hashlib
import json
from pathlib import Path

from repo_agent.memory import MemoryError, MemoryStore
from repo_agent.memory_writer import harvest
from repo_agent.state import Journal


def proposal_id_for(run_id: str) -> str:
    return "prop-" + hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:12]


def propose(
    store: MemoryStore,
    journal: Journal,
    run_id: str,
    evidence_dir: Path | None = None,
) -> dict[str, object]:
    """Emit (never activate) the evidence-linked proposal for one run."""
    if journal.run_state(run_id) not in ("accepted", "needs_evidence"):
        raise MemoryError(
            "run_not_settled",
            f"{run_id} has not settled; proposals come from settled runs",
        )
    harvest(store, journal)
    candidates = []
    for m in store.list_memories(include_flagged=True):
        scope = m["scope"]
        assert isinstance(scope, dict)
        if scope.get("source_run") == run_id:
            candidates.append(m)
    proposal: dict[str, object] = {
        "proposal_id": proposal_id_for(run_id),
        "run_id": run_id,
        "candidates": candidates,
    }
    if evidence_dir is not None:
        out = Path(evidence_dir) / run_id
        out.mkdir(parents=True, exist_ok=True)
        (out / "proposal.json").write_text(
            json.dumps(proposal, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return proposal


def promote_memory(
    store: MemoryStore,
    memory_id: str,
    to_status: str,
    verification_json: str | None,
    yes: bool,
) -> int:
    """Human-gated transition; returns a CLI exit code."""
    if not yes:
        print(
            "refused: promotion is a human decision; re-run with --yes",
        )
        return 2
    try:
        if verification_json:
            store.attach_verification(
                memory_id, json.loads(verification_json)
            )
        store.promote(memory_id, to_status)
        return 0
    except MemoryError as exc:
        print(f"refused: {exc}")
        return 2
