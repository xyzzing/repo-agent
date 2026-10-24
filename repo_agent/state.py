"""Durable run journal (RA-005, PRD §6).

Code-controlled transitions: callers propose, the journal validates
against TRANSITIONS — a worker message is never an authoritative state
change. Events are append-only (SQL triggers refuse UPDATE/DELETE), carry
increasing sequence numbers, and deduplicate on optional idempotency keys
so a replayed dispatch cannot create a second run or a duplicate external
request event. A per-run lock makes two concurrent resumes exclusive.
"""
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

STATES = frozenset(
    {
        "created", "preflight", "baselined", "contracted", "running",
        "verifying", "reviewing", "accepted", "needs_evidence", "escalating",
        "paused", "blocked", "failed", "cancelled",
    }
)

TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"preflight", "blocked", "cancelled"}),
    "preflight": frozenset({"baselined", "blocked", "failed", "cancelled"}),
    "baselined": frozenset(
        {"contracted", "needs_evidence", "escalating", "blocked", "failed", "cancelled"}
    ),
    "contracted": frozenset({"running", "blocked", "failed", "cancelled"}),
    "running": frozenset(
        {"verifying", "needs_evidence", "escalating", "paused", "blocked",
         "failed", "cancelled"}
    ),
    "verifying": frozenset(
        {"reviewing", "running", "needs_evidence", "failed", "cancelled"}
    ),
    "reviewing": frozenset({"accepted", "running", "escalating", "failed", "cancelled"}),
    "needs_evidence": frozenset(
        {"running", "escalating", "blocked", "failed", "cancelled"}
    ),
    "escalating": frozenset({"running", "blocked", "failed", "cancelled"}),
    "paused": frozenset({"running", "cancelled"}),
    "blocked": frozenset({"running", "cancelled", "failed"}),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "accepted": frozenset(),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  state TEXT NOT NULL,
  idempotency_key TEXT UNIQUE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events(
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  run_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  idempotency_key TEXT UNIQUE,
  ts TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TABLE IF NOT EXISTS checkpoints(
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  completed_json TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  hypothesis TEXT NOT NULL,
  next_action TEXT NOT NULL,
  ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_locks(
  run_id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  acquired_at TEXT NOT NULL
);
"""

# Columns added after the first release; CREATE IF NOT EXISTS does not
# extend an existing table, so each is applied idempotently in _migrate.
_MIGRATIONS = (
    "ALTER TABLE runs ADD COLUMN packet_path TEXT",
    "ALTER TABLE runs ADD COLUMN repo_path TEXT",
    "ALTER TABLE runs ADD COLUMN attempts_used INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE runs ADD COLUMN model_profile TEXT",
)


class InvalidTransition(Exception):
    pass


class RunLocked(Exception):
    pass


class UnknownRun(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


class Journal:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            for statement in _MIGRATIONS:
                try:
                    conn.execute(statement)
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc):
                        raise
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _read(self, sql: str, params: tuple[object, ...]) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            return list(conn.execute(sql, params).fetchall())

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

    def _insert_event(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        kind: str,
        payload: dict[str, object],
        idempotency_key: str | None,
    ) -> str:
        event_id = _new_id("event")
        try:
            conn.execute(
                "INSERT INTO events(event_id, run_id, kind, payload_json,"
                " idempotency_key, ts) VALUES(?,?,?,?,?,?)",
                (event_id, run_id, kind, json.dumps(payload, sort_keys=True),
                 idempotency_key, _now()),
            )
            return event_id
        except sqlite3.IntegrityError:
            if idempotency_key is None:
                raise
            row = conn.execute(
                "SELECT event_id FROM events WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            assert row is not None
            return str(row["event_id"])

    def create_run(
        self, task_id: str, idempotency_key: str | None = None
    ) -> str:
        with self._tx() as conn:
            if idempotency_key is not None:
                row = conn.execute(
                    "SELECT run_id FROM runs WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if row is not None:
                    return str(row["run_id"])
            run_id = _new_id("run")
            conn.execute(
                "INSERT INTO runs(run_id, task_id, state, idempotency_key,"
                " created_at, updated_at) VALUES(?,?,?,?,?,?)",
                (run_id, task_id, "created", idempotency_key, _now(), _now()),
            )
            self._insert_event(
                conn, run_id, "run.created", {"task_id": task_id}, None
            )
            return run_id

    def run_state(self, run_id: str) -> str:
        rows = self._read("SELECT state FROM runs WHERE run_id=?", (run_id,))
        if not rows:
            raise UnknownRun(run_id)
        return str(rows[0]["state"])

    def transition(
        self,
        run_id: str,
        to_state: str,
        idempotency_key: str | None = None,
    ) -> None:
        if to_state not in STATES:
            raise InvalidTransition(f"unknown state {to_state!r}")
        with self._tx() as conn:
            row = conn.execute(
                "SELECT state FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise UnknownRun(run_id)
            current = str(row["state"])
            if to_state not in TRANSITIONS[current]:
                raise InvalidTransition(
                    f"{current} -> {to_state} is not a legal transition"
                )
            conn.execute(
                "UPDATE runs SET state=?, updated_at=? WHERE run_id=?",
                (to_state, _now(), run_id),
            )
            self._insert_event(
                conn, run_id, "state.changed", {"from": current, "to": to_state},
                idempotency_key,
            )

    def record_event(
        self,
        run_id: str,
        kind: str,
        payload: dict[str, object],
        idempotency_key: str | None = None,
    ) -> str:
        with self._tx() as conn:
            if conn.execute(
                "SELECT 1 FROM runs WHERE run_id=?", (run_id,)
            ).fetchone() is None:
                raise UnknownRun(run_id)
            return self._insert_event(conn, run_id, kind, payload, idempotency_key)

    def events(self, run_id: str) -> list[dict[str, object]]:
        rows = self._read(
            "SELECT event_id, sequence, kind, payload_json, ts FROM events"
            " WHERE run_id=? ORDER BY sequence",
            (run_id,),
        )
        return [
            {
                "event_id": str(r["event_id"]),
                "sequence": int(r["sequence"]),
                "kind": str(r["kind"]),
                "payload": json.loads(str(r["payload_json"])),
                "ts": str(r["ts"]),
            }
            for r in rows
        ]

    def checkpoint(
        self,
        run_id: str,
        completed: list[str],
        evidence_refs: list[str],
        hypothesis: str,
        next_action: str,
    ) -> None:
        with self._tx() as conn:
            if conn.execute(
                "SELECT 1 FROM runs WHERE run_id=?", (run_id,)
            ).fetchone() is None:
                raise UnknownRun(run_id)
            conn.execute(
                "INSERT INTO checkpoints(run_id, completed_json, evidence_json,"
                " hypothesis, next_action, ts) VALUES(?,?,?,?,?,?)",
                (
                    run_id,
                    json.dumps(completed),
                    json.dumps(evidence_refs),
                    hypothesis,
                    next_action,
                    _now(),
                ),
            )

    def latest_checkpoint(self, run_id: str) -> dict[str, object]:
        rows = self._read(
            "SELECT completed_json, evidence_json, hypothesis, next_action, ts"
            " FROM checkpoints WHERE run_id=? ORDER BY seq DESC LIMIT 1",
            (run_id,),
        )
        row = rows[0] if rows else None
        if row is None:
            raise UnknownRun(f"no checkpoint for {run_id}")
        return {
            "completed": json.loads(str(row["completed_json"])),
            "evidence_refs": json.loads(str(row["evidence_json"])),
            "hypothesis": str(row["hypothesis"]),
            "next_action": str(row["next_action"]),
            "ts": str(row["ts"]),
        }

    def acquire_run_lock(self, run_id: str, owner: str) -> bool:
        with self._tx() as conn:
            try:
                conn.execute(
                    "INSERT INTO run_locks(run_id, owner, acquired_at)"
                    " VALUES(?,?,?)",
                    (run_id, owner, _now()),
                )
                return True
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT owner FROM run_locks WHERE run_id=?", (run_id,)
                ).fetchone()
                if row is not None and str(row["owner"]) == owner:
                    return True
                raise RunLocked(f"{run_id} is locked") from None

    def runs(self) -> list[dict[str, object]]:
        rows = self._read(
            "SELECT run_id, task_id, state, attempts_used FROM runs"
            " ORDER BY created_at, run_id",
            (),
        )
        return [
            {
                "run_id": str(r["run_id"]),
                "task_id": str(r["task_id"]),
                "state": str(r["state"]),
                "attempts_used": int(r["attempts_used"]),
            }
            for r in rows
        ]

    def set_run_context(
        self, run_id: str, packet_path: str, repo_path: str,
        model_profile: str = "unrecorded",
    ) -> None:
        with self._tx() as conn:
            cursor = conn.execute(
                "UPDATE runs SET packet_path=?, repo_path=?, model_profile=?"
                " WHERE run_id=?",
                (packet_path, repo_path, model_profile, run_id),
            )
            if cursor.rowcount == 0:
                raise UnknownRun(run_id)

    def run_context(self, run_id: str) -> dict[str, object]:
        rows = self._read(
            "SELECT packet_path, repo_path, attempts_used, model_profile"
            " FROM runs WHERE run_id=?",
            (run_id,),
        )
        if not rows:
            raise UnknownRun(run_id)
        row = rows[0]
        return {
            "packet_path": str(row["packet_path"] or ""),
            "repo_path": str(row["repo_path"] or ""),
            "attempts_used": int(row["attempts_used"]),
            "model_profile": str(row["model_profile"] or "unrecorded"),
        }

    def bump_attempts(self, run_id: str) -> int:
        with self._tx() as conn:
            cursor = conn.execute(
                "UPDATE runs SET attempts_used = attempts_used + 1"
                " WHERE run_id=?",
                (run_id,),
            )
            if cursor.rowcount == 0:
                raise UnknownRun(run_id)
            row = conn.execute(
                "SELECT attempts_used FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            assert row is not None
            return int(row["attempts_used"])

    def release_run_lock(self, run_id: str, owner: str) -> None:
        with self._tx() as conn:
            cursor = conn.execute(
                "DELETE FROM run_locks WHERE run_id=? AND owner=?",
                (run_id, owner),
            )
            if cursor.rowcount == 0:
                raise RunLocked(f"{run_id} is not locked by {owner}")
