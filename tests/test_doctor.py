"""RA-007: doctor checks.

Every check reports {name, status, detail}; status is pass/fail/skip and a
skip names its reason — a skip is never a pass. With --live, the doctor
performs one harmless model ping through the adapter.
"""
import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from repo_agent import doctor


@pytest.fixture()
def healthy_endpoint(tmp_path: Path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            body = json.dumps(
                {"status": "ok", "model": "qwen3.8-flash-next", "loaded": True}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    old = os.environ.get("REPO_AGENT_ENDPOINT")
    os.environ["REPO_AGENT_ENDPOINT"] = f"http://127.0.0.1:{server.server_port}"
    yield f"http://127.0.0.1:{server.server_port}"
    if old is None:
        os.environ.pop("REPO_AGENT_ENDPOINT", None)
    else:
        os.environ["REPO_AGENT_ENDPOINT"] = old
    server.shutdown()


def make_dsh_shim(tmp_path: Path, version_line: str, help_rc: int = 0) -> Path:
    shim = tmp_path / "fake-dsh.sh"
    shim.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "--version" ]; then echo "{version_line}"; exit 0; fi\n'
        f"exit {help_rc}\n",
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    return shim


def test_doctor_reports_named_checks(tmp_path, healthy_endpoint, monkeypatch):
    shim = make_dsh_shim(tmp_path, "0.2.1-rc.2")
    monkeypatch.setenv("DSH_BIN", str(shim))
    report = doctor.run_doctor(tmp_path, live=False)
    names = {c["name"] for c in report["checks"]}
    assert {
        "dsh_binary", "dsh_profile", "endpoint_health",
        "containment", "journal_write",
    } <= names
    by_name = {c["name"]: c for c in report["checks"]}
    assert by_name["dsh_binary"]["status"] == "pass"
    assert "0.2.1" in by_name["dsh_binary"]["detail"]
    assert by_name["endpoint_health"]["status"] == "pass"
    assert "qwen3.8-flash-next" in by_name["endpoint_health"]["detail"]
    assert report["ok"] is True


def test_doctor_dsh_missing_is_block_not_fail(tmp_path, healthy_endpoint, monkeypatch):
    monkeypatch.setenv("DSH_BIN", str(tmp_path / "no-such-dsh"))
    report = doctor.run_doctor(tmp_path, live=False)
    by_name = {c["name"]: c for c in report["checks"]}
    assert by_name["dsh_binary"]["status"] == "fail"
    assert by_name["dsh_profile"]["status"] == "skip"
    assert "reason" in by_name["dsh_profile"]
    assert report["ok"] is False
    assert report["blocked"] is True


def test_doctor_endpoint_down_is_fail(tmp_path, monkeypatch):
    shim = make_dsh_shim(tmp_path, "0.2.1-rc.2")
    monkeypatch.setenv("DSH_BIN", str(shim))
    monkeypatch.setenv("REPO_AGENT_ENDPOINT", "http://127.0.0.1:1")
    report = doctor.run_doctor(tmp_path, live=False)
    by_name = {c["name"]: c for c in report["checks"]}
    assert by_name["endpoint_health"]["status"] == "fail"
    assert report["ok"] is False


def test_doctor_live_ping_records_usage(tmp_path, healthy_endpoint, monkeypatch):
    shim = tmp_path / "fake-dsh-live.sh"
    shim.write_text(
        "#!/bin/sh\n"
        "cat > /dev/null\n"
        'echo \'{"type":"session","sessionId":"session-live"}\'\n'
        'echo \'{"type":"status","phase":"step_end","step":1,"usage":'
        '{"inputTokens":10,"outputTokens":2,"totalTokens":12}}\'\n'
        'echo \'{"type":"final","text":"doctor-ok"}\'\n',
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("DSH_BIN", str(shim))
    report = doctor.run_doctor(tmp_path, live=True)
    by_name = {c["name"]: c for c in report["checks"]}
    live = by_name["dsh_live"]
    assert live["status"] == "pass"
    assert live["detail"]["final_text"] == "doctor-ok"
    assert live["detail"]["usage"]["totalTokens"] == 12
    assert live["detail"]["session_id"] == "session-live"


# --- RA-009: minder telemetry check ---


def test_doctor_minder_telemetry_reachable(tmp_path, healthy_endpoint, monkeypatch):
    shim = make_dsh_shim(tmp_path, "0.2.1-rc.2")
    monkeypatch.setenv("DSH_BIN", str(shim))
    monkeypatch.setenv("REPO_AGENT_MINDER_SINK_URL", healthy_endpoint)
    report = doctor.run_doctor(tmp_path, live=False)
    check = {c["name"]: c for c in report["checks"]}["minder_telemetry"]
    assert check["status"] == "pass"


def test_doctor_minder_telemetry_degraded_is_skip_not_fail(
    tmp_path, healthy_endpoint, monkeypatch
):
    shim = make_dsh_shim(tmp_path, "0.2.1-rc.2")
    monkeypatch.setenv("DSH_BIN", str(shim))
    # hermetic: the model endpoint fixture answers /health; only the
    # telemetry sink is unreachable
    monkeypatch.setenv("REPO_AGENT_ENDPOINT", healthy_endpoint)
    monkeypatch.setenv("REPO_AGENT_MINDER_SINK_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("MINDER_SINK_URL", "http://127.0.0.1:1")
    report = doctor.run_doctor(tmp_path, live=False)
    check = {c["name"]: c for c in report["checks"]}["minder_telemetry"]
    assert check["status"] == "skip"
    assert "degraded" in check["reason"]
    assert report["ok"] is True, "optional telemetry must not fail the doctor"
