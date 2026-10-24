"""Configuration loading and validation (RA-002, PRD §4).

Parsing is inert: nothing here executes setup, verify, or any other
command. Rejections are ValidationError with a stable reason code so CLI
layers can report them without string matching.
"""
import dataclasses
import hashlib
import json
import posixpath
from pathlib import Path, PurePosixPath

import yaml
from yaml.constructor import ConstructorError
from yaml.error import YAMLError

from repo_agent import config_schema as schema


class ValidationError(Exception):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate keys. Depth is checked after the
    parse: SafeLoader defers nested construction, so a load-time counter
    does not see real nesting."""

    def construct_mapping(self, node, deep=False):  # type: ignore[override]
        keys: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            try:
                duplicate = key in keys
            except TypeError:
                raise ValidationError(
                    "duplicate_key", f"unhashable mapping key: {key_node.value!r}"
                ) from None
            if duplicate:
                raise ValidationError("duplicate_key", f"key {key!r} appears twice")
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def _walk_depth(node: object, depth: int = 1) -> None:
    if depth > schema.MAX_DEPTH:
        raise ValidationError("too_deep", f"nesting exceeds {schema.MAX_DEPTH} levels")
    if isinstance(node, dict):
        for value in node.values():
            _walk_depth(value, depth + 1)
    elif isinstance(node, list):
        for value in node:
            _walk_depth(value, depth + 1)


def _parse(raw: bytes) -> object:
    if len(raw) > schema.MAX_BYTES:
        raise ValidationError("too_large", f"config exceeds {schema.MAX_BYTES} bytes")
    try:
        return yaml.load(raw.decode("utf-8"), Loader=_StrictLoader)
    except ConstructorError as exc:
        raise ValidationError("unsafe_tag", str(exc.problem)) from None
    except YAMLError as exc:
        raise ValidationError("invalid_yaml", str(exc)) from None
    except UnicodeDecodeError as exc:
        raise ValidationError("invalid_yaml", str(exc)) from None
    except RecursionError:
        raise ValidationError(
            "too_deep", "document too deeply nested to parse safely"
        ) from None


def _check_type(value: object, kind: str, where: str) -> None:
    if kind == "argv" or kind == "str_list" or kind == "path_list" or kind == "glob_list":
        if not isinstance(value, list) or not value:
            raise ValidationError("invalid_command" if kind == "argv" else "invalid_type",
                                  f"{where} must be a nonempty list")
        for item in value:
            if not isinstance(item, str) or not item:
                raise ValidationError(
                    "invalid_command" if kind == "argv" else "invalid_type",
                    f"{where} entries must be nonempty strings",
                )
        if kind == "argv" and not value[0]:
            raise ValidationError("invalid_command", f"{where} has an empty argv[0]")
    elif kind == schema.INT:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError("invalid_type", f"{where} must be an integer")
    elif kind == schema.BOOL:
        if not isinstance(value, bool):
            raise ValidationError("invalid_type", f"{where} must be a boolean")
    elif kind == "path":
        if not isinstance(value, str) or not value:
            raise ValidationError("invalid_type", f"{where} must be a path string")
    elif kind == "verify":
        if not isinstance(value, list) or not value or not all(
            isinstance(item, str) and item for item in value
        ):
            raise ValidationError(
                "invalid_command", f"{where} must be a nonempty list of command names"
            )
    elif kind.startswith("enum:"):
        allowed = kind[5:].split("|")
        if value not in allowed:
            raise ValidationError(
                "invalid_type", f"{where} must be one of {', '.join(allowed)}"
            )
    elif kind == schema.STRING:
        if not isinstance(value, str) or not value:
            raise ValidationError("invalid_type", f"{where} must be a nonempty string")
    else:  # pragma: no cover - schema bug guard
        raise ValidationError("invalid_type", f"{where}: unknown spec kind {kind}")


def _safe_rel_path(raw: str, where: str, repo_root: Path) -> str:
    pure = PurePosixPath(raw)
    if pure.is_absolute() or raw.startswith("~"):
        raise ValidationError("invalid_path", f"{where} must be repo-relative: {raw}")
    normalized = posixpath.normpath(raw)
    if normalized == ".." or normalized.startswith("../"):
        raise ValidationError("invalid_path", f"{where} escapes the repo: {raw}")
    resolved = (repo_root / normalized).resolve()
    root_resolved = repo_root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValidationError(
            "invalid_path", f"{where} resolves outside the repo via symlink: {raw}"
        )
    return normalized


def _validate_section(
    body: object,
    spec: dict[str, object],
    prefix: str,
    repo_root: Path,
    out: dict[str, object],
    where_prefix: str = "",
) -> None:
    if not isinstance(body, dict):
        raise ValidationError("invalid_type", f"{prefix} must be a mapping")
    wildcard = spec.get("*")
    for key, value in body.items():
        where = f"{prefix}.{key}"
        if key == "*":
            raise ValidationError("unknown_field", f"literal '*' key in {prefix}")
        if key in spec:
            kind = spec[key]
        elif wildcard is not None:
            kind = wildcard
        else:
            raise ValidationError("unknown_field", f"unknown key {where}")
        if isinstance(kind, dict):
            _validate_section(value, kind, where, repo_root, out, where_prefix)
            continue
        assert isinstance(kind, str)
        _check_type(value, kind, where)
        if kind == "path":
            out[str(key)] = _safe_rel_path(value, where, repo_root)
        elif kind == "path_list":
            out[str(key)] = [_safe_rel_path(item, where, repo_root) for item in value]
        elif kind == "verify":
            out[str(key)] = list(value)
        elif kind == schema.INT and f"{prefix}.{key}" in schema.POSITIVE_INTS and value <= 0:
            raise ValidationError("invalid_type", f"{where} must be positive")
        else:
            out[str(key)] = value


def _check_commands(commands: dict[str, object]) -> None:
    verify = commands.get("verify")
    if verify is None:
        return
    assert isinstance(verify, list)
    for name in verify:
        if name not in commands:
            raise ValidationError(
                "invalid_command", f"verify references unknown command {name!r}"
            )
        if name == "verify":
            raise ValidationError(
                "cycle", "verify composes commands; it cannot reference itself"
            )


@dataclasses.dataclass(frozen=True)
class LoadedConfig:
    config: dict[str, object]
    defaults_applied: dict[str, object]
    source: dict[str, object]

    def effective(self, generator: str) -> dict[str, object]:
        return {
            "config_schema_version": schema.SCHEMA_VERSION,
            "generated_by": generator,
            "source": self.source,
            "defaults_applied": dict(self.defaults_applied),
            "config": self.config,
        }

    def write_effective(self, generator: str, path: Path) -> None:
        path.write_text(
            json.dumps(self.effective(generator), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def load(path: Path, repo_root: Path) -> LoadedConfig:
    raw = path.read_bytes()
    source = {
        "path": _safe_rel_path(
            path.relative_to(repo_root).as_posix(), "config location", repo_root
        )
        if path.is_relative_to(repo_root)
        else str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    document = _parse(raw)
    _walk_depth(document)
    if not isinstance(document, dict):
        raise ValidationError("invalid_yaml", "top level must be a mapping")
    version = document.get("schema_version")
    if version != schema.SCHEMA_VERSION:
        raise ValidationError(
            "unsupported_version", f"schema_version {version!r} not supported"
        )
    for name in schema.REQUIRED_SECTIONS:
        if name not in document:
            raise ValidationError("missing_required", f"missing section {name!r}")
    unknown_top = set(document) - {"schema_version"} - set(schema.SECTIONS)
    if unknown_top:
        raise ValidationError(
            "unknown_field", f"unknown top-level keys: {sorted(unknown_top)}"
        )

    validated: dict[str, object] = {"schema_version": version}
    defaults_applied: dict[str, object] = {}
    for section, spec in schema.SECTIONS.items():
        body: dict[str, object] = {}
        if section in document:
            _validate_section(
                document[section], spec, section, repo_root, body, where_prefix=section
            )
        for dotted, default in schema.DEFAULTS.items():
            head, _, rest = dotted.partition(".")
            if head != section:
                continue
            leaf, _, sub = rest.partition(".")
            if sub:
                nested = body.setdefault(leaf, {})
                if not isinstance(nested, dict):
                    raise ValidationError(
                        "invalid_type", f"{section}.{leaf} must be a mapping"
                    )
                if sub not in nested:
                    nested[sub] = default
                    defaults_applied[dotted] = default
            elif leaf not in body:
                body[leaf] = default
                defaults_applied[dotted] = default
        if body:
            validated[section] = body
    if "commands" in validated:
        _check_commands(validated["commands"])  # type: ignore[arg-type]
    return LoadedConfig(config=validated, defaults_applied=defaults_applied, source=source)
