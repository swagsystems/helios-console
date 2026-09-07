import os
_tf = os.environ.get("DASHBOARD_TOKEN_FILE")
if _tf and os.path.exists(_tf) and not os.environ.get("DASHBOARD_TOKEN"):
    with open(_tf) as f: os.environ["DASHBOARD_TOKEN"] = f.read().strip()

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import hmac

from .routes_items import router as items_router
from .routes_runs import router as runs_router
from .routes_messages import router as messages_router
from .routes_forge import router as forge_router
from .routes_session import router as session_router
from .mcp_server import build_server
from .watchdog import watchdog_loop, sweep_once

mcp_server = build_server()

@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    async with mcp_server.session_manager.run():
        task = asyncio.create_task(watchdog_loop())
        try:
            yield
        finally:
            task.cancel()

app = FastAPI(title="Helios Dashboard API", lifespan=lifespan)
app.include_router(items_router)
app.include_router(runs_router)
app.include_router(messages_router)
app.include_router(forge_router)
app.include_router(session_router)

@app.get("/api/health")
def health():
    return {"ok": True}

from .routes_passthrough import router as passthrough_router
app.include_router(passthrough_router)

app.mount("/mcp", mcp_server.streamable_http_app())


# ── MCP auth middleware (existing, unchanged) ──
@app.middleware("http")
async def mcp_auth(request: Request, call_next):
    if request.url.path.startswith("/mcp"):
        expected = os.environ.get("DASHBOARD_TOKEN", "")
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        if not expected or not hmac.compare_digest(token, expected):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


# ── Security headers middleware ──
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # CSP is set by nginx for HTML; API returns JSON which doesn't execute scripts
    return response


# ── Sweep endpoint (existing) ──
from .auth import require_token
from fastapi import Depends
@app.post("/api/runs/_sweep", dependencies=[Depends(require_token)])
def sweep_runs():
    return sweep_once()
