"""RA-014: paired evaluation of a lesson proposal (PRD §11/§12C arms).

Two arms over an identical packet and repository: baseline (no memory
injection) versus candidate (the proposal's records injected through
the normal retrieval path). Outcomes use the PRD §11 vocabulary and
n=1 is always flagged `sufficient: false` — a paired single-run result
can justify a larger experiment, never a promotion claim.
"""
import json
from pathlib import Path

from repo_agent.memory import MemoryStore
from repo_agent.state import Journal
from repo_agent.taskrun import run_packet


def load_proposal(path: Path) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run_arm(arm: str, proposal: dict, packet_path: Path, repo: Path,
             work_root: Path, journal: Journal, store: MemoryStore,
             grader, worker, suffix: str = ""):
    handoff = run_packet(
        packet_path,
        repo=repo,
        work_root=work_root / arm,
        journal=journal,
        worker=worker,
        graders=[grader] if grader is not None else [],
        memory_store=store if arm == "candidate" else None,
        idempotency_suffix=suffix,
    )
    return {
        "arm": arm,
        "verdict": str(handoff["verdict"]),
        "reason_code": str(handoff["reason_code"]),
        "model_profile": str(handoff["model_profile"]),
        "total_tokens": int(
            isinstance(handoff["usage"], dict)
            and handoff["usage"].get("totalTokens", 0)  # type: ignore[union-attr]
        ),
    }


def evaluate_proposal(
    proposal: dict[str, object],
    packet_path: Path,
    repo: Path,
    work_root: Path,
    journal: Journal,
    store: MemoryStore,
    grader=None,
    worker=None,
) -> dict[str, object]:
    """Run baseline and candidate arms; report the paired outcome."""
    records = proposal["records"]
    assert isinstance(records, list)
    baseline = _run_arm("baseline", proposal, packet_path, repo, work_root,
                        journal, store, grader, worker,
                        suffix=":arm-baseline")
    candidate = _run_arm("candidate", proposal, packet_path, repo, work_root,
                         journal, store, grader, worker,
                         suffix=":arm-candidate")

    if baseline["model_profile"] != candidate["model_profile"]:
        outcome = "NON_COMPARABLE"
    elif baseline["verdict"] == "PASS" and candidate["verdict"] == "PASS":
        ratio = candidate["total_tokens"] / max(1, baseline["total_tokens"])
        outcome = "IMPROVEMENT_CANDIDATE" if ratio < 0.9 else "NO_MATERIAL_CHANGE"
    elif baseline["verdict"] == "FAIL" and candidate["verdict"] == "PASS":
        outcome = "IMPROVEMENT_CANDIDATE"
    elif baseline["verdict"] == "PASS" and candidate["verdict"] == "FAIL":
        outcome = "REGRESSION"
    else:
        outcome = "CANDIDATE_REJECTED"

    return {
        "proposal_id": proposal["proposal_id"],
        "outcome": outcome,
        "sample": 1,
        "sufficient": False,
        "arms": {"baseline": baseline, "candidate": candidate},
        "note": "paired single-run result; promotion claims require a "
                "multi-sample evaluation on held-out tasks",
    }
