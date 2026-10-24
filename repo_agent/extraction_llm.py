"""RA-018: the LLM-assisted refine pass over deterministic candidates.

Deterministic harvest stays the baseline (PRD §12A); this module is the
optional layer above it. The refiner is injectable for tests; the
shipped dsh-backed refiner is bounded (a claim limit per pass, one
bounded prompt per candidate) and the whole pass is inert without a
model. A refined claim lands as a NEW revision on the same record —
history is never rewritten — and the model_specific heuristic flips
applicability when the refined claim names prompt-, reasoning-, or
model-bound behavior.
"""
from repo_agent.memory import MemoryStore

_BOUND_WORDS = ("prompt", "thinking", "reasoning", "dialect", "model",
                "token", "template", "effort")


def dsh_refiner(profile: str):
    """The shipped refiner: one bounded dsh headless call per claim.
    Returns None when no model profile is configured."""
    import os

    profile = profile or os.environ.get("REPO_AGENT_MODEL_PROFILE", "")
    if not profile or profile == "unrecorded":
        return None

    def refiner(claim: str, kind: str, context: str) -> str | None:
        from repo_agent.adapters.dsh import run_task

        task = (
            "Rewrite this memory claim to be one specific, testable "
            "sentence. Keep only what the evidence supports; add nothing. "
            "Reply with the rewritten claim only.\n"
            f"kind: {kind}\ncontext: {context}\nclaim: {claim}"
        )
        run = run_task(task, timeout_seconds=180)
        text = (run.final_text or "").strip()
        return text or None

    return refiner


def _model_specific(claim: str) -> bool:
    lowered = claim.lower()
    return any(word in lowered for word in _BOUND_WORDS)


def refine_candidates(
    store: MemoryStore, refiner, limit: int = 10
) -> dict[str, int]:
    """One bounded pass over candidate records that have never been
    refined (revision 1). Returns counts; a refiner that declines
    (returns None) leaves the record untouched."""
    refined = 0
    declined = 0
    for mem in store.list_memories():
        if refined >= limit:
            break
        if mem["revision"] != 1 or mem["status"] != "candidate":
            continue
        claim = str(mem["claim"])
        kind = str(mem["kind"])
        scope = mem["scope"]
        source_run = (
            scope.get("source_run", "") if isinstance(scope, dict) else ""
        )
        proposed = refiner(claim, kind, f"run {source_run}")
        if not proposed or not str(proposed).strip():
            declined += 1
            continue
        sharper = str(proposed).strip()
        applicability = mem["applicability"]
        assert isinstance(applicability, dict)
        refined += 1
        store.refine(
            str(mem["memory_id"]),
            sharper,
            model_specific=_model_specific(sharper),
        )
    return {"refined": refined, "declined": declined}
