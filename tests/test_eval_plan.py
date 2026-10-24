"""RA-013: eval-plan extensions — per-task repos, family/split labels,
and a versioned policy field so an arm's configuration lives in the
plan digest and its manifests stay comparable.
"""
import subprocess
from pathlib import Path

import pytest

from repo_agent import evaluate

BASE_CALC = "def add(a, b):\n    return a - b\n"
FIX_CALC = "def add(a, b):\n    return a + b\n"
PACKET = """
task_schema_version: 1
task_id: 'TID'
base_commit: 'BASE'
goal: 'Make add add'
read_first: [calc.py]
expected_write_scope: [calc.py]
acceptance:
  - 'calc.add(2, 2) returns 4'
invariants: []
non_goals: []
verification_commands:
  - [python3, -c, "import calc; assert calc.add(2,2)==4"]
budget:
  max_attempts: 1
  timeout_seconds: 300
required_skills: []
escalate_when: []
"""


def git(repo: Path, *argv: str) -> str:
    out = subprocess.run(
        ["git", *argv], cwd=repo, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def make_repo(tmp_path: Path, name: str) -> tuple[Path, Path]:
    repo = tmp_path / name
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "calc.py").write_text(BASE_CALC, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
    head = git(repo, "rev-parse", "HEAD")
    packet = tmp_path / f"{name}-packet.yaml"
    packet.write_text(
        PACKET.replace("TID", f"task-{name}").replace("BASE", head), encoding="utf-8"
    )
    return repo, packet


def write_plan(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


# --- schema: per-task repo, family, split; plan-level policy ---------


def test_plan_task_may_carry_repo_family_split(tmp_path):
    repo_a, packet_a = make_repo(tmp_path, "alpha")
    repo_b, packet_b = make_repo(tmp_path, "beta")
    plan = write_plan(
        tmp_path / "plan.yaml",
        "eval_schema_version: 1\n"
        "eval_id: two-repos\n"
        "tasks:\n"
        f"  - packet: {packet_a}\n"
        f"    repo: {repo_a}\n"
        "    family: bugfix\n"
        "    split: dev\n"
        f"  - packet: {packet_b}\n"
        f"    repo: {repo_b}\n"
        "    family: bugfix\n"
        "    split: holdout\n",
    )
    loaded = evaluate.load_plan(plan)
    assert loaded.tasks[0].repo == repo_a
    assert loaded.tasks[0].family == "bugfix"
    assert loaded.tasks[0].split == "dev"
    assert loaded.tasks[1].split == "holdout"


def test_plan_rejects_unknown_task_field(tmp_path):
    repo, packet = make_repo(tmp_path, "alpha")
    plan = write_plan(
        tmp_path / "plan.yaml",
        "eval_schema_version: 1\n"
        "eval_id: bad\n"
        "tasks:\n"
        f"  - packet: {packet}\n"
        "    oops: true\n",
    )
    with pytest.raises(evaluate.PlanError, match="unknown_field"):
        evaluate.load_plan(plan)


def test_plan_rejects_unknown_family_or_split(tmp_path):
    repo, packet = make_repo(tmp_path, "alpha")
    plan = write_plan(
        tmp_path / "plan.yaml",
        "eval_schema_version: 1\n"
        "eval_id: bad\n"
        "tasks:\n"
        f"  - packet: {packet}\n"
        "    family: bugfix\n"
        "    split: sometimes\n",
    )
    with pytest.raises(evaluate.PlanError, match="invalid_type"):
        evaluate.load_plan(plan)


def test_plan_policy_field_validated_and_defaulted(tmp_path):
    repo, packet = make_repo(tmp_path, "alpha")
    body = (
        "eval_schema_version: 1\n"
        "eval_id: p\n"
        "tasks:\n"
        f"  - packet: {packet}\n"
        f"    repo: {repo}\n"
    )
    loaded = evaluate.load_plan(write_plan(tmp_path / "p1.yaml", body))
    assert loaded.policy == "none"
    loaded = evaluate.load_plan(
        write_plan(tmp_path / "p2.yaml", body.replace("eval_id: p", "eval_id: p\npolicy: local"))
    )
    assert loaded.policy == "local"
    with pytest.raises(evaluate.PlanError, match="invalid_policy"):
        evaluate.load_plan(
            write_plan(
                tmp_path / "p3.yaml",
                body.replace("eval_id: p", "eval_id: p\npolicy: aggressive"),
            )
        )


def test_task_without_repo_falls_back_to_plan_default(tmp_path):
    repo, packet = make_repo(tmp_path, "alpha")
    plan = write_plan(
        tmp_path / "plan.yaml",
        "eval_schema_version: 1\n"
        f"default_repo: {repo}\n"
        "eval_id: d\n"
        "tasks:\n"
        f"  - packet: {packet}\n",
    )
    loaded = evaluate.load_plan(plan)
    assert loaded.tasks[0].repo == repo
    # repo-less tasks load fine (a caller may supply the repo) but
    # refuse to RUN without one
    bare = write_plan(
        tmp_path / "plan2.yaml",
        "eval_schema_version: 1\n"
        "eval_id: d2\n"
        "tasks:\n"
        f"  - packet: {packet}\n",
    )
    assert evaluate.load_plan(bare).tasks[0].repo is None
    with pytest.raises(evaluate.PlanError, match="missing_repo"):
        evaluate.run_plan(bare, out_dir=tmp_path / "out2", worker=_GoodWorker())


# --- run_plan drives per-task repos and records family/split/policy ----


class _GoodWorker:
    def __call__(self, prompt: str, workspace: Path):
        from repo_agent.adapters.dsh import DshRun

        (workspace / "calc.py").write_text(FIX_CALC, encoding="utf-8")
        return DshRun(
            final_text="fixed", session_id="s", events=[],
            usage={"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
            returncode=0,
        )


def test_run_plan_uses_each_task_repo_and_labels_entries(tmp_path):
    repo_a, packet_a = make_repo(tmp_path, "alpha")
    repo_b, packet_b = make_repo(tmp_path, "beta")
    plan = write_plan(
        tmp_path / "plan.yaml",
        "eval_schema_version: 1\n"
        "eval_id: two\n"
        "tasks:\n"
        f"  - packet: {packet_a}\n"
        f"    repo: {repo_a}\n"
        "    family: bugfix\n"
        "    split: dev\n"
        f"  - packet: {packet_b}\n"
        f"    repo: {repo_b}\n"
        "    family: bugfix\n"
        "    split: holdout\n",
    )
    manifest = evaluate.run_plan(
        plan, out_dir=tmp_path / "out", worker=_GoodWorker()
    )
    assert manifest["policy"] == "none"
    entries = {t["task_id"]: t for t in manifest["tasks"]}
    assert entries["task-alpha"]["verdict"] == "PASS"
    assert entries["task-beta"]["verdict"] == "PASS"
    assert entries["task-alpha"]["family"] == "bugfix"
    assert entries["task-alpha"]["split"] == "dev"
    assert entries["task-beta"]["split"] == "holdout"
    # each task actually ran against its own repo
    assert entries["task-alpha"]["repo"] == str(repo_a)
    assert entries["task-beta"]["repo"] == str(repo_b)
    assert entries["task-alpha"]["run_id"] != entries["task-beta"]["run_id"]


def test_run_plan_policy_none_never_touches_minder_paths(tmp_path):
    repo, packet = make_repo(tmp_path, "alpha")
    plan = write_plan(
        tmp_path / "plan.yaml",
        "eval_schema_version: 1\n"
        "eval_id: isolated\n"
        "tasks:\n"
        f"  - packet: {packet}\n"
        f"    repo: {repo}\n",
    )
    out = tmp_path / "out"
    evaluate.run_plan(plan, out_dir=out, worker=_GoodWorker())
    assert not (out / "minder").exists()
    assert not list(out.glob("minder*"))
