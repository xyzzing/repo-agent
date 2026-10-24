"""Minder adapter (RA-009, PRD §9): evidence out, decisions local.

Two facts pinned by exploration of the minder tree drive this contract:

1. minder's sink (POST /persist, Bearer token from its state dir,
   append_jsonl op) is the only sanctioned evidence-ingest surface, and
   minder's report() reader breaks on any malformed events.jsonl line —
   so every record is single-line JSON with a namespaced `repo_agent_*`
   event name that all minder readers ignore.
2. minder has no out-of-process decision surface (policy_gate is
   in-process only). Decisions are therefore local and fail-closed:
   LocalPolicy enforces the packet's own immutable budget; an operator
   who demands minder decisions gets RequiredMinderPolicy, which blocks
   escalation rather than fail open. Evaluation runs with minder fully
   disabled stay green.

Verification events carry the PRD §9 contract fields (schema_version,
event_id, attempt, producer, evidence_ref, evidence_sha256,
failure_signature) inside the minder record envelope. Evidence refs
resolve only inside the trusted artifact root — traversal, symlink
escape, missing files and digest mismatches are named rejections.
Decision/policy machinery lives in minder_decisions (minder has no
out-of-process decision surface; policy is local and fail-closed).
"""
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from repo_agent.adapters.http import http_get_json, http_post_json

DEFAULT_MAX_BUFFER = 500
_MAX_TRACKED_IDS = 1000
_WELL_KNOWN_MINDER_STATE = Path.home() / ".local" / "state" / "minder"


class EvidenceError(Exception):
    """An evidence reference does not resolve inside the trusted root."""

    def __init__(self, reason_code: str, detail: str):
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code


def _now() -> datetime:
    return datetime.now(UTC)


def _base_url(url: str) -> str:
    """Normalize a sink URL to its base: /persist is appended per call."""
    base = url.rstrip("/")
    if base.endswith("/persist"):
        base = base[: -len("/persist")]
    return base


def discover_sink_url(hooks_path: Path | None = None) -> str | None:
    """Env first (repo-agent override, then minder's own), then minder's
    hooks.json — mirroring minder_memory/sink.py's discovery order."""
    for var in ("REPO_AGENT_MINDER_SINK_URL", "MINDER_SINK_URL"):
        value = os.environ.get(var)
        if value:
            return value
    path = hooks_path or Path.home() / ".local/share/minder/dsh/hooks.json"
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "MINDER_SINK_URL=" in line:
                tail = line.split("MINDER_SINK_URL=", 1)[1].split()
                if tail:
                    return tail[0].strip()
    except OSError:
        return None
    return None


def _read_token(state_dir: Path) -> str | None:
    for directory in (state_dir, _WELL_KNOWN_MINDER_STATE):
        try:
            token = (directory / "sink.token").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if token:
            return token
    return None


def _discover_token(state_dir: Path) -> str | None:
    for var in ("REPO_AGENT_MINDER_TOKEN", "MINDER_TOKEN"):
        value = os.environ.get(var)
        if value:
            return value
    return _read_token(state_dir)


class MinderEvents:
    """Emit repo_agent_* records to minder's sink; bounded buffer when the
    sink is unreachable. Emission never raises and never blocks the run.

    `event_id` makes emission idempotent: a replayed id returns
    "duplicate" instead of re-posting. Buffered events are the same
    single-line records the sink would store, so recovery can append
    them directly; they are not drained automatically."""

    def __init__(
        self,
        state_dir: Path,
        sink_url: str | None = None,
        token: str | None = None,
        buffer_dir: Path | None = None,
        max_buffer: int = DEFAULT_MAX_BUFFER,
    ):
        self.state_dir = Path(state_dir)
        discovered = sink_url if sink_url else discover_sink_url()
        self.sink_url = _base_url(discovered) if discovered else None
        self.token = token if token is not None else _discover_token(self.state_dir)
        self.buffer_dir = Path(buffer_dir) if buffer_dir else None
        self.max_buffer = max_buffer
        self.buffered_count = 0
        self.dropped_count = 0
        self._seen_path = self.state_dir / "emitted-ids.json"
        self._seen: list[str] = self._load_seen()

    def _load_seen(self) -> list[str]:
        try:
            data = json.loads(self._seen_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [str(item) for item in data] if isinstance(data, list) else []

    def _remember(self, event_id: str) -> None:
        self._seen.append(event_id)
        if len(self._seen) > _MAX_TRACKED_IDS:
            self._seen = self._seen[-_MAX_TRACKED_IDS:]
        try:
            self._seen_path.parent.mkdir(parents=True, exist_ok=True)
            self._seen_path.write_text(json.dumps(self._seen), encoding="utf-8")
        except OSError:
            self._seen = self._seen[:-1]  # dedup degrades to in-memory only

    def emit(
        self, task: str, event: str, event_id: str | None = None, **fields: object
    ) -> str:
        marker = str(event_id) if event_id is not None else None
        if marker is not None and marker in self._seen:
            return "duplicate"
        record = {
            "ts": _now().timestamp(),
            "task": task,
            "event": f"repo_agent_{event}",
            **fields,
        }
        if self.sink_url:
            status, _ = http_post_json(
                self.sink_url + "/persist",
                {"op": "append_jsonl", "name": "events.jsonl", "record": record},
                token=self.token,
                timeout=3.0,
            )
            if status == 200:
                if marker is not None:
                    self._remember(marker)
                return "sink"
        return self._buffer(record)

    def _buffer(self, record: dict) -> str:
        if self.buffer_dir is None:
            self.dropped_count += 1  # counted, never silent
            return "buffered"
        try:
            self.buffer_dir.mkdir(parents=True, exist_ok=True)
            out = self.buffer_dir / "events.jsonl"
            lines: list[str] = []
            if out.exists():
                lines = out.read_text(encoding="utf-8").splitlines()
            if len(lines) >= self.max_buffer:
                self.dropped_count += len(lines) + 1 - self.max_buffer
                lines = lines[len(lines) + 1 - self.max_buffer :]
            lines.append(json.dumps(record, sort_keys=True))
            tmp = out.with_suffix(".jsonl.tmp")
            tmp.write_text(
                "".join(line + "\n" for line in lines), encoding="utf-8"
            )
            tmp.replace(out)
            self.buffered_count = len(lines)
        except OSError:
            self.dropped_count += 1
        return "buffered"

    def degraded(self) -> bool:
        return self.buffered_count > 0 or self.dropped_count > 0

    def status(self) -> dict[str, object]:
        return {
            "telemetry": "degraded" if self.degraded() else "ok",
            "buffered": self.buffered_count,
            "dropped": self.dropped_count,
        }


def _sink_health(url: str) -> tuple[bool, str]:
    status, body = http_get_json(_base_url(url) + "/healthz", timeout=3.0)
    if status == 200 and isinstance(body, dict) and body.get("status") == "ok":
        return True, "sink reachable"
    return False, f"sink answered {status}"


def telemetry_status(sink_url: str | None = None) -> dict[str, object]:
    """Doctor-facing: is minder telemetry reachable, and at what URL?"""
    url = _base_url(sink_url) if sink_url else discover_sink_url()
    if url is None:
        return {
            "ok": False,
            "reason_code": "sink_not_found",
            "detail": "no sink URL configured or discovered; events will "
            "buffer locally (degraded capture)",
        }
    ok, detail = _sink_health(url)
    if ok:
        return {"ok": True, "reason_code": "ok", "detail": detail, "url": url}
    return {
        "ok": False,
        "reason_code": "sink_unreachable",
        "detail": detail,
        "url": url,
    }


def resolve_evidence(
    artifact_root: Path, evidence_ref: str, expected_sha256: str | None = None
) -> Path:
    """Resolve an evidence ref inside the trusted artifact root (PRD §9):
    traversal, symlink escape, missing files and digest mismatches are
    named rejections, never best-effort reads."""
    ref = PurePosixPath(evidence_ref)
    if ref.is_absolute():
        raise EvidenceError(
            "absolute_ref", f"evidence_ref must be root-relative: {evidence_ref!r}"
        )
    if ".." in ref.parts:
        raise EvidenceError(
            "traversal", f"evidence_ref escapes the artifact root: {evidence_ref!r}"
        )
    root = Path(artifact_root).resolve()
    candidate = (root / evidence_ref).resolve()
    if not candidate.is_relative_to(root):
        raise EvidenceError("traversal", f"symlink escape: {evidence_ref!r}")
    if not candidate.is_file():
        raise EvidenceError("missing_artifact", f"no artifact at {evidence_ref!r}")
    if expected_sha256 is not None:
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != expected_sha256:
            raise EvidenceError(
                "digest_mismatch",
                f"{evidence_ref!r} digests {actual[:12]}… != expected "
                f"{expected_sha256[:12]}…",
            )
    return candidate


