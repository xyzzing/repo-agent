"""RA-006: workspace staging, patch freezing, and the protected verifier.

Trust model (stated honestly): isolation_by_construction. The worker runs
in a disposable workspace whose HOME/TMPDIR are built inside it. The
verifier never trusts worker output: it freezes a patch digest, rebuilds
its own environment from the trusted base plus that patch, injects
graders afterwards, and binds its verdict to the digest — any patch
mutation invalidates prior verdicts. A fresh directory is not a sandbox;
the podman-backed probes measure containment separately and report the
level that actually enforced them.
"""
import base64
import hashlib
import json
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from repo_agent.containment import _execute, containment_level
from repo_agent.state import Journal

TAMPERED_GRADER = "tampered_grader"
VERDICT_INVALIDATED = "verdict_invalidated"

# Generated artifacts never enter a patch: the worker's own tooling
# creates them as side effects (the live dogfood produced __pycache__).
DEFAULT_EXCLUDES = ("__pycache__/*", "*.pyc", "*.pyo", ".DS_Store", "node_modules/*")
# Total uncompressed binary content a patch may carry; over the cap is a
# named ValueError, not silent truncation.
MAX_BINARY_BYTES = 512 * 1024

WORKER_HOME = ".worker-home"
WORKER_TMP = ".worker-tmp"
GRADERS_DIR = "graders"
_KEEP_ENV = ("PATH", "LANG", "LC_ALL")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _copy_tree(base: Path, target: Path) -> None:
    for src in sorted(base.rglob("*")):
        rel = src.relative_to(base)
        if rel.parts[0] == ".git":
            continue  # the worker never sees repo history
        if src.is_symlink():
            raise ValueError(f"symlink in source tree is refused: {rel}")
        if src.is_dir():
            (target / rel).mkdir(parents=True, exist_ok=True)
        elif src.is_file():
            shutil.copy2(src, target / rel)


def stage_workspace(base: Path, work_root: Path) -> Path:
    """Overlay-copy base into a fresh workspace with worker HOME/TMP inside."""
    work_root.mkdir(parents=True, exist_ok=True)
    ws = Path(work_root / f"ws-{uuid.uuid4().hex}")
    ws.mkdir()
    _copy_tree(base, ws)
    (ws / WORKER_HOME).mkdir()
    (ws / WORKER_TMP).mkdir()
    return ws


def _excluded(rel: str) -> bool:
    from fnmatch import fnmatch

    return any(fnmatch(rel, pattern) for pattern in DEFAULT_EXCLUDES)


def _file_map(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    binary_total = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".worker-") or rel == ".git" or rel.startswith(".git/"):
            continue
        if _excluded(rel):
            continue
        raw = path.read_bytes()
        try:
            out[rel] = raw.decode("utf-8")
        except UnicodeDecodeError:
            binary_total += len(raw)
            if binary_total > MAX_BINARY_BYTES:
                raise ValueError(
                    f"binary patch budget of {MAX_BINARY_BYTES} bytes exceeded"
                ) from None
            out[rel] = "base64:" + base64.b64encode(raw).decode("ascii")
    return out


def collect_patch(
    workspace: Path, base: Path, protected: frozenset[str] = frozenset()
) -> dict[str, object]:
    """Diff workspace against base; protected paths are excluded and flagged."""
    base_files = _file_map(base)
    workspace_files = _file_map(workspace)
    files: dict[str, str] = {}
    for rel, text in workspace_files.items():
        if rel in protected:
            continue
        if rel not in base_files or base_files[rel] != text:
            files[rel] = text
    tampered = sorted(set(workspace_files) & protected)
    canonical = json.dumps(files, sort_keys=True, ensure_ascii=True)
    return {
        "files": files,
        "tampered_protected": tampered,
        "digest": _digest(canonical.encode("utf-8")),
    }


def apply_patch(base: Path, patch_files: dict[str, str], target: Path) -> None:
    """Rebuild target from the trusted base plus exactly the patch files."""
    target.mkdir(parents=True, exist_ok=True)
    _copy_tree(base, target)
    for rel, payload in patch_files.items():
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str) and payload.startswith("base64:"):
            dest.write_bytes(base64.b64decode(payload[len("base64:"):]))
        else:
            assert isinstance(payload, str)
            dest.write_text(payload, encoding="utf-8")


class Verifier:
    """Freezes a patch, rebuilds its own environment, and renders verdicts."""

    def __init__(self, base: Path, work_root: Path, journal: Journal, run_id: str):
        self.base = Path(base)
        self.work_root = Path(work_root)
        self.journal = journal
        self.label = run_id
        self._workspace: Path | None = None
        self._frozen: str | None = None
        self._patch: dict[str, object] | None = None
        self._journal_run: str | None = None

    def _ensure_journal_run(self) -> str:
        if self._journal_run is None:
            self._journal_run = self.journal.create_run(
                task_id=f"verify:{self.label}",
                idempotency_key=f"verifier-run:{self.label}",
            )
        return self._journal_run

    def freeze(self, workspace: Path) -> str:
        self._workspace = Path(workspace)
        self._patch = collect_patch(self._workspace, self.base, frozenset())
        assert isinstance(self._patch["digest"], str)
        self._frozen = self._patch["digest"]
        patch_files = self._patch["files"]
        assert isinstance(patch_files, dict)
        self.journal.record_event(
            self._ensure_journal_run(),
            "verifier.frozen",
            {
                "patch_digest": self._frozen,
                "changed_files": sorted(patch_files),
            },
            idempotency_key=f"{self.label}:freeze:{self._frozen}",
        )
        return self._frozen

    def bind_frozen(self, digest: str) -> None:
        """Adopt an externally held frozen digest (resume after crash)."""
        self._frozen = digest

    def current_digest(self) -> str:
        if self._workspace is None:
            raise RuntimeError("no workspace bound; freeze first")
        patch = collect_patch(self._workspace, self.base, frozenset())
        assert isinstance(patch["digest"], str)
        return patch["digest"]

    def frozen_changed_files(self) -> list[str]:
        if self._patch is None:
            raise RuntimeError("nothing frozen yet")
        files = self._patch["files"]
        assert isinstance(files, dict)
        return sorted(files)

    def verify(
        self,
        checks: list[list[str]],
        graders: list[Path],
        timeout_seconds: int = 300,
    ) -> dict[str, object]:
        if self._frozen is None:
            raise RuntimeError("verify called before freeze")
        if self._workspace is None:
            # A resumed verifier holds the frozen digest but no workspace to
            # re-derive the current patch from; conservatively void.
            return self._record(
                {
                    "verdict": "FAIL",
                    "reason_code": VERDICT_INVALIDATED,
                    "patch_digest": self._frozen,
                    "detail": "resume holds a frozen digest without a bound "
                    "workspace; re-verification requires staging it again",
                }
            )
        current = self.current_digest()
        if current != self._frozen:
            return self._record(
                {
                    "verdict": "FAIL",
                    "reason_code": VERDICT_INVALIDATED,
                    "patch_digest": self._frozen,
                    "current_digest": current,
                    "detail": "workspace changed after freezing; verdict void",
                }
            )

        assert self._patch is not None
        protected = frozenset(f"{GRADERS_DIR}/{g.name}" for g in graders)
        patch_files = self._patch["files"]
        assert isinstance(patch_files, dict)
        tampered = sorted(set(patch_files) & protected)
        if tampered:
            return self._record(
                {
                    "verdict": "FAIL",
                    "reason_code": TAMPERED_GRADER,
                    "patch_digest": self._frozen,
                    "tampered": tampered,
                    "detail": "worker wrote into grader-owned paths",
                }
            )

        env_dir = self.work_root / f"verify-{uuid.uuid4().hex}"
        apply_patch(self.base, patch_files, env_dir)
        (env_dir / WORKER_HOME).mkdir(exist_ok=True)
        graders_dir = env_dir / GRADERS_DIR
        graders_dir.mkdir()
        for grader in graders:
            shutil.copy2(grader, graders_dir / grader.name)

        base_env = {k: v for k, v in os.environ.items() if k in _KEEP_ENV}
        base_env["VERIFIER_ROOT"] = str(env_dir)
        base_env["HOME"] = str(env_dir / WORKER_HOME)
        level = containment_level()
        self._level = level

        records: list[dict[str, object]] = []
        for argv in checks:
            code, out = _execute(
                argv, env_dir=env_dir, env=base_env, timeout=timeout_seconds,
                level=level,
            )
            records.append({"argv": argv, "exit": code, "output_tail": out[-2000:]})
            if code != 0:
                return self._record(
                    {
                        "verdict": "FAIL",
                        "reason_code": "check_failed",
                        "patch_digest": self._frozen,
                        "checks": records,
                    }
                )
        grader_outputs: list[str] = []
        for grader in graders:
            code, out = _execute(
                [str(graders_dir / grader.name)],
                env_dir=env_dir,
                env=base_env,
                timeout=timeout_seconds,
                level=level,
            )
            grader_outputs.append(out[-2000:])
            if code != 0:
                return self._record(
                    {
                        "verdict": "FAIL",
                        "reason_code": "grader_failed",
                        "patch_digest": self._frozen,
                        "grader": grader.name,
                        "grader_output": out[-2000:],
                        "checks": records,
                    }
                )
        return self._record(
            {
                "verdict": "PASS",
                "reason_code": "ok",
                "patch_digest": self._frozen,
                "checks": records,
                "grader_output": "\n".join(grader_outputs),
            }
        )

    def _record(self, verdict: dict[str, object]) -> dict[str, object]:
        verdict = {"containment": getattr(self, "_level", containment_level()), **verdict}
        envelope = {"ts": _now(), **verdict}
        envelope["result_digest"] = _digest(
            json.dumps(verdict, sort_keys=True, ensure_ascii=True).encode("utf-8")
        )
        digest16 = str(envelope["result_digest"])[:16]
        self.journal.record_event(
            self._ensure_journal_run(),
            "verifier.verdict",
            {
                "verdict": verdict["verdict"],
                "reason_code": verdict["reason_code"],
                "result_digest": envelope["result_digest"],
                "patch_digest": verdict.get("patch_digest"),
            },
            idempotency_key=f"{self.label}:verdict:{digest16}",
        )
        return envelope


