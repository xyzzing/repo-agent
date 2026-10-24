"""RA-008: the authorized task-run lifecycle (PRD §6, §10).

One packet, one worker, one protected verdict. The journal records every
transition; the worker's prose and any file it writes are observations,
never authority: acceptance comes only from the protected verifier bound
to the frozen patch digest. Preflight refuses a moved base (base_mismatch)
or a dirty repo (dirty_repo) before the worker spends anything.

RA-009: an optional policy authority (PRD §9) gates every spend — before
the first dispatch and at each needs_evidence retry point. A refusal
(pause/stop/consult_frontier) or an unavailable required decision blocks
further spend; policy is off by default, so evaluation runs without it.
"""
import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from repo_agent.adapters.dsh import DshRun
from repo_agent.adapters.minder import MinderEvents
from repo_agent.adapters.minder_decisions import (
    Decision,
    LocalPolicy,
    PolicyBlocked,
    RequiredMinderPolicy,
    RunPolicy,
    validate_decision,
)
from repo_agent.packets import Packet
from repo_agent.state import Journal
from repo_agent.verifier import Verifier, stage_workspace

WorkerFn = Callable[[str, Path], DshRun]
PolicyFactory = Callable[[Journal, str, Packet], RunPolicy]


class TaskBlocked(Exception):
    def __init__(self, reason_code: str, detail: str):
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


def _git(repo: Path, *argv: str) -> str:
    out = subprocess.run(
        ["git", *argv], cwd=repo, capture_output=True, text=True
    )
    if out.returncode != 0:
        raise TaskBlocked("git_failed", out.stderr.strip()[:400])
    return out.stdout.strip()


RESUMABLE_STATES = frozenset({"needs_evidence", "blocked", "paused"})


def policy_from_options(
    name: str, sink_url: str | None, state_dir: Path
) -> tuple[RunPolicy | None, PolicyFactory | None]:
    """CLI wiring for the PRD §9 spend gate: "local" enforces the
    packet's own budget and emits telemetry to the sink (buffered when
    unreachable); "required" fails closed; anything else is no policy."""
    if name == "required":
        return RequiredMinderPolicy(
            "operator requires external minder decisions"
        ), None
    if name == "local":
        events = MinderEvents(
            state_dir=Path(state_dir) / "minder",
            sink_url=sink_url,
            buffer_dir=Path(state_dir) / "minder-buffer",
        )

        def factory(journal, run_id, packet):
            return LocalPolicy(
                journal,
                run_id,
                max_attempts=packet.budget["max_attempts"],
                events=events,
            )

        return None, factory
    return None, None


def cancel_run(journal: Journal, run_id: str) -> dict[str, object]:
    """Cancel a non-terminal run; terminal states refuse."""
    state = journal.run_state(run_id)
    if state in ("accepted", "failed", "cancelled"):
        raise TaskBlocked(
            "not_cancellable", f"run is terminal ({state}); nothing to cancel"
        )
    journal.transition(run_id, "cancelled")
    return {"run_id": run_id, "state": "cancelled", "previous_state": state}


def _consult_policy(
    policy: RunPolicy,
    journal: Journal,
    run_id: str,
    attempt: int,
    seen: set[str],
) -> Decision:
    """Ask the policy authority for a decision and validate it before the
    caller may act. Any rejection blocks escalation (PRD §9: fail closed)."""
    basis = [str(e["event_id"]) for e in journal.events(run_id)[-2:]]
    try:
        decision = policy.decide(
            attempt=attempt, basis_event_ids=basis, run_id=run_id
        )
        validate_decision(decision, run_id=run_id, seen=seen)
    except PolicyBlocked as exc:
        raise TaskBlocked("policy_unavailable", str(exc)) from exc
    return decision


def _emit_verdict_event(
    policy: RunPolicy,
    packet: Packet,
    run_id: str,
    attempt: int,
    verdict: dict[str, object],
    evidence_dir: Path,
) -> None:
    """Telemetry only (PRD §9): the trusted controller records the verdict
    as an artifact and emits a namespaced event bound to its digest."""
    if policy.events is None:
        return
    run_dir = Path(evidence_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "verdict.json"
    path.write_text(
        json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    verdict_name = {"PASS": "passed", "FAIL": "failed"}.get(
        str(verdict.get("verdict", "")), "unknown"
    )
    fields: dict[str, object] = {
        "schema_version": 1,
        "attempt": attempt,
        "producer": "trusted-verifier",
        "evidence_ref": f"{run_id}/verdict.json",
        "evidence_sha256": digest,
    }
    if verdict_name != "passed":
        fields["failure_signature"] = str(verdict.get("reason_code", "unknown"))
    policy.events.emit(
        packet.task_id,
        f"verification.{verdict_name}",
        run_id=run_id,
        event_id=f"{run_id}:verdict:{str(verdict.get('result_digest', ''))[:16]}",
        **fields,
    )


def _consult_or_block(
    policy: RunPolicy,
    journal: Journal,
    run_id: str,
    attempt: int,
    seen: set[str],
) -> Decision:
    """Consult the policy; an unavailable required decision parks the run
    in blocked before raising — fail closed with state preserved."""
    try:
        return _consult_policy(policy, journal, run_id, attempt, seen)
    except TaskBlocked as exc:
        if exc.reason_code == "policy_unavailable" and journal.run_state(
            run_id
        ) != "blocked":
            journal.transition(run_id, "blocked")
        raise


def run_packet(
    packet_path: Path,
    repo: Path,
    work_root: Path,
    journal: Journal,
    worker: WorkerFn | None = None,
    graders: list[Path] | None = None,
    profile_prompt_renderer: Callable[[Packet], str] | None = None,
    resume: bool = False,
    evidence_dir: Path | None = None,
    policy: RunPolicy | None = None,
    policy_factory: PolicyFactory | None = None,
    memory_store=None,
    idempotency_suffix: str = "",
) -> dict[str, object]:
    from repo_agent.packets import load, render_prompt

    packet = load(packet_path)
    if worker is not None:
        worker_fn: WorkerFn = worker
    else:

        def worker_fn(prompt: str, workspace: Path) -> DshRun:
            from repo_agent.adapters.dsh import run_task

            return run_task(
                prompt,
                timeout_seconds=packet.budget["timeout_seconds"],
                cwd=workspace,
            )

    grader_paths = graders if graders is not None else []
    repo = Path(repo)
    work_root = Path(work_root)

    run_id = journal.create_run(
        task_id=packet.task_id,
        idempotency_key=f"task:{packet.task_id}:{packet.base_commit}"
        + idempotency_suffix,
    )
    journal.set_run_context(
        run_id,
        str(Path(packet_path).resolve()),
        str(repo.resolve()),
        model_profile=os.environ.get("REPO_AGENT_MODEL_PROFILE", "unrecorded"),
    )
    if policy is None and policy_factory is not None:
        policy = policy_factory(journal, run_id, packet)
    seen_decisions: set[str] = set()
    policy_trace: list[dict[str, object]] = []
    if evidence_dir is None and policy is not None and policy.events is not None:
        evidence_dir = work_root / "evidence"
    state = journal.run_state(run_id)
    if state != "created":
        if not resume:
            raise TaskBlocked(
                "run_not_resumable",
                f"run {run_id} already exists in state {state!r}; "
                "pass resume=True to continue it",
            )
        if state not in RESUMABLE_STATES:
            raise TaskBlocked(
                "not_resumable",
                f"run is in {state!r}; only {sorted(RESUMABLE_STATES)} resume",
            )
    else:
        journal.transition(run_id, "preflight")

    head = _git(repo, "rev-parse", "HEAD")
    blocked_reason = None
    if head != packet.base_commit:
        blocked_reason = (
            "base_mismatch",
            f"packet pins {packet.base_commit[:12]}, repo HEAD is {head[:12]}",
        )
    elif _git(repo, "status", "--porcelain"):
        blocked_reason = ("dirty_repo", "refusing to stage a dirty repository")
    if blocked_reason is not None:
        if journal.run_state(run_id) != "blocked":
            journal.transition(run_id, "blocked")
        raise TaskBlocked(*blocked_reason)

    used = journal.run_context(run_id)["attempts_used"]
    assert isinstance(used, int)
    attempts_used = used
    max_attempts = packet.budget["max_attempts"]
    if attempts_used >= max_attempts:
        raise TaskBlocked(
            "budget_exhausted",
            f"{attempts_used} of {max_attempts} attempts already spent",
        )

    if policy is not None:
        decision = _consult_or_block(
            policy, journal, run_id, attempts_used, seen_decisions
        )
        policy_trace.append({"attempt": attempts_used, "action": decision.action})
        if decision.action not in ("continue", "retry_with_evidence"):
            if journal.run_state(run_id) != "blocked":
                journal.transition(run_id, "blocked")
            raise TaskBlocked(
                f"policy_{decision.action}",
                f"policy refused dispatch: {decision.action} "
                f"({decision.reason_code})",
            )

    if state == "created":
        journal.transition(run_id, "baselined")
        journal.transition(run_id, "contracted")
    journal.transition(run_id, "running")

    workspace = stage_workspace(repo, work_root)
    base_prompt = (profile_prompt_renderer or render_prompt)(packet)
    injection_record = None
    if memory_store is not None:
        from repo_agent.retrieval import inject_memories

        base_prompt, injection_record = inject_memories(
            memory_store, journal, run_id, base_prompt, packet.goal,
            str(repo.resolve()),
        )
    verifier = Verifier(repo, work_root / "verify", journal, run_id)
    attempts = attempts_used
    evidence = ""
    dispatch = None
    verdict: dict[str, object] = {}
    patch_digest = ""
    while attempts < max_attempts:
        attempts = journal.bump_attempts(run_id)
        dispatch = worker_fn(base_prompt + evidence, workspace)
        journal.transition(run_id, "verifying")
        patch_digest = verifier.freeze(workspace)
        verdict = verifier.verify(
            checks=packet.verification_commands,
            graders=grader_paths,
            timeout_seconds=packet.budget["timeout_seconds"],
        )
        if policy is not None and evidence_dir is not None:
            _emit_verdict_event(
                policy, packet, run_id, attempts, verdict, Path(evidence_dir)
            )
        if verdict["verdict"] == "PASS":
            journal.transition(run_id, "reviewing")
            journal.transition(run_id, "accepted")
            break
        if attempts >= max_attempts:
            journal.transition(run_id, "needs_evidence")
            break
        journal.transition(run_id, "needs_evidence")
        if policy is not None:
            decision = _consult_or_block(
                policy, journal, run_id, attempts, seen_decisions
            )
            policy_trace.append({"attempt": attempts, "action": decision.action})
            if decision.action == "stop":
                journal.transition(run_id, "failed")
                break
            if decision.action == "pause":
                journal.transition(run_id, "blocked")
                break
            if decision.action == "consult_frontier":
                journal.transition(run_id, "escalating")
                break
            # continue / retry_with_evidence: spend another attempt
        failure_tail = str(
            verdict.get("grader_output") or verdict.get("detail") or ""
        )[-2000:]
        evidence = (
            "\n\nYour previous attempt did not pass verification. Failure "
            "output (tail):\n" + failure_tail + "\nFix and hand off again."
        )
        journal.transition(run_id, "running")

    changed = verifier.frozen_changed_files()
    assert dispatch is not None
    handoff = {
        "task_id": packet.task_id,
        "run_id": run_id,
        "base_commit": packet.base_commit,
        "changed_paths": changed,
        "patch_digest": patch_digest,
        "verdict": verdict["verdict"],
        "reason_code": verdict["reason_code"],
        "result_digest": verdict["result_digest"],
        "attempts": attempts,
        "model_profile": os.environ.get(
            "REPO_AGENT_MODEL_PROFILE", "unrecorded"
        ),
        "usage": dispatch.usage,
        "session_id": dispatch.session_id,
        "worker_final": dispatch.final_text,
        "acceptance": list(packet.acceptance),
    }
    if policy is not None:
        handoff["policy"] = {
            "decisions": policy_trace,
            "telemetry": (
                policy.events.status() if policy.events is not None else None
            ),
        }
    if evidence_dir is not None:
        run_dir = Path(evidence_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "handoff.json").write_text(
            json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (run_dir / "events.jsonl").write_text(
            "".join(
                json.dumps(event, sort_keys=True) + "\n"
                for event in journal.events(run_id)
            ),
            encoding="utf-8",
        )
    return handoff
