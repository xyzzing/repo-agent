"""RA-010/RA-013: the independent evaluator (PRD §3, §11).

A versioned eval plan (closed schema, packets.py discipline) drives
task packets through the ordinary protected lifecycle; the controller —
never the worker — writes the manifest that binds plan, packet and
grader digests to each task's patch/result digests, verdict and cost.
Evaluation works with the policy authority fully off (PRD §9); a plan
may opt an arm into a policy configuration (PRD §11's configuration
comparison), which is then versioned in the plan digest and recorded
in the manifest. Comparison semantics live in eval_compare.
"""
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from yaml.constructor import ConstructorError
from yaml.error import YAMLError

from repo_agent.packets import PacketError
from repo_agent.packets import load as load_packet
from repo_agent.state import Journal
from repo_agent.taskrun import TaskBlocked, policy_from_options, run_packet

PLAN_FIELDS = {
    "eval_schema_version", "eval_id", "description", "tasks",
    "default_repo", "policy",
}
TASK_FIELDS = {"packet", "grader", "repo", "family", "split"}
POLICIES = ("none", "local", "required")
SPLITS = ("dev", "holdout")


class PlanError(Exception):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


@dataclass(frozen=True)
class EvalTask:
    task_id: str
    packet: Path
    grader: Path | None
    packet_digest: str
    grader_digest: str | None
    repo: Path | None = None
    family: str | None = None
    split: str | None = None


@dataclass(frozen=True)
class EvalPlan:
    eval_id: str
    description: str
    tasks: tuple[EvalTask, ...]
    plan_digest: str
    policy: str = "none"


def _no_dupes(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[object, object]:
    seen: set[object] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in seen:
            raise PlanError("duplicate_key", f"key {key!r} appears twice")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=True)


class _PlanLoader(yaml.SafeLoader):
    pass


_PlanLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dupes
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(base: Path, raw: object, where: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise PlanError("invalid_type", f"{where} must be a nonempty path string")
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return base / candidate


def load_plan(path: Path) -> EvalPlan:
    """Validate the plan and every referenced packet up front: a plan
    that cannot fully parse never reaches a worker."""
    path = Path(path)
    try:
        raw_bytes = path.read_bytes()
        document = yaml.load(raw_bytes.decode("utf-8"), Loader=_PlanLoader)
    except ConstructorError as exc:
        raise PlanError("unsafe_tag", str(exc.problem)) from None
    except YAMLError as exc:
        message = str(exc)
        reason = "duplicate_key" if "appears twice" in message else "invalid_yaml"
        raise PlanError(reason, message) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise PlanError("unreadable_plan", str(exc)) from None
    if not isinstance(document, dict):
        raise PlanError("invalid_yaml", "top level must be a mapping")
    unknown = set(document) - PLAN_FIELDS
    if unknown:
        raise PlanError("unknown_field", f"unknown keys: {sorted(unknown)}")
    if document.get("eval_schema_version") != 1:
        raise PlanError(
            "unsupported_version",
            f"eval_schema_version {document.get('eval_schema_version')!r} "
            "not supported",
        )
    eval_id = document.get("eval_id")
    if not isinstance(eval_id, str) or not eval_id.strip():
        raise PlanError("invalid_type", "eval_id must be a nonempty string")
    description = document.get("description", "")
    if not isinstance(description, str):
        raise PlanError("invalid_type", "description must be a string")
    tasks_raw = document.get("tasks")
    if not isinstance(tasks_raw, list) or not tasks_raw:
        raise PlanError("empty_plan", "tasks must be a nonempty list")
    base = path.resolve().parent
    policy = document.get("policy", "none")
    if policy not in POLICIES:
        raise PlanError(
            "invalid_policy",
            f"policy must be one of {list(POLICIES)}, not {policy!r}",
        )
    default_repo: Path | None = None
    if document.get("default_repo") is not None:
        default_repo = _resolve(
            base, document.get("default_repo"), "default_repo"
        )
        if not default_repo.is_dir():
            raise PlanError(
                "missing_repo", f"default_repo is not a directory: {default_repo}"
            )

    tasks: list[EvalTask] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(tasks_raw):
        if not isinstance(entry, dict):
            raise PlanError("invalid_type", f"tasks[{index}] must be a mapping")
        unknown_task = set(entry) - TASK_FIELDS
        if unknown_task:
            raise PlanError(
                "unknown_field", f"unknown task keys: {sorted(unknown_task)}"
            )
        packet_path = _resolve(base, entry.get("packet"), f"tasks[{index}].packet")
        if not packet_path.is_file():
            raise PlanError(
                "missing_packet", f"no packet file at {packet_path}"
            )
        try:
            packet = load_packet(packet_path)
        except PacketError as exc:
            raise PlanError("invalid_packet", str(exc)) from None
        if packet.task_id in seen_ids:
            raise PlanError(
                "duplicate_task", f"task_id {packet.task_id!r} appears twice"
            )
        seen_ids.add(packet.task_id)
        grader_path: Path | None = None
        if entry.get("grader") is not None:
            grader_path = _resolve(base, entry.get("grader"),
                                   f"tasks[{index}].grader")
            if not grader_path.is_file():
                raise PlanError(
                    "missing_grader", f"no grader file at {grader_path}"
                )
        task_repo: Path | None = default_repo
        if entry.get("repo") is not None:
            task_repo = _resolve(base, entry.get("repo"), f"tasks[{index}].repo")
            if not task_repo.is_dir():
                raise PlanError(
                    "missing_repo", f"tasks[{index}].repo is not a directory"
                )
        # A repo-less task is legal only when run_plan receives a
        # caller-supplied repo; that refusal happens at run time.
        family = entry.get("family")
        if family is not None and (not isinstance(family, str) or not family):
            raise PlanError("invalid_type", "family must be a nonempty string")
        split = entry.get("split")
        if split is not None and split not in SPLITS:
            raise PlanError(
                "invalid_type", f"split must be one of {list(SPLITS)}, not {split!r}"
            )
        tasks.append(
            EvalTask(
                task_id=packet.task_id,
                packet=packet_path,
                grader=grader_path,
                packet_digest=_digest(packet_path),
                grader_digest=_digest(grader_path) if grader_path else None,
                repo=task_repo,
                family=family,
                split=split,
            )
        )
    return EvalPlan(
        eval_id=eval_id,
        description=description,
        tasks=tuple(tasks),
        plan_digest=_digest(path),
        policy=policy,
    )


def _task_entry(
    plan_task: EvalTask,
    journal: Journal,
    handoff: dict[str, object] | None,
    wall_seconds: float,
    blocked: TaskBlocked | None,
) -> dict[str, object]:
    run_id: str | None
    if handoff is not None:
        run_id = str(handoff["run_id"])
        entry: dict[str, object] = {
            "task_id": plan_task.task_id,
            "packet": str(plan_task.packet),
            "packet_digest": plan_task.packet_digest,
            "grader": (
                plan_task.grader.name if plan_task.grader else None
            ),
            "grader_digest": plan_task.grader_digest,
            "family": plan_task.family,
            "split": plan_task.split,
            "repo": str(plan_task.repo) if plan_task.repo else None,
            "run_id": run_id,
            "state": journal.run_state(run_id),
            "verdict": handoff["verdict"],
            "reason_code": handoff["reason_code"],
            "patch_digest": handoff["patch_digest"],
            "result_digest": handoff["result_digest"],
            "attempts": handoff["attempts"],
            "usage": handoff["usage"],
            "wall_seconds": round(wall_seconds, 3),
        }
        return entry
    runs = [r for r in journal.runs() if r["task_id"] == plan_task.task_id]
    run_id = str(runs[-1]["run_id"]) if runs else None
    return {
        "task_id": plan_task.task_id,
        "packet": str(plan_task.packet),
        "packet_digest": plan_task.packet_digest,
        "grader": plan_task.grader.name if plan_task.grader else None,
        "grader_digest": plan_task.grader_digest,
        "family": plan_task.family,
        "split": plan_task.split,
        "repo": str(plan_task.repo) if plan_task.repo else None,
        "run_id": run_id,
        "state": journal.run_state(run_id) if run_id else None,
        "verdict": "BLOCKED",
        "reason_code": blocked.reason_code if blocked else "unknown",
        "detail": blocked.detail if blocked else "",
        "patch_digest": None,
        "result_digest": None,
        "attempts": 0,
        "usage": None,
        "wall_seconds": round(wall_seconds, 3),
    }


def run_plan(
    plan_path: Path,
    out_dir: Path,
    repo: Path | None = None,
    worker=None,
) -> dict[str, object]:
    """Execute every task in the plan and write the manifest. The output
    directory is a fresh experiment space: an existing manifest is never
    overwritten, and the journal is local to this eval run. Each task
    runs against its own repo (plan default_repo unless the task names
    one); `repo` overrides the plan default and is refused when tasks
    carry their own."""
    plan = load_plan(plan_path)
    out_dir = Path(out_dir)
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        raise PlanError(
            "output_exists",
            f"{manifest_path} already exists; use a fresh output directory",
        )
    if repo is not None and any(t.repo is not None for t in plan.tasks):
        raise PlanError(
            "repo_conflict",
            "the plan resolves its own repos; a blanket --repo would "
            "silently override pinned task repos",
        )
    if repo is None and any(t.repo is None for t in plan.tasks):
        raise PlanError(
            "missing_repo",
            "the plan expects a caller-supplied repo (no default_repo, "
            "and at least one task names none)",
        )
    effective_repo = Path(repo) if repo is not None else None
    out_dir.mkdir(parents=True, exist_ok=True)
    journal = Journal(out_dir / "journal.sqlite")
    policy, policy_factory = policy_from_options(
        plan.policy, None, out_dir
    )

    entries: list[dict[str, object]] = []
    for plan_task in plan.tasks:
        started = time.monotonic()
        handoff: dict[str, object] | None = None
        blocked: TaskBlocked | None = None
        task_repo = plan_task.repo or effective_repo
        assert task_repo is not None, "load_plan guarantees a repo per task"
        try:
            handoff = run_packet(
                plan_task.packet,
                repo=Path(task_repo),
                work_root=out_dir / "work",
                journal=journal,
                worker=worker,
                graders=[plan_task.grader] if plan_task.grader else [],
                evidence_dir=out_dir / "runs",
                policy=policy,
                policy_factory=policy_factory,
            )
        except TaskBlocked as exc:
            blocked = exc
        entry = _task_entry(
            plan_task,
            journal,
            handoff,
            time.monotonic() - started,
            blocked,
        )
        entries.append(entry)

    aggregate = {
        "total": len(entries),
        "passed": sum(1 for e in entries if e["verdict"] == "PASS"),
        "failed": sum(1 for e in entries if e["verdict"] == "FAIL"),
        "blocked": sum(1 for e in entries if e["verdict"] == "BLOCKED"),
    }
    manifest: dict[str, object] = {
        "command": "eval run",
        "eval_id": plan.eval_id,
        "description": plan.description,
        "plan_digest": plan.plan_digest,
        "policy": plan.policy,
        "tasks": entries,
        "aggregate": aggregate,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest
