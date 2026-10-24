"""RA-008: worker packet schema and prompt rendering (PRD §10).

Placeholders must be resolved before dispatch: an unresolved example
value is a rejection, not a packet. Validation is inert — nothing here
runs verification commands or reads repos.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from yaml.constructor import ConstructorError
from yaml.error import YAMLError

HEX40 = re.compile(r"^[0-9a-f]{40}$")
UNRESOLVED = ("<", ">", "example", "actual", "placeholder")
UPPER_UNRESOLVED = tuple(t.upper() for t in UNRESOLVED)

_FIELDS = {
    "task_schema_version": int,
    "task_id": str,
    "base_commit": str,
    "goal": str,
    "read_first": list,
    "expected_write_scope": list,
    "acceptance": list,
    "invariants": list,
    "non_goals": list,
    "verification_commands": list,
    "budget": dict,
    "required_skills": list,
    "escalate_when": list,
}
_LIST_FIELDS = (
    "read_first",
    "expected_write_scope",
    "acceptance",
    "invariants",
    "non_goals",
    "verification_commands",
    "required_skills",
    "escalate_when",
)
_BUDGET_FIELDS = {"max_attempts": int, "timeout_seconds": int}


class PacketError(Exception):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


@dataclass(frozen=True)
class Packet:
    task_schema_version: int
    task_id: str
    base_commit: str
    goal: str
    read_first: list[str]
    expected_write_scope: list[str]
    acceptance: list[str]
    invariants: list[str]
    non_goals: list[str]
    verification_commands: list[list[str]]
    budget: dict[str, int]
    required_skills: list[str]
    escalate_when: list[str]


def _no_dupes(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[object, object]:
    seen: set[object] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in seen:
            raise PacketError("duplicate_key", f"key {key!r} appears twice")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=True)


class _PacketLoader(yaml.SafeLoader):
    pass


_PacketLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dupes
)


def _err(reason: str, message: str) -> PacketError:
    return PacketError(reason, message)


def _strings(value: object, where: str) -> list[str]:
    if not isinstance(value, list):
        raise _err("invalid_type", f"{where} must be a list")
    for item in value:
        if not isinstance(item, str) or not item:
            raise _err("invalid_type", f"{where} entries must be nonempty strings")
    return list(value)  # type: ignore[arg-type]


def _load_raw(raw: bytes) -> dict[str, object]:
    try:
        document = yaml.load(raw.decode("utf-8"), Loader=_PacketLoader)
    except ConstructorError as exc:
        raise _err("unsafe_tag", str(exc.problem)) from None
    except YAMLError as exc:
        message = str(exc)
        reason = "duplicate_key" if "appears twice" in message else "invalid_yaml"
        raise _err(reason, message) from None
    except UnicodeDecodeError as exc:
        raise _err("invalid_yaml", str(exc)) from None
    if not isinstance(document, dict):
        raise _err("invalid_yaml", "top level must be a mapping")
    return document


def load(path: Path) -> Packet:
    document = _load_raw(Path(path).read_bytes())
    unknown = set(document) - set(_FIELDS)
    if unknown:
        raise _err("unknown_field", f"unknown keys: {sorted(unknown)}")
    version = document.get("task_schema_version")
    if version != 1:
        raise _err("unsupported_version", f"task_schema_version {version!r} not supported")
    for name in ("task_id", "goal", "base_commit"):
        value = document.get(name)
        if not isinstance(value, str) or not value.strip():
            raise _err("invalid_type", f"{name} must be a nonempty string")
    base_commit = str(document["base_commit"])
    if not HEX40.match(base_commit):
        lowered = base_commit.lower()
        if any(token in lowered for token in UNRESOLVED) or any(
            token in base_commit for token in UPPER_UNRESOLVED
        ):
            raise _err(
                "unresolved_placeholder", f"base_commit is not a resolved hash: {base_commit!r}"
            )
        raise _err("invalid_base_commit", f"base_commit must be a 40-hex sha: {base_commit!r}")

    acceptance = _strings(document.get("acceptance"), "acceptance")
    if not acceptance:
        raise _err("invalid_acceptance", "a packet without acceptance is not a task")
    verification = document.get("verification_commands")
    if not isinstance(verification, list):
        raise _err("invalid_type", "verification_commands must be a list of argv")
    commands: list[list[str]] = []
    for entry in verification:
        if not isinstance(entry, list) or not entry:
            raise _err("invalid_command", "verification_commands entries must be nonempty argv")
        for item in entry:
            if not isinstance(item, str) or not item:
                raise _err("invalid_command", "argv entries must be nonempty strings")
        commands.append(list(entry))  # type: ignore[arg-type]

    budget_raw = document.get("budget")
    if not isinstance(budget_raw, dict):
        raise _err("invalid_type", "budget must be a mapping")
    unknown_budget = set(budget_raw) - set(_BUDGET_FIELDS)
    if unknown_budget:
        raise _err("unknown_field", f"unknown budget keys: {sorted(unknown_budget)}")
    budget: dict[str, int] = {}
    for name, kind in _BUDGET_FIELDS.items():
        value = budget_raw.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise _err("invalid_type", f"budget.{name} must be a positive integer")
        assert kind is int
        budget[name] = value

    return Packet(
        task_schema_version=1,
        task_id=str(document["task_id"]),
        base_commit=base_commit,
        goal=str(document["goal"]),
        read_first=_strings(document.get("read_first", []), "read_first"),
        expected_write_scope=_strings(
            document.get("expected_write_scope", []), "expected_write_scope"
        ),
        acceptance=acceptance,
        invariants=_strings(document.get("invariants", []), "invariants"),
        non_goals=_strings(document.get("non_goals", []), "non_goals"),
        verification_commands=commands,
        budget=budget,
        required_skills=_strings(document.get("required_skills", []), "required_skills"),
        escalate_when=_strings(document.get("escalate_when", []), "escalate_when"),
    )


def render_prompt(packet: Packet) -> str:
    """Deterministic worker prompt: the packet contract, nothing else."""
    lines = [
        f"Task {packet.task_id}: {packet.goal}",
        "",
        f"Base commit (do not change): {packet.base_commit}",
        "",
        "Read first: " + (", ".join(packet.read_first) or "(nothing listed)"),
        "",
        "Expected write scope (never modify anything outside it): "
        + (", ".join(packet.expected_write_scope) or "(no scope listed; ask)"),
        "",
        "Acceptance (all must hold):",
    ]
    lines += [f"- {item}" for item in packet.acceptance]
    if packet.invariants:
        lines += ["", "Invariants:"] + [f"- {item}" for item in packet.invariants]
    if packet.non_goals:
        lines += ["", "Non-goals (do not do these):"] + [
            f"- {item}" for item in packet.non_goals
        ]
    lines += ["", "Verification you may run:"]
    lines += [f"- {' '.join(argv)}" for argv in packet.verification_commands]
    if packet.escalate_when:
        lines += ["", "Escalate instead of retrying when:"] + [
            f"- {item}" for item in packet.escalate_when
        ]
    lines += [
        "",
        "Handoff: report what you changed, the checks you ran with exit "
        "codes, baseline failures, and remaining risks. Never claim a "
        "check you did not run.",
        "",
    ]
    return "\n".join(lines)
