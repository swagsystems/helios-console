from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Agent(BaseModel):
    name: str
    aliases: List[str] = Field(default_factory=list)
    inbound_url: Optional[str] = None
    color: str = "#888"
    kind: str = "agent"


class AgentUpsert(BaseModel):
    name: str
    aliases: Optional[List[str]] = None
    inbound_url: Optional[str] = None
    color: Optional[str] = None
    kind: Optional[str] = None


class AgentMessage(BaseModel):
    id: str
    ts: str
    sender: str
    recipients: List[str]
    body: str
    thread_id: Optional[str] = None
    read_by: List[str] = Field(default_factory=list)


class AgentMessageCreate(BaseModel):
    sender: str
    body: str
    to: Optional[List[str]] = None
    thread_id: Optional[str] = None
