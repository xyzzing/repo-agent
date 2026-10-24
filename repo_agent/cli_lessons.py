"""Lesson-lane command group (RA-014): `lesson propose|evaluate` and
`memory promote`, split out of cli.py for the 400-line ratchet."""
import argparse
from pathlib import Path

from repo_agent.cli import (
    EXIT_BLOCKED,
    EXIT_CHECKS_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    emit,
    emit_payload,
)


def _lesson_propose(args: argparse.Namespace) -> int:
    from repo_agent.cli import _state_root
    from repo_agent.lessons_cli import propose
    from repo_agent.memory import MemoryError, MemoryStore
    from repo_agent.state import Journal, UnknownRun

    journal = Journal(_state_root() / "journal.sqlite")
    store = MemoryStore(_state_root() / "memory.sqlite", journal=journal)
    try:
        proposal = propose(
            store, journal, args.run_id,
            evidence_dir=_state_root() / "runs",
        )
    except (MemoryError, UnknownRun) as exc:
        reason = exc.reason_code if isinstance(exc, MemoryError) else "unknown_run"
        emit("lesson propose", ok=False, reason_code=reason, detail=str(exc))
        return EXIT_BLOCKED
    emit_payload({"command": "lesson propose", **proposal})
    return EXIT_OK


def _memory_promote(args: argparse.Namespace) -> int:
    from repo_agent.cli import _state_root
    from repo_agent.lessons_cli import promote_memory
    from repo_agent.memory import MemoryStore

    store = MemoryStore(_state_root() / "memory.sqlite")
    code = promote_memory(
        store, args.memory_id, args.to,
        verification_json=args.verification, yes=bool(args.yes),
    )
    if code == 0:
        emit_payload({
            "command": "memory promote", "ok": True, "reason_code": "ok",
            "memory_id": args.memory_id, "status": args.to,
        })
    return code


def _memory_ls(args: argparse.Namespace) -> int:
    from repo_agent.cli import _state_root
    from repo_agent.memory import MemoryStore

    store = MemoryStore(_state_root() / "memory.sqlite")
    items = store.list_memories(include_flagged=bool(args.all))
    emit_payload(
        {
            "command": "memory ls",
            "ok": True,
            "reason_code": "ok",
            "count": len(items),
            "memories": [
                {"memory_id": m["memory_id"], "kind": m["kind"],
                 "status": m["status"], "claim": m["claim"],
                 "flags": m["flags"]}
                for m in items
            ],
        }
    )
    return EXIT_OK


def _lesson_evaluate(args: argparse.Namespace) -> int:
    from repo_agent.cli import _state_root
    from repo_agent.lesson_eval import evaluate_proposal, load_proposal
    from repo_agent.memory import MemoryStore
    from repo_agent.state import Journal

    proposal = load_proposal(Path(args.proposal))
    journal = Journal(_state_root() / "journal.sqlite")
    store = MemoryStore(_state_root() / "memory.sqlite", journal=journal)
    report = evaluate_proposal(
        proposal,
        packet_path=Path(args.packet),
        repo=Path(args.repo),
        work_root=_state_root() / "work",
        journal=journal,
        store=store,
        grader=Path(args.grader) if args.grader else None,
    )
    emit_payload({"command": "lesson evaluate", **report})
    if report["outcome"] in ("NON_COMPARABLE", "REGRESSION"):
        return EXIT_USAGE
    if report["outcome"] == "CANDIDATE_REJECTED":
        return EXIT_CHECKS_FAILED
    return EXIT_OK


def register(sub) -> None:
    p = sub.add_parser("lesson", help="evidence-linked lesson candidates")
    lesson_sub = p.add_subparsers(dest="lesson_command", metavar="ACTION",
                                  required=True)
    sp = lesson_sub.add_parser("propose")
    sp.add_argument("run_id")
    sp.set_defaults(handler=_lesson_propose)
    sp = lesson_sub.add_parser("evaluate")
    sp.add_argument("proposal")
    sp.add_argument("packet")
    sp.add_argument("--repo", required=True)
    sp.add_argument("--grader", default=None)
    sp.set_defaults(handler=_lesson_evaluate)

    p = sub.add_parser("memory", help="canonical memory store (RA-016)")
    memory_sub = p.add_subparsers(dest="memory_command", metavar="ACTION",
                                  required=True)
    sp = memory_sub.add_parser("ls")
    sp.add_argument("--all", action="store_true")
    sp.set_defaults(handler=_memory_ls)
    sp = memory_sub.add_parser("refine")
    sp.add_argument("--limit", type=int, default=5)
    sp.add_argument("--profile", default=None)
    sp.set_defaults(handler=_memory_refine)
    sp = memory_sub.add_parser("export")
    sp.add_argument("out")
    sp.set_defaults(handler=_memory_export)
    sp = memory_sub.add_parser("import")
    sp.add_argument("source")
    sp.set_defaults(handler=_memory_import)
    sp = memory_sub.add_parser("retire")
    sp.add_argument("memory_id")
    sp.add_argument("--reason", required=True)
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(handler=_memory_retire)
    sp = memory_sub.add_parser("purge")
    sp.add_argument("--profile", required=True)
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(handler=_memory_purge)

    p = sub.add_parser("profile", help="serving-profile registry (RA-021)")
    profile_sub = p.add_subparsers(dest="profile_command", metavar="ACTION",
                                   required=True)
    sp = profile_sub.add_parser("register")
    sp.add_argument("profile_id")
    sp.add_argument("--engine", default="")
    sp.add_argument("--model", default="")
    sp.add_argument("--quantisation", default="")
    sp.set_defaults(handler=_profile)
    sp = profile_sub.add_parser("qualify")
    sp.add_argument("profile_id")
    sp.add_argument("--suites", required=True,
                    help="pinned suites the qualification ran against")
    sp.set_defaults(handler=_profile)
    sp = profile_sub.add_parser("ls")
    sp.set_defaults(handler=_profile)

    sp = memory_sub.add_parser("promote")
    sp.add_argument("memory_id")
    sp.add_argument("--to", required=True,
                    choices=("evidence_checked", "locally_verified", "reusable"))
    sp.add_argument("--verification", default=None,
                    help="JSON verification record for locally_verified")
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(handler=_memory_promote)


def _profile(args: argparse.Namespace) -> int:
    from repo_agent.cli import _state_root
    from repo_agent.profiles import ProfileError, ProfileStore

    store = ProfileStore(_state_root() / "profiles.sqlite")
    try:
        if args.profile_command == "register":
            state = store.register(
                args.profile_id, engine=args.engine, model=args.model,
                quantisation=args.quantisation,
            )
            emit_payload({"command": "profile register", "ok": True,
                          "reason_code": "ok", "profile": state})
            return EXIT_OK
        if args.profile_command == "qualify":
            state = store.qualify(args.profile_id, suites_ref=args.suites)
            emit_payload({"command": "profile qualify", "ok": True,
                          "reason_code": "ok", "profile": state})
            return EXIT_OK
        emit_payload({"command": "profile ls", "ok": True,
                      "reason_code": "ok", "profiles": store.list()})
        return EXIT_OK
    except ProfileError as exc:
        emit(f"profile {args.profile_command}", ok=False,
             reason_code=exc.reason_code, detail=str(exc))
        return EXIT_USAGE


def _memory_refine(args: argparse.Namespace) -> int:
    from repo_agent.cli import _state_root
    from repo_agent.extraction_llm import dsh_refiner, refine_candidates
    from repo_agent.memory import MemoryStore

    store = MemoryStore(_state_root() / "memory.sqlite")
    refiner = dsh_refiner(args.profile)
    if refiner is None:
        emit("memory refine", ok=False, reason_code="no_model_profile",
             detail="set REPO_AGENT_MODEL_PROFILE (and start the engine) "
             "to enable the refine pass")
        return EXIT_BLOCKED
    report = refine_candidates(store, refiner, limit=args.limit)
    emit_payload({"command": "memory refine", "ok": True,
                  "reason_code": "ok", **report})
    return EXIT_OK


def _memory_export(args: argparse.Namespace) -> int:
    from repo_agent.cli import _state_root
    from repo_agent.memory import MemoryStore
    from repo_agent.memory_port import export_memories

    store = MemoryStore(_state_root() / "memory.sqlite")
    out = export_memories(store, Path(args.out))
    emit_payload({"command": "memory export", "ok": True,
                  "reason_code": "ok", "out": str(out)})
    return EXIT_OK


def _memory_import(args: argparse.Namespace) -> int:
    from repo_agent.cli import _state_root
    from repo_agent.memory import MemoryStore
    from repo_agent.memory_port import import_memories

    store = MemoryStore(_state_root() / "memory.sqlite")
    report = import_memories(store, Path(args.source),
                             quarantine_dir=_state_root() / "quarantine")
    emit_payload({"command": "memory import", "ok": True,
                  "reason_code": "ok", **report})
    return EXIT_OK if report["quarantined"] == 0 else EXIT_CHECKS_FAILED


def _memory_retire(args: argparse.Namespace) -> int:
    from repo_agent.cli import _state_root
    from repo_agent.memory import MemoryStore
    from repo_agent.memory_port import retire

    store = MemoryStore(_state_root() / "memory.sqlite")
    if not args.yes:
        emit("memory retire", ok=False, reason_code="requires_yes",
             detail="retire is a human decision; re-run with --yes")
        return EXIT_USAGE
    retire(store, args.memory_id, args.reason)
    emit_payload({"command": "memory retire", "ok": True,
                  "reason_code": "ok", "memory_id": args.memory_id})
    return EXIT_OK


def _memory_purge(args: argparse.Namespace) -> int:
    from repo_agent.cli import _state_root
    from repo_agent.memory import MemoryStore
    from repo_agent.memory_port import purge_profile

    store = MemoryStore(_state_root() / "memory.sqlite")
    if not args.yes:
        emit("memory purge", ok=False, reason_code="requires_yes",
             detail="purge tombstones every record of a profile; "
             "re-run with --yes")
        return EXIT_USAGE
    purged = purge_profile(store, args.profile)
    emit_payload({"command": "memory purge", "ok": True,
                  "reason_code": "ok", "purged": purged,
                  "profile": args.profile})
    return EXIT_OK


