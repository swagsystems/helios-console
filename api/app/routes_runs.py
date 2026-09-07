import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Response
from fastapi.responses import PlainTextResponse

from .auth import require_token
from .models_runs import (
    Run, RunCreate, RunUpdate, Step, StepCreate, StepUpdate,
)
from .store_runs import RunStore, RunNotFound, StepNotFound


def _store() -> RunStore:
    data_dir = Path(os.environ.get("DASHBOARD_DATA_DIR", "/opt/dashboard/data"))
    return RunStore(data_dir / "runs.db")


router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[Run], dependencies=[Depends(require_token)])
def list_runs(status: str | None = None, provider: str | None = None,
              model: str | None = None, limit: int = 50):
    return _store().list_runs(status=status, provider=provider, model=model, limit=limit)


@router.get("/counts", dependencies=[Depends(require_token)])
def run_counts():
    return _store().count_runs()


@router.post("", response_model=Run, status_code=201, dependencies=[Depends(require_token)])
def start_run(payload: RunCreate):
    return _store().create_run(payload)


@router.get("/{run_id}", response_model=Run, dependencies=[Depends(require_token)])
def get_run(run_id: str):
    try:
        return _store().get_run(run_id)
    except RunNotFound:
        raise HTTPException(404, "run not found")


@router.patch("/{run_id}", response_model=Run, dependencies=[Depends(require_token)])
def update_run(run_id: str, payload: RunUpdate):
    try:
        return _store().update_run(run_id, payload)
    except RunNotFound:
        raise HTTPException(404, "run not found")


@router.delete("/{run_id}", status_code=204, dependencies=[Depends(require_token)])
def delete_run(run_id: str):
    try:
        _store().delete_run(run_id)
    except RunNotFound:
        raise HTTPException(404, "run not found")
    return Response(status_code=204)


@router.post("/{run_id}/heartbeat", response_model=Run, dependencies=[Depends(require_token)])
def heartbeat(run_id: str):
    try:
        return _store().heartbeat(run_id)
    except RunNotFound:
        raise HTTPException(404, "run not found")


@router.post("/{run_id}/steps", response_model=Step, status_code=201,
             dependencies=[Depends(require_token)])
def add_step(run_id: str, payload: StepCreate):
    try:
        return _store().add_step(run_id, payload)
    except RunNotFound:
        raise HTTPException(404, "run not found")


@router.patch("/{run_id}/steps/{idx}", response_model=Step,
              dependencies=[Depends(require_token)])
def patch_step(run_id: str, idx: int, payload: StepUpdate):
    try:
        return _store().update_step(run_id, idx, payload)
    except StepNotFound:
        raise HTTPException(404, "step not found")


@router.get("/{run_id}/resume", response_class=PlainTextResponse,
            dependencies=[Depends(require_token)])
def resume(run_id: str):
    """Resume prompt — requires auth because it contains agent context blobs."""
    try:
        return _store().build_resume_prompt(run_id)
    except RunNotFound:
        raise HTTPException(404, "run not found")
