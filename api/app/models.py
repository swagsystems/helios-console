from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator


# Aliases agents commonly use that don't match the canonical enum values.
# Forgive them rather than 422 the request.
ITEM_STATUS_ALIASES = {
    "closed": "done", "complete": "done", "completed": "done", "finished": "done",
    "resolved": "done", "fixed": "done",
    "wip": "in_progress", "inprogress": "in_progress", "in-progress": "in_progress",
    "active": "in_progress", "started": "in_progress", "working": "in_progress",
    "pending": "open", "todo": "open", "new": "open",
    "stalled": "blocked", "stuck": "blocked", "waiting": "blocked",
}
ITEM_PRIORITY_ALIASES = {
    "medium": "med", "normal": "med", "default": "med",
    "highest": "high", "urgent": "high", "critical": "high", "p0": "high", "p1": "high",
    "lowest": "low", "p3": "low", "p4": "low",
}


def _normalize(value, aliases):
    if isinstance(value, str):
        return aliases.get(value.lower().strip(), value)
    return value

class ItemType(str, Enum):
    objective = "objective"
    task = "task"
    issue = "issue"
    note = "note"
    guardrail = "guardrail"

class ItemStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"

class ItemPriority(str, Enum):
    low = "low"
    med = "med"
    high = "high"

class Link(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    url: str

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

class _ItemFields:
    @field_validator("status", mode="before")
    @classmethod
    def _norm_status(cls, v): return _normalize(v, ITEM_STATUS_ALIASES)

    @field_validator("priority", mode="before")
    @classmethod
    def _norm_priority(cls, v): return _normalize(v, ITEM_PRIORITY_ALIASES)


class Item(_ItemFields, BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: ItemType
    title: str
    body: str = ""
    status: Optional[ItemStatus] = None
    priority: Optional[ItemPriority] = None
    tags: List[str] = Field(default_factory=list)
    parent: Optional[str] = None
    pinned: bool = False
    links: List[Link] = Field(default_factory=list)
    created: str = Field(default_factory=_now)
    updated: str = Field(default_factory=_now)
    completed: Optional[str] = None

class ItemCreate(_ItemFields, BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Optional[str] = None
    type: ItemType
    title: str
    body: str = ""
    status: Optional[ItemStatus] = None
    priority: Optional[ItemPriority] = None
    tags: List[str] = Field(default_factory=list)
    parent: Optional[str] = None
    pinned: bool = False
    links: List[Link] = Field(default_factory=list)

class ItemUpdate(_ItemFields, BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Optional[ItemType] = None
    title: Optional[str] = None
    body: Optional[str] = None
    status: Optional[ItemStatus] = None
    priority: Optional[ItemPriority] = None
    tags: Optional[List[str]] = None
    parent: Optional[str] = None
    pinned: Optional[bool] = None
    links: Optional[List[Link]] = None
