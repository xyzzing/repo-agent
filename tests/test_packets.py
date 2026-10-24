"""RA-008: worker packet schema (PRD §10 template).

Placeholders must be resolved before dispatch: an unresolved example path
or a 40-hex-looking placeholder base_commit is a rejection, not a packet.
Validation is inert; nothing here runs verification commands.
"""
from pathlib import Path

import pytest

from repo_agent import packets

VALID = """
task_schema_version: 1
task_id: RA-008-fixture
base_commit: '0123456789abcdef0123456789abcdef01234567'
goal: 'Make calc.add add instead of subtract'
read_first: [calc.py]
expected_write_scope: [calc.py]
acceptance:
  - 'calc.add(2, 2) returns 4'
invariants: ['No command execution during render']
non_goals: ['CLI changes']
verification_commands:
  - [python3, -c, "import calc; assert calc.add(2,2)==4"]
budget:
  max_attempts: 3
  timeout_seconds: 1800
required_skills: []
escalate_when:
  - 'Two attempts fail without new diagnostic evidence'
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "task.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_packet_loads(tmp_path):
    packet = packets.load(write(tmp_path, VALID))
    assert packet.task_id == "RA-008-fixture"
    assert packet.acceptance == ["calc.add(2, 2) returns 4"]
    assert packet.budget == {"max_attempts": 3, "timeout_seconds": 1800}
    assert packet.verification_commands == [
        ["python3", "-c", "import calc; assert calc.add(2,2)==4"]
    ]


def test_unknown_field_rejected(tmp_path):
    with pytest.raises(packets.PacketError) as e:
        packets.load(write(tmp_path, VALID + "\nsurprise: 1\n"))
    assert e.value.reason_code == "unknown_field"


def test_placeholder_base_commit_rejected(tmp_path):
    text = VALID.replace("0123456789abcdef0123456789abcdef01234567", "<actual commit>")
    with pytest.raises(packets.PacketError) as e:
        packets.load(write(tmp_path, text))
    assert e.value.reason_code == "unresolved_placeholder"


def test_bad_hex_base_commit_rejected(tmp_path):
    text = VALID.replace("0123456789abcdef0123456789abcdef01234567", "zzz")
    with pytest.raises(packets.PacketError) as e:
        packets.load(write(tmp_path, text))
    assert e.value.reason_code == "invalid_base_commit"


def test_empty_acceptance_rejected(tmp_path):
    text = VALID.replace(
        "acceptance:\n  - 'calc.add(2, 2) returns 4'\n", "acceptance: []\n"
    )
    with pytest.raises(packets.PacketError) as e:
        packets.load(write(tmp_path, text))
    assert e.value.reason_code == "invalid_acceptance"


def test_empty_argv_command_rejected(tmp_path):
    text = VALID.replace(
        "  - [python3, -c, \"import calc; assert calc.add(2,2)==4\"]",
        "  - []",
    )
    with pytest.raises(packets.PacketError) as e:
        packets.load(write(tmp_path, text))
    assert e.value.reason_code == "invalid_command"


def test_prompt_mentions_contract_and_scope(tmp_path):
    packet = packets.load(write(tmp_path, VALID))
    prompt = packets.render_prompt(packet)
    assert packet.goal in prompt
    assert "calc.py" in prompt
    assert "calc.add(2, 2) returns 4" in prompt
    assert "No command execution during render" in prompt
    assert "never modify" in prompt.lower()


def test_duplicate_keys_rejected(tmp_path):
    with pytest.raises(packets.PacketError) as e:
        packets.load(write(tmp_path, VALID + "\ntask_id: other\n"))
    assert e.value.reason_code == "duplicate_key"
