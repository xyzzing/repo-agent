"""Canonical memory store (RA-016, PRD §12A).

Records are append-only rows with code-controlled lifecycle transitions
(candidate → evidence_checked → locally_verified → reusable) and
parallel flags (stale/contradicted/superseded/retired) that never
overwrite status. Evidence gates per kind: a fact may be retrieved once
evidence-checked; procedures and strategies must reach locally_verified
before reusable. Provenance citations are checked against the journal —
a source_event_id that does not exist is a rejection, never a silent
acceptance. Writer output stays candidate: promotion to reusable is a
review decision, never the writer's own.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

KINDS = ("fact", "verified_procedure", "failure_pattern", "strategy")
STATUSES = ("candidate", "evidence_checked", "locally_verified", "reusable")
FLAGS = ("stale", "contradicted", "superseded", "retired", "purged")
_KIND_FLOOR = {"fact": "evidence_checked", "failure_pattern": "evidence_checked",
               "verified_procedure": "locally_verified", "strategy": "locally_verified"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories(
  memory_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  claim TEXT NOT NULL,
  scope_json TEXT NOT NULL,
  applicability_json TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  verification_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'candidate',
  flags_json TEXT NOT NULL DEFAULT '[]',
  flag_reason TEXT NOT NULL DEFAULT '',
  supersedes_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS memories_no_update BEFORE UPDATE ON memories
  BEGIN SELECT RAISE(ABORT, 'memories are append-only'); END;
CREATE TRIGGER IF NOT EXISTS memories_no_delete BEFORE DELETE ON memories
  BEGIN SELECT RAISE(ABORT, 'memories are append-only'); END;
CREATE TABLE IF NOT EXISTS harvest_cursor(
  run_id TEXT PRIMARY KEY,
  harvested_at TEXT NOT NULL
);
"""


class MemoryError(Exception):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


def _now() -> str:
    return datetime.now(UTC).isoformat()


class MemoryStore:
    def __init__(self, db_path: Path, journal=None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.journal = journal
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _read(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            return list(conn.execute(sql, params).fetchall())

    def _check_citations(self, provenance: dict) -> None:
        ids = provenance.get("source_event_ids") or []
        if self.journal is None:
            return
        for event_id in ids:
            rows = self.journal._read(  # noqa: SLF001 - citation check
                "SELECT 1 FROM events WHERE event_id=?", (event_id,)
            )
            if not rows:
                raise MemoryError(
                    "unknown_event", f"source_event_id {event_id!r} not in journal"
                )

    def record(
        self,
        kind: str,
        claim: str,
        scope: dict,
        provenance: dict,
        applicability: dict | None = None,
        verification: dict | None = None,
        revision: int = 1,
        supersedes: list[str] | None = None,
    ) -> dict[str, object]:
        if kind not in KINDS:
            raise MemoryError("unknown_kind", f"kind {kind!r} not in {KINDS}")
        if not isinstance(claim, str) or not claim.strip():
            raise MemoryError("empty_claim", "claim must be a nonempty string")
        self._check_citations(provenance)
        self.validate_candidate(kind, claim, provenance)
        mem = {
            "memory_id": f"mem-{uuid.uuid4().hex}",
            "kind": kind,
            "claim": claim,
            "scope": scope or {},
            "applicability": applicability or {},
            "provenance": provenance,
            "verification": verification or {},
            "revision": revision,
            "status": "candidate",
            "flags": [],
            "flag_reason": "",
            "supersedes": supersedes or [],
        }
        with self._tx() as conn:
            self._insert(conn, mem)
        return mem

    def validate_candidate(self, kind: str, claim: str, provenance: dict) -> None:
        if kind not in KINDS:
            raise MemoryError("unknown_kind", f"kind {kind!r} not in {KINDS}")
        if not isinstance(claim, str) or not claim.strip():
            raise MemoryError("empty_claim", "claim must be a nonempty string")
        self._check_citations(provenance)

    def _insert(self, conn: sqlite3.Connection, mem: dict) -> None:
        """Insert inside a caller-held transaction (harvest batches the
        cursor and candidates into one write, so a crash loses nothing
        and a replay duplicates nothing)."""
        conn.execute(
            "INSERT INTO memories(memory_id, kind, claim, scope_json,"
            " applicability_json, provenance_json, verification_json,"
            " revision, status, flags_json, flag_reason, supersedes_json,"
            " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                mem["memory_id"], mem["kind"], mem["claim"],
                json.dumps(mem["scope"], sort_keys=True),
                json.dumps(mem["applicability"], sort_keys=True),
                json.dumps(mem["provenance"], sort_keys=True),
                json.dumps(mem["verification"], sort_keys=True),
                mem["revision"], mem["status"],
                json.dumps(mem["flags"]), mem["flag_reason"],
                json.dumps(mem["supersedes"]), _now(), _now(),
            ),
        )

    def _row_to_mem(self, row: sqlite3.Row) -> dict[str, object]:
        return {
            "memory_id": str(row["memory_id"]),
            "kind": str(row["kind"]),
            "claim": str(row["claim"]),
            "scope": json.loads(str(row["scope_json"])),
            "applicability": json.loads(str(row["applicability_json"])),
            "provenance": json.loads(str(row["provenance_json"])),
            "verification": json.loads(str(row["verification_json"])),
            "revision": int(row["revision"]),
            "status": str(row["status"]),
            "flags": json.loads(str(row["flags_json"])),
            "flag_reason": str(row["flag_reason"]),
            "supersedes": json.loads(str(row["supersedes_json"])),
        }

    def promote(self, memory_id: str, to_status: str) -> None:
        if to_status not in STATUSES:
            raise MemoryError("unknown_status", to_status)
        mem = self.get(memory_id)
        order = {s: i for i, s in enumerate(STATUSES)}
        kind = str(mem["kind"])
        status = str(mem["status"])
        provenance = mem["provenance"]
        assert isinstance(provenance, dict)
        verification = mem["verification"]
        assert isinstance(verification, dict)
        if order[to_status] != order[status] + 1:
            raise MemoryError(
                "illegal_transition",
                f"{status} -> {to_status} must be one step",
            )
        if to_status == "evidence_checked":
            has_evidence = bool(
                provenance.get("evidence_digest")
                or provenance.get("source_event_ids")
            )
            if not has_evidence:
                raise MemoryError(
                    "evidence_required",
                    "evidence_checked needs evidence_digest or source_event_ids",
                )
        if to_status in ("locally_verified", "reusable"):
            if to_status == "locally_verified" and not verification.get("state"):
                raise MemoryError(
                    "verification_required",
                    "locally_verified needs attach_verification() first",
                )
            if to_status == "reusable":
                floor = _KIND_FLOOR[kind]
                if order["locally_verified"] < order[floor]:
                    raise MemoryError(
                        "evidence_gate", f"{kind} requires {floor} first"
                    )
        self._advance(memory_id, mem, to_status)

    def attach_verification(self, memory_id: str, verification: dict) -> None:
        if not verification.get("state"):
            raise MemoryError("invalid_verification", "verification.state required")
        mem = self.get(memory_id)
        self._advance(
            memory_id, mem, str(mem["status"]),
            verification_overwrite=verification,
        )

    def _advance(
        self,
        memory_id: str,
        mem: dict,
        to_status: str,
        verification_overwrite: dict | None = None,
    ) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO memories(memory_id, kind, claim, scope_json,"
                " applicability_json, provenance_json, verification_json,"
                " revision, status, flags_json, flag_reason, supersedes_json,"
                " created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    mem["memory_id"] + f".r{mem['revision'] + 1}",
                    mem["kind"], mem["claim"],
                    json.dumps(mem["scope"], sort_keys=True),
                    json.dumps(mem["applicability"], sort_keys=True),
                    json.dumps(mem["provenance"], sort_keys=True),
                    json.dumps(
                        verification_overwrite
                        if verification_overwrite is not None
                        else mem["verification"],
                        sort_keys=True,
                    ),
                    mem["revision"] + 1,
                    to_status,
                    json.dumps(mem["flags"]),
                    mem["flag_reason"],
                    json.dumps(mem["supersedes"]),
                    mem["created_at"] if "created_at" in mem else _now(),
                    _now(),
                ),
            )

    def get(self, memory_id: str) -> dict[str, object]:
        rows = self._read(
            "SELECT * FROM memories WHERE memory_id=? OR memory_id LIKE ?"
            " ORDER BY revision DESC LIMIT 1",
            (memory_id, memory_id + ".r%"),
        )
        if not rows:
            raise MemoryError("unknown_memory", memory_id)
        return self._row_to_mem(rows[0])

    def list_memories(self, include_flagged: bool = False) -> list[dict[str, object]]:
        rows = self._read(
            "SELECT * FROM memories m WHERE revision = ("
            "  SELECT MAX(revision) FROM memories x"
            "  WHERE x.memory_id LIKE m.memory_id || '.r%'"
            "     OR x.memory_id = m.memory_id)"
            " ORDER BY created_at, memory_id"
        )
        out: list[dict[str, object]] = []
        seen_bases: set[str] = set()
        for row in rows:
            mem = self._row_to_mem(row)
            base = str(mem["memory_id"]).split(".r")[0]
            if base in seen_bases:
                continue
            seen_bases.add(base)
            if not include_flagged and mem["flags"]:
                continue
            out.append(mem)
        return out

    def refine(
        self, memory_id: str, new_claim: str, model_specific: bool = False
    ) -> dict[str, object]:
        """A refined claim lands as a NEW revision on the same record;
        history is never rewritten. Model-bound refined claims flip the
        applicability flag so other profiles stop seeing them."""
        if not new_claim.strip():
            raise MemoryError("empty_claim", "refined claim must be nonempty")
        mem = self.get(memory_id)
        applicability = mem["applicability"]
        assert isinstance(applicability, dict)
        new_applicability = {**applicability, "model_specific": model_specific}
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO memories(memory_id, kind, claim, scope_json,"
                " applicability_json, provenance_json, verification_json,"
                " revision, status, flags_json, flag_reason, supersedes_json,"
                " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(mem["memory_id"]) + f".r{int(str(mem['revision'])) + 1}",
                    mem["kind"], new_claim,
                    json.dumps(mem["scope"], sort_keys=True),
                    json.dumps(new_applicability, sort_keys=True),
                    json.dumps(mem["provenance"], sort_keys=True),
                    json.dumps(mem["verification"], sort_keys=True),
                    int(str(mem["revision"])) + 1, mem["status"],
                    json.dumps(mem["flags"]), mem["flag_reason"],
                    json.dumps(mem["supersedes"]), _now(), _now(),
                ),
            )
        return self.get(memory_id)

    def mark_stale(self, memory_id: str, reason: str) -> None:
        self._flag(memory_id, "stale", reason)

    def _flag(self, memory_id: str, flag: str, reason: str) -> None:
        if flag not in FLAGS:
            raise MemoryError("unknown_flag", flag)
        mem = self.get(memory_id)
        revision = int(str(mem["revision"]))
        flags_raw = mem["flags"]
        assert isinstance(flags_raw, list)
        flags = [str(f) for f in flags_raw]
        if flag not in flags:
            flags.append(flag)
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO memories(memory_id, kind, claim, scope_json,"
                " applicability_json, provenance_json, verification_json,"
                " revision, status, flags_json, flag_reason, supersedes_json,"
                " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(mem["memory_id"]) + f".r{revision + 1}",
                    mem["kind"], mem["claim"],
                    json.dumps(mem["scope"], sort_keys=True),
                    json.dumps(mem["applicability"], sort_keys=True),
                    json.dumps(mem["provenance"], sort_keys=True),
                    json.dumps(mem["verification"], sort_keys=True),
                    revision + 1, mem["status"],
                    json.dumps(flags), reason,
                    json.dumps(mem["supersedes"]), _now(), _now(),
                ),
            )

    def supersede(
        self, old_id: str, kind: str, claim: str, scope: dict, provenance: dict
    ) -> dict[str, object]:
        old = self.get(old_id)
        new = self.record(
            kind=kind, claim=claim, scope=scope, provenance=provenance,
            revision=int(str(old["revision"])) + 1, supersedes=[old_id],
        )
        self._flag(old_id, "superseded", f"superseded by {new['memory_id']}")
        return new

    def query(
        self, keyword: str, include_flagged: bool = False
    ) -> list[dict[str, object]]:
        needle = keyword.lower()
        memories = self.list_memories(
            include_flagged=include_flagged
        )
        return [m for m in memories if needle in str(m["claim"]).lower()]
