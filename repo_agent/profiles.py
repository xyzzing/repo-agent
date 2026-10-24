"""Profile registry (RA-021, PRD §12B): versioned execution identities
and their qualification status.

A profile is an engine/model/quantisation identity, not a name: the
registry exists so the corpus can answer "is THIS producer's
model-specific knowledge safe to surface for THIS serving profile?"
Status is candidate by default; qualification requires a reference to
the pinned suites that were run; retiring revokes it. Rows are
append-only — status changes add a new revision, like memories.
"""
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

_STATUSES = ("candidate", "qualified", "retired")


class ProfileError(Exception):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


def _now() -> str:
    return datetime.now(UTC).isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles(
  rowid_pk INTEGER PRIMARY KEY AUTOINCREMENT,
  profile_id TEXT NOT NULL,
  engine TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  quantisation TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'candidate',
  suites_ref TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  ts TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS profiles_no_update BEFORE UPDATE ON profiles
  BEGIN SELECT RAISE(ABORT, 'profiles are append-only'); END;
CREATE TRIGGER IF NOT EXISTS profiles_no_delete BEFORE DELETE ON profiles
  BEGIN SELECT RAISE(ABORT, 'profiles are append-only'); END;
CREATE INDEX IF NOT EXISTS profiles_latest ON profiles(profile_id, rowid_pk);
"""


class ProfileStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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

    def _insert(self, state: dict[str, object]) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO profiles(profile_id, engine, model, quantisation,"
                " status, suites_ref, note, ts) VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(state["profile_id"]), str(state["engine"]),
                    str(state["model"]), str(state["quantisation"]),
                    str(state["status"]), str(state["suites_ref"]),
                    str(state["note"]), _now(),
                ),
            )

    def _latest(self, profile_id: str) -> dict[str, object] | None:
        rows = self._read(
            "SELECT * FROM profiles WHERE profile_id=?"
            " ORDER BY rowid_pk DESC LIMIT 1",
            (profile_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "profile_id": str(r["profile_id"]),
            "engine": str(r["engine"]),
            "model": str(r["model"]),
            "quantisation": str(r["quantisation"]),
            "status": str(r["status"]),
            "suites_ref": str(r["suites_ref"]),
            "note": str(r["note"]),
        }

    def register(
        self, profile_id: str, engine: str = "", model: str = "",
        quantisation: str = "", note: str = "",
    ) -> dict[str, object]:
        if not profile_id.strip():
            raise ProfileError("empty_profile", "profile_id required")
        state: dict[str, object] = {
            "profile_id": profile_id, "engine": engine, "model": model,
            "quantisation": quantisation, "status": "candidate",
            "suites_ref": "", "note": note,
        }
        self._insert(state)
        return state

    def qualify(self, profile_id: str, suites_ref: str) -> dict[str, object]:
        state = self._latest(profile_id)
        if state is None:
            raise ProfileError("unknown_profile", profile_id)
        if not suites_ref.strip():
            raise ProfileError(
                "suites_required",
                "qualification needs the pinned suites it ran against",
            )
        if state["status"] == "retired":
            raise ProfileError("retired_profile", f"{profile_id} is retired")
        state = {**state, "status": "qualified", "suites_ref": suites_ref}
        self._insert(state)
        return state

    def retire(self, profile_id: str, note: str) -> dict[str, object]:
        state = self._latest(profile_id)
        if state is None:
            raise ProfileError("unknown_profile", profile_id)
        state = {**state, "status": "retired", "note": note}
        self._insert(state)
        return state

    def get(self, profile_id: str) -> dict[str, object]:
        state = self._latest(profile_id)
        if state is None:
            raise ProfileError("unknown_profile", profile_id)
        return state

    def list(self) -> list[dict[str, object]]:
        rows = self._read(
            "SELECT p.* FROM profiles p"
            " JOIN (SELECT profile_id, MAX(rowid_pk) AS m FROM profiles"
            "  GROUP BY profile_id) l"
            " ON p.profile_id = l.profile_id AND p.rowid_pk = l.m"
            " ORDER BY p.profile_id"
        )
        return [
            {
                "profile_id": str(r["profile_id"]),
                "engine": str(r["engine"]),
                "model": str(r["model"]),
                "quantisation": str(r["quantisation"]),
                "status": str(r["status"]),
                "suites_ref": str(r["suites_ref"]),
            }
            for r in rows
        ]

    def qualified_ids(self) -> set[str]:
        return {
            str(p["profile_id"]) for p in self.list()
            if p["status"] == "qualified"
        }

    def is_qualified(self, profile_id: str) -> bool:
        return profile_id in self.qualified_ids()
