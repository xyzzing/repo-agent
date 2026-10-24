"""RA-020: export/import portability and tombstoned purge.

Export writes schema-versioned JSONL plus a sha256 manifest; import
validates, deduplicates by id, and quarantines same-id-different-content
rather than guessing. Purge tombstones (append-only: retire + purged
flag) — raw rows are never deleted, audit stays intact.
"""
import json

from repo_agent.memory import MemoryStore
from repo_agent.memory_port import export_memories, import_memories, purge_profile, retire
from repo_agent.state import Journal


def seed(tmp_path, producer=None):
    journal = Journal(tmp_path / "j.sqlite")
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    run = journal.create_run(task_id="t")
    eid = journal.record_event(run, "verifier.verdict", {"verdict": "PASS"})
    provenance = {"source_event_ids": [eid], "evidence_digest": "d" * 8}
    if producer:
        provenance["producer_profile"] = producer
    mem = store.record(
        kind="fact", claim="portable operational fact",
        scope={"repository_id": "/repos/a"}, provenance=provenance,
    )
    return journal, store, mem


def test_export_writes_jsonl_and_manifest(tmp_path):
    journal, store, _ = seed(tmp_path)
    out = export_memories(store, tmp_path / "export")
    records = (out / "memories.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(records) == 1
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 1
    assert manifest["schema_version"] == 1
    assert len(manifest["sha256"]) == 64


def test_import_roundtrip_identity(tmp_path):
    journal, store, mem = seed(tmp_path)
    out = export_memories(store, tmp_path / "export")
    other = MemoryStore(tmp_path / "other.sqlite", journal=journal)
    report = import_memories(other, out)
    assert report["imported"] == 1
    assert report["quarantined"] == 0
    got = other.get(mem["memory_id"])
    assert got["claim"] == mem["claim"]


def test_import_quarantines_conflicting_content(tmp_path):
    journal, store, mem = seed(tmp_path)
    out = export_memories(store, tmp_path / "export")
    line = json.loads(
        (out / "memories.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    line["claim"] = "forged claim under a known id"
    (tmp_path / "conflict.jsonl").write_text(
        json.dumps(line) + "\n", encoding="utf-8"
    )
    report = import_memories(store, tmp_path / "conflict.jsonl",
                             quarantine_dir=tmp_path / "quarantine")
    assert report["quarantined"] == 1
    assert report["imported"] == 0
    quarantined = list((tmp_path / "quarantine").glob("*.json"))
    assert quarantined, "conflicting record preserved for review"
    assert store.get(mem["memory_id"])["claim"] == "portable operational fact"


def test_retire_and_purge_tombstone_without_deletion(tmp_path):
    journal, store, mem = seed(tmp_path, producer="old-model@engine")
    store.promote(mem["memory_id"], "evidence_checked")
    retire(store, mem["memory_id"], "superseded by engine change")
    assert "retired" in store.get(mem["memory_id"])["flags"]

    purge_profile(store, "old-model@engine")
    purged = store.get(mem["memory_id"])
    assert "purged" in purged["flags"]
    # the row is still there: append-only tombstone, never a deletion
    raw = store._read(
        "SELECT COUNT(*) AS n FROM memories WHERE memory_id LIKE ?",
        (mem["memory_id"] + "%",),
    )
    assert raw[0]["n"] >= 2
    assert store.list_memories() == []
