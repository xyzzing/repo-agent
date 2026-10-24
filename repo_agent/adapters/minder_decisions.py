"""Minder decision contract and policies (RA-009, PRD §9).

Minder has no out-of-process decision surface (verified against the
minder tree: its sink is persistence + stats only). Decisions are
therefore local and fail-closed: LocalPolicy enforces the packet's own
immutable budget; an operator who demands minder decisions gets
RequiredMinderPolicy, which blocks escalation rather than fail open.

Every decision carries the PRD §9 fields; parse_decision validates
untrusted dicts (unknown fields, missing fields, bad types and unknown
actions are named rejections) and validate_decision rejects stale,
expired and replayed decisions before the runner acts on them.
"""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Protocol

from repo_agent.adapters.minder import MinderEvents

MINDER_ACTIONS = (
    "continue",
    "retry_with_evidence",
    "consult_frontier",
    "pause",
    "stop",
)
POLICY_VERSION = "local-v1"

class PolicyBlocked(Exception):
    """A required policy decision is unavailable; escalation must stop."""


def _now():
    return datetime.now(UTC)



class Decision:
    def __init__(
        self,
        decision_id: str,
        run_id: str,
        basis_event_ids: list[str],
        action: str,
        reason_code: str,
        remaining_budget: int | None,
        policy_version: str = POLICY_VERSION,
        expires_at: str | None = None,
    ):
        assert action in MINDER_ACTIONS, action
        self.decision_id = decision_id
        self.run_id = run_id
        self.basis_event_ids = tuple(basis_event_ids)
        self.action = action
        self.reason_code = reason_code
        self.remaining_budget = remaining_budget
        self.policy_version = policy_version
        self.expires_at = expires_at or (
            (_now() + timedelta(hours=1)).isoformat()
        )


_DECISION_KEYS = {
    "decision_id",
    "run_id",
    "basis_event_ids",
    "action",
    "reason_code",
    "policy_version",
    "remaining_budget",
    "expires_at",
}
_DECISION_REQUIRED = (
    "decision_id",
    "run_id",
    "basis_event_ids",
    "action",
    "reason_code",
    "policy_version",
)


def parse_decision(raw: object) -> Decision:
    """Validate an untrusted decision dict against the PRD §9 contract:
    unknown fields, missing fields, bad types and unknown actions are
    named rejections before anything is constructed."""
    if not isinstance(raw, dict):
        raise PolicyBlocked("malformed_decision: decision must be a JSON object")
    unknown = set(raw) - _DECISION_KEYS
    if unknown:
        raise PolicyBlocked(f"unknown_field: decision carries {sorted(unknown)}")
    missing = [key for key in _DECISION_REQUIRED if key not in raw]
    if missing:
        raise PolicyBlocked(f"malformed_decision: missing {missing}")
    for key in ("decision_id", "run_id", "action", "reason_code", "policy_version"):
        value = raw[key]
        if not isinstance(value, str) or not value:
            raise PolicyBlocked(
                f"malformed_decision: {key} must be a nonempty string"
            )
    basis = raw["basis_event_ids"]
    if not isinstance(basis, list) or any(
        not isinstance(item, str) or not item for item in basis
    ):
        raise PolicyBlocked(
            "malformed_decision: basis_event_ids must be nonempty strings"
        )
    budget = raw.get("remaining_budget")
    if budget is not None and (isinstance(budget, bool) or not isinstance(budget, int)):
        raise PolicyBlocked(
            "malformed_decision: remaining_budget must be an integer or null"
        )
    expires = raw.get("expires_at")
    if expires is not None and (not isinstance(expires, str) or not expires):
        raise PolicyBlocked(
            "malformed_decision: expires_at must be a timestamp string or null"
        )
    if raw["action"] not in MINDER_ACTIONS:
        raise PolicyBlocked(f"unknown_action: {raw['action']}")
    return Decision(
        decision_id=str(raw["decision_id"]),
        run_id=str(raw["run_id"]),
        basis_event_ids=list(basis),
        action=str(raw["action"]),
        reason_code=str(raw["reason_code"]),
        remaining_budget=budget,
        policy_version=str(raw["policy_version"]),
        expires_at=expires,
    )


class RunPolicy(Protocol):
    """What the runner needs from a policy authority (PRD §9): optional
    telemetry, and a validated decision before every spend."""

    events: MinderEvents | None

    def decide(
        self, attempt: int, basis_event_ids: list[str], run_id: str | None = ...
    ) -> Decision: ...


class LocalPolicy:
    """Deterministic decisions from the packet's own immutable budget:
    continue while attempts remain, stop at the floor. Each decision is
    audited into the run journal; the runner still validates before
    acting — replay/run checks are the runner's enforcement point."""

    events: MinderEvents | None = None

    def __init__(
        self,
        journal,
        run_id: str,
        max_attempts: int,
        events: MinderEvents | None = None,
    ):
        self.journal = journal
        self.run_id = run_id
        self.max_attempts = max_attempts
        self.events = events

    def decide(
        self, attempt: int, basis_event_ids: list[str], run_id: str | None = None
    ) -> Decision:
        if run_id is not None and run_id != self.run_id:
            raise PolicyBlocked(
                f"stale decision: run_mismatch ({run_id} != {self.run_id})"
            )
        remaining = max(0, self.max_attempts - attempt)
        if remaining <= 0:
            action, reason = "stop", "budget_exhausted"
        elif attempt == 1:
            action, reason = "continue", "budget_available"
        else:
            action, reason = "retry_with_evidence", "attempts_remain"
        decision = Decision(
            decision_id=f"dec-{uuid.uuid4().hex}",
            run_id=self.run_id,
            basis_event_ids=basis_event_ids,
            action=action,
            reason_code=reason,
            remaining_budget=remaining,
        )
        self.journal.record_event(
            self.run_id,
            "policy.decision",
            {
                "decision_id": decision.decision_id,
                "attempt": attempt,
                "action": action,
                "reason_code": reason,
                "policy_version": POLICY_VERSION,
                "basis_event_ids": list(basis_event_ids),
            },
            idempotency_key=f"policy:{decision.decision_id}",
        )
        return decision


class RequiredMinderPolicy:
    """The operator requires minder to decide; minder has no external
    decision surface today, so every escalation blocks (fail closed)."""

    events: MinderEvents | None = None

    def __init__(self, reason: str):
        self.reason = reason

    def decide(
        self, attempt: int, basis_event_ids: list[str], run_id: str | None = None
    ) -> Decision:
        raise PolicyBlocked(
            f"minder policy required but unavailable: {self.reason}"
        )


def validate_decision(
    decision: Decision, run_id: str, seen: set[str], now: datetime | None = None
) -> None:
    """Reject decisions that are for another run, expired, or replayed.
    The runner calls this before acting; a rejection blocks escalation."""
    if decision.run_id != run_id:
        raise PolicyBlocked(f"stale decision: run_mismatch ({decision.run_id})")
    if decision.decision_id in seen:
        raise PolicyBlocked(f"stale decision: replayed ({decision.decision_id})")
    expires = datetime.fromisoformat(decision.expires_at)
    if (now or _now()) >= expires:
        raise PolicyBlocked("stale decision: expired")
    seen.add(decision.decision_id)
