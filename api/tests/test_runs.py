HEADERS = {"Authorization": "Bearer testtoken"}


def test_list_empty(client):
    assert client.get("/api/runs").status_code == 401
    r = client.get("/api/runs", headers=HEADERS)
    assert r.status_code == 200 and r.json() == []


def test_start_requires_token(client):
    r = client.post("/api/runs", json={"goal": "x"})
    assert r.status_code == 401


def test_full_lifecycle(client):
    # start
    r = client.post("/api/runs", headers=HEADERS,
                    json={"goal": "build feature X", "provider": "claude-code", "model": "sonnet-4"})
    assert r.status_code == 201
    body = r.json()
    rid = body["id"]
    assert body["status"] == "active" and body["steps"] == []
    assert body["provider"] == "claude-code"
    assert body["model"] == "sonnet-4"

    # add step
    r = client.post(f"/api/runs/{rid}/steps", headers=HEADERS,
                    json={"title": "plan", "status": "in_progress"})
    assert r.status_code == 201 and r.json()["idx"] == 0
    assert r.json()["started"] is not None

    # second step
    r = client.post(f"/api/runs/{rid}/steps", headers=HEADERS,
                    json={"title": "implement"})
    assert r.json()["idx"] == 1

    # patch step
    r = client.patch(f"/api/runs/{rid}/steps/0", headers=HEADERS,
                     json={"status": "done", "output": "decided to use SQLite"})
    assert r.status_code == 200 and r.json()["status"] == "done"
    assert r.json()["finished"] is not None

    # save context
    r = client.patch(f"/api/runs/{rid}", headers=HEADERS,
                     json={"context_blob": {"next": "step 2", "files": ["a.py"]},
                           "model": "sonnet-4.5",
                           "current_step": 1})
    assert r.status_code == 200
    assert r.json()["context_blob"]["next"] == "step 2"
    assert r.json()["model"] == "sonnet-4.5"

    # heartbeat
    r = client.post(f"/api/runs/{rid}/heartbeat", headers=HEADERS)
    assert r.status_code == 200

    # resume bundle
    r = client.get(f"/api/runs/{rid}/resume", headers=HEADERS)
    assert r.status_code == 200
    body = r.text
    assert "Resume run" in body and rid in body and "step 2" in body

    # active list
    assert len(client.get("/api/runs?status=active", headers=HEADERS).json()) == 1


def test_get_missing_404(client):
    assert client.get("/api/runs/nope").status_code == 401
    assert client.get("/api/runs/nope/resume").status_code == 401
    assert client.get("/api/runs/nope", headers=HEADERS).status_code == 404
    assert client.get("/api/runs/nope/resume", headers=HEADERS).status_code == 404


def test_step_404(client):
    rid = client.post("/api/runs", headers=HEADERS,
                      json={"goal": "x"}).json()["id"]
    r = client.patch(f"/api/runs/{rid}/steps/99", headers=HEADERS,
                     json={"status": "done"})
    assert r.status_code == 404


def test_delete(client):
    rid = client.post("/api/runs", headers=HEADERS, json={"goal": "x"}).json()["id"]
    assert client.delete(f"/api/runs/{rid}", headers=HEADERS).status_code == 204
    assert client.get(f"/api/runs/{rid}", headers=HEADERS).status_code == 404


def test_filter_by_provider(client):
    client.post("/api/runs", headers=HEADERS, json={"goal": "a", "provider": "claude-code", "model": "sonnet"})
    client.post("/api/runs", headers=HEADERS, json={"goal": "b", "provider": "hermes", "model": "gpt-5.5"})
    assert len(client.get("/api/runs?provider=hermes", headers=HEADERS).json()) == 1
    assert len(client.get("/api/runs?model=gpt-5.5", headers=HEADERS).json()) == 1


def test_counts_requires_auth_and_counts_all_runs(client):
    assert client.get("/api/runs/counts").status_code == 401

    active = client.post("/api/runs", headers=HEADERS, json={"goal": "active"}).json()["id"]
    done = client.post("/api/runs", headers=HEADERS, json={"goal": "done"}).json()["id"]
    client.patch(f"/api/runs/{done}", headers=HEADERS, json={"status": "completed"})

    r = client.get("/api/runs/counts", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"total": 2, "active": 1, "previous": 1}
    assert client.get("/api/runs?limit=1", headers=HEADERS).status_code == 200


def test_stalled_run_revives_on_activity(client):
    rid = client.post("/api/runs", headers=HEADERS, json={"goal": "x"}).json()["id"]
    client.post(f"/api/runs/{rid}/steps", headers=HEADERS, json={"title": "plan"})

    def stall():
        assert client.patch(f"/api/runs/{rid}", headers=HEADERS,
                            json={"status": "stalled"}).json()["status"] == "stalled"

    def run_status():
        return client.get(f"/api/runs/{rid}", headers=HEADERS).json()["status"]

    stall()
    r = client.post(f"/api/runs/{rid}/heartbeat", headers=HEADERS)
    assert r.json()["status"] == "active"

    stall()
    client.patch(f"/api/runs/{rid}/steps/0", headers=HEADERS, json={"status": "done"})
    assert run_status() == "active"

    stall()
    client.post(f"/api/runs/{rid}/steps", headers=HEADERS, json={"title": "more"})
    assert run_status() == "active"

    stall()
    client.patch(f"/api/runs/{rid}", headers=HEADERS, json={"context_blob": {"next": "y"}})
    assert run_status() == "active"

    # explicit status writes are never overridden by the revive logic
    client.patch(f"/api/runs/{rid}", headers=HEADERS, json={"status": "completed"})
    client.post(f"/api/runs/{rid}/heartbeat", headers=HEADERS)
    assert run_status() == "completed"


def test_finish_run_via_patch(client):
    rid = client.post("/api/runs", headers=HEADERS, json={"goal": "x"}).json()["id"]
    r = client.patch(f"/api/runs/{rid}", headers=HEADERS, json={"status": "completed"})
    assert r.json()["status"] == "completed"
    assert len(client.get("/api/runs?status=active", headers=HEADERS).json()) == 0
    assert len(client.get("/api/runs?status=completed", headers=HEADERS).json()) == 1
