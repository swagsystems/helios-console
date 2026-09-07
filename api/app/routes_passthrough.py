import json
import os
import subprocess
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from .auth import require_token

router = APIRouter()

def _data_dir() -> Path:
    return Path(os.environ.get("DASHBOARD_DATA_DIR", "/opt/dashboard/data"))

def _llm_dir() -> Path:
    return Path(os.environ.get("DASHBOARD_LLM_DIR", "/opt/dashboard/llm"))

def _passthrough(name: str):
    p = _data_dir() / name
    if not p.exists(): raise HTTPException(404, f"{name} not generated yet")
    return json.loads(p.read_text())

@router.get("/api/system", dependencies=[Depends(require_token)])
def system(): return _passthrough("system.json")

@router.get("/api/services", dependencies=[Depends(require_token)])
def services(): return _passthrough("services.json")

@router.get("/api/cron", dependencies=[Depends(require_token)])
def cron(): return _passthrough("cron.json")

@router.get("/api/context.md", response_class=PlainTextResponse, dependencies=[Depends(require_token)])
def context_md():
    p = _llm_dir() / "context.md"
    if not p.exists(): raise HTTPException(404, "context.md not generated")
    return p.read_text()

@router.post("/api/refresh", dependencies=[Depends(require_token)])
def refresh():
    script = Path("/opt/dashboard/scripts/refresh-data.sh")
    if not script.exists(): raise HTTPException(500, "refresh script missing")
    r = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=120)
    return {"ok": r.returncode == 0, "stdout": r.stdout[-500:], "stderr": r.stderr[-500:]}
