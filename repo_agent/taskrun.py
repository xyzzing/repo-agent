"""RA-008: the authorized task-run lifecycle (PRD §6, §10).

One packet, one worker, one protected verdict. The journal records every
transition; the worker's prose and any file it writes are observations,
never authority: acceptance comes only from the protected verifier bound
to the frozen patch digest. Preflight refuses a moved base (base_mismatch)
or a dirty repo (dirty_repo) before the worker spends anything.
"""
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from repo_agent.adapters.dsh import DshRun
from repo_agent.packets import Packet
from repo_agent.state import Journal
from repo_agent.verifier import Verifier, stage_workspace

WorkerFn = Callable[[str, Path], DshRun]


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


def cancel_run(journal: Journal, run_id: str) -> dict[str, object]:
    """Cancel a non-terminal run; terminal states refuse."""
    state = journal.run_state(run_id)
    if state in ("accepted", "failed", "cancelled"):
        raise TaskBlocked(
            "not_cancellable", f"run is terminal ({state}); nothing to cancel"
        )
    journal.transition(run_id, "cancelled")
    return {"run_id": run_id, "state": "cancelled", "previous_state": state}


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
        idempotency_key=f"task:{packet.task_id}:{packet.base_commit}",
    )
    journal.set_run_context(
        run_id, str(Path(packet_path).resolve()), str(repo.resolve())
    )
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

    if state == "created":
        journal.transition(run_id, "baselined")
        journal.transition(run_id, "contracted")
    journal.transition(run_id, "running")

    workspace = stage_workspace(repo, work_root)
    base_prompt = (profile_prompt_renderer or render_prompt)(packet)
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
        if verdict["verdict"] == "PASS":
            journal.transition(run_id, "reviewing")
            journal.transition(run_id, "accepted")
            break
        if attempts >= max_attempts:
            journal.transition(run_id, "needs_evidence")
            break
        journal.transition(run_id, "needs_evidence")
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
        "usage": dispatch.usage,
        "session_id": dispatch.session_id,
        "worker_final": dispatch.final_text,
        "acceptance": list(packet.acceptance),
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
