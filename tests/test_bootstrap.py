"""RA-004b: bootstrap proposals for new and mature repos (issue #4).

Default is plan-only: a proposal names every file it would create,
overwrite, or back up, with the base content hash it reviewed. --apply
executes that recorded proposal and refuses if the world drifted since.
"""
import json

from repo_agent import cli
from repo_agent.config import load


def payload_of(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_new_mode_plan_writes_nothing(tmp_path, capsys):
    assert cli.main(["bootstrap", str(tmp_path), "--mode", "new"]) == 0
    payload = payload_of(capsys)
    assert payload["proposal"]["create"]["repo-agent.yaml"]
    assert not (tmp_path / "repo-agent.yaml").exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_new_mode_apply_creates_valid_config_and_owned_agents(tmp_path, capsys):
    assert cli.main(["bootstrap", str(tmp_path), "--mode", "new", "--apply"]) == 0
    loaded = load(tmp_path / "repo-agent.yaml", repo_root=tmp_path)
    assert loaded.config["project"]["name"] == tmp_path.name
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "repo-agent:generated" in agents
    assert (tmp_path / "AGENTS.project.md").is_file()
    # a second apply is refused: already configured
    assert cli.main(["bootstrap", str(tmp_path), "--mode", "new", "--apply"]) == 3


def test_new_mode_uses_inspected_test_runner(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8"
    )
    assert cli.main(["bootstrap", str(tmp_path), "--mode", "new", "--apply"]) == 0
    config_text = (tmp_path / "repo-agent.yaml").read_text(encoding="utf-8")
    assert "pytest" in config_text


def test_mature_mode_preserves_handwritten_agents_verbatim(tmp_path, capsys):
    hand = "# Hand-written rules\n\nKeep off the mainframe. Never edit gen/.\n"
    (tmp_path / "AGENTS.md").write_text(hand, encoding="utf-8")
    assert cli.main(["bootstrap", str(tmp_path), "--mode", "mature", "--apply"]) == 0
    payload = payload_of(capsys)
    # the original is backed up, byte-identical
    backups = list((tmp_path / ".repo-agent" / "backups").glob("AGENTS.md.*"))
    assert backups and backups[0].read_text(encoding="utf-8") == hand
    # the migrated notes carry the old content verbatim
    notes = (tmp_path / "AGENTS.project.md").read_text(encoding="utf-8")
    assert "Keep off the mainframe. Never edit gen/." in notes
    # the generated file is now owned
    assert "repo-agent:generated" in (tmp_path / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    assert payload["proposal"]["backup"]


def test_apply_refuses_drift_since_proposal(tmp_path, capsys):
    hand = "# original\n"
    (tmp_path / "AGENTS.md").write_text(hand, encoding="utf-8")
    assert cli.main(["bootstrap", str(tmp_path), "--mode", "mature"]) == 0
    payload_of(capsys)  # discard the plan payload before reading the apply output
    proposal_file = tmp_path / ".repo-agent" / "proposal.json"
    assert proposal_file.is_file()
    # someone edits between plan and apply
    (tmp_path / "AGENTS.md").write_text("# edited after plan\n", encoding="utf-8")
    assert cli.main(["bootstrap", str(tmp_path), "--mode", "mature", "--apply"]) == 3
    payload = payload_of(capsys)
    assert payload["reason_code"] == "drift_since_proposal"
    # and the drifted file is untouched
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "# edited after plan\n"


def test_unrelated_files_untouched(tmp_path, capsys):
    (tmp_path / "unrelated.txt").write_text("keep me\n", encoding="utf-8")
    assert cli.main(["bootstrap", str(tmp_path), "--mode", "new", "--apply"]) == 0
    assert (tmp_path / "unrelated.txt").read_text(encoding="utf-8") == "keep me\n"
