"""RA-002: YAML configuration contract.

Every rejection is a structured reason code; a valid config roundtrips
through effective_config() identically; parsing never executes anything.
"""
import json
from pathlib import Path

import pytest

from repo_agent import config

VALID = """
schema_version: 1
project:
  name: sample-project
  maturity: mature
commands:
  lint: [uv, run, ruff, check, .]
  test: [uv, run, pytest, -q]
  verify: [lint, test]
"""


def write(tmp_path: Path, text: str, name: str = "repo-agent.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def reason_for(tmp_path, text) -> str:
    with pytest.raises(config.ValidationError) as excinfo:
        config.load(write(tmp_path, text), repo_root=tmp_path)
    return excinfo.value.reason_code


def test_valid_config_loads_with_defaults(tmp_path):
    loaded = config.load(write(tmp_path, VALID), repo_root=tmp_path)
    assert loaded.config["project"]["name"] == "sample-project"
    assert loaded.config["execution"]["max_attempts"] == 3
    assert loaded.defaults_applied["execution.max_attempts"] == 3


def test_effective_config_roundtrip_and_provenance(tmp_path):
    loaded = config.load(write(tmp_path, VALID), repo_root=tmp_path)
    effective = loaded.effective(generator="repo-agent 0.1.0")
    again = json.loads(json.dumps(effective))
    assert again == effective
    assert effective["source"]["sha256"]
    assert effective["source"]["bytes"] > 0
    assert effective["config_schema_version"] == 1
    assert set(effective) == {
        "config",
        "config_schema_version",
        "defaults_applied",
        "generated_by",
        "source",
    }


def test_duplicate_key_rejected(tmp_path):
    text = VALID + "\nproject:\n  name: other\n"
    assert reason_for(tmp_path, text) == "duplicate_key"


def test_unknown_field_rejected(tmp_path):
    assert reason_for(tmp_path, VALID + "\nsurprise: 1\n") == "unknown_field"


def test_unknown_nested_field_rejected(tmp_path):
    assert (
        reason_for(tmp_path, VALID + "\nexecution:\n  max_attempts: 1\n  zorp: 2\n")
        == "unknown_field"
    )


def test_unsupported_version_rejected(tmp_path):
    assert reason_for(tmp_path, VALID.replace("schema_version: 1", "schema_version: 2")) == (
        "unsupported_version"
    )


def test_unsafe_tag_rejected(tmp_path):
    text = "schema_version: 1\nproject: !!python/object/apply:os.system ['echo hi']\n"
    assert reason_for(tmp_path, text) == "unsafe_tag"


def test_oversized_input_rejected(tmp_path):
    big = VALID + "\n#" + "x" * 300_000
    assert reason_for(tmp_path, big) == "too_large"


def test_excessive_nesting_rejected(tmp_path):
    deep = VALID.replace(
        "  name: sample-project\n",
        "  name:\n    a:\n      b:\n        c:\n          d: 1\n",
    )
    assert reason_for(tmp_path, deep) == "too_deep"


def test_path_traversal_rejected(tmp_path):
    text = VALID + "\ninstructions:\n  project_notes: ../../etc/passwd\n"
    assert reason_for(tmp_path, text) == "invalid_path"


def test_absolute_path_rejected(tmp_path):
    text = VALID + "\ninstructions:\n  project_notes: /etc/passwd\n"
    assert reason_for(tmp_path, text) == "invalid_path"


def test_symlink_escape_rejected(tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("x", encoding="utf-8")
    link = tmp_path / "leak.md"
    link.symlink_to(outside)
    text = VALID + "\ninstructions:\n  project_notes: leak.md\n"
    assert reason_for(tmp_path, text) == "invalid_path"


def test_in_repo_symlink_and_path_accepted(tmp_path):
    notes = tmp_path / "AGENTS.project.md"
    notes.write_text("notes", encoding="utf-8")
    text = VALID + "\ninstructions:\n  project_notes: AGENTS.project.md\n"
    loaded = config.load(write(tmp_path, text), repo_root=tmp_path)
    assert loaded.config["instructions"]["project_notes"] == "AGENTS.project.md"


def commands_config(commands_body: str) -> str:
    return (
        "schema_version: 1\nproject:\n  name: x\n  maturity: new\n"
        "commands:\n" + commands_body
    )


def test_empty_argv_rejected(tmp_path):
    assert reason_for(tmp_path, commands_config("  lint: []\n")) == "invalid_command"


def test_non_string_argv_rejected(tmp_path):
    assert (
        reason_for(tmp_path, commands_config("  lint: [uv, run, 3]\n"))
        == "invalid_command"
    )


def test_verify_unknown_reference_rejected(tmp_path):
    assert reason_for(tmp_path, commands_config("  verify: [nope]\n")) == (
        "invalid_command"
    )


def test_verify_cycle_rejected(tmp_path):
    # Only `verify` composes other commands (PRD §4), so the only cycle
    # shape is a self-reference.
    assert reason_for(tmp_path, commands_config("  verify: [verify]\n")) == "cycle"


def test_typoed_section_rejected(tmp_path):
    assert reason_for(tmp_path, VALID + "\ncommandz:\n  lint: []\n") == "unknown_field"


def test_validation_is_inert(tmp_path):
    inert = VALID.replace("schema_version: 1", "schema_version: 1") + (
        "\nenvironment:\n  setup: [definitely-missing-binary-abc, --flag]\n"
    )
    loaded = config.load(write(tmp_path, inert), repo_root=tmp_path)
    assert loaded.config["environment"]["setup"] == [
        "definitely-missing-binary-abc",
        "--flag",
    ]


def test_missing_required_sections(tmp_path):
    assert reason_for(tmp_path, "schema_version: 1\n") == "missing_required"
