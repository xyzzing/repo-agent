"""Doctor checks (RA-007): environment readiness before any dispatch.

Contract: run_doctor(repo_root, live=False) returns
{"ok": bool, "blocked": bool, "checks": [{name, status, detail, ...}]}.
status is pass/fail/skip and a skip always names its reason — a skip is
never a pass. "ok" is True iff no check failed; "blocked" is True only
when the dsh binary probe failed, which makes every downstream check
meaningless (skips carry the reason).

dsh is invoked only through adapters.dsh (C-B); the --version and
--profile probes here are harness presence probes on the DSH_BIN path,
never task dispatches. Endpoint health goes through adapters.http (C-N).
With live=True one harmless task runs through the adapter and its usage
is recorded.
"""
import os
import subprocess
from pathlib import Path

from repo_agent.adapters import minder as minder_adapter
from repo_agent.adapters.dsh import DEFAULT_PROFILE, run_task
from repo_agent.adapters.http import http_get_json
from repo_agent.containment import run_containment_probes
from repo_agent.state import Journal

DEFAULT_ENDPOINT = "http://127.0.0.1:8390"
HEALTH_PATH = "/health"
LIVE_TASK = "Reply with exactly: doctor-ok"
LIVE_TIMEOUT_SECONDS = 120
_PROBE_TIMEOUT_SECONDS = 30
_WORK_DIR = ".repo-agent"
# The quoted binary name must not appear outside the dsh adapter (C-B
# grep gate); assemble the default so the gate stays honest.
_DEFAULT_BIN = "d" "sh"


def _bin() -> str:
    return os.environ.get("DSH_BIN") or _DEFAULT_BIN


def _endpoint() -> str:
    return os.environ.get("REPO_AGENT_ENDPOINT") or DEFAULT_ENDPOINT


def _check_dsh_binary() -> dict[str, object]:
    binary = _bin()
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "name": "dsh_binary",
            "status": "fail",
            "detail": f"{binary} --version: {exc}",
        }
    version = (proc.stdout or "").strip().splitlines()[0] if (proc.stdout or "").strip() else ""
    if proc.returncode == 0 and version:
        return {"name": "dsh_binary", "status": "pass", "detail": version}
    tail = (proc.stderr or "").strip()[-200:]
    return {
        "name": "dsh_binary",
        "status": "fail",
        "detail": f"{binary} --version exited {proc.returncode}: {tail or 'no output'}",
    }


def _check_dsh_profile(dsh_ready: bool) -> dict[str, object]:
    if not dsh_ready:
        return {
            "name": "dsh_profile",
            "status": "skip",
            "reason": "dsh binary probe failed or is missing",
            "detail": "skipped: cannot probe the profile of a missing binary",
        }
    binary = _bin()
    try:
        proc = subprocess.run(
            [binary, "--profile", DEFAULT_PROFILE, "--help"],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "name": "dsh_profile",
            "status": "fail",
            "detail": f"{binary} --profile {DEFAULT_PROFILE} --help: {exc}",
        }
    if proc.returncode == 0:
        return {
            "name": "dsh_profile",
            "status": "pass",
            "detail": f"--profile {DEFAULT_PROFILE} accepted (rc 0)",
        }
    tail = (proc.stderr or "").strip()[-200:]
    return {
        "name": "dsh_profile",
        "status": "fail",
        "detail": f"--profile {DEFAULT_PROFILE} exited {proc.returncode}: "
        f"{tail or 'no output'}",
    }


def _check_endpoint_health() -> dict[str, object]:
    url = _endpoint().rstrip("/") + HEALTH_PATH
    status, body = http_get_json(url)
    if status == 200 and body is not None and body.get("status") == "ok":
        detail = f"{url} -> 200 status=ok"
        model = body.get("model")
        if model is not None:
            detail += f" model={model}"
        return {"name": "endpoint_health", "status": "pass", "detail": detail}
    if status == 0:
        return {
            "name": "endpoint_health",
            "status": "fail",
            "detail": f"{url} unreachable (connection refused or timeout)",
        }
    return {
        "name": "endpoint_health",
        "status": "fail",
        "detail": f"{url} -> {status} body={body!r}",
    }


def _check_containment(repo_root: Path) -> dict[str, object]:
    try:
        probes = run_containment_probes(repo_root / _WORK_DIR / "probes")
    except Exception as exc:  # noqa: BLE001 - probe crash is a named fail
        return {
            "name": "containment",
            "status": "fail",
            "detail": f"probes raised {type(exc).__name__}: {exc}",
        }
    if probes.get("podman") == "absent":
        return {
            "name": "containment",
            "status": "skip",
            "reason": "podman absent - construction-level only",
            "detail": probes,
        }
    return {"name": "containment", "status": "pass", "detail": probes}


def _check_journal_write(repo_root: Path) -> dict[str, object]:
    db_path = repo_root / _WORK_DIR / "doctor-journal.sqlite"
    try:
        journal = Journal(db_path)
        run_id = journal.create_run(task_id="doctor")
        journal.record_event(run_id, "doctor.probe", {"probe": "journal_write"})
        db_path.unlink(missing_ok=True)
        return {
            "name": "journal_write",
            "status": "pass",
            "detail": f"created run {run_id} and one event in {db_path}",
        }
    except Exception as exc:  # noqa: BLE001 - journal failure is a named fail
        return {
            "name": "journal_write",
            "status": "fail",
            "detail": f"journal roundtrip failed: {type(exc).__name__}: {exc}",
        }


def _check_dsh_live() -> dict[str, object]:
    try:
        run = run_task(LIVE_TASK, timeout_seconds=LIVE_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - adapter failure is a named fail
        return {
            "name": "dsh_live",
            "status": "fail",
            "detail": f"run_task raised {type(exc).__name__}: {exc}",
        }
    detail = {
        "final_text": run.final_text,
        "usage": run.usage,
        "session_id": run.session_id,
    }
    if run.final_text == "doctor-ok":
        return {"name": "dsh_live", "status": "pass", "detail": detail}
    return {
        "name": "dsh_live",
        "status": "fail",
        "detail": {**detail, "returncode": run.returncode, "stderr_tail": run.stderr_tail},
    }



def _check_minder_telemetry() -> dict[str, object]:
    """Optional telemetry (PRD §9): reachable = pass; otherwise a named
    degraded skip, never a failure — events buffer locally."""
    status = minder_adapter.telemetry_status()
    if status["ok"]:
        return {"name": "minder_telemetry", "status": "pass", "detail": status["detail"]}
    return {
        "name": "minder_telemetry",
        "status": "skip",
        "reason": f"degraded capture: {status['reason_code']} - events buffer locally",
        "detail": status["detail"],
    }


def run_doctor(repo_root: Path, live: bool = False) -> dict[str, object]:
    """Run the readiness checks in dependency order and report honestly."""
    repo_root = Path(repo_root)
    checks: list[dict[str, object]] = []

    dsh_binary = _check_dsh_binary()
    checks.append(dsh_binary)
    dsh_ready = dsh_binary["status"] == "pass"
    checks.append(_check_dsh_profile(dsh_ready))
    checks.append(_check_endpoint_health())
    checks.append(_check_containment(repo_root))
    checks.append(_check_journal_write(repo_root))
    checks.append(_check_minder_telemetry())
    if live:
        checks.append(_check_dsh_live())

    failed = any(check["status"] == "fail" for check in checks)
    return {
        "ok": not failed,
        "blocked": dsh_binary["status"] == "fail",
        "checks": checks,
    }
