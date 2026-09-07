import logging
import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Response

from .auth import require_token
from .models_forge import (
    ForgeAgent,
    ForgeApproval,
    ForgeApprovalCreate,
    ForgeApprovalUpdate,
    ForgeEvent,
    ForgeEventCreate,
    ForgeJob,
    ForgeJobCreate,
    ForgeRunnerClaim,
    ForgeRunnerJobUpdate,
    ForgeRunnerRecover,
    ForgeRunnerRecoverResult,
    ForgeJobUpdate,
)
from .models_runs import RunCreate, RunUpdate, StepCreate, StepUpdate
from .store_forge import ForgeApprovalConflict, ForgeApprovalNotFound, ForgeJobNotFound, ForgeStore
from .store_runs import RunNotFound, RunStore, StepNotFound


FORGE_RUN_STEPS = [
    "Queued",
    "Approval/setup gate",
    "Agent subprocess",
    "Finalize",
]

FORGE_RUN_STATUS = {
    "queued": "active",
    "waiting": "active",
    "running": "active",
    "completed": "completed",
    "failed": "failed",
    "cancelled": "abandoned",
}

LOGGER = logging.getLogger(__name__)


def _data_dir() -> Path:
    return Path(os.environ.get("DASHBOARD_DATA_DIR", "/opt/dashboard/data"))


def _store() -> ForgeStore:
    return ForgeStore(_data_dir() / "forge.db")


def _runs() -> RunStore:
    return RunStore(_data_dir() / "runs.db")


def _value(value):
    return value.value if hasattr(value, "value") else value


def _ensure_forge_run_steps(runs: RunStore, run_id: str) -> None:
    existing = runs.get_run(run_id).steps
    if len(existing) >= len(FORGE_RUN_STEPS):
        return
    for title in FORGE_RUN_STEPS[len(existing):]:
        runs.add_step(run_id, StepCreate(title=title))


def _step_statuses_for_forge(status: str) -> tuple[list[str], int]:
    if status == "queued":
        return ["in_progress", "pending", "pending", "pending"], 0
    if status == "waiting":
        return ["done", "in_progress", "pending", "pending"], 1
    if status == "running":
        return ["done", "done", "in_progress", "pending"], 2
    if status == "completed":
        return ["done", "done", "done", "done"], 3
    if status == "failed":
        return ["done", "done", "failed", "failed"], 3
    if status == "cancelled":
        return ["done", "done", "skipped", "skipped"], 3
    return ["pending", "pending", "pending", "pending"], 0


def _next_for_forge(status: str, job: ForgeJob) -> str:
    if status == "queued":
        return f"Wait for a Forge runner to claim job {job.id}."
    if status == "waiting":
        return f"Resolve setup questions or approvals for Forge job {job.id}."
    if status == "running":
        return f"Monitor Forge job {job.id} in {job.runner_log_path or 'the Forge timeline'}."
    if status == "completed":
        return f"Review completed Forge job {job.id} and its timeline."
    if status == "failed":
        return f"Inspect Forge job {job.id} failure details and log {job.runner_log_path or '(none recorded)'}."
    if status == "cancelled":
        return f"Forge job {job.id} was cancelled; inspect preserved timeline and logs if needed."
    return f"Inspect Forge job {job.id}."


def _forge_context(job: ForgeJob) -> dict:
    status = _value(job.status)
    return {
        "job_id": job.id,
        "title": job.title,
        "prompt": job.prompt,
        "mode": _value(job.mode),
        "job_type": _value(job.job_type),
        "selected_agent": job.selected_agent,
        "cwd": job.cwd,
        "autonomy": _value(job.autonomy),
        "status": status,
        "runner_id": job.runner_id,
        "runner_pid": job.runner_pid,
        "runner_session_id": job.runner_session_id,
        "runner_log_path": job.runner_log_path,
        "runner_started": job.runner_started,
        "runner_ended": job.runner_ended,
        "runner_heartbeat": job.runner_heartbeat,
        "last_error": job.runner_error,
        "resume_hint": _next_for_forge(status, job),
    }


def _sync_forge_run(job: ForgeJob) -> None:
    if not job.dashboard_run_id:
        return
    try:
        runs = _runs()
        _ensure_forge_run_steps(runs, job.dashboard_run_id)
        run = runs.get_run(job.dashboard_run_id)

        status = _value(job.status)
        step_statuses, current_step = _step_statuses_for_forge(status)
        for idx, step_status in enumerate(step_statuses):
            runs.update_step(job.dashboard_run_id, idx, StepUpdate(status=step_status))

        context = dict(run.context_blob or {})
        context["next"] = _next_for_forge(status, job)
        context["forge"] = _forge_context(job)
        runs.update_run(
            job.dashboard_run_id,
            RunUpdate(
                status=FORGE_RUN_STATUS.get(status, "active"),
                current_step=current_step,
                context_blob=context,
            ),
        )
        if status in {"queued", "waiting", "running"}:
            runs.heartbeat(job.dashboard_run_id)
    except (RunNotFound, StepNotFound):
        return
    except Exception:
        LOGGER.exception("Failed to sync Forge job %s to dashboard run %s", job.id, job.dashboard_run_id)


router = APIRouter(prefix="/api/forge", tags=["forge"], dependencies=[Depends(require_token)])


@router.get("/agents", response_model=List[ForgeAgent])
def list_agents():
    return _store().list_agents()


@router.get("/jobs", response_model=List[ForgeJob])
def list_jobs(status: Optional[str] = None, limit: int = 50):
    return _store().list_jobs(status=status, limit=limit)


@router.post("/jobs", response_model=ForgeJob, status_code=201)
def create_job(payload: ForgeJobCreate):
    run = _runs().create_run(
        RunCreate(
            goal=f"Forge: {' '.join(payload.prompt.strip().split())[:100]}",
            provider="forge",
            session_label="forge",
            context_blob={
                "prompt": payload.prompt,
                "mode": payload.mode.value,
                "job_type": payload.job_type.value,
                "selected_agent": payload.selected_agent,
                "cwd": payload.cwd,
                "autonomy": payload.autonomy.value,
            },
        )
    )
    job = _store().create_job(payload, dashboard_run_id=run.id)
    _sync_forge_run(job)
    return job


@router.post("/runner/claim", response_model=ForgeJob, responses={204: {"description": "No queued job available"}})
def claim_next_job(payload: ForgeRunnerClaim):
    job = _store().claim_next_job(payload)
    if job is None:
        return Response(status_code=204)
    _sync_forge_run(job)
    return job


@router.patch("/runner/jobs/{job_id}", response_model=ForgeJob)
def update_runner_job(job_id: str, payload: ForgeRunnerJobUpdate):
    try:
        job = _store().update_runner_job(job_id, payload)
        _sync_forge_run(job)
        return job
    except ForgeJobNotFound:
        raise HTTPException(404, "forge job not found")


@router.post("/runner/recover-stale", response_model=ForgeRunnerRecoverResult)
def recover_stale_jobs(payload: ForgeRunnerRecover):
    store = _store()
    stale_job_ids = store.list_stale_job_ids(payload)
    result = store.recover_stale_jobs(payload)
    for job_id in stale_job_ids:
        try:
            job = store.get_job(job_id)
        except ForgeJobNotFound:
            continue
        if job.status.value == "queued":
            _sync_forge_run(job)
    return result


@router.get("/jobs/{job_id}", response_model=ForgeJob)
def get_job(job_id: str):
    try:
        return _store().get_job(job_id)
    except ForgeJobNotFound:
        raise HTTPException(404, "forge job not found")


@router.patch("/jobs/{job_id}", response_model=ForgeJob)
def update_job(job_id: str, payload: ForgeJobUpdate):
    try:
        job = _store().update_job(job_id, payload)
        _sync_forge_run(job)
        return job
    except ForgeJobNotFound:
        raise HTTPException(404, "forge job not found")


@router.post("/jobs/{job_id}/stop", response_model=ForgeJob)
def stop_job(job_id: str):
    try:
        job = _store().stop_job(job_id)
        _sync_forge_run(job)
        return job
    except ForgeJobNotFound:
        raise HTTPException(404, "forge job not found")


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str):
    try:
        _store().delete_job(job_id)
    except ForgeJobNotFound:
        raise HTTPException(404, "forge job not found")
    return Response(status_code=204)


@router.get("/jobs/{job_id}/events", response_model=List[ForgeEvent])
def list_events(job_id: str):
    try:
        return _store().list_events(job_id)
    except ForgeJobNotFound:
        raise HTTPException(404, "forge job not found")


@router.post("/jobs/{job_id}/events", response_model=ForgeEvent, status_code=201)
def add_event(job_id: str, payload: ForgeEventCreate):
    try:
        return _store().add_event(job_id, payload)
    except ForgeJobNotFound:
        raise HTTPException(404, "forge job not found")


@router.get("/jobs/{job_id}/approvals", response_model=List[ForgeApproval])
def list_approvals(job_id: str):
    try:
        return _store().list_approvals(job_id)
    except ForgeJobNotFound:
        raise HTTPException(404, "forge job not found")


@router.post("/jobs/{job_id}/approvals", response_model=ForgeApproval, status_code=201)
def create_approval(job_id: str, payload: ForgeApprovalCreate):
    try:
        return _store().create_approval(job_id, payload)
    except ForgeJobNotFound:
        raise HTTPException(404, "forge job not found")


@router.patch("/approvals/{approval_id}", response_model=ForgeApproval)
def update_approval(approval_id: str, payload: ForgeApprovalUpdate):
    try:
        approval = _store().update_approval(approval_id, payload)
        _sync_forge_run(_store().get_job(approval.job_id))
        return approval
    except ForgeApprovalConflict as exc:
        raise HTTPException(409, str(exc))
    except ForgeApprovalNotFound:
        raise HTTPException(404, "forge approval not found")
