"""RA-013: eval compare — paired manifests classified against
predeclared tolerances into the PRD §11 outcome vocabulary, with
critical integrity findings blocking promotion regardless of scores.
"""
import pytest

from repo_agent.eval_compare import compare_manifests, load_manifest


def task(task_id, verdict="PASS", reason="ok", tokens=1000, wall=10.0,
         attempts=1, family="bugfix", split="dev", packet_digest="pd",
         usage_missing=False):
    return {
        "task_id": task_id,
        "verdict": verdict,
        "reason_code": reason,
        "attempts": attempts,
        "usage": None if usage_missing else {"totalTokens": tokens},
        "wall_seconds": wall,
        "family": family,
        "split": split,
        "packet_digest": packet_digest,
        "patch_digest": "x",
        "result_digest": "y",
    }


def manifest(tasks, eval_id="e", policy="none"):
    return {
        "command": "eval run",
        "eval_id": eval_id,
        "plan_digest": "plan",
        "policy": policy,
        "tasks": tasks,
        "aggregate": {
            "total": len(tasks),
            "passed": sum(1 for t in tasks if t["verdict"] == "PASS"),
            "failed": sum(1 for t in tasks if t["verdict"] == "FAIL"),
            "blocked": sum(1 for t in tasks if t["verdict"] == "BLOCKED"),
        },
    }


def ids(n, prefix="t"):
    return [f"{prefix}{i:02d}" for i in range(n)]


BASE = manifest([task(i) for i in ids(20)])


def test_identical_manifests_are_no_material_change():
    report = compare_manifests(
        BASE, manifest([task(i) for i in ids(20)]),
        max_quality_loss=0, min_cost_improvement=0.0, min_paired=20,
    )
    assert report["outcome"] == "NO_MATERIAL_CHANGE"
    assert report["paired"] == 20
    assert report["base_passed"] == report["candidate_passed"] == 20
    assert report["critical_integrity"] == []


def test_task_set_mismatch_is_non_comparable():
    cand = manifest([task(i) for i in ids(20) if i != "t05"] + [task("zzz")])
    report = compare_manifests(
        BASE, cand, max_quality_loss=0, min_cost_improvement=0.0, min_paired=20
    )
    assert report["outcome"] == "NON_COMPARABLE"
    assert report["detail"]


def test_packet_digest_mismatch_is_non_comparable():
    cand = manifest(
        [task(i, packet_digest="different") for i in ids(20)]
    )
    report = compare_manifests(
        BASE, cand, max_quality_loss=0, min_cost_improvement=0.0, min_paired=20
    )
    assert report["outcome"] == "NON_COMPARABLE"


def test_quality_regression_beyond_tolerance():
    cand = manifest(
        [task(i) for i in ids(20)][:19]
        + [task("t19", verdict="FAIL", reason="check_failed")]
    )
    report = compare_manifests(
        BASE, cand, max_quality_loss=0, min_cost_improvement=0.5, min_paired=20
    )
    assert report["outcome"] == "REGRESSION"
    assert report["quality_loss"] == 1


def test_quality_loss_within_tolerance_with_cost_win_is_improvement():
    base = manifest([task(i, tokens=2000) for i in ids(20)])
    cand = manifest([task(i, tokens=1000) for i in ids(20)])
    report = compare_manifests(
        base, cand, max_quality_loss=0, min_cost_improvement=0.5, min_paired=20
    )
    assert report["outcome"] == "IMPROVEMENT_CANDIDATE"
    assert report["cost_improvement"] == pytest.approx(0.5)


def test_cost_win_below_target_is_no_material_change():
    base = manifest([task(i, tokens=1100) for i in ids(20)])
    cand = manifest([task(i, tokens=1000) for i in ids(20)])
    report = compare_manifests(
        base, cand, max_quality_loss=0, min_cost_improvement=0.5, min_paired=20
    )
    assert report["outcome"] == "NO_MATERIAL_CHANGE"


def test_improvement_below_min_paired_denies_promotion():
    base = manifest([task(i, tokens=2000) for i in ids(10)])
    cand = manifest([task(i, tokens=1000) for i in ids(10)])
    report = compare_manifests(
        base, cand, max_quality_loss=0, min_cost_improvement=0.5, min_paired=20
    )
    assert report["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert report["promotion_denied"]
    assert report["paired"] == 10


def test_tamper_blocks_improvement_promotion():
    base = manifest([task(i, tokens=2000) for i in ids(20)])
    cand = manifest(
        [task(i, tokens=1000) for i in ids(19)]
        + [task(
            "t19", tokens=1000, verdict="FAIL",
            reason="tampered_grader",
        )]
    )
    report = compare_manifests(
        base, cand, max_quality_loss=1, min_cost_improvement=0.5, min_paired=20
    )
    assert report["critical_integrity"]
    assert report["outcome"] != "IMPROVEMENT_CANDIDATE"


def test_invalidated_verdict_is_critical_integrity():
    cand = manifest(
        [task(i) for i in ids(19)]
        + [task("t19", verdict="FAIL", reason="verdict_invalidated")]
    )
    report = compare_manifests(
        BASE, cand, max_quality_loss=1, min_cost_improvement=0.0, min_paired=20
    )
    assert any(
        f["reason_code"] == "verdict_invalidated"
        for f in report["critical_integrity"]
    )


def test_none_usage_counted_as_unknown_not_zero():
    base = manifest([task(i, tokens=2000) for i in ids(20)])
    cand = manifest(
        [task(i, tokens=1000, usage_missing=True) for i in ids(20)]
    )
    report = compare_manifests(
        base, cand, max_quality_loss=0, min_cost_improvement=0.5, min_paired=20
    )
    # candidate cost unknown → the cost claim cannot stand
    assert report["outcome"] in ("INSUFFICIENT_EVIDENCE", "NON_COMPARABLE")
    assert report["candidate_cost_unknown"] > 0


def test_load_manifest_rejects_missing_and_shapeless(tmp_path):
    missing = tmp_path / "nope.json"
    with pytest.raises(ValueError, match="unreadable_manifest"):
        load_manifest(missing)
    bad = tmp_path / "bad.json"
    bad.write_text('{"tasks": "nope"}', encoding="utf-8")
    with pytest.raises(ValueError, match="malformed_manifest"):
        load_manifest(bad)
