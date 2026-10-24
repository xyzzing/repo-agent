"""RA-019: scoped retrieval and reconstructable injection (PRD §12A).

Retrieval filters scope BEFORE similarity: a record from repository A
never surfaces for a task in repository B; unscoped records are global.
Kind floors, lifecycle flags, and per-model shelving all gate what is
eligible; the token budget bounds what is injected. Injection renders
an evidence block (quoted, never instructions) bound to a digest so the
exact projection is reconstructable from the journal event.
"""
import hashlib
import os
from pathlib import Path

from repo_agent.memory import MemoryStore
from repo_agent.retrieval import estimate_tokens, render_injection, retrieve
from repo_agent.state import Journal


def make_store(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    return journal, store


def seed(store, journal, claim, repo=None, kind="fact", status_floor=False,
         producer=None, model_specific=False, flags=()):
    run = journal.create_run(task_id="seed")
    eid = journal.record_event(run, "verifier.verdict", {"verdict": "PASS"})
    provenance = {"source_event_ids": [eid], "evidence_digest": "d" * 8}
    if producer:
        provenance["producer_profile"] = producer
    scope = {"repository_id": repo} if repo else {}
    mem = store.record(
        kind=kind, claim=claim, scope=scope, provenance=provenance,
        applicability={"model_specific": model_specific},
    )
    if status_floor:
        store.promote(mem["memory_id"], "evidence_checked")
    for flag in flags:
        store.mark_stale(mem["memory_id"], flag)
    return mem


def test_scope_filters_before_similarity(tmp_path):
    journal, store = make_store(tmp_path)
    seed(store, journal, "cache key omits revision", repo="/repos/alpha",
         status_floor=True)
    seed(store, journal, "trading suite preregisters thresholds", repo="/repos/beta",
         status_floor=True)
    seed(store, journal, "unscoped operational fact", status_floor=True)

    alpha = [m["claim"] for m in retrieve(
        store, repository_id="/repos/alpha", keywords=["cache"],
        profile="qwen@r020",
    )]
    assert any("cache key" in c for c in alpha)
    assert not any("trading suite" in c for c in alpha), (
        "repo B records must not surface for repo A tasks"
    )
    everything = [m["claim"] for m in retrieve(
        store, repository_id="/repos/alpha", keywords=[],
        profile="qwen@r020",
    )]
    assert any("unscoped" in c for c in everything), (
        "unscoped records are global"
    )
    assert not any("trading suite" in c for c in everything)


def test_kind_floor_gates_retrieval(tmp_path):
    journal, store = make_store(tmp_path)
    seed(store, journal, "candidate procedure not yet verified",
         repo="/repos/a", kind="verified_procedure")
    seed(store, journal, "evidence-checked fact", repo="/repos/a",
         status_floor=True)

    claims = [m["claim"] for m in retrieve(
        store, repository_id="/repos/a", keywords=[], profile="p",
    )]
    assert any("evidence-checked fact" in c for c in claims)
    assert not any("candidate procedure" in c for c in claims), (
        "procedures need locally_verified before retrieval"
    )


def test_flagged_records_excluded(tmp_path):
    journal, store = make_store(tmp_path)
    mem = seed(store, journal, "stale claim about the cache", repo="/repos/a",
               status_floor=True, flags=("source changed",))
    assert store.get(mem["memory_id"])["flags"] == ["stale"]
    assert retrieve(store, repository_id="/repos/a", keywords=[],
                    profile="p") == []


def test_profile_shelving_applies_in_retrieval(tmp_path):
    journal, store = make_store(tmp_path)
    seed(store, journal, "qwen dialect workaround", repo="/repos/a",
         status_floor=True, producer="qwen@r020", model_specific=True)
    seed(store, journal, "portable fact", repo="/repos/a", status_floor=True)

    qwen = [m["claim"] for m in retrieve(
        store, repository_id="/repos/a", keywords=[], profile="qwen@r020")]
    deepseek = [m["claim"] for m in retrieve(
        store, repository_id="/repos/a", keywords=[], profile="deepseek@v3")]
    assert any("dialect" in c for c in qwen)
    assert not any("dialect" in c for c in deepseek)


def test_keyword_terms_narrow_the_set(tmp_path):
    journal, store = make_store(tmp_path)
    seed(store, journal, "cache key omits revision", repo="/repos/a",
         status_floor=True)
    seed(store, journal, "retry budget refunds on success", repo="/repos/a",
         status_floor=True)
    hits = retrieve(store, repository_id="/repos/a", keywords=["budget"],
                    profile="p")
    assert len(hits) == 1 and "budget" in hits[0]["claim"]


def test_budget_bounds_injection(tmp_path):
    journal, store = make_store(tmp_path)
    for i in range(6):
        seed(store, journal, f"portable fact number {i} about caching",
             repo="/repos/a", status_floor=True)
    hits = retrieve(store, repository_id="/repos/a", keywords=["caching"],
                    profile="p", budget_tokens=40)
    total = sum(estimate_tokens(str(m["claim"])) for m in hits)
    assert 0 < len(hits) < 6
    assert total <= 40 + estimate_tokens(str(hits[-1]["claim"])), (
        "budget is conservative, not exact"
    )


def test_render_injection_is_reconstructable(tmp_path):
    journal, store = make_store(tmp_path)
    mem = seed(store, journal, "cache key omits revision", repo="/repos/a",
               status_floor=True)
    records = retrieve(store, repository_id="/repos/a", keywords=["cache"],
                       profile="p")
    text, record = render_injection(records)
    latest = store.get(mem["memory_id"])
    assert "not instructions" in text.lower()
    assert latest["memory_id"] in text
    assert record["memories"][0]["memory_id"] == latest["memory_id"]
    assert record["memories"][0]["revision"] == latest["revision"]
    again_text, again_record = render_injection(records)
    assert again_record["digest"] == hashlib.sha256(
        again_text.encode("utf-8")
    ).hexdigest()
    assert record["digest"] == again_record["digest"]


def test_task_run_injects_scoped_memory_into_worker_prompt(tmp_path):
    from repo_agent import taskrun
    from repo_agent.adapters.dsh import DshRun

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    os.system(f"cd {repo} && git init -q -b main && git add -A && "
              f"git -c user.email=t@t -c user.name=t commit -qm base")
    head = subprocess_head(repo)

    packet_file = tmp_path / "task.yaml"
    packet_file.write_text(
        "task_schema_version: 1\n"
        f"task_id: inject-fixture\nbase_commit: '{head}'\n"
        "goal: 'Make calc.add add instead of subtract'\n"
        "read_first: [calc.py]\nexpected_write_scope: [calc.py]\n"
        "acceptance:\n  - 'calc.add(2, 2) returns 4'\n"
        "invariants: []\nnon_goals: []\n"
        "verification_commands:\n  - [python3, -c, \"pass\"]\n"
        "budget: {max_attempts: 1, timeout_seconds: 60}\n"
        "required_skills: []\nescalate_when: []\n",
        encoding="utf-8",
    )

    journal = Journal(tmp_path / "j.sqlite")
    store = MemoryStore(tmp_path / "memory.sqlite", journal=journal)
    mem = seed(store, journal, "subtract historically fails here on negative numbers",
               repo=str(repo), status_floor=True)

    seen = {}

    def spy_worker(prompt: str, workspace: Path):
        seen["prompt"] = prompt
        (workspace / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        return DshRun(
            final_text="fixed", session_id="session-x", events=[],
            usage={"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
            returncode=0,
        )

    taskrun.run_packet(
        packet_file, repo=repo, work_root=tmp_path / "work", journal=journal,
        worker=spy_worker, graders=[], memory_store=store,
    )
    assert "Recalled memory" in seen["prompt"]
    assert mem["memory_id"] in seen["prompt"]
    injected = [
        e for r in journal.runs() for e in journal.events(r["run_id"])
        if e["kind"] == "memory.injected"
    ]
    assert injected, "injection is recorded in the journal (reconstructable)"


def subprocess_head(repo: Path) -> str:
    import subprocess

    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
        check=True,
    )
    return out.stdout.strip()


# --- RA-021: qualification gates model_specific visibility ---


def test_model_specific_withheld_until_producer_qualified(tmp_path):
    journal, store = make_store(tmp_path)
    seed(store, journal, "qwen dialect workaround", repo="/repos/a",
         status_floor=True, producer="qwen@r020", model_specific=True)
    from repo_agent.profiles import ProfileStore

    profiles = ProfileStore(tmp_path / "profiles.sqlite")
    profiles.register("qwen@r020", engine="strata", model="flash-next")

    unqualified = retrieve(store, repository_id="/repos/a", keywords=[],
                           profile="qwen@r020",
                           qualified_profiles=profiles.qualified_ids())
    assert unqualified == [], "unqualified producer's specific records withheld"

    profiles.qualify("qwen@r020", suites_ref="suites/coding-core-v1")
    qualified = retrieve(store, repository_id="/repos/a", keywords=[],
                         profile="qwen@r020",
                         qualified_profiles=profiles.qualified_ids())
    assert len(qualified) == 1
