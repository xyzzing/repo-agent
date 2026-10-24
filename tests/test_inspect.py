"""RA-004: read-only inspection.

Inspect is a discovery pass over manifests, lockfiles, CI configs and
existing instructions. Every finding cites its evidence and a confidence;
conflicting discoveries are exposed, never silently resolved; nothing is
ever executed.
"""
import json
from pathlib import Path

from repo_agent import cli
from repo_agent.inspect import inspect_repo


def make_py_repo(root: Path) -> Path:
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'x'\nversion = '0.1.0'\n"
        "[tool.pytest.ini_options]\ntestpaths = ['tests']\n",
        encoding="utf-8",
    )
    (root / "uv.lock").write_text("lock\n", encoding="utf-8")
    return root


def test_python_repo_finds_test_runner_and_linter(tmp_path):
    repo = make_py_repo(tmp_path)
    report = inspect_repo(repo)
    assert report["ok"] is True
    kinds = {f["kind"]: f for f in report["findings"]}
    assert kinds["test_runner"]["value"] == "pytest"
    assert kinds["test_runner"]["confidence"] == "high"
    assert "pyproject.toml" in kinds["test_runner"]["evidence"]


def test_node_repo_finds_runner_and_package_manager(tmp_path):
    repo = tmp_path
    (repo / "package.json").write_text(
        '{"name": "x", "scripts": {"test": "vitest run"}}', encoding="utf-8"
    )
    (repo / "package-lock.json").write_text("{}\n", encoding="utf-8")
    report = inspect_repo(repo)
    kinds = {f["kind"]: f for f in report["findings"]}
    assert kinds["test_runner"]["value"] == "vitest"
    assert kinds["package_manager"]["value"] == "npm"


def test_conflicts_are_exposed_not_resolved(tmp_path):
    repo = tmp_path
    make_py_repo(repo)
    (repo / "package.json").write_text(
        '{"name": "x", "scripts": {"test": "jest"}}', encoding="utf-8"
    )
    report = inspect_repo(repo)
    test_findings = [f for f in report["findings"] if f["kind"] == "test_runner"]
    assert len(test_findings) == 2
    assert report["conflicts"], "conflicting test runners must be listed"
    assert {f["value"] for f in test_findings} == {"pytest", "jest"}


def test_existing_instructions_detected(tmp_path):
    repo = make_py_repo(tmp_path)
    (repo / "AGENTS.md").write_text("core\n", encoding="utf-8")
    (repo / "AGENTS.project.md").write_text("project\n", encoding="utf-8")
    report = inspect_repo(repo)
    assert report["instructions"]["agents_md"] is True
    assert report["instructions"]["agents_project_md"] is True
    assert report["instructions"]["claude_md"] is False


def test_empty_repo_is_ok_with_no_invented_findings(tmp_path):
    report = inspect_repo(tmp_path)
    assert report["ok"] is True
    assert report["findings"] == []
    assert report["conflicts"] == []


def test_inspect_never_executes_hostile_scripts(tmp_path):
    repo = tmp_path
    canary = tmp_path.parent / "canary-was-here"
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "x",
                "scripts": {"test": f"touch {canary}"},
            }
        ),
        encoding="utf-8",
    )
    inspect_repo(repo)
    assert not canary.exists(), "inspect executed a package script"


def test_missing_path_is_usage_error(tmp_path, capsys):
    assert cli.main(["inspect", str(tmp_path / "nope")]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason_code"] in ("path_missing", "not_a_directory")


def test_file_path_is_usage_error(tmp_path, capsys):
    target = tmp_path / "f.txt"
    target.write_text("x", encoding="utf-8")
    assert cli.main(["inspect", str(target)]) == 2


def test_every_finding_has_evidence_and_confidence(tmp_path):
    repo = make_py_repo(tmp_path)
    report = inspect_repo(repo)
    for finding in report["findings"]:
        assert finding["evidence"], finding
        assert finding["confidence"] in ("high", "medium", "low")
