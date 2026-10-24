"""RA-011: structural gates for CI and packaging.

The CI workflow must name every enforced gate — a check that silently
disappears from CI is a gate that no longer runs. The packaging smoke
script must exist and be executable; its behavior is exercised by the
packaging job (and locally), not here: building a wheel inside the unit
suite would be slow and networked.
"""
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SMOKE = ROOT / "scripts" / "packaging-smoke.sh"

REQUIRED_IN_CI = (
    "make gates",
    "scripts/proven-red.sh",
    "scripts/packaging-smoke.sh",
    "mypy repo_agent --ignore-missing-imports",
)


def test_ci_workflow_names_every_gate():
    text = WORKFLOW.read_text(encoding="utf-8")
    for required in REQUIRED_IN_CI:
        assert required in text, f"CI workflow omits gate: {required}"


def test_packaging_smoke_exists_and_is_executable():
    mode = SMOKE.stat().st_mode
    assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH), \
        "scripts/packaging-smoke.sh is not executable"


def test_smoke_script_runs_the_installed_cli():
    text = SMOKE.read_text(encoding="utf-8")
    for required in ("--version", "render --check", "render --write",
                     "task validate", "inspect", "doctor"):
        assert required in text, f"smoke script omits: {required}"
