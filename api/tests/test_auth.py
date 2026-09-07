from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from app.auth import SessionUser, create_oidc_state, consume_oidc_state, create_session, require_token, session_user

def make_app():
    app = FastAPI()
    @app.get("/protected", dependencies=[Depends(require_token)])
    def protected(): return {"ok": True}
    return app

def test_missing_token_rejected(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret")
    c = TestClient(make_app())
    assert c.get("/protected").status_code == 401

def test_wrong_token_rejected(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret")
    c = TestClient(make_app())
    assert c.get("/protected", headers={"Authorization": "Bearer nope"}).status_code == 401

def test_correct_token_accepted(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret")
    c = TestClient(make_app())
    r = c.get("/protected", headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200

def test_bearer_token_still_works_with_oidc_env(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret")
    monkeypatch.setenv("AUTHENTIK_CLIENT_ID", "dashboard")
    monkeypatch.setenv("AUTHENTIK_CLIENT_SECRET", "not-used-by-bearer")
    c = TestClient(make_app())
    r = c.get("/protected", headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200

def test_session_cookie_accepted(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret")
    c = TestClient(make_app())
    sid = create_session()
    r = c.get("/protected", cookies={"dashboard_session": sid})
    assert r.status_code == 200

def test_session_user_is_stored(monkeypatch):
    user = SessionUser(username="virgo", email="v@example.test", source="authentik")
    sid = create_session(user)
    assert session_user(sid) == user

def test_oidc_state_is_single_use(monkeypatch):
    state = create_oidc_state()
    assert consume_oidc_state(state) is True
    assert consume_oidc_state(state) is False
