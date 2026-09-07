import hmac
import os
import secrets
import time
from dataclasses import dataclass
from fastapi import Cookie, Header, HTTPException, status

SESSION_COOKIE = "dashboard_session"
SESSION_TTL_SECONDS = int(os.environ.get("DASHBOARD_SESSION_TTL_SECONDS", str(12 * 60 * 60)))
_sessions: dict[str, float] = {}
_session_users: dict[str, "SessionUser"] = {}
_oidc_states: dict[str, float] = {}
OIDC_STATE_TTL_SECONDS = 5 * 60


@dataclass
class SessionUser:
    username: str
    email: str = ""
    name: str = ""
    source: str = "token"


def _expected_token() -> str:
    expected = os.environ.get("DASHBOARD_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=500, detail="server token not configured")
    return expected


def _prune_sessions(now: float | None = None) -> None:
    now = now or time.time()
    for sid, expires in list(_sessions.items()):
        if expires <= now:
            _sessions.pop(sid, None)
            _session_users.pop(sid, None)
    for state, expires in list(_oidc_states.items()):
        if expires <= now:
            _oidc_states.pop(state, None)


def create_session(user: SessionUser | None = None) -> str:
    _prune_sessions()
    sid = secrets.token_urlsafe(32)
    _sessions[sid] = time.time() + SESSION_TTL_SECONDS
    if user:
        _session_users[sid] = user
    return sid


def destroy_session(sid: str | None) -> None:
    if sid:
        _sessions.pop(sid, None)
        _session_users.pop(sid, None)


def session_valid(sid: str | None) -> bool:
    if not sid:
        return False
    _prune_sessions()
    expires = _sessions.get(sid)
    if not expires:
        return False
    _sessions[sid] = time.time() + SESSION_TTL_SECONDS
    return True


def session_user(sid: str | None) -> SessionUser | None:
    if not session_valid(sid):
        return None
    return _session_users.get(sid)


def create_oidc_state() -> str:
    _prune_sessions()
    state = secrets.token_urlsafe(32)
    _oidc_states[state] = time.time() + OIDC_STATE_TTL_SECONDS
    return state


def consume_oidc_state(state: str | None) -> bool:
    if not state:
        return False
    _prune_sessions()
    expires = _oidc_states.pop(state, None)
    return bool(expires and expires > time.time())


def check_bearer(token: str) -> bool:
    return hmac.compare_digest(token, _expected_token())


def require_token(
    authorization: str | None = Header(default=None),
    dashboard_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    if session_valid(dashboard_session):
        return True
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    presented = authorization.removeprefix("Bearer ").strip()
    if not check_bearer(presented):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad token")
    return True
