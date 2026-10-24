"""RA-006: fake-worker vertical slice through the protected verifier.

The fake worker is a real subprocess (a small script the tests write into
the workspace), so every claim below is exercised across a process
boundary: staging, patch freezing, verdict binding, grader integrity, and
forged-result rejection.
"""
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from repo_agent.containment import (
    PROBE_IMAGE,
    containment_level,
    run_containment_probes,
)
from repo_agent.state import Journal
from repo_agent.verifier import (
    TAMPERED_GRADER,
    VERDICT_INVALIDATED,
    Verifier,
    apply_patch,
    collect_patch,
    stage_workspace,
)

BASE_FILES = {
    "calc.py": "def add(a, b):\n    return a - b\n",  # the planted bug
    "README.md": "fixture\n",
}


@pytest.fixture()
def base(tmp_path: Path) -> Path:
    root = tmp_path / "base"
    root.mkdir()
    for name, text in BASE_FILES.items():
        (root / name).write_text(text, encoding="utf-8")
    return root


GRADER = """#!/bin/sh
# trusted grader: reruns the pinned test file against the candidate
set -e
cd "$VERIFIER_ROOT"
python3 - <<'PY'
import calc
assert calc.add(2, 2) == 4, "add is broken"
print("grader-ok")
PY
"""


def make_worker(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake-worker.py"
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


GOOD_WORKER = """
import os, pathlib
ws = os.environ["WORKSPACE"]
p = pathlib.Path(ws, "calc.py")
p.write_text("def add(a, b):\\n    return a + b\\n")
print("worker done")
"""

FORGING_WORKER = GOOD_WORKER + """
import json, pathlib
pathlib.Path(os.environ["WORKSPACE"], ".verdict.json").write_text(
    json.dumps({"accepted": True, "note": "worker declares success"})
)
"""

GRADER_TAMPERING_WORKER = GOOD_WORKER.replace(
    'p.write_text("def add(a, b):\\n    return a + b\\n")',
    'p.write_text("def add(a, b):\\n    return a + b\\n")\n'
    "grader = pathlib.Path(os.environ['WORKSPACE'], 'graders', 'run.sh')\n"
    "grader.parent.mkdir(exist_ok=True)\n"
    "grader.write_text('#!/bin/sh\\nexit 0\\n')",
)


@pytest.fixture()
def grader(tmp_path: Path) -> Path:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    path = trusted / "run.sh"
    path.write_text(GRADER, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture()
def journal(tmp_path: Path) -> Journal:
    return Journal(tmp_path / "journal.sqlite")


def run_worker(script: Path, workspace: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["WORKSPACE"] = str(workspace)
    return subprocess.run(
        ["python3", str(script)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_stage_builds_home_and_tmpdir_inside_workspace(base: Path, tmp_path: Path):
    ws = stage_workspace(base, tmp_path / "work")
    assert (ws / "calc.py").read_text(encoding="utf-8") == BASE_FILES["calc.py"]
    assert ws == ws.resolve()
    assert (ws / ".worker-home").is_dir()
    assert (ws / ".worker-tmp").is_dir()



def test_symlink_in_base_is_refused(base: Path, tmp_path: Path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (base / "leak.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        stage_workspace(base, tmp_path / "work")


def test_happy_path_pass_and_bind(base: Path, tmp_path: Path, grader: Path, journal: Journal):
    ws = stage_workspace(base, tmp_path / "work")
    proc = run_worker(make_worker(tmp_path, GOOD_WORKER), ws)
    assert proc.returncode == 0
    verifier = Verifier(base, tmp_path / "verify", journal, "run-v1")
    digest = verifier.freeze(ws)
    verdict = verifier.verify(
        checks=[["python3", "-c", "print('check')"]], graders=[grader]
    )
    assert verdict["verdict"] == "PASS"
    assert verdict["patch_digest"] == digest
    assert verdict["result_digest"]


def test_forged_worker_result_is_not_acceptance(
    base: Path, tmp_path: Path, grader: Path, journal: Journal
):
    ws = stage_workspace(base, tmp_path / "work")
    run_worker(make_worker(tmp_path, FORGING_WORKER), ws)
    verifier = Verifier(base, tmp_path / "verify", journal, "run-v2")
    verifier.freeze(ws)
    verdict = verifier.verify(checks=[], graders=[grader])
    assert verdict["verdict"] == "PASS"  # the fix itself is good
    assert ".verdict.json" not in verdict["result_digest"]
    # the worker's self-declared verdict never appears in the record
    record = json.dumps(verdict)
    assert '"accepted": true' not in record


def test_broken_fix_fails(base: Path, tmp_path: Path, grader: Path, journal: Journal):
    ws = stage_workspace(base, tmp_path / "work")
    verifier = Verifier(base, tmp_path / "verify", journal, "run-v3")
    verifier.freeze(ws)  # no worker run: the planted bug survives
    verdict = verifier.verify(checks=[], graders=[grader])
    assert verdict["verdict"] == "FAIL"
    assert "add is broken" in verdict["grader_output"]


def test_grader_tampering_is_integrity_failure(
    base: Path, tmp_path: Path, grader: Path, journal: Journal
):
    ws = stage_workspace(base, tmp_path / "work")
    run_worker(make_worker(tmp_path, GRADER_TAMPERING_WORKER), ws)
    verifier = Verifier(base, tmp_path / "verify", journal, "run-v4")
    verifier.freeze(ws)
    verdict = verifier.verify(checks=[], graders=[grader])
    assert verdict["verdict"] == "FAIL"
    assert verdict["reason_code"] == TAMPERED_GRADER


def test_patch_mutation_invalidates_verdict(
    base: Path, tmp_path: Path, grader: Path, journal: Journal
):
    ws = stage_workspace(base, tmp_path / "work")
    run_worker(make_worker(tmp_path, GOOD_WORKER), ws)
    verifier = Verifier(base, tmp_path / "verify", journal, "run-v5")
    digest = verifier.freeze(ws)
    verdict = verifier.verify(checks=[], graders=[grader])
    assert verdict["verdict"] == "PASS"
    # worker mutates the patch after verification: the old verdict is void
    (ws / "calc.py").write_text("def add(a, b):\n    return a * b\n", encoding="utf-8")
    assert verifier.current_digest() != digest
    stale = Verifier(base, tmp_path / "verify", journal, "run-v5")
    stale.bind_frozen(digest)
    assert stale.verify(checks=[], graders=[grader])["reason_code"] == VERDICT_INVALIDATED


def test_apply_patch_is_limited_to_patch_files(base: Path, tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    patch = collect_patch(base, base, frozenset())  # empty patch
    assert patch["files"] == {}
    apply_patch(base, {"README.md": "changed\n"}, target)
    assert (target / "README.md").read_text(encoding="utf-8") == "changed\n"
    assert (target / "calc.py").read_text(encoding="utf-8") == BASE_FILES["calc.py"]


def test_containment_probes_report_podman_level(tmp_path: Path):
    report = run_containment_probes(tmp_path / "probes")
    if report["podman"] == "absent":
        pytest.skip("podman not available on this host")
    assert report["level"] == "container"
    assert report["egress_deny"] == "denied"
    assert report["readonly_mount"] == "denied"


# --- RA-006b: container-level verification (issue #1) ---


def test_verdict_records_containment_level(
    base: Path, tmp_path: Path, grader: Path, journal: Journal
):
    """Every verdict names the containment level it actually ran at."""
    ws = stage_workspace(base, tmp_path / "work")
    verifier = Verifier(base, tmp_path / "verify", journal, "run-c1")
    verifier.freeze(ws)
    verdict = verifier.verify(checks=[], graders=[grader])
    assert verdict["containment"] == containment_level()


def test_containment_level_honest_about_podman():
    has_podman = shutil.which("podman") is not None
    image_ready = False
    if has_podman:
        image_ready = (
            subprocess.run(
                ["podman", "image", "exists", PROBE_IMAGE], capture_output=True
            ).returncode
            == 0
        )
    expected = "container" if (has_podman and image_ready) else "isolation_by_construction"
    assert containment_level() == expected


def test_container_verify_runs_checks_and_graders(
    base: Path, tmp_path: Path, grader: Path, journal: Journal
):
    if containment_level() != "container":
        pytest.skip("reason: podman or probe image absent on this host")
    ws = stage_workspace(base, tmp_path / "work")
    run_worker(make_worker(tmp_path, GOOD_WORKER), ws)
    verifier = Verifier(base, tmp_path / "verify", journal, "run-c2")
    verifier.freeze(ws)
    verdict = verifier.verify(
        checks=[["python3", "-c", "print('check-ok')"]], graders=[grader]
    )
    assert verdict["verdict"] == "PASS"
    assert "grader-ok" in verdict["grader_output"]


def test_container_denies_egress_inside_verify(
    base: Path, tmp_path: Path, grader: Path, journal: Journal
):
    if containment_level() != "container":
        pytest.skip("reason: podman or probe image absent on this host")
    ws = stage_workspace(base, tmp_path / "work")
    verifier = Verifier(base, tmp_path / "verify", journal, "run-c3")
    verifier.freeze(ws)
    verdict = verifier.verify(
        checks=[["timeout", "8", "bash", "-c", "echo > /dev/tcp/example.com/80"]],
        graders=[grader],
    )
    assert verdict["verdict"] == "FAIL"
    assert verdict["reason_code"] == "check_failed"


def test_container_readonly_rootfs_blocks_host_style_canary(
    base: Path, tmp_path: Path, grader: Path, journal: Journal
):
    if containment_level() != "container":
        pytest.skip("reason: podman or probe image absent on this host")
    ws = stage_workspace(base, tmp_path / "work")
    verifier = Verifier(base, tmp_path / "verify", journal, "run-c4")
    verifier.freeze(ws)
    verdict = verifier.verify(
        checks=[["touch", "/canary-outside-work"]],
        graders=[grader],
    )
    assert verdict["verdict"] == "FAIL"


# --- issue #3: binary patch policy ---


def test_generated_artifacts_never_enter_a_patch(
    base: Path, tmp_path: Path, grader: Path, journal: Journal
):
    ws = stage_workspace(base, tmp_path / "work")
    run_worker(make_worker(tmp_path, GOOD_WORKER), ws)
    cache = ws / "__pycache__"
    cache.mkdir()
    (cache / "calc.cpython-314.pyc").write_bytes(b"\x00\x01binary")
    (ws / ".DS_Store").write_bytes(b"\x00\x02")
    verifier = Verifier(base, tmp_path / "verify", journal, "run-b1")
    digest = verifier.freeze(ws)
    verdict = verifier.verify(checks=[], graders=[grader])
    assert verdict["verdict"] == "PASS"
    assert verifier.frozen_changed_files() == ["calc.py"]
    # exclusion is deterministic: same tree, same digest, pyc or no pyc
    (cache / "calc.cpython-314.pyc").write_bytes(b"\xff" + b"different")
    assert collect_patch(ws, base, frozenset())["digest"] == digest


def test_binary_file_survives_patch_roundtrip(
    base: Path, tmp_path: Path, grader: Path, journal: Journal
):
    ws = stage_workspace(base, tmp_path / "work")
    run_worker(make_worker(tmp_path, GOOD_WORKER), ws)
    payload = bytes(range(256)) * 4 + b"\xff\xfe not utf8 \x00"
    (ws / "logo.bin").write_bytes(payload)
    verifier = Verifier(base, tmp_path / "verify", journal, "run-b2")
    verifier.freeze(ws)
    verdict = verifier.verify(checks=[], graders=[grader])
    assert verdict["verdict"] == "PASS"
    assert verifier.frozen_changed_files() == ["calc.py", "logo.bin"]
    envs = sorted((tmp_path / "verify").glob("verify-*"))
    assert (envs[-1] / "logo.bin").read_bytes() == payload


def test_binary_budget_is_a_named_failure(base: Path, tmp_path: Path):
    ws = stage_workspace(base, tmp_path / "work")
    big = bytes(range(1, 256)) * 1620  # ~410 KiB, invalid as UTF-8
    (ws / "a.bin").write_bytes(big)
    (ws / "b.bin").write_bytes(big)
    with pytest.raises(ValueError, match="binary patch budget"):
        collect_patch(ws, base, frozenset())
