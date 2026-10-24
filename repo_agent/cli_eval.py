"""Eval command group (RA-010/013): `eval run|compare`, split out of
cli.py to hold the file under the 400-line ratchet. Registration stays
in cli.py; handlers live here."""
import argparse
from pathlib import Path

from repo_agent.cli import (
    EXIT_CHECKS_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    emit,
    emit_payload,
)


def _eval_run(args: argparse.Namespace) -> int:
    from repo_agent.evaluate import PlanError, run_plan

    plan_path = Path(args.plan_file)
    out_dir = (
        Path(args.out)
        if args.out
        else plan_path.parent / (plan_path.stem + "-eval")
    )
    repo = Path(args.repo) if args.repo else None
    try:
        manifest = run_plan(plan_path, repo=repo, out_dir=out_dir)
    except PlanError as exc:
        emit("eval run", ok=False, reason_code=exc.reason_code, detail=str(exc))
        return EXIT_USAGE
    emit_payload({"command": "eval run", **manifest})
    aggregate = manifest["aggregate"]
    assert isinstance(aggregate, dict)
    if aggregate["blocked"] or aggregate["failed"]:
        return EXIT_CHECKS_FAILED
    return EXIT_OK


def _eval_compare(args: argparse.Namespace) -> int:
    from repo_agent.eval_compare import CompareError, compare_manifests, load_manifest

    try:
        base = load_manifest(Path(args.baseline))
        candidate = load_manifest(Path(args.candidate))
        report = compare_manifests(
            base,
            candidate,
            max_quality_loss=args.max_quality_loss,
            min_cost_improvement=args.min_cost_improvement,
            min_paired=args.min_paired,
        )
    except CompareError as exc:
        emit("eval compare", ok=False, reason_code=str(exc).split(":")[0],
             detail=str(exc))
        return EXIT_USAGE
    emit_payload(report)
    if report["outcome"] == "NON_COMPARABLE":
        return EXIT_USAGE
    return EXIT_OK


def register(sub) -> None:
        p = sub.add_parser("eval", help="versioned evaluation plans")
        eval_sub = p.add_subparsers(dest="eval_command", metavar="ACTION", required=True)
        sp = eval_sub.add_parser("run")
        sp.add_argument("plan_file")
        sp.add_argument("--repo", default=None,
                        help="repo for plans that do not resolve their own")
        sp.add_argument("--out", default=None, help="output dir (default: <plan>-eval)")
        sp.set_defaults(handler=_eval_run)
        sp = eval_sub.add_parser("compare")
        sp.add_argument("baseline")
        sp.add_argument("candidate")
        sp.add_argument("--max-quality-loss", type=int, default=0,
                        help="tolerated PASS-count decrease (predeclared)")
        sp.add_argument("--min-cost-improvement", type=float, default=0.0,
                        help="desired fractional token-cost improvement")
        sp.add_argument("--min-paired", type=int, default=20,
                        help="paired tasks required to claim an improvement")
        sp.set_defaults(handler=_eval_compare)
