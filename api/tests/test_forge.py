HEADERS = {"Authorization": "Bearer testtoken"}


def test_forge_requires_auth(client):
    assert client.get("/api/forge/agents").status_code == 401
    assert client.get("/api/forge/jobs").status_code == 401
    assert client.post("/api/forge/jobs", json={"prompt": "x"}).status_code == 401


def test_agent_registry(client):
    r = client.get("/api/forge/agents", headers=HEADERS)
    assert r.status_code == 200
    names = [a["name"] for a in r.json()]
    assert names[:4] == ["claude", "codex", "codex-xhigh", "hermes"]


def test_job_lifecycle_creates_run_and_events(client):
    r = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={
            "prompt": "audit dashboard auth",
            "mode": "auto",
            "job_type": "background",
            "cwd": "/opt/dashboard",
            "autonomy": "supervised",
        },
    )
    assert r.status_code == 201
    job = r.json()
    assert job["id"]
    assert job["title"] == "audit dashboard auth"
    assert job["selected_agent"] == "claude"
    assert job["status"] == "queued"
    assert job["dashboard_run_id"]

    runs = client.get("/api/runs", headers=HEADERS).json()
    assert runs[0]["id"] == job["dashboard_run_id"]
    assert runs[0]["provider"] == "forge"
    assert [step["title"] for step in runs[0]["steps"]] == [
        "Queued",
        "Approval/setup gate",
        "Agent subprocess",
        "Finalize",
    ]
    assert runs[0]["context_blob"]["forge"]["job_id"] == job["id"]
    assert runs[0]["context_blob"]["forge"]["status"] == "queued"

    events = client.get(f"/api/forge/jobs/{job['id']}/events", headers=HEADERS).json()
    assert [e["kind"] for e in events] == ["job_created"]
    assert events[0]["actor"] == "forge"

    r = client.post(
        f"/api/forge/jobs/{job['id']}/events",
        headers=HEADERS,
        json={"kind": "agent_message", "actor": "claude", "body": "Routing to Codex."},
    )
    assert r.status_code == 201
    events = client.get(f"/api/forge/jobs/{job['id']}/events", headers=HEADERS).json()
    assert [e["kind"] for e in events] == ["job_created", "agent_message"]

    r = client.patch(
        f"/api/forge/jobs/{job['id']}",
        headers=HEADERS,
        json={"status": "running", "selected_agent": "codex"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert r.json()["selected_agent"] == "codex"

    r = client.post(f"/api/forge/jobs/{job['id']}/stop", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    events = client.get(f"/api/forge/jobs/{job['id']}/events", headers=HEADERS).json()
    assert events[-1]["kind"] == "status"
    assert "Graceful stop" in events[-1]["body"]

    assert client.delete(f"/api/forge/jobs/{job['id']}", headers=HEADERS).status_code == 204
    assert client.get(f"/api/forge/jobs/{job['id']}", headers=HEADERS).status_code == 404


def test_runner_claim_and_status_updates(client):
    first = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={"prompt": "first job", "mode": "manual", "selected_agent": "codex"},
    ).json()
    second = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={"prompt": "second job", "mode": "manual", "selected_agent": "claude"},
    ).json()

    r = client.post(
        "/api/forge/runner/claim",
        headers=HEADERS,
        json={"runner_id": "forge-runner-test", "supported_agents": ["codex"]},
    )
    assert r.status_code == 200
    claimed = r.json()
    assert claimed["id"] == first["id"]
    assert claimed["status"] == "waiting"
    assert claimed["runner_id"] == "forge-runner-test"
    assert claimed["runner_session_id"] == "forge-runner-test"
    assert claimed["runner_heartbeat"]

    assert client.get(f"/api/forge/jobs/{second['id']}", headers=HEADERS).json()["status"] == "queued"

    r = client.patch(
        f"/api/forge/runner/jobs/{first['id']}",
        headers=HEADERS,
        json={
            "status": "running",
            "runner_pid": 12345,
            "runner_log_path": "/var/log/forge/first.log",
            "runner_heartbeat": True,
        },
    )
    assert r.status_code == 200
    updated = r.json()
    assert updated["runner_pid"] == 12345
    assert updated["runner_log_path"] == "/var/log/forge/first.log"
    assert updated["status"] == "running"

    r = client.patch(
        f"/api/forge/runner/jobs/{first['id']}",
        headers=HEADERS,
        json={"status": "completed", "runner_error": ""},
    )
    assert r.status_code == 200
    finished = r.json()
    assert finished["status"] == "completed"
    assert finished["runner_ended"]

    assert client.post(
        "/api/forge/runner/claim",
        headers=HEADERS,
        json={"runner_id": "forge-runner-test", "supported_agents": ["codex"]},
    ).status_code == 204


def test_runner_status_updates_project_to_linked_dashboard_run(client):
    job = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={"prompt": "sync live run", "mode": "manual", "selected_agent": "codex"},
    ).json()
    run_id = job["dashboard_run_id"]

    claimed = client.post(
        "/api/forge/runner/claim",
        headers=HEADERS,
        json={"runner_id": "run-sync-test", "supported_agents": ["codex"]},
    ).json()
    assert claimed["id"] == job["id"]

    run = client.get(f"/api/runs/{run_id}", headers=HEADERS).json()
    assert run["status"] == "active"
    assert run["current_step"] == 1
    assert run["steps"][0]["status"] == "done"
    assert run["steps"][1]["status"] == "in_progress"
    assert run["context_blob"]["forge"]["status"] == "waiting"
    assert run["context_blob"]["forge"]["runner_id"] == "run-sync-test"

    client.patch(
        f"/api/forge/runner/jobs/{job['id']}",
        headers=HEADERS,
        json={
            "status": "running",
            "runner_pid": 4321,
            "runner_session_id": "session-1",
            "runner_log_path": "/tmp/forge/sync.log",
            "runner_heartbeat": True,
        },
    )
    run = client.get(f"/api/runs/{run_id}", headers=HEADERS).json()
    assert run["status"] == "active"
    assert run["current_step"] == 2
    assert run["steps"][1]["status"] == "done"
    assert run["steps"][2]["status"] == "in_progress"
    assert run["context_blob"]["forge"]["status"] == "running"
    assert run["context_blob"]["forge"]["runner_pid"] == 4321
    assert run["context_blob"]["forge"]["runner_session_id"] == "session-1"
    assert run["context_blob"]["forge"]["runner_log_path"] == "/tmp/forge/sync.log"
    assert run["context_blob"]["next"].startswith("Monitor Forge job")

    client.patch(
        f"/api/forge/runner/jobs/{job['id']}",
        headers=HEADERS,
        json={"status": "completed", "runner_error": ""},
    )
    run = client.get(f"/api/runs/{run_id}", headers=HEADERS).json()
    assert run["status"] == "completed"
    assert run["current_step"] == 3
    assert [step["status"] for step in run["steps"]] == ["done", "done", "done", "done"]
    assert run["context_blob"]["forge"]["status"] == "completed"

    resume = client.get(f"/api/runs/{run_id}/resume", headers=HEADERS).text
    assert job["id"] in resume
    assert "/tmp/forge/sync.log" in resume


def test_cancelled_forge_job_marks_linked_dashboard_run_abandoned(client):
    job = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={"prompt": "cancel live run", "mode": "manual", "selected_agent": "codex"},
    ).json()

    client.post(
        "/api/forge/runner/claim",
        headers=HEADERS,
        json={"runner_id": "cancel-sync-test", "supported_agents": ["codex"]},
    )
    client.patch(
        f"/api/forge/runner/jobs/{job['id']}",
        headers=HEADERS,
        json={"status": "cancelled", "runner_error": "stop requested"},
    )

    run = client.get(f"/api/runs/{job['dashboard_run_id']}", headers=HEADERS).json()
    assert run["status"] == "abandoned"
    assert run["steps"][3]["status"] == "skipped"
    assert run["context_blob"]["forge"]["status"] == "cancelled"
    assert run["context_blob"]["forge"]["last_error"] == "stop requested"


def test_runner_claim_filters_job_type(client):
    background = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={"prompt": "background job", "mode": "manual", "selected_agent": "codex", "job_type": "background"},
    ).json()
    interactive = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={"prompt": "interactive job", "mode": "manual", "selected_agent": "codex", "job_type": "interactive"},
    ).json()

    r = client.post(
        "/api/forge/runner/claim",
        headers=HEADERS,
        json={"runner_id": "forge-runner-test", "supported_agents": ["codex"], "job_types": ["interactive"]},
    )

    assert r.status_code == 200
    assert r.json()["id"] == interactive["id"]
    assert client.get(f"/api/forge/jobs/{background['id']}", headers=HEADERS).json()["status"] == "queued"


def test_runner_recovers_stale_jobs(client):
    job = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={"prompt": "stale job", "mode": "manual", "selected_agent": "codex"},
    ).json()
    claimed = client.post(
        "/api/forge/runner/claim",
        headers=HEADERS,
        json={"runner_id": "stale-runner", "supported_agents": ["codex"]},
    ).json()
    assert claimed["id"] == job["id"]

    r = client.post(
        "/api/forge/runner/recover-stale",
        headers=HEADERS,
        json={"runner_id": "stale-runner", "stale_after_seconds": -1},
    )

    assert r.status_code == 200
    assert r.json()["recovered"] == 1
    recovered = client.get(f"/api/forge/jobs/{job['id']}", headers=HEADERS).json()
    assert recovered["status"] == "queued"
    assert recovered["runner_id"] is None
    assert recovered["runner_pid"] is None
    assert recovered["runner_session_id"] is None
    events = client.get(f"/api/forge/jobs/{job['id']}/events", headers=HEADERS).json()
    assert events[-1]["payload"]["recovered"] is True
    run = client.get(f"/api/runs/{job['dashboard_run_id']}", headers=HEADERS).json()
    assert run["status"] == "active"
    assert run["current_step"] == 0
    assert run["context_blob"]["forge"]["status"] == "queued"
    assert run["context_blob"]["forge"]["last_error"] == "stale runner recovered"


def test_runner_recovers_all_stale_job_runs_beyond_list_page(client):
    jobs = [
        client.post(
            "/api/forge/jobs",
            headers=HEADERS,
            json={"prompt": f"stale job {idx}", "mode": "manual", "selected_agent": "codex"},
        ).json()
        for idx in range(205)
    ]
    for job in jobs:
        claimed = client.post(
            "/api/forge/runner/claim",
            headers=HEADERS,
            json={"runner_id": "stale-page-runner", "supported_agents": ["codex"]},
        ).json()
        assert claimed["id"] == job["id"]

    r = client.post(
        "/api/forge/runner/recover-stale",
        headers=HEADERS,
        json={"runner_id": "stale-page-runner", "stale_after_seconds": -1},
    )

    assert r.status_code == 200
    assert r.json()["recovered"] == len(jobs)
    for job in jobs:
        run = client.get(f"/api/runs/{job['dashboard_run_id']}", headers=HEADERS).json()
        assert run["status"] == "active"
        assert run["context_blob"]["forge"]["status"] == "queued"


def test_forge_projection_failure_does_not_break_runner_update(client, monkeypatch):
    job = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={"prompt": "projection outage", "mode": "manual", "selected_agent": "codex"},
    ).json()

    class BrokenRunStore:
        def get_run(self, run_id):
            raise RuntimeError("runs db unavailable")

    from app import routes_forge

    monkeypatch.setattr(routes_forge, "_runs", lambda: BrokenRunStore())

    r = client.post(
        "/api/forge/runner/claim",
        headers=HEADERS,
        json={"runner_id": "projection-outage", "supported_agents": ["codex"]},
    )

    assert r.status_code == 200
    claimed = r.json()
    assert claimed["id"] == job["id"]
    assert claimed["status"] == "waiting"


def test_runner_fields_migrate_existing_forge_db(data_dir):
    import sqlite3

    db = data_dir / "forge.db"
    with sqlite3.connect(db) as c:
        c.execute(
            "CREATE TABLE forge_jobs ("
            "id TEXT PRIMARY KEY, title TEXT NOT NULL, prompt TEXT NOT NULL, mode TEXT NOT NULL, "
            "job_type TEXT NOT NULL, status TEXT NOT NULL, selected_agent TEXT NOT NULL, cwd TEXT NOT NULL, "
            "autonomy TEXT NOT NULL, dashboard_run_id TEXT, created TEXT NOT NULL, updated TEXT NOT NULL)"
        )
        c.execute("CREATE TABLE forge_events (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, ts TEXT NOT NULL, kind TEXT NOT NULL, actor TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', payload TEXT NOT NULL DEFAULT '{}')")
        c.execute("CREATE TABLE forge_approvals (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, action TEXT NOT NULL, risk TEXT NOT NULL, authority TEXT NOT NULL, target TEXT NOT NULL DEFAULT '', rollback TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, reviewer TEXT, note TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, updated TEXT NOT NULL)")

    from app.models_forge import ForgeJobCreate
    from app.store_forge import ForgeStore

    store = ForgeStore(db)
    job = store.create_job(ForgeJobCreate(prompt="migration check"))
    assert job.runner_pid is None
    assert job.runner_session_id is None


def test_approval_lifecycle(client):
    job = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={"prompt": "restart dashboard api", "mode": "manual", "selected_agent": "codex"},
    ).json()

    r = client.post(
        f"/api/forge/jobs/{job['id']}/approvals",
        headers=HEADERS,
        json={
            "action": "restart dashboard-api",
            "risk": "medium",
            "authority": "user",
            "target": "dashboard-api",
            "rollback": "docker restart dashboard-api again or restore LXC backup",
        },
    )
    assert r.status_code == 201
    approval = r.json()
    assert approval["status"] == "pending"
    assert approval["risk"] == "medium"

    r = client.patch(
        f"/api/forge/approvals/{approval['id']}",
        headers=HEADERS,
        json={"status": "approved", "reviewer": "user", "note": "ok"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert r.json()["reviewer"] == "user"
    events = client.get(f"/api/forge/jobs/{job['id']}/events", headers=HEADERS).json()
    assert events[-1]["body"].startswith("Request approved:")


def test_approval_transitions_are_enforced(client):
    job = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={"prompt": "dangerous action", "mode": "manual", "selected_agent": "codex"},
    ).json()

    hard_stop = client.post(
        f"/api/forge/jobs/{job['id']}/approvals",
        headers=HEADERS,
        json={
            "action": "touch protected cluster config",
            "risk": "hard_stop",
            "authority": "autonomous",
            "target": "/etc/pve",
            "rollback": "none",
        },
    ).json()
    assert hard_stop["authority"] == "blocked"
    assert client.patch(
        f"/api/forge/approvals/{hard_stop['id']}",
        headers=HEADERS,
        json={"status": "approved", "reviewer": "codex-xhigh"},
    ).status_code == 409

    approval = client.post(
        f"/api/forge/jobs/{job['id']}/approvals",
        headers=HEADERS,
        json={
            "action": "start job",
            "risk": "medium",
            "authority": "user",
            "target": f"job:{job['id']}",
            "rollback": "stop it",
        },
    ).json()
    assert client.patch(
        f"/api/forge/approvals/{approval['id']}",
        headers=HEADERS,
        json={"status": "denied", "reviewer": "user"},
    ).status_code == 200
    run = client.get(f"/api/runs/{job['dashboard_run_id']}", headers=HEADERS).json()
    assert run["status"] == "abandoned"
    assert run["context_blob"]["forge"]["status"] == "cancelled"
    assert client.patch(
        f"/api/forge/approvals/{approval['id']}",
        headers=HEADERS,
        json={"status": "approved", "reviewer": "user"},
    ).status_code == 409
    assert client.get(f"/api/forge/jobs/{job['id']}", headers=HEADERS).json()["status"] == "cancelled"


def test_stop_job_is_idempotent_and_does_not_rewrite_finished_jobs(client):
    job = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={"prompt": "finish then stop", "mode": "manual", "selected_agent": "codex"},
    ).json()

    assert client.post(f"/api/forge/jobs/{job['id']}/stop", headers=HEADERS).json()["status"] == "cancelled"
    assert client.post(f"/api/forge/jobs/{job['id']}/stop", headers=HEADERS).json()["status"] == "cancelled"

    done = client.post(
        "/api/forge/jobs",
        headers=HEADERS,
        json={"prompt": "already done", "mode": "manual", "selected_agent": "codex"},
    ).json()
    client.patch(f"/api/forge/runner/jobs/{done['id']}", headers=HEADERS, json={"status": "completed"})
    assert client.post(f"/api/forge/jobs/{done['id']}/stop", headers=HEADERS).json()["status"] == "completed"


def test_missing_forge_records_404(client):
    assert client.get("/api/forge/jobs/nope", headers=HEADERS).status_code == 404
    assert client.get("/api/forge/jobs/nope/events", headers=HEADERS).status_code == 404
    assert client.post("/api/forge/jobs/nope/stop", headers=HEADERS).status_code == 404
    assert client.delete("/api/forge/jobs/nope", headers=HEADERS).status_code == 404
    assert client.patch("/api/forge/approvals/nope", headers=HEADERS, json={"status": "denied"}).status_code == 404
