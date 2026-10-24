"""RA-020: export/import portability and tombstoned purge.

Export writes schema-versioned JSONL (one record per line, latest
revisions only) plus a manifest binding the sha256. Import validates the
vocabulary, deduplicates by memory id, and QUARANTINES a record whose id
exists with different content — a known id never gets silently
overwritten. Purge tombstones: retire + a `purged` flag on a new
revision; the append-only rows are never deleted, so audit survives.
"""
import hashlib
import json
from pathlib import Path

from repo_agent.memory import KINDS, STATUSES, MemoryError, MemoryStore

SCHEMA_VERSION = 1


def _latest_records(store: MemoryStore) -> list[dict[str, object]]:
    out = []
    for mem in store.list_memories(include_flagged=True):
        mem = dict(mem)
        mem["schema_version"] = SCHEMA_VERSION
        out.append(mem)
    return out


def export_memories(store: MemoryStore, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = _latest_records(store)
    lines = "".join(
        json.dumps(r, sort_keys=True, ensure_ascii=True) + "\n" for r in records
    )
    (out_dir / "memories.jsonl").write_text(lines, encoding="utf-8")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "count": len(records),
        "sha256": hashlib.sha256(lines.encode("utf-8")).hexdigest(),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return out_dir


def import_memories(
    store: MemoryStore, source: Path, quarantine_dir: Path | None = None
) -> dict[str, int]:
    """Import records from memories.jsonl (a directory holding it or the
    file itself). Same id with different content is quarantined, never
    applied; validation failures quarantine too."""
    source = Path(source)
    jsonl = source / "memories.jsonl" if source.is_dir() else source
    report = {"imported": 0, "skipped_duplicate": 0, "quarantined": 0}
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            record = {"claim": "<unparsable>"}
        if (
            not isinstance(record, dict)
            or record.get("kind") not in ("fact", "verified_procedure",
                                          "failure_pattern", "strategy")
            or not isinstance(record.get("claim"), str)
            or not record["claim"].strip()
            or not isinstance(record.get("memory_id"), str)
            or not record["memory_id"]
        ):
            report["quarantined"] += 1
            _quarantine(record, quarantine_dir, "invalid")
            continue
        try:
            existing = store.get(record["memory_id"])
        except MemoryError:
            existing = None
        if existing is not None:
            if existing["claim"] != record.get("claim"):
                report["quarantined"] += 1
                _quarantine(record, quarantine_dir, "conflict")
            else:
                report["skipped_duplicate"] += 1
            continue
        try:
            import_insert(store, record)
            report["imported"] += 1
        except MemoryError:
            report["quarantined"] += 1
            _quarantine(record, quarantine_dir, "invalid")
    return report


def _quarantine(record: object, quarantine_dir: Path | None, why: str) -> None:
    if quarantine_dir is None:
        return
    quarantine_dir = Path(quarantine_dir)
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(
        json.dumps(record, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]
    name = f"{why}-{fingerprint}.json"
    (quarantine_dir / name).write_text(
        json.dumps({"why": why, "record": record}, indent=2, sort_keys=True,
                   default=str) + "\n",
        encoding="utf-8",
    )


def retire(store: MemoryStore, memory_id: str, reason: str) -> None:
    store._flag(memory_id, "retired", reason)  # noqa: SLF001 - sibling API


def purge_profile(store: MemoryStore, producer_profile: str) -> int:
    """Tombstone every record produced by a profile: retire + purged flag
    on a new revision. Append-only: the rows stay, visibility ends."""
    purged = 0
    for mem in store.list_memories(include_flagged=True):
        provenance = mem["provenance"]
        assert isinstance(provenance, dict)
        if provenance.get("producer_profile") != producer_profile:
            continue
        memory_id = str(mem["memory_id"])
        store._flag(  # noqa: SLF001
            memory_id, "retired", f"purged: producer {producer_profile}"
        )
        store._flag(  # noqa: SLF001
            memory_id.rsplit(".r", 1)[0], "purged",
            f"producer {producer_profile}",
        )
        purged += 1
    return purged


def import_insert(store: MemoryStore, record: dict[str, object]) -> None:
    """Insert an already-validated imported record with its own id through
    the store's transaction and insert helper (module-level sibling: the
    importer owns vocabulary and id policy; the store owns the write)."""
    mem = {
        "memory_id": str(record["memory_id"]),
        "kind": str(record["kind"]),
        "claim": str(record["claim"]),
        "scope": record.get("scope") or {},
        "applicability": record.get("applicability") or {},
        "provenance": record.get("provenance") or {},
        "verification": record.get("verification") or {},
        "revision": int(str(record.get("revision", 1))),
        "status": str(record.get("status", "candidate")),
        "flags": record.get("flags") or [],
        "flag_reason": str(record.get("flag_reason", "")),
        "supersedes": record.get("supersedes") or [],
    }
    if mem["kind"] not in KINDS:
        raise MemoryError("unknown_kind", str(mem["kind"]))
    if mem["status"] not in STATUSES:
        raise MemoryError("unknown_status", str(mem["status"]))
    with store._tx() as conn:  # noqa: SLF001 - sibling of the store
        store._insert(conn, mem)  # noqa: SLF001
