HEADERS = {"Authorization": "Bearer testtoken"}

def test_list_empty(client):
    assert client.get("/api/items").status_code == 401
    r = client.get("/api/items", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == []

def test_create_requires_token(client):
    r = client.post("/api/items", json={"type": "note", "title": "x"})
    assert r.status_code == 401

def test_create_and_list(client):
    r = client.post("/api/items", headers=HEADERS, json={"type": "note", "title": "hi"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] and body["type"] == "note"
    r2 = client.get("/api/items", headers=HEADERS)
    assert len(r2.json()) == 1

def test_get_item(client):
    rid = client.post("/api/items", headers=HEADERS,
                      json={"id": "x", "type": "note", "title": "hi"}).json()["id"]
    r = client.get(f"/api/items/{rid}", headers=HEADERS)
    assert r.status_code == 200 and r.json()["id"] == "x"

def test_get_missing_404(client):
    assert client.get("/api/items/nope").status_code == 401
    assert client.get("/api/items/nope", headers=HEADERS).status_code == 404

def test_patch(client):
    rid = client.post("/api/items", headers=HEADERS,
                      json={"id": "x", "type": "task", "title": "t",
                            "status": "open", "priority": "med"}).json()["id"]
    r = client.patch(f"/api/items/{rid}", headers=HEADERS, json={"status": "in_progress"})
    assert r.status_code == 200 and r.json()["status"] == "in_progress"

def test_delete(client):
    rid = client.post("/api/items", headers=HEADERS,
                      json={"id": "x", "type": "note", "title": "hi"}).json()["id"]
    assert client.delete(f"/api/items/{rid}", headers=HEADERS).status_code == 204
    assert client.get(f"/api/items/{rid}", headers=HEADERS).status_code == 404

def test_complete(client):
    rid = client.post("/api/items", headers=HEADERS,
                      json={"id": "x", "type": "task", "title": "t",
                            "status": "open", "priority": "med"}).json()["id"]
    r = client.post(f"/api/items/{rid}/complete", headers=HEADERS)
    assert r.status_code == 200 and r.json()["status"] == "done"

def test_list_filters(client):
    client.post("/api/items", headers=HEADERS,
                json={"type": "task", "title": "a", "status": "open",
                      "priority": "high", "tags": ["media"]})
    client.post("/api/items", headers=HEADERS,
                json={"type": "note", "title": "b", "tags": ["dispo"]})
    assert len(client.get("/api/items?type=task", headers=HEADERS).json()) == 1
    assert len(client.get("/api/items?tag=media", headers=HEADERS).json()) == 1
    assert len(client.get("/api/items?q=b", headers=HEADERS).json()) == 1
