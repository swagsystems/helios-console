HEADERS = {"Authorization": "Bearer testtoken"}

def test_system_returns_json(client, data_dir):
    (data_dir / "system.json").write_text('{"host":{"name":"helios"}}')
    assert client.get("/api/system").status_code == 401
    r = client.get("/api/system", headers=HEADERS)
    assert r.status_code == 200 and r.json()["host"]["name"] == "helios"

def test_system_404_when_missing(client):
    assert client.get("/api/system").status_code == 401
    assert client.get("/api/system", headers=HEADERS).status_code == 404

def test_context_md(client, data_dir, tmp_path):
    import os
    llm = tmp_path / "llm"
    (llm / "context.md").write_text("hello")
    assert client.get("/api/context.md").status_code == 401
    r = client.get("/api/context.md", headers=HEADERS)
    assert r.status_code == 200 and r.text == "hello"

def test_refresh_requires_token(client):
    assert client.post("/api/refresh").status_code == 401
