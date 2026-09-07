from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict, Field, field_validator


# Forgive common alias spellings agents send instead of the canonical enum.
RUN_STATUS_ALIASES = {
    "closed": "completed", "complete": "completed", "done": "completed", "finished": "completed",
    "running": "active", "in_progress": "active", "in-progress": "active",
    "abandon": "abandoned", "cancelled": "abandoned", "canceled": "abandoned", "killed": "abandoned",
    "stuck": "stalled", "hung": "stalled",
    "error": "failed", "errored": "failed", "broken": "failed",
}
STEP_STATUS_ALIASES = {
    "closed": "done", "complete": "done", "completed": "done", "finished": "done",
    "started": "in_progress", "wip": "in_progress", "active": "in_progress",
    "todo": "pending", "new": "pending",
    "skip": "skipped", "skipping": "skipped",
    "error": "failed", "errored": "failed", "broken": "failed",
}


def _norm(v, aliases):
    if isinstance(v, str):
        return aliases.get(v.lower().strip(), v)
    return v


class RunStatus(str, Enum):
    active = "active"
    completed = "completed"
    failed = "failed"
    stalled = "stalled"
    abandoned = "abandoned"


class StepStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    skipped = "skipped"
    failed = "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _RunStatusMixin:
    @field_validator("status", mode="before")
    @classmethod
    def _norm_run_status(cls, v): return _norm(v, RUN_STATUS_ALIASES)


class _StepStatusMixin:
    @field_validator("status", mode="before")
    @classmethod
    def _norm_step_status(cls, v): return _norm(v, STEP_STATUS_ALIASES)


class Step(_StepStatusMixin, BaseModel):
    model_config = ConfigDict(extra="forbid")
    idx: int
    title: str
    status: StepStatus = StepStatus.pending
    output: str = ""
    started: Optional[str] = None
    finished: Optional[str] = None


class Run(_RunStatusMixin, BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    goal: str
    provider: str = "unknown"
    model: Optional[str] = None
    session_label: Optional[str] = None
    status: RunStatus = RunStatus.active
    current_step: int = 0
    context_blob: Dict[str, Any] = Field(default_factory=dict)
    steps: List[Step] = Field(default_factory=list)
    created: str = Field(default_factory=_now)
    updated: str = Field(default_factory=_now)
    last_heartbeat: str = Field(default_factory=_now)
    parent_run: Optional[str] = None  # for resumption chains
    item_id: Optional[str] = None     # link to a dashboard Item (task/objective)


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Optional[str] = None
    goal: str
    provider: str = "unknown"
    model: Optional[str] = None
    session_label: Optional[str] = None
    parent_run: Optional[str] = None
    item_id: Optional[str] = None
    context_blob: Dict[str, Any] = Field(default_factory=dict)


class StepCreate(_StepStatusMixin, BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    status: StepStatus = StepStatus.pending
    output: str = ""


class StepUpdate(_StepStatusMixin, BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = None
    status: Optional[StepStatus] = None
    output: Optional[str] = None


class RunUpdate(_RunStatusMixin, BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Optional[RunStatus] = None
    model: Optional[str] = None
    current_step: Optional[int] = None
    context_blob: Optional[Dict[str, Any]] = None
    item_id: Optional[str] = None
