"""RA-004b: bootstrap onboarding proposals for new and mature repos.

Plan-then-apply: without --apply the proposal is computed, persisted to
.repo-agent/proposal.json, and nothing else in the repo changes. With
--apply the recorded proposal is loaded — never silently recomputed —
and executed only if every file it touches still matches the sha256 the
plan reviewed; any drift refuses the whole operation and changes
nothing. A hand-written AGENTS.md is never destroyed: it is backed up
byte-identical and migrated verbatim into the project notes, and the
generated AGENTS.md is produced by render (the single renderer).
"""
import hashlib
import json
from pathlib import Path

from repo_agent.inspect import inspect_repo
from repo_agent.render import (
    AGENTS_NAME,
    CONFIG_NAME,
    DEFAULT_NOTES,
    GENERATED_BEGIN,
    render_repo,
)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_BLOCKED = 3
EXIT_INFRA = 4

STATE_DIR = ".repo-agent"
PROPOSAL_RELPATH = f"{STATE_DIR}/proposal.json"
BACKUP_DIR = f"{STATE_DIR}/backups"

_MODES = ("new", "mature")
_PYTEST_ARGV = ["python3", "-m", "pytest", "-q"]

_NOTES_HEADER = (
    "# Project notes\n\n"
    "Hand-editable notes; `repo-agent render` copies them verbatim "
    "into AGENTS.md.\n"
)
_MIGRATION_HEADING = "## Migrated from the previous AGENTS.md (verbatim)"


class _Blocked(Exception):
    """A refusal that maps to exit 3 with a stable reason code."""

    def __init__(self, reason_code: str, detail: str):
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rel(root: Path, rel: str) -> Path:
    """Resolve a proposal-relative path, refusing anything outside root."""
    resolved = (root / rel).resolve()
    root_resolved = root.resolve()
    if resolved == root_resolved or root_resolved not in resolved.parents:
        raise _Blocked("invalid_proposal", f"path escapes the repo: {rel}")
    return resolved


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".repo-agent-tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _sections(proposal: dict[str, object]) -> tuple[dict, dict, dict]:
    create, overwrite, backup = (proposal[k] for k in ("create", "overwrite", "backup"))  # noqa: E501
    assert isinstance(create, dict) and isinstance(overwrite, dict)
    assert isinstance(backup, dict)
    return create, overwrite, backup


def _config_text(root: Path, maturity: str, test_argv: list[str] | None) -> str:
    lines = [
        "schema_version: 1",
        "project:",
        f"  name: {json.dumps(root.name)}",
        f"  maturity: {maturity}",
    ]
    if test_argv is None:
        lines.append("commands: {}")
    else:
        lines += ["commands:", "  test:"]
        lines += [f"    - {json.dumps(arg)}" for arg in test_argv]
    return "\n".join(lines) + "\n"


def _inspected_pytest(root: Path) -> list[str] | None:
    """The pytest command, but only when inspection found the runner."""
    findings = inspect_repo(root).get("findings", [])
    assert isinstance(findings, list)
    for finding in findings:
        assert isinstance(finding, dict)
        if finding.get("kind") == "test_runner" and finding.get("value") == "pytest":
            return list(_PYTEST_ARGV)
    return None


def _migrated_notes(old_agents_text: str, existing_notes: str | None) -> str:
    base = _NOTES_HEADER if existing_notes is None else existing_notes
    if not base.endswith("\n\n"):
        base += "\n" if base.endswith("\n") else "\n\n"
    return base + f"{_MIGRATION_HEADING}\n\n{old_agents_text.rstrip()}\n"


def _precheck(root: Path, mode: str) -> None:
    """Mode preconditions, checked before any proposal is read or made."""
    if mode == "new":
        if (root / CONFIG_NAME).is_file():
            raise _Blocked("already_configured", f"{CONFIG_NAME} already exists in {root}")
        return
    agents = root / AGENTS_NAME
    if not agents.is_file():
        raise _Blocked("no_unowned_agents_md", f"no {AGENTS_NAME} to migrate in {root}")
    if GENERATED_BEGIN.encode("utf-8") in agents.read_bytes():
        raise _Blocked(
            "no_unowned_agents_md", f"{AGENTS_NAME} is already owned by repo-agent"
        )


def _plan(root: Path, mode: str) -> dict[str, object]:
    if mode == "new":
        create = {
            CONFIG_NAME: _config_text(root, "new", _inspected_pytest(root)),
            DEFAULT_NOTES: _NOTES_HEADER,
        }
        return {"mode": "new", "create": create, "overwrite": {}, "backup": {}}
    agents = root / AGENTS_NAME
    raw = agents.read_bytes()
    digest = _digest(raw)
    notes = root / DEFAULT_NOTES
    notes_text = notes.read_text(encoding="utf-8") if notes.is_file() else None
    migrated = _migrated_notes(raw.decode("utf-8"), notes_text)
    create_entries: dict[str, str] = {}
    overwrite: dict[str, dict[str, object]] = {}
    if not (root / CONFIG_NAME).is_file():
        # render needs a config to project; propose one when none exists.
        create_entries[CONFIG_NAME] = _config_text(root, "mature", None)
    if notes_text is None:
        create_entries[DEFAULT_NOTES] = migrated
    else:
        overwrite[DEFAULT_NOTES] = {
            "content": migrated,
            "base_sha256": _digest(notes.read_bytes()),
        }
    backup = {
        AGENTS_NAME: {
            "to": f"{BACKUP_DIR}/{AGENTS_NAME}.{digest[:12]}",
            "base_sha256": digest,
        }
    }
    return {"mode": "mature", "create": create_entries, "overwrite": overwrite, "backup": backup}


def _load_proposal(root: Path, mode: str) -> dict[str, object]:
    path = root / PROPOSAL_RELPATH
    if not path.is_file():
        raise _Blocked(
            "proposal_missing",
            f"no recorded proposal at {PROPOSAL_RELPATH}; "
            "run bootstrap without --apply first",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise _Blocked("invalid_proposal", f"{PROPOSAL_RELPATH} is not readable JSON") from None
    if not isinstance(data, dict) or not all(
        isinstance(data.get(key), dict) for key in ("create", "overwrite", "backup")
    ):
        raise _Blocked(
            "invalid_proposal", f"{PROPOSAL_RELPATH} lacks create/overwrite/backup mappings"
        )
    if data.get("mode") != mode:
        raise _Blocked(
            "proposal_mode_mismatch",
            f"recorded proposal is mode {data.get('mode')!r}, not {mode!r}",
        )
    _validate_shape(data)
    return data


def _validate_shape(proposal: dict[str, object]) -> None:
    create, overwrite, backup = _sections(proposal)
    for rel, content in create.items():
        if not isinstance(rel, str) or not isinstance(content, str):
            raise _Blocked("invalid_proposal", f"create entry {rel!r} must map a path to text")
    for rel, entry in overwrite.items():
        base = entry.get("base_sha256") if isinstance(entry, dict) else None
        if (
            not isinstance(rel, str)
            or not isinstance(entry, dict)
            or not isinstance(entry.get("content"), str)
            or not (base is None or isinstance(base, str))
        ):
            raise _Blocked(
                "invalid_proposal", f"overwrite entry {rel!r} needs content and base_sha256"
            )
    for rel, entry in backup.items():
        if (
            not isinstance(rel, str)
            or not isinstance(entry, dict)
            or not isinstance(entry.get("to"), str)
            or not isinstance(entry.get("base_sha256"), str)
        ):
            raise _Blocked(
                "invalid_proposal", f"backup entry {rel!r} needs to and base_sha256"
            )


def _check_drift(root: Path, proposal: dict[str, object]) -> None:
    """Re-verify every base hash; any mismatch refuses before any write."""
    drifted = "drift_since_proposal"
    create, overwrite, backup = _sections(proposal)
    for rel in create:
        if _rel(root, str(rel)).exists():
            raise _Blocked(drifted, f"{rel} exists but was absent when the proposal was recorded")
    for rel, entry in overwrite.items():
        assert isinstance(entry, dict)
        path = _rel(root, str(rel))
        expected = entry["base_sha256"]
        if expected is None:
            if path.exists():
                raise _Blocked(
                    drifted, f"{rel} exists but was absent when the proposal was recorded"
                )
        elif not path.is_file():
            raise _Blocked(drifted, f"{rel} is missing but existed when the proposal was recorded")
        elif _digest(path.read_bytes()) != expected:
            raise _Blocked(drifted, f"{rel} changed since the proposal was recorded")
    backups_root = (root / BACKUP_DIR).resolve()
    for rel, entry in backup.items():
        assert isinstance(entry, dict)
        source = _rel(root, str(rel))
        if not source.is_file():
            raise _Blocked(drifted, f"{rel} is missing but existed when the proposal was recorded")
        if _digest(source.read_bytes()) != entry["base_sha256"]:
            raise _Blocked(drifted, f"{rel} changed since the proposal was recorded")
        dest = _rel(root, str(entry["to"]))
        if not dest.is_relative_to(backups_root):
            raise _Blocked("invalid_proposal", f"backup target must live in {BACKUP_DIR}")
        if dest.exists():
            raise _Blocked(drifted, f"backup target {entry['to']} already exists")


def _execute(root: Path, proposal: dict[str, object]) -> None:
    create, overwrite, backup = _sections(proposal)
    for rel, entry in backup.items():
        assert isinstance(entry, dict)
        source = _rel(root, str(rel))
        dest = _rel(root, str(entry["to"]))
        dest.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(dest, source.read_bytes())
        if str(rel) == AGENTS_NAME:
            # render refuses to take over an unowned AGENTS.md; the
            # byte-identical backup above is what makes removal safe.
            source.unlink()
    for rel, content in create.items():
        path = _rel(root, str(rel))
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, str(content).encode("utf-8"))
    for rel, entry in overwrite.items():
        assert isinstance(entry, dict)
        path = _rel(root, str(rel))
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, str(entry["content"]).encode("utf-8"))
    code, payload = render_repo(root, write=True)
    if code != EXIT_OK:
        raise _Blocked(
            "render_failed",
            f"render after migration exited {code}: {payload.get('reason_code')}",
        )


def bootstrap(repo_root: Path, mode: str, apply: bool = False) -> tuple[int, dict[str, object]]:
    """Plan or apply one bootstrap. Exit codes follow the PRD §5 contract.

    Without --apply: compute the proposal, persist it to
    .repo-agent/proposal.json, change nothing else. With --apply: run
    mode preconditions, load the recorded proposal (computing and
    persisting one only if none was recorded), re-check every base hash,
    then write. Any refusal changes nothing in the repo.
    """
    root = Path(repo_root)
    if not root.is_dir():
        return EXIT_USAGE, {
            "ok": False,
            "reason_code": "path_missing",
            "detail": f"not a directory: {repo_root}",
        }
    if mode not in _MODES:
        return EXIT_USAGE, {
            "ok": False,
            "reason_code": "invalid_mode",
            "detail": f"unknown mode {mode!r}",
        }
    recorded = root / PROPOSAL_RELPATH
    try:
        _precheck(root, mode)
        if apply and recorded.is_file():
            proposal = _load_proposal(root, mode)
        else:
            proposal = _plan(root, mode)
            recorded.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(
                recorded,
                (json.dumps(proposal, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            )
        if apply:
            _check_drift(root, proposal)
            _execute(root, proposal)
    except _Blocked as exc:
        return EXIT_BLOCKED, {
            "ok": False,
            "reason_code": exc.reason_code,
            "detail": exc.detail,
        }
    except UnicodeDecodeError as exc:
        return EXIT_INFRA, {
            "ok": False,
            "reason_code": "undecodable_input",
            "detail": str(exc),
        }
    except OSError as exc:
        return EXIT_INFRA, {"ok": False, "reason_code": "io_error", "detail": str(exc)}
    return EXIT_OK, {
        "ok": True,
        "reason_code": "ok",
        "mode": mode,
        "proposal_path": PROPOSAL_RELPATH,
        "proposal": proposal,
    }
