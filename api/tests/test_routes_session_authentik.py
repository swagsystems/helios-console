HEADERS = {"Authorization": "Bearer testtoken"}


def make_session_app():
    from fastapi import FastAPI
    from app.routes_session import router

    app = FastAPI()
    app.include_router(router)
    return app


def test_session_status_accepts_bearer_with_oidc_configured(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DASHBOARD_TOKEN", "testtoken")
    monkeypatch.setenv("AUTHENTIK_CLIENT_ID", "dashboard")
    monkeypatch.setenv("AUTHENTIK_CLIENT_SECRET", "not-used-by-bearer")
    client = TestClient(make_session_app())
    r = client.get("/api/session", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_session_login_redirects_to_authentik_when_configured(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DASHBOARD_TOKEN", "testtoken")
    monkeypatch.setenv("AUTHENTIK_PUBLIC_BASE_URL", "https://authentik.example.test")
    monkeypatch.setenv("AUTHENTIK_CLIENT_ID", "dashboard")
    monkeypatch.setenv("AUTHENTIK_CLIENT_SECRET", "secret")
    client = TestClient(make_session_app())
    r = client.get("/api/session/login", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].startswith(
        "https://authentik.example.test/application/o/authorize/"
    )


def test_session_login_uses_configured_dashboard_public_base(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DASHBOARD_TOKEN", "testtoken")
    monkeypatch.setenv("DASHBOARD_PUBLIC_BASE_URL", "https://dashboard.example.com")
    monkeypatch.setenv("AUTHENTIK_PUBLIC_BASE_URL", "https://dashboard.example.com")
    monkeypatch.setenv("AUTHENTIK_CLIENT_ID", "dashboard")
    monkeypatch.setenv("AUTHENTIK_CLIENT_SECRET", "secret")
    client = TestClient(make_session_app())
    r = client.get(
        "/api/session/login",
        headers={"host": "dashboard.example.com", "x-forwarded-proto": "http"},
        follow_redirects=False,
    )
    assert "redirect_uri=https%3A%2F%2Fdashboard.example.com%2Fapi%2Fsession%2Foidc%2Fcallback" in r.headers["location"]
