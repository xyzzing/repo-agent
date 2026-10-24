"""RA-004: read-only repository inspection (PRD §5).

inspect_repo scans manifests, lockfiles and instruction files in the
repository root and reports only what the evidence supports: each finding
carries a kind, a value, a confidence, and evidence naming the file that
justifies it. Discovery is inert: files are read, never executed, so a
hostile "test" script stays untouched. A missing or malformed source is
skipped silently — hostile or malformed input is routine, not an error.
Conflicting discoveries are exposed side by side, never silently resolved.
"""
import json
import re
import tomllib
from pathlib import Path

Finding = dict[str, str]

_INSTRUCTION_FILES = (
    ("agents_md", "AGENTS.md"),
    ("agents_project_md", "AGENTS.project.md"),
    ("claude_md", "CLAUDE.md"),
)

# Lockfiles are written by exactly one manager, so presence is strong
# evidence. Content formats vary wildly; we never parse them.
_LOCKFILES = (
    ("uv.lock", "uv"),
    ("package-lock.json", "npm"),
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("Cargo.lock", "cargo"),
    ("poetry.lock", "poetry"),
)

# Manifest whose presence pins the build system outright.
_BUILD_SYSTEM_FILES = (
    ("Cargo.toml", "cargo"),
    ("go.mod", "go"),
)

# Distribution name at the head of a requirement string ("setuptools>=68").
_REQUIREMENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _finding(kind: str, value: str, confidence: str, evidence: str) -> Finding:
    if confidence not in ("high", "medium", "low"):  # pragma: no cover - bug guard
        raise ValueError(f"unknown confidence {confidence!r}")
    return {"kind": kind, "value": value, "confidence": confidence, "evidence": evidence}


def _read_text(root: Path, name: str) -> str | None:
    """Read one root-level file, or None if it is missing or unreadable."""
    try:
        return (root / name).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def _load_pyproject(root: Path) -> dict[str, object] | None:
    text = _read_text(root, "pyproject.toml")
    if text is None:
        return None
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _pyproject_findings(root: Path) -> list[Finding]:
    data = _load_pyproject(root)
    if data is None:
        return []
    out: list[Finding] = []
    tool = data.get("tool")
    if isinstance(tool, dict):
        if "pytest" in tool:
            out.append(
                _finding(
                    "test_runner",
                    "pytest",
                    "high",
                    "pyproject.toml declares [tool.pytest] configuration",
                )
            )
        if "ruff" in tool:
            out.append(
                _finding(
                    "linter",
                    "ruff",
                    "high",
                    "pyproject.toml declares [tool.ruff] configuration",
                )
            )
    build = data.get("build-system")
    if isinstance(build, dict):
        requires = build.get("requires")
        if isinstance(requires, list):
            for item in requires:
                if not isinstance(item, str):
                    continue
                match = _REQUIREMENT_NAME.match(item)
                if match:
                    out.append(
                        _finding(
                            "build_system",
                            match.group(0),
                            "medium",
                            "pyproject.toml [build-system] requires "
                            f"{item!r}; requires lists build dependencies, "
                            "not always the backend alone",
                        )
                    )
                break
    return out


def _package_json_findings(root: Path) -> list[Finding]:
    text = _read_text(root, "package.json")
    if text is None:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return []
    test = scripts.get("test")
    if not isinstance(test, str) or not test.split():
        return []
    first_word = test.split()[0]
    return [
        _finding(
            "test_runner",
            first_word,
            "high",
            f'package.json "scripts.test" runs {first_word!r} first '
            f"(script: {test!r}); the script text is quoted evidence and "
            "was never executed",
        )
    ]


def _presence_findings(root: Path) -> list[Finding]:
    out: list[Finding] = []
    for name, manager in _LOCKFILES:
        if (root / name).is_file():
            out.append(
                _finding(
                    "package_manager",
                    manager,
                    "high",
                    f"{name} present; only {manager} writes this lockfile",
                )
            )
    for name, system in _BUILD_SYSTEM_FILES:
        if (root / name).is_file():
            out.append(
                _finding(
                    "build_system",
                    system,
                    "high",
                    f"{name} present; the {system} toolchain builds from it",
                )
            )
    return out


def _conflicts(findings: list[Finding]) -> list[dict[str, object]]:
    """Findings sharing a kind but differing in value, exposed not resolved."""
    values_by_kind: dict[str, list[str]] = {}
    for finding in findings:
        values = values_by_kind.setdefault(finding["kind"], [])
        if finding["value"] not in values:
            values.append(finding["value"])
    out: list[dict[str, object]] = []
    for kind, values in values_by_kind.items():
        if len(values) < 2:
            continue
        for value in values:
            out.append(
                {
                    "kind": kind,
                    "value": value,
                    "conflict_with": [other for other in values if other != value],
                }
            )
    return out


def _instruction_flags(root: Path) -> dict[str, bool]:
    return {key: (root / name).is_file() for key, name in _INSTRUCTION_FILES}


def inspect_repo(repo_root: Path) -> dict[str, object]:
    """Read-only inventory of one repository root.

    Returns ok, findings, conflicts and instructions. Nothing is executed
    and nothing is written; every finding cites its evidence file.
    """
    root = Path(repo_root)
    if not root.is_dir():
        return {
            "ok": False,
            "reason_code": "not_a_directory",
            "findings": [],
            "conflicts": [],
            "instructions": {key: False for key, _ in _INSTRUCTION_FILES},
        }
    findings: list[Finding] = []
    findings += _pyproject_findings(root)
    findings += _package_json_findings(root)
    findings += _presence_findings(root)
    return {
        "ok": True,
        "findings": findings,
        "conflicts": _conflicts(findings),
        "instructions": _instruction_flags(root),
    }
