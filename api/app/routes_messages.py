import os
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from .auth import require_token
from .models_messages import Agent, AgentUpsert, AgentMessage, AgentMessageCreate
from .store_messages import MessageStore
from .messaging_fanout import fanout


def _store() -> MessageStore:
    data_dir = Path(os.environ.get("DASHBOARD_DATA_DIR", "/opt/dashboard/data"))
    return MessageStore(data_dir / "runs.db")


router = APIRouter(prefix="/api", tags=["messages"])


@router.get("/agents", response_model=List[Agent], dependencies=[Depends(require_token)])
def list_agents():
    """Agent registry — requires auth."""
    return _store().list_agents()


@router.post("/agents", response_model=Agent, dependencies=[Depends(require_token)])
def upsert_agent(payload: AgentUpsert):
    return _store().upsert_agent(payload)


@router.get("/messages", response_model=List[AgentMessage], dependencies=[Depends(require_token)])
def list_messages(
    recipient: Optional[str] = None,
    sender: Optional[str] = None,
    unread_for: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 100,
):
    """Agent messages — requires auth (contains agent prompts and responses)."""
    return _store().list_messages(
        recipient=recipient, sender=sender, unread_for=unread_for, since=since, limit=limit
    )


@router.post("/messages", response_model=AgentMessage, status_code=201, dependencies=[Depends(require_token)])
def create_message(payload: AgentMessageCreate, background: BackgroundTasks, broadcast: bool = True):
    store = _store()
    msg = store.create_message(payload)
    if broadcast:
        background.add_task(fanout, msg, store)
    return msg


@router.post("/messages/{mid}/read", response_model=AgentMessage, dependencies=[Depends(require_token)])
def mark_read(mid: str, reader: str):
    msg = _store().mark_read(mid, reader)
    if not msg:
        raise HTTPException(404, "message not found")
    return msg


@router.post("/messages/_read_all", dependencies=[Depends(require_token)])
def mark_all_read(reader: str):
    return {"marked": _store().mark_all_read(reader)}
