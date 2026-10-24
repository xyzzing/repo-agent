"""Structural gates (C-S/C-N/C-B in AGENTS.project.md).

Grep-level checks for contracts a type checker cannot see. Every gate
reports the contract it enforces through its name; a silent pass over zero
files would be a defect, so the helpers assert the package exists (M2).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "repo_agent"


def _py_files() -> list[Path]:
    files = sorted(PKG.rglob("*.py"))
    assert files, "gate scanned zero files - package missing?"
    return files


def _scan(pattern: str, allow: set[str] | None = None) -> list[str]:
    rx = re.compile(pattern)
    hits: list[str] = []
    for path in _py_files():
        rel = path.relative_to(ROOT).as_posix()
        if allow and rel in allow:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if rx.search(line):
                hits.append(f"{rel}:{lineno}: {line.strip()}")
    return hits


def test_sqlite_connect_only_in_state_and_memory_modules():
    # proven-red: allow-pass: gate relaxation riding with the RA-016 memory
    # store; the range's red is carried by tests/test_memory.py (new file).
    hits = _scan(
        r"sqlite3\.connect",
        allow={"repo_agent/state.py", "repo_agent/memory.py",
               "repo_agent/profiles.py"},
    )
    assert hits == [], "C-S: sqlite3.connect outside state.py/memory.py/profiles.py"


def test_no_requests_or_httpx_imports():
    hits = _scan(r"\b(import requests|import httpx|from requests|from httpx)\b")
    assert hits == [], "C-N: non-sanctioned HTTP client"


def test_urlopen_only_in_http_adapter():
    hits = _scan(
        r"urlopen|urllib\.request", allow={"repo_agent/adapters/http.py"}
    )
    assert hits == [], "C-N: HTTP outside repo_agent/adapters/http.py"


def test_no_shell_eval_exec():
    hits = _scan(r"shell\s*=\s*True|os\.system\(|\beval\(|\bexec\(")
    assert hits == [], "C-N: shell/eval/exec use"


def test_dsh_invoked_only_by_dsh_adapter():
    # proven-red: allow-pass: gate-relaxation edit (schema enum default
    # names the adapter); the RA-002 red is carried by tests/test_config.py
    # config_schema.py legitimately names adapter values in enum defaults;
    # it cannot invoke anything.
    hits = _scan(
        r"[\'\"]dsh[\'\"]",
        allow={"repo_agent/adapters/dsh.py", "repo_agent/config_schema.py"},
    )
    assert hits == [], "C-B: dsh invoked outside repo_agent/adapters/dsh.py"


def test_agents_core_present():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Portable core" in text, "AGENTS.md core missing"
