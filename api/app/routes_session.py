from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
import httpx
import os
from urllib.parse import urlencode

from .auth import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    check_bearer,
    create_session,
    create_oidc_state,
    consume_oidc_state,
    destroy_session,
    require_token,
    session_user,
    SessionUser,
)


router = APIRouter(prefix="/api/session", tags=["session"])


class SessionLogin(BaseModel):
    token: str


def _secure_cookie(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto == "https"


def _public_base_url(request: Request) -> str:
    configured = os.environ.get("DASHBOARD_PUBLIC_BASE_URL", "").rstrip("/")
    if configured:
        return configured
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    return f"{proto}://{host}".rstrip("/")


def _authentik_base_url() -> str:
    return os.environ.get("AUTHENTIK_BASE_URL", "http://authentik:9000").rstrip("/")


def _authentik_public_base_url() -> str:
    return os.environ.get("AUTHENTIK_PUBLIC_BASE_URL", _authentik_base_url()).rstrip("/")


def _oidc_client_id() -> str:
    return os.environ.get("AUTHENTIK_CLIENT_ID", "")


def _oidc_client_secret() -> str:
    return os.environ.get("AUTHENTIK_CLIENT_SECRET", "")


def _oidc_slug() -> str:
    return os.environ.get("AUTHENTIK_APP_SLUG", "dashboard")


def _oidc_enabled() -> bool:
    return bool(_oidc_client_id() and _oidc_client_secret())


def _set_session_cookie(response: Response, request: Request, sid: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=_secure_cookie(request),
        samesite="strict",
        path="/",
    )


@router.get("", dependencies=[Depends(require_token)])
def session_status(request: Request):
    user = session_user(request.cookies.get(SESSION_COOKIE))
    return {"ok": True, "user": user.__dict__ if user else None}


@router.get("/login")
def oidc_login(request: Request):
    if not _oidc_enabled():
        return RedirectResponse("/", status_code=307)
    state = create_oidc_state()
    redirect_uri = f"{_public_base_url(request)}/api/session/oidc/callback"
    params = urlencode({
        "client_id": _oidc_client_id(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    })
    return RedirectResponse(
        f"{_authentik_public_base_url()}/application/o/authorize/?{params}",
        status_code=307,
    )


@router.get("/oidc/callback")
def oidc_callback(request: Request, code: str | None = None, state: str | None = None):
    if not _oidc_enabled() or not code or not consume_oidc_state(state):
        return RedirectResponse("/", status_code=307)

    base_url = _authentik_base_url()
    slug = _oidc_slug()
    redirect_uri = f"{_public_base_url(request)}/api/session/oidc/callback"
    token_url = f"{base_url}/application/o/token/"
    userinfo_url = f"{base_url}/application/o/userinfo/"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": _oidc_client_id(),
        "client_secret": _oidc_client_secret(),
    }
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        token_response = client.post(token_url, data=data)
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        user_response = client.get(userinfo_url, headers={"Authorization": f"Bearer {access_token}"})
        user_response.raise_for_status()
        claims = user_response.json()

    user = SessionUser(
        username=claims.get("preferred_username") or claims.get("sub", "authentik-user"),
        email=claims.get("email", ""),
        name=claims.get("name", ""),
        source="authentik",
    )
    response = RedirectResponse("/", status_code=303)
    _set_session_cookie(response, request, create_session(user))
    return response


@router.post("")
def login(payload: SessionLogin, request: Request, response: Response):
    if not check_bearer(payload.token.strip()):
        response.status_code = 401
        return {"detail": "bad token"}
    sid = create_session()
    _set_session_cookie(response, request, sid)
    return {"ok": True}


@router.delete("")
def logout(request: Request, response: Response):
    destroy_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    return {"ok": True}
