"""RA-013: comparison semantics for eval manifests (PRD §11).

Pairs two manifests by task and classifies against PREDECLARED
tolerances into exactly the PRD outcome vocabulary: NON_COMPARABLE,
INSUFFICIENT_EVIDENCE, REGRESSION, NO_MATERIAL_CHANGE,
IMPROVEMENT_CANDIDATE. Quality is independently verified completion
(PASS verdicts); cost is total local worker tokens, with unknown usage
counted as unknown — never as zero. Critical integrity findings
(tampered graders, invalidated verdicts) block promotion regardless of
aggregate scores. An insufficient-sample comparison is a valid
operation whose report explicitly denies promotion.
"""
import json
from pathlib import Path

CRITICAL_REASONS = frozenset({"tampered_grader", "verdict_invalidated"})
OUTCOMES = (
    "NON_COMPARABLE",
    "INSUFFICIENT_EVIDENCE",
    "REGRESSION",
    "NO_MATERIAL_CHANGE",
    "IMPROVEMENT_CANDIDATE",
)


class CompareError(ValueError):
    pass


def load_manifest(path: Path) -> dict:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CompareError(f"unreadable_manifest: {exc}") from None
    except ValueError as exc:
        raise CompareError(f"malformed_manifest: {exc}") from None
    if not isinstance(raw, dict) or not isinstance(raw.get("tasks"), list):
        raise CompareError("malformed_manifest: no tasks list")
    return raw


def _tokens(task: dict) -> int | None:
    usage = task.get("usage")
    if not isinstance(usage, dict):
        return None
    value = usage.get("totalTokens")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _pair(base: dict, cand: dict) -> tuple[dict[str, dict], list[str], list[str]]:
    base_tasks = {t["task_id"]: t for t in base["tasks"]}
    cand_tasks = {t["task_id"]: t for t in cand["tasks"]}
    only_base = sorted(set(base_tasks) - set(cand_tasks))
    only_cand = sorted(set(cand_tasks) - set(base_tasks))
    shared = {
        tid: {"base": base_tasks[tid], "cand": cand_tasks[tid]}
        for tid in set(base_tasks) & set(cand_tasks)
    }
    return shared, only_base, only_cand


def compare_manifests(
    base: dict,
    candidate: dict,
    max_quality_loss: int,
    min_cost_improvement: float,
    min_paired: int,
) -> dict[str, object]:
    paired, only_base, only_cand = _pair(base, candidate)
    detail_parts: list[str] = []
    if only_base or only_cand:
        detail_parts.append(
            f"task sets differ: only-in-base={only_base} only-in-candidate={only_cand}"
        )
    digest_changed = sorted(
        tid
        for tid, pair in paired.items()
        if pair["base"].get("packet_digest") != pair["cand"].get("packet_digest")
    )
    if digest_changed:
        detail_parts.append(f"packet digests differ for {digest_changed}")

    base_passed = sum(1 for p in paired.values() if p["base"]["verdict"] == "PASS")
    cand_passed = sum(1 for p in paired.values() if p["cand"]["verdict"] == "PASS")
    quality_loss = base_passed - cand_passed

    base_cost = sum(
        t for t in (_tokens(p["base"]) for p in paired.values()) if t is not None
    )
    cand_known = [t for t in (_tokens(p["cand"]) for p in paired.values()) if t]
    cand_cost = sum(cand_known) if len(cand_known) == len(paired) else None
    cost_unknown = sum(
        1 for p in paired.values() if _tokens(p["cand"]) is None
    )
    if cand_cost is not None and base_cost > 0:
        cost_improvement = (base_cost - cand_cost) / base_cost
    else:
        cost_improvement = None

    critical: list[dict[str, str]] = []
    for side in ("base", "cand"):
        for tid, pair in paired.items():
            if pair[side].get("reason_code") in CRITICAL_REASONS:
                critical.append(
                    {
                        "task_id": tid,
                        "arm": side,
                        "reason_code": str(pair[side].get("reason_code")),
                    }
                )

    outcome: str
    promotion_denied = False
    would_improve = (
        cost_improvement is not None
        and cost_improvement > 0
        and cost_improvement >= min_cost_improvement
    )
    if detail_parts:
        outcome = "NON_COMPARABLE"
    elif quality_loss > max_quality_loss:
        outcome = "REGRESSION"
    elif critical and would_improve:
        outcome = "REGRESSION" if quality_loss > 0 else "INSUFFICIENT_EVIDENCE"
        promotion_denied = True
    elif would_improve and len(paired) < min_paired:
        outcome = "INSUFFICIENT_EVIDENCE"
        promotion_denied = True
    elif would_improve:
        outcome = "IMPROVEMENT_CANDIDATE"
    elif cost_improvement is None:
        outcome = "INSUFFICIENT_EVIDENCE"
        promotion_denied = True
    else:
        outcome = "NO_MATERIAL_CHANGE"

    verdict_changes = [
        {
            "task_id": tid,
            "base": p["base"]["verdict"],
            "cand": p["cand"]["verdict"],
            "reason_code": str(p["cand"].get("reason_code")),
        }
        for tid, p in sorted(paired.items())
        if p["base"]["verdict"] != p["cand"]["verdict"]
    ]
    return {
        "command": "eval compare",
        "outcome": outcome,
        "promotion_denied": promotion_denied,
        "detail": "; ".join(detail_parts),
        "paired": len(paired),
        "base_passed": base_passed,
        "candidate_passed": cand_passed,
        "quality_loss": quality_loss,
        "max_quality_loss": max_quality_loss,
        "base_cost_tokens": base_cost,
        "candidate_cost_tokens": cand_cost,
        "candidate_cost_unknown": cost_unknown,
        "cost_improvement": cost_improvement,
        "min_cost_improvement": min_cost_improvement,
        "min_paired": min_paired,
        "critical_integrity": critical,
        "verdict_changes": verdict_changes,
        "base_eval_id": base.get("eval_id"),
        "candidate_eval_id": candidate.get("eval_id"),
    }
