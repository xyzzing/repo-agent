"""RA-009: minder adapter — events into the sink (bounded buffer when
unreachable) and the decision contract.

Facts pinned by the design (minder tree, verified): the sink is
POST /persist with Bearer auth and an append_jsonl op; minder's report()
reader breaks on any malformed events.jsonl line, so records are
single-line JSON with namespaced `repo_agent_*` event names minder's
filters ignore; minder has NO out-of-process decision surface, so
decisions are local-and-fail-closed: LocalPolicy enforces the packet's
own immutable budget, RequiredMinderPolicy blocks rather than fail open.
"""
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from repo_agent.adapters.minder import (
    EvidenceError,
    MinderEvents,
    discover_sink_url,
    resolve_evidence,
)
from repo_agent.adapters.minder_decisions import (
    LocalPolicy,
    PolicyBlocked,
    RequiredMinderPolicy,
    parse_decision,
    validate_decision,
)
from repo_agent.state import Journal

# --- fake sink ---------------------------------------------------------

class SinkHandler(BaseHTTPRequestHandler):
    seen: list[dict] = []
    auth: list[str | None] = []

    def do_POST(self):  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        SinkHandler.auth.append(self.headers.get("Authorization"))
        SinkHandler.seen.append(json.loads(body))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *args):
        pass


@pytest.fixture()
def fake_sink():
    SinkHandler.seen = []
    SinkHandler.auth = []
    server = HTTPServer(("127.0.0.1", 0), SinkHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


# --- event emission ----------------------------------------------------


def test_emit_posts_namespaced_single_line_record(fake_sink, tmp_path):
    events = MinderEvents(
        state_dir=tmp_path / "minder-state",
        sink_url=fake_sink,
        token="tok-1",
        buffer_dir=tmp_path / "buffer",
    )
    where = events.emit("task-1", "state.changed", run_id="run-1", to="verifying")
    assert where == "sink"
    record = SinkHandler.seen[0]
    assert record["op"] == "append_jsonl"
    assert record["name"] == "events.jsonl"
    sent = record["record"]
    assert sent["event"] == "repo_agent_state.changed"
    assert sent["task"] == "task-1"
    assert sent["run_id"] == "run-1"
    assert isinstance(sent["ts"], float)
    assert SinkHandler.auth[0] == "Bearer tok-1"
    assert "\n" not in json.dumps(record)


def test_unreachable_sink_buffers_bounded_and_flags_degraded(tmp_path):
    buffer_dir = tmp_path / "buffer"
    events = MinderEvents(
        state_dir=tmp_path / "minder-state",
        sink_url="http://127.0.0.1:1",  # nothing listens
        token="t",
        buffer_dir=buffer_dir,
        max_buffer=3,
    )
    results = [events.emit("t", f"e{i}") for i in range(5)]
    assert all(r == "buffered" for r in results)
    assert events.degraded() is True
    lines = (buffer_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3, "buffer is bounded at max_buffer"
    dropped = json.loads(lines[-1])
    assert dropped["event"].startswith("repo_agent_e")
    for line in lines:
        json.loads(line)  # every buffered line is valid single-line JSON


def test_sink_url_discovery_precedence(tmp_path, monkeypatch):
    hooks = tmp_path / "hooks.json"
    hooks.write_text(
        'x MINDER_SINK_URL=http://127.0.0.1:9999 x\n', encoding="utf-8"
    )
    monkeypatch.setenv("MINDER_SINK_URL", "http://127.0.0.1:7777")
    monkeypatch.delenv("REPO_AGENT_MINDER_SINK_URL", raising=False)
    assert discover_sink_url(hooks_path=hooks) == "http://127.0.0.1:7777"
    monkeypatch.setenv("REPO_AGENT_MINDER_SINK_URL", "http://127.0.0.1:8888")
    assert discover_sink_url(hooks_path=hooks) == "http://127.0.0.1:8888"
    monkeypatch.delenv("MINDER_SINK_URL")
    monkeypatch.delenv("REPO_AGENT_MINDER_SINK_URL")
    assert discover_sink_url(hooks_path=hooks) == "http://127.0.0.1:9999"


# --- decision contract -------------------------------------------------


@pytest.fixture()
def journal(tmp_path):
    return Journal(tmp_path / "j.sqlite")


def test_local_policy_ladder(journal):
    run_id = journal.create_run(task_id="t")
    policy = LocalPolicy(journal, run_id, max_attempts=2)
    first = policy.decide(attempt=1, basis_event_ids=["e1"])
    assert first.action == "continue"
    assert first.policy_version == "local-v1"
    assert first.run_id == run_id
    assert first.remaining_budget == 1
    second = policy.decide(attempt=2, basis_event_ids=["e2"])
    assert second.action == "stop"
    assert second.remaining_budget == 0


def test_validate_decision_rejects_stale_or_mismatched(journal):
    run_id = journal.create_run(task_id="t")
    policy = LocalPolicy(journal, run_id, max_attempts=3)
    decision = policy.decide(attempt=1, basis_event_ids=[])
    seen: set[str] = set()
    validate_decision(decision, run_id=run_id, seen=seen)
    with pytest.raises(PolicyBlocked, match="run_mismatch"):
        validate_decision(decision, run_id="run-other", seen=seen)
    with pytest.raises(PolicyBlocked, match="replayed"):
        validate_decision(decision, run_id=run_id, seen={decision.decision_id})


def test_required_minder_policy_fails_closed():
    with pytest.raises(PolicyBlocked, match="minder"):
        RequiredMinderPolicy(reason="no external decision surface").decide(
            attempt=1, basis_event_ids=[]
        )


def test_decision_never_allows_frontier_from_policy(journal):
    run_id = journal.create_run(task_id="t")
    policy = LocalPolicy(journal, run_id, max_attempts=3)
    for attempt in (1, 2, 3):
        assert policy.decide(attempt=attempt, basis_event_ids=[]).action in (
            "continue",
            "retry_with_evidence",
            "pause",
            "stop",
        )


def test_event_emission_never_raises(tmp_path):
    events = MinderEvents(
        state_dir=tmp_path,
        sink_url="http://127.0.0.1:1",
        token=None,
        buffer_dir=tmp_path / "b",
    )
    assert events.emit("t", "boom", detail=json.dumps({"x": ["\n", 1]})) in (
        "sink",
        "buffered",
    )


# --- idempotent emission and event status -------------------------------


def test_emit_is_idempotent_on_event_id(tmp_path, fake_sink):
    events = MinderEvents(
        state_dir=tmp_path / "st",
        sink_url=fake_sink,
        token="t",
        buffer_dir=tmp_path / "b",
    )
    first = events.emit("t", "verification.failed", run_id="r", event_id="ev-1")
    second = events.emit("t", "verification.failed", run_id="r", event_id="ev-1")
    assert (first, second) == ("sink", "duplicate")
    assert len(SinkHandler.seen) == 1, "replayed event_id is not re-posted"


def test_event_id_dedup_persists_across_instances(tmp_path, fake_sink):
    state = tmp_path / "st"
    first = MinderEvents(
        state_dir=state, sink_url=fake_sink, token="t", buffer_dir=tmp_path / "b1"
    )
    assert first.emit("t", "e1", event_id="ev-9") == "sink"
    second = MinderEvents(
        state_dir=state, sink_url=fake_sink, token="t", buffer_dir=tmp_path / "b2"
    )
    assert second.emit("t", "e1", event_id="ev-9") == "duplicate"
    assert len(SinkHandler.seen) == 1


def test_status_reports_degraded_and_dropped(tmp_path):
    events = MinderEvents(
        state_dir=tmp_path / "st",
        sink_url="http://127.0.0.1:1",
        token=None,
        buffer_dir=tmp_path / "b",
        max_buffer=2,
    )
    for i in range(4):
        events.emit("t", f"e{i}")
    status = events.status()
    assert status["telemetry"] == "degraded"
    assert status["buffered"] == 2
    assert status["dropped"] == 2, "overflow drops oldest and counts it"


# --- verification event contract (PRD §9) -------------------------------


def test_verification_event_carries_contract_fields(tmp_path, fake_sink):
    events = MinderEvents(
        state_dir=tmp_path / "st",
        sink_url=fake_sink,
        token="t",
        buffer_dir=tmp_path / "b",
    )
    events.emit(
        "task-1",
        "verification.failed",
        run_id="run-1",
        event_id="run-1:verdict:abc",
        schema_version=1,
        attempt=2,
        producer="trusted-verifier",
        evidence_ref="run-1/verdict.json",
        evidence_sha256="a" * 64,
        failure_signature="check_failed",
    )
    sent = SinkHandler.seen[0]["record"]
    assert sent["event"] == "repo_agent_verification.failed"
    assert sent["schema_version"] == 1
    assert sent["attempt"] == 2
    assert sent["producer"] == "trusted-verifier"
    assert sent["evidence_ref"] == "run-1/verdict.json"
    assert sent["evidence_sha256"] == "a" * 64
    assert sent["failure_signature"] == "check_failed"


def test_passed_verification_event_omits_failure_signature(tmp_path, fake_sink):
    events = MinderEvents(
        state_dir=tmp_path / "st",
        sink_url=fake_sink,
        token="t",
        buffer_dir=tmp_path / "b",
    )
    events.emit(
        "task-1",
        "verification.passed",
        run_id="run-1",
        event_id="run-1:verdict:def",
        producer="trusted-verifier",
    )
    sent = SinkHandler.seen[0]["record"]
    assert sent["event"] == "repo_agent_verification.passed"
    assert "failure_signature" not in sent


# --- evidence artifact validation (PRD §9) ------------------------------


def test_resolve_evidence_accepts_rooted_ref_with_digest(tmp_path):
    root = tmp_path / "artifacts"
    run_dir = root / "run-1"
    run_dir.mkdir(parents=True)
    artifact = run_dir / "verdict.json"
    data = b'{"verdict": "PASS"}\n'
    artifact.write_bytes(data)
    resolved = resolve_evidence(
        root, "run-1/verdict.json", expected_sha256=hashlib.sha256(data).hexdigest()
    )
    assert resolved == artifact


def test_resolve_evidence_rejects_escape_missing_and_mismatch(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "in.json").write_bytes(b"x")
    with pytest.raises(EvidenceError, match="traversal"):
        resolve_evidence(root, "../outside.json")
    with pytest.raises(EvidenceError, match="absolute_ref"):
        resolve_evidence(root, "/etc/passwd")
    with pytest.raises(EvidenceError, match="missing_artifact"):
        resolve_evidence(root, "missing.json")
    with pytest.raises(EvidenceError, match="digest_mismatch"):
        resolve_evidence(root, "in.json", expected_sha256="0" * 64)


def test_resolve_evidence_rejects_symlink_escape(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("s", encoding="utf-8")
    (root / "link.json").symlink_to(outside)
    with pytest.raises(EvidenceError, match="traversal"):
        resolve_evidence(root, "link.json")


# --- decision parsing extras --------------------------------------------


VALID_DECISION = {
    "decision_id": "d-1",
    "run_id": "run-1",
    "basis_event_ids": ["event-1"],
    "action": "continue",
    "reason_code": "within_budget",
    "policy_version": "local-v1",
    "remaining_budget": 1,
    "expires_at": None,
}


def test_parse_decision_roundtrip_and_rejections():
    decision = parse_decision(VALID_DECISION)
    assert decision.action == "continue"
    assert decision.basis_event_ids == ("event-1",)
    with pytest.raises(PolicyBlocked, match="malformed_decision"):
        parse_decision({"decision_id": "d-1"})
    with pytest.raises(PolicyBlocked, match="unknown_field"):
        parse_decision({**VALID_DECISION, "grant_root": True})
    with pytest.raises(PolicyBlocked, match="unknown_action"):
        parse_decision({**VALID_DECISION, "action": "promote_self"})
    with pytest.raises(PolicyBlocked, match="malformed_decision"):
        parse_decision({**VALID_DECISION, "remaining_budget": True})


def test_parse_decision_accepts_consult_frontier_as_external_action():
    decision = parse_decision({**VALID_DECISION, "action": "consult_frontier"})
    assert decision.action == "consult_frontier"


def test_validate_decision_rejects_expired():
    decision = parse_decision(
        {**VALID_DECISION, "expires_at": "2000-01-01T00:00:00+00:00"}
    )
    with pytest.raises(PolicyBlocked, match="expired"):
        validate_decision(decision, run_id="run-1", seen=set())
