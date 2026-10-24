"""RA-021: the profile registry — versioned identities, qualification,
and the visibility flip. A model_specific record is withheld unless its
producer profile is QUALIFIED; portable records are unaffected. This is
the mechanism that makes a qwen→deepseek switch safe: register the new
profile, qualify it against pinned suites, and the corpus opens up.
"""
import pytest

from repo_agent.profiles import ProfileError, ProfileStore


@pytest.fixture()
def profiles(tmp_path):
    return ProfileStore(tmp_path / "profiles.sqlite")


def test_register_defaults_to_candidate(profiles):
    p = profiles.register(
        "qwen3.8-flash-next@strata-r020", engine="strata-r020",
        model="qwen3.8-flash-next", quantisation="IQ3_S",
    )
    assert p["status"] == "candidate"
    assert profiles.is_qualified("qwen3.8-flash-next@strata-r020") is False


def test_qualify_requires_a_suites_reference(profiles):
    profiles.register("p1", engine="e", model="m")
    with pytest.raises(ProfileError, match="suites"):
        profiles.qualify("p1", suites_ref="")


def test_qualify_flips_status_and_is_qualified(profiles):
    profiles.register("p1", engine="e", model="m")
    profiles.qualify("p1", suites_ref="suites/coding-core-v1")
    assert profiles.is_qualified("p1") is True
    assert profiles.get("p1")["status"] == "qualified"
    assert profiles.get("p1")["suites_ref"] == "suites/coding-core-v1"


def test_unknown_profile_is_never_qualified(profiles):
    assert profiles.is_qualified("never-registered") is False


def test_retired_profile_loses_qualification(profiles):
    profiles.register("p1", engine="e", model="m")
    profiles.qualify("p1", suites_ref="s")
    profiles.retire("p1", "engine replaced")
    assert profiles.is_qualified("p1") is False


def test_rows_append_only(profiles):
    profiles.register("p1", engine="e", model="m")
    import sqlite3

    conn = profiles._connect()  # noqa: SLF001 - the gate under test
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE profiles SET status = 'qualified'")
    finally:
        conn.rollback()
        conn.close()
