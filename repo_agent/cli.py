"""CLI skeleton (RA-001).

Exit-code contract (PRD §5): 0 success; 1 checks failed; 2
usage/configuration error; 3 blocked prerequisite/policy; 4
infrastructure failure. Every PRD §5 command parses and dispatches;
commands without an implementation yet exit 3 with reason
"unimplemented" — the skeleton never fabricates success. argparse's own
usage errors and --help/--version are normalized to the same contract.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from repo_agent import __version__

EXIT_OK = 0
EXIT_CHECKS_FAILED = 1
EXIT_USAGE = 2
EXIT_BLOCKED = 3
EXIT_INFRA = 4

UNIMPLEMENTED = "unimplemented"


def emit(command: str, ok: bool, reason_code: str, **extra: object) -> None:
    payload: dict[str, object] = {
        "command": command,
        "ok": ok,
        "reason_code": reason_code,
        **extra,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def emit_payload(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _stub(command: str):
    def handler(args: argparse.Namespace) -> int:
        emit(command, ok=False, reason_code=UNIMPLEMENTED)
        return EXIT_BLOCKED

    return handler


def _inspect(args: argparse.Namespace) -> int:
    from repo_agent.inspect import inspect_repo

    root = Path(args.path)
    if not root.exists():
        emit_payload(
            {
                "command": "inspect",
                "ok": False,
                "reason_code": "path_missing",
                "detail": f"no such path: {args.path}",
            }
        )
        return EXIT_USAGE
    if not root.is_dir():
        emit_payload(
            {
                "command": "inspect",
                "ok": False,
                "reason_code": "not_a_directory",
                "detail": f"not a directory: {args.path}",
            }
        )
        return EXIT_USAGE
    report = inspect_repo(root)
    emit_payload({"command": "inspect", **report})
    return EXIT_OK if report["ok"] else EXIT_INFRA


def _render(args: argparse.Namespace) -> int:
    from repo_agent.render import render_repo

    code, payload = render_repo(Path(args.path), write=bool(args.write))
    emit_payload({"command": "render", **payload})
    return code


def _bootstrap(args: argparse.Namespace) -> int:
    from repo_agent.bootstrap import bootstrap

    code, payload = bootstrap(Path(args.path), args.mode, apply=bool(args.apply))
    emit_payload({"command": "bootstrap", **payload})
    return code


def _task_validate(args: argparse.Namespace) -> int:
    from repo_agent.packets import PacketError, load

    try:
        packet = load(Path(args.task_file))
    except PacketError as exc:
        emit_payload(
            {
                "command": "task validate",
                "ok": False,
                "reason_code": exc.reason_code,
                "detail": str(exc),
            }
        )
        return EXIT_USAGE
    emit_payload(
        {
            "command": "task validate",
            "ok": True,
            "reason_code": "ok",
            "task_id": packet.task_id,
            "base_commit": packet.base_commit,
        }
    )
    return EXIT_OK


def _state_root() -> Path:
    return Path(
        os.environ.get(
            "REPO_AGENT_STATE_DIR", Path.home() / ".local" / "state" / "repo-agent"
        )
    )


def _task_run(args: argparse.Namespace) -> int:
    from repo_agent.packets import PacketError
    from repo_agent.state import Journal
    from repo_agent.taskrun import TaskBlocked, run_packet

    repo = Path(args.repo)
    state = _state_root()
    state.mkdir(parents=True, exist_ok=True)
    # Journal and work areas live outside the repo (PRD §6): a journal
    # inside the target would make every repo dirty by its own bookkeeping.
    journal = Journal(state / "journal.sqlite")
    graders = [Path(args.grader)] if args.grader else []
    try:
        handoff = run_packet(
            Path(args.task_file),
            repo=repo,
            work_root=state / "work",
            journal=journal,
            graders=graders,
            evidence_dir=state / "runs",
        )
    except TaskBlocked as exc:
        emit_payload(
            {
                "command": "task run",
                "ok": False,
                "reason_code": exc.reason_code,
                "detail": exc.detail,
            }
        )
        return EXIT_BLOCKED
    except PacketError as exc:
        emit_payload(
            {
                "command": "task run",
                "ok": False,
                "reason_code": exc.reason_code,
                "detail": str(exc),
            }
        )
        return EXIT_USAGE
    emit_payload({"command": "task run", **handoff})
    return EXIT_OK if handoff["verdict"] == "PASS" else EXIT_CHECKS_FAILED


def _task_cancel(args: argparse.Namespace) -> int:
    from repo_agent.state import Journal
    from repo_agent.taskrun import TaskBlocked, cancel_run

    journal = Journal(_state_root() / "journal.sqlite")
    try:
        result = cancel_run(journal, args.run_id)
    except TaskBlocked as exc:
        emit_payload(
            {
                "command": "task cancel",
                "ok": False,
                "reason_code": exc.reason_code,
                "detail": exc.detail,
            }
        )
        return EXIT_BLOCKED
    emit_payload({"command": "task cancel", **result})
    return EXIT_OK


def _task_resume(args: argparse.Namespace) -> int:
    from repo_agent.state import Journal
    from repo_agent.taskrun import TaskBlocked, run_packet

    journal = Journal(_state_root() / "journal.sqlite")
    try:
        ctx = journal.run_context(args.run_id)
    except Exception:
        emit_payload(
            {
                "command": "task resume",
                "ok": False,
                "reason_code": "unknown_run",
                "detail": f"no run {args.run_id} in the journal",
            }
        )
        return EXIT_BLOCKED
    state = _state_root()
    try:
        handoff = run_packet(
            Path(str(ctx["packet_path"])),
            repo=Path(str(ctx["repo_path"])),
            work_root=state / "work",
            journal=journal,
            evidence_dir=state / "runs",
            resume=True,
        )
    except TaskBlocked as exc:
        emit_payload(
            {
                "command": "task resume",
                "ok": False,
                "reason_code": exc.reason_code,
                "detail": exc.detail,
            }
        )
        return EXIT_BLOCKED
    emit_payload({"command": "task resume", **handoff})
    return EXIT_OK if handoff["verdict"] == "PASS" else EXIT_CHECKS_FAILED


def _doctor(args: argparse.Namespace) -> int:
    import repo_agent.doctor

    report = repo_agent.doctor.run_doctor(Path(args.path), live=bool(args.live))
    emit_payload({"command": "doctor", **report})
    if report.get("blocked"):
        return EXIT_BLOCKED
    return EXIT_OK if report["ok"] else EXIT_CHECKS_FAILED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-agent",
        description="Onboard repos, generate agent instructions, run bounded "
        "tasks through DSH, verify outcomes independently.",
    )
    parser.add_argument(
        "--version", action="version", version=f"repo-agent {__version__}"
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p = sub.add_parser("inspect", help="read-only repo inventory")
    p.add_argument("path")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.set_defaults(handler=_inspect)

    p = sub.add_parser("bootstrap", help="proposed onboarding patch")
    p.add_argument("path")
    p.add_argument("--mode", choices=("new", "mature"), required=True)
    p.add_argument("--apply", action="store_true")
    p.set_defaults(handler=_bootstrap)

    p = sub.add_parser("doctor", help="prerequisite and readiness checks")
    p.add_argument("path")
    p.add_argument("--live", action="store_true", help="include a harmless model ping")
    p.set_defaults(handler=_doctor)

    p = sub.add_parser("render", help="deterministic instruction rendering")
    p.add_argument("path")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    p.set_defaults(handler=_render)

    p = sub.add_parser("task", help="authorized task lifecycle")
    task_sub = p.add_subparsers(dest="task_command", metavar="ACTION", required=True)
    sp = task_sub.add_parser("validate", help="validate a task packet")
    sp.add_argument("task_file")
    sp.set_defaults(handler=_task_validate)
    sp = task_sub.add_parser("run", help="run one authorized task")
    sp.add_argument("task_file")
    sp.add_argument("--repo", required=True)
    sp.add_argument("--grader", default=None)
    sp.set_defaults(handler=_task_run)
    sp = task_sub.add_parser("resume", help="reconcile and resume a run")
    sp.add_argument("run_id")
    sp.set_defaults(handler=_task_resume)
    sp = task_sub.add_parser("cancel", help="cancel a non-terminal run")
    sp.add_argument("run_id")
    sp.set_defaults(handler=_task_cancel)

    p = sub.add_parser("eval", help="versioned evaluation plans")
    eval_sub = p.add_subparsers(dest="eval_command", metavar="ACTION", required=True)
    sp = eval_sub.add_parser("run")
    sp.add_argument("plan_file")
    sp.set_defaults(handler=_stub("eval run"))
    sp = eval_sub.add_parser("compare")
    sp.add_argument("baseline")
    sp.add_argument("candidate")
    sp.set_defaults(handler=_stub("eval compare"))

    p = sub.add_parser("lesson", help="evidence-linked lesson candidates")
    lesson_sub = p.add_subparsers(dest="lesson_command", metavar="ACTION", required=True)
    sp = lesson_sub.add_parser("propose")
    sp.add_argument("run_id")
    sp.set_defaults(handler=_stub("lesson propose"))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else EXIT_USAGE
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_usage(sys.stderr)
        return EXIT_USAGE
    return int(handler(args))
