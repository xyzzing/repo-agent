"""RA-010: the independent evaluator — plan validation, trusted
manifest, and the integrity regressions PRD §13 pins on RA-010.

The controller owns every verdict: a worker that forges an accepted
result file, tampers with grader paths, or claims success in prose
still lands whatever the protected verifier says. Grader content never
reaches the worker's prompt or workspace. The manifest binds plan,
packet and grader digests to patch and result digests so a later
mutation cannot inherit an old verdict. Minder is off in the eval path.
"""
import hashlib
import json
import stat
import subprocess
from pathlib import Path

import pytest

from repo_agent import evaluate
from repo_agent.adapters.dsh import DshRun

BASE_CALC = "def add(a, b):\n    return a - b\n"
FIX_CALC = "def add(a, b):\n    return a + b\n"
PACKET = """
task_schema_version: 1
task_id: fix-add
base_commit: 'BASE'
goal: 'Make calc.add add instead of subtract'
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
  timeout_seconds: 600
required_skills: []
escalate_when: []
"""
GRADER = """#!/bin/sh
cd "$VERIFIER_ROOT"
python3 -c "import calc; assert calc.add(2,2)==4"
"""


def git(repo: Path, *argv: str) -> str:
    out = subprocess.run(
        ["git", *argv], cwd=repo, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "calc.py").write_text(BASE_CALC, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
    return root


@pytest.fixture()
def grader(tmp_path: Path) -> Path:
    path = tmp_path / "grader.sh"
    path.write_text(GRADER, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def write_plan(
    tmp_path: Path,
    repo: Path,
    grader: Path | None,
    *,
    raw: str | None = None,
    task_id: str = "fix-add",
) -> Path:
    head = git(repo, "rev-parse", "HEAD")
    packet = tmp_path / "packet.yaml"
    packet.write_text(
        PACKET.replace("BASE", head).replace("fix-add", task_id), encoding="utf-8"
    )
    if raw is not None:
        plan = tmp_path / "plan.yaml"
        plan.write_text(raw, encoding="utf-8")
        return plan
    grader_line = f"\n    grader: {grader}" if grader else ""
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        "eval_schema_version: 1\n"
        "eval_id: smoke-1\n"
        "description: one-task smoke\n"
        "tasks:\n"
        f"  - packet: {packet}{grader_line}\n",
        encoding="utf-8",
    )
    return plan


def dsh_run(text: str) -> DshRun:
    return DshRun(
        final_text=text, session_id="session-fake", events=[],
        usage={"inputTokens": 10, "outputTokens": 2, "totalTokens": 12},
        returncode=0,
    )


def good_worker(prompt: str, workspace: Path) -> DshRun:
    (workspace / "calc.py").write_text(FIX_CALC, encoding="utf-8")
    return dsh_run("fixed")


def idle_worker(prompt: str, workspace: Path) -> DshRun:
    return dsh_run("did nothing")


# --- plan validation (fail before any worker spend) ----------------------


def test_plan_rejects_unknown_field(tmp_path: Path, repo: Path):
    plan = write_plan(tmp_path, repo, None)
    text = plan.read_text(encoding="utf-8")
    plan.write_text(text + "surprise: true\n", encoding="utf-8")
    with pytest.raises(evaluate.PlanError, match="unknown_field"):
        evaluate.load_plan(plan)


def test_plan_rejects_duplicate_keys(tmp_path: Path, repo: Path):
    plan = write_plan(tmp_path, repo, None)
    text = plan.read_text(encoding="utf-8")
    plan.write_text(text + "eval_id: smoke-2\n", encoding="utf-8")
    with pytest.raises(evaluate.PlanError, match="duplicate_key"):
        evaluate.load_plan(plan)


def test_plan_rejects_bad_version_and_empty_tasks(tmp_path: Path, repo: Path):
    plan = write_plan(tmp_path, repo, None)
    text = plan.read_text(encoding="utf-8")
    plan.write_text(text.replace("eval_schema_version: 1", "eval_schema_version: 9"),
                    encoding="utf-8")
    with pytest.raises(evaluate.PlanError, match="unsupported_version"):
        evaluate.load_plan(plan)
    empty = tmp_path / "empty.yaml"
    empty.write_text(
        "eval_schema_version: 1\neval_id: e\ntasks: []\n", encoding="utf-8"
    )
    with pytest.raises(evaluate.PlanError, match="empty_plan"):
        evaluate.load_plan(empty)


def test_plan_rejects_missing_packet_file(tmp_path: Path, repo: Path):
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        "eval_schema_version: 1\neval_id: e\n"
        "tasks:\n  - packet: /nonexistent/packet.yaml\n",
        encoding="utf-8",
    )
    with pytest.raises(evaluate.PlanError, match="missing_packet"):
        evaluate.load_plan(plan)


def test_plan_rejects_duplicate_task_ids(tmp_path: Path, repo: Path):
    plan = write_plan(tmp_path, repo, None)
    text = plan.read_text(encoding="utf-8")
    plan.write_text(text + f"  - packet: {tmp_path / 'packet.yaml'}\n",
                    encoding="utf-8")
    with pytest.raises(evaluate.PlanError, match="duplicate_task"):
        evaluate.load_plan(plan)


# --- trusted manifest -----------------------------------------------------


def test_manifest_records_pass_with_digests(
    tmp_path: Path, repo: Path, grader: Path
):
    plan = write_plan(tmp_path, repo, grader)
    manifest = evaluate.run_plan(
        plan, repo=repo, out_dir=tmp_path / "out", worker=good_worker
    )
    assert manifest["command"] == "eval run"
    assert manifest["policy"] == "none"
    assert manifest["plan_digest"] == hashlib.sha256(
        plan.read_bytes()
    ).hexdigest()
    task = manifest["tasks"][0]
    assert task["verdict"] == "PASS"
    assert task["patch_digest"] and task["result_digest"]
    assert task["packet_digest"] == hashlib.sha256(
        Path(task["packet"]).read_bytes()
    ).hexdigest()
    assert task["usage"]["totalTokens"] == 12
    assert task["wall_seconds"] >= 0
    assert manifest["aggregate"] == {"total": 1, "passed": 1, "failed": 0,
                                     "blocked": 0}
    on_disk = json.loads(
        (tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")
    )
    assert on_disk == manifest, "the controller writes the manifest"


def test_manifest_records_fail_with_reason(tmp_path: Path, repo: Path,
                                           grader: Path):
    plan = write_plan(tmp_path, repo, grader)
    manifest = evaluate.run_plan(
        plan, repo=repo, out_dir=tmp_path / "out", worker=idle_worker
    )
    task = manifest["tasks"][0]
    assert task["verdict"] == "FAIL"
    assert task["reason_code"] == "check_failed"
    assert manifest["aggregate"]["failed"] == 1


def test_eval_runs_without_minder(tmp_path: Path, repo: Path, grader: Path):
    plan = write_plan(tmp_path, repo, grader)
    manifest = evaluate.run_plan(
        plan, repo=repo, out_dir=tmp_path / "out", worker=good_worker
    )
    assert manifest["policy"] == "none"
    assert not (tmp_path / "out" / "minder").exists()
    assert not list((tmp_path / "out").glob("minder*"))
    journal = manifest["tasks"][0]
    assert "policy" not in json.loads(
        (tmp_path / "out" / "runs" / journal["run_id"] / "handoff.json")
        .read_text(encoding="utf-8")
    )


def test_blocked_task_is_recorded_and_run_continues(
    tmp_path: Path, repo: Path, grader: Path
):
    stale = tmp_path / "stale.yaml"
    stale.write_text(
        PACKET.replace("BASE", "0123456789abcdef0123456789abcdef01234567")
        .replace("task_id: fix-add", "task_id: fix-add-stale"),
        encoding="utf-8",
    )
    fresh_packet = tmp_path / "packet.yaml"
    head = git(repo, "rev-parse", "HEAD")
    fresh_packet.write_text(PACKET.replace("BASE", head), encoding="utf-8")
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        "eval_schema_version: 1\neval_id: mixed\n"
        "tasks:\n"
        f"  - packet: {stale}\n  - packet: {fresh_packet}\n",
        encoding="utf-8",
    )
    manifest = evaluate.run_plan(
        plan, repo=repo, out_dir=tmp_path / "out", worker=good_worker
    )
    assert manifest["tasks"][0]["verdict"] == "BLOCKED"
    assert manifest["tasks"][0]["reason_code"] == "base_mismatch"
    assert manifest["tasks"][1]["verdict"] == "PASS"
    assert manifest["aggregate"]["blocked"] == 1
    assert manifest["aggregate"]["passed"] == 1


# --- integrity regressions ------------------------------------------------


def test_forged_worker_result_is_not_acceptance(
    tmp_path: Path, repo: Path, grader: Path
):
    def forging_worker(prompt: str, workspace: Path) -> DshRun:
        (workspace / "result.json").write_text(
            '{"accepted": true, "verdict": "PASS"}', encoding="utf-8"
        )
        return dsh_run("wrote an accepted result; all done")

    plan = write_plan(tmp_path, repo, grader)
    manifest = evaluate.run_plan(
        plan, repo=repo, out_dir=tmp_path / "out", worker=forging_worker
    )
    assert manifest["tasks"][0]["verdict"] == "FAIL", \
        "a worker-written result file is never acceptance authority"


def test_grader_tamper_fails_the_task(tmp_path: Path, repo: Path,
                                      grader: Path):
    def tampering_worker(prompt: str, workspace: Path) -> DshRun:
        (workspace / "calc.py").write_text(FIX_CALC, encoding="utf-8")
        protected = workspace / "graders"
        protected.mkdir()
        (protected / grader.name).write_text("#!/bin/sh\nexit 0\n",
                                             encoding="utf-8")
        return dsh_run("also adjusted the grader to be more lenient")

    plan = write_plan(tmp_path, repo, grader)
    manifest = evaluate.run_plan(
        plan, repo=repo, out_dir=tmp_path / "out", worker=tampering_worker
    )
    assert manifest["tasks"][0]["verdict"] == "FAIL"
    assert manifest["tasks"][0]["reason_code"] == "tampered_grader"


def test_grader_canary_never_reaches_worker(tmp_path: Path, repo: Path,
                                            grader: Path):
    canary = "CANARY-SECRET-HOLDOUT-9f3a"
    grader.write_text(grader.read_text(encoding="utf-8") + f"# {canary}\n",
                      encoding="utf-8")
    seen: list[tuple[str, list[str]]] = []

    def spy_worker(prompt: str, workspace: Path) -> DshRun:
        files = [
            str(p.relative_to(workspace))
            for p in sorted(workspace.rglob("*")) if p.is_file()
        ]
        seen.append((prompt, files))
        return good_worker(prompt, workspace)

    plan = write_plan(tmp_path, repo, grader)
    evaluate.run_plan(plan, repo=repo, out_dir=tmp_path / "out",
                      worker=spy_worker)
    prompt, files = seen[0]
    assert canary not in prompt
    assert "graders" not in " ".join(files), "no grader dir in the workspace"


def test_identical_runs_reproduce_digests(tmp_path: Path, repo: Path,
                                          grader: Path):
    plan = write_plan(tmp_path, repo, grader)
    first = evaluate.run_plan(plan, repo=repo, out_dir=tmp_path / "out1",
                              worker=good_worker)
    second = evaluate.run_plan(plan, repo=repo, out_dir=tmp_path / "out2",
                               worker=good_worker)
    assert first["tasks"][0]["patch_digest"] == \
        second["tasks"][0]["patch_digest"]
    assert first["tasks"][0]["result_digest"] == \
        second["tasks"][0]["result_digest"]


def test_different_patches_bind_to_different_digests(tmp_path: Path,
                                                     repo: Path,
                                                     grader: Path):
    """A manifest result is bound to the exact patch: a different patch
    yields a different patch digest and a different result digest, so a
    mutated patch cannot inherit an old verdict's identity."""
    plan = write_plan(tmp_path, repo, grader)

    def fixed(prompt: str, workspace: Path) -> DshRun:
        (workspace / "calc.py").write_text(FIX_CALC, encoding="utf-8")
        return dsh_run("fixed")

    def fixed_with_comment(prompt: str, workspace: Path) -> DshRun:
        (workspace / "calc.py").write_text(FIX_CALC + "# tuned\n",
                                           encoding="utf-8")
        return dsh_run("fixed, with a comment")

    first = evaluate.run_plan(plan, repo=repo, out_dir=tmp_path / "out1",
                              worker=fixed)
    second = evaluate.run_plan(plan, repo=repo, out_dir=tmp_path / "out2",
                               worker=fixed_with_comment)
    a, b = first["tasks"][0], second["tasks"][0]
    assert a["verdict"] == "PASS" and b["verdict"] == "PASS"
    assert a["patch_digest"] != b["patch_digest"]
    assert a["result_digest"] != b["result_digest"]
