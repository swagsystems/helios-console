from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ForgeMode(str, Enum):
    auto = "auto"
    manual = "manual"
    suggested = "suggested"


class ForgeJobType(str, Enum):
    background = "background"
    interactive = "interactive"


class ForgeAutonomy(str, Enum):
    ask = "ask"
    supervised = "supervised"
    autonomous = "autonomous"


class ForgeJobStatus(str, Enum):
    queued = "queued"
    running = "running"
    waiting = "waiting"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ForgeEventKind(str, Enum):
    job_created = "job_created"
    user_message = "user_message"
    agent_message = "agent_message"
    status = "status"
    approval_requested = "approval_requested"
    approval_resolved = "approval_resolved"
    system = "system"


class ApprovalRisk(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    hard_stop = "hard_stop"


class ApprovalAuthority(str, Enum):
    user = "user"
    supervisor = "supervisor"
    autonomous = "autonomous"
    blocked = "blocked"


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    cancelled = "cancelled"


class ForgeAgent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    role: str
    label: str
    description: str
    color: str
    default_for: List[str] = Field(default_factory=list)


class ForgeJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    prompt: str
    mode: ForgeMode = ForgeMode.auto
    job_type: ForgeJobType = ForgeJobType.background
    status: ForgeJobStatus = ForgeJobStatus.queued
    selected_agent: str = "claude"
    cwd: str = "/root"
    autonomy: ForgeAutonomy = ForgeAutonomy.supervised
    dashboard_run_id: Optional[str] = None
    runner_id: Optional[str] = None
    runner_pid: Optional[int] = None
    runner_session_id: Optional[str] = None
    runner_started: Optional[str] = None
    runner_ended: Optional[str] = None
    runner_log_path: Optional[str] = None
    runner_error: Optional[str] = None
    runner_heartbeat: Optional[str] = None
    created: str = Field(default_factory=_now)
    updated: str = Field(default_factory=_now)


class ForgeJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str
    mode: ForgeMode = ForgeMode.auto
    job_type: ForgeJobType = ForgeJobType.background
    selected_agent: Optional[str] = None
    cwd: str = "/root"
    autonomy: ForgeAutonomy = ForgeAutonomy.supervised


class ForgeJobUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Optional[ForgeJobStatus] = None
    selected_agent: Optional[str] = None
    cwd: Optional[str] = None
    autonomy: Optional[ForgeAutonomy] = None


class ForgeRunnerClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runner_id: str
    supported_agents: List[str] = Field(default_factory=list)
    job_types: List[ForgeJobType] = Field(default_factory=list)


class ForgeRunnerRecover(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runner_id: str
    stale_after_seconds: int = 900


class ForgeRunnerRecoverResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recovered: int


class ForgeRunnerJobUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Optional[ForgeJobStatus] = None
    runner_pid: Optional[int] = None
    runner_session_id: Optional[str] = None
    runner_log_path: Optional[str] = None
    runner_error: Optional[str] = None
    runner_heartbeat: bool = False


class ForgeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    job_id: str
    ts: str = Field(default_factory=_now)
    kind: ForgeEventKind
    actor: str = "forge"
    body: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)


class ForgeEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: ForgeEventKind
    actor: str = "forge"
    body: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)


class ForgeApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    job_id: str
    action: str
    risk: ApprovalRisk
    authority: ApprovalAuthority
    target: str = ""
    rollback: str = ""
    status: ApprovalStatus = ApprovalStatus.pending
    reviewer: Optional[str] = None
    note: str = ""
    created: str = Field(default_factory=_now)
    updated: str = Field(default_factory=_now)


class ForgeApprovalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    risk: ApprovalRisk
    authority: ApprovalAuthority
    target: str = ""
    rollback: str = ""

    @field_validator("authority")
    @classmethod
    def hard_stop_is_blocked(cls, value, info):
        risk = info.data.get("risk")
        if risk == ApprovalRisk.hard_stop:
            return ApprovalAuthority.blocked
        return value


class ForgeApprovalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ApprovalStatus
    reviewer: Optional[str] = None
    note: str = ""
