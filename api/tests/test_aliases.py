"""Forgive common alias spellings agents send for status/priority enums."""
HEADERS = {"Authorization": "Bearer testtoken"}


def test_item_status_closed_normalized_to_done(client):
    rid = client.post("/api/items", headers=HEADERS,
                      json={"id": "x", "type": "task", "title": "t",
                            "status": "open", "priority": "med"}).json()["id"]
    r = client.patch(f"/api/items/{rid}", headers=HEADERS, json={"status": "closed"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"


def test_item_status_completed_normalized(client):
    rid = client.post("/api/items", headers=HEADERS,
                      json={"id": "y", "type": "task", "title": "t",
                            "status": "open"}).json()["id"]
    r = client.patch(f"/api/items/{rid}", headers=HEADERS, json={"status": "completed"})
    assert r.status_code == 200
    assert r.json()["status"] == "done"


def test_item_status_wip_to_in_progress(client):
    rid = client.post("/api/items", headers=HEADERS,
                      json={"id": "z", "type": "task", "title": "t"}).json()["id"]
    r = client.patch(f"/api/items/{rid}", headers=HEADERS, json={"status": "wip"})
    assert r.json()["status"] == "in_progress"


def test_item_status_case_insensitive(client):
    rid = client.post("/api/items", headers=HEADERS,
                      json={"id": "u", "type": "task", "title": "t"}).json()["id"]
    r = client.patch(f"/api/items/{rid}", headers=HEADERS, json={"status": "CLOSED"})
    assert r.json()["status"] == "done"


def test_item_priority_medium_to_med(client):
    r = client.post("/api/items", headers=HEADERS,
                    json={"type": "task", "title": "t", "priority": "medium"})
    assert r.status_code == 201
    assert r.json()["priority"] == "med"


def test_item_priority_urgent_to_high(client):
    r = client.post("/api/items", headers=HEADERS,
                    json={"type": "task", "title": "t", "priority": "urgent"})
    assert r.json()["priority"] == "high"


def test_item_canonical_values_unchanged(client):
    """Existing canonical values must still pass through unchanged."""
    rid = client.post("/api/items", headers=HEADERS,
                      json={"id": "c", "type": "task", "title": "t",
                            "status": "in_progress", "priority": "high"}).json()["id"]
    r = client.get(f"/api/items/{rid}", headers=HEADERS)
    assert r.json()["status"] == "in_progress"
    assert r.json()["priority"] == "high"


def test_item_invalid_status_still_rejected(client):
    """Random unknown values should still 422 — we forgive aliases, not garbage."""
    r = client.post("/api/items", headers=HEADERS,
                    json={"type": "task", "title": "t", "status": "fizzbuzz"})
    assert r.status_code == 422


def test_run_status_closed_normalized(client):
    rid = client.post("/api/runs", headers=HEADERS, json={"goal": "x"}).json()["id"]
    r = client.patch(f"/api/runs/{rid}", headers=HEADERS, json={"status": "closed"})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_run_status_done_normalized(client):
    rid = client.post("/api/runs", headers=HEADERS, json={"goal": "x"}).json()["id"]
    r = client.patch(f"/api/runs/{rid}", headers=HEADERS, json={"status": "done"})
    assert r.json()["status"] == "completed"


def test_step_status_completed_normalized(client):
    rid = client.post("/api/runs", headers=HEADERS, json={"goal": "x"}).json()["id"]
    s = client.post(f"/api/runs/{rid}/steps", headers=HEADERS,
                    json={"title": "s", "status": "completed"})
    assert s.status_code == 201
    assert s.json()["status"] == "done"


def test_step_status_started_to_in_progress(client):
    rid = client.post("/api/runs", headers=HEADERS, json={"goal": "x"}).json()["id"]
    s = client.post(f"/api/runs/{rid}/steps", headers=HEADERS, json={"title": "s"})
    r = client.patch(f"/api/runs/{rid}/steps/{s.json()['idx']}",
                     headers=HEADERS, json={"status": "started"})
    assert r.json()["status"] == "in_progress"
