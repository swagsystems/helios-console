import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Response
from .auth import require_token
from .models import Item, ItemCreate, ItemUpdate
from .store import ItemStore, ItemNotFound, DuplicateId

router = APIRouter(prefix="/api/items")

def _store() -> ItemStore:
    data_dir = Path(os.environ.get("DASHBOARD_DATA_DIR", "/opt/dashboard/data"))
    llm_dir = Path(os.environ.get("DASHBOARD_LLM_DIR", "/opt/dashboard/llm"))
    from .context_builder import regenerate
    return ItemStore(data_dir / "items.json", on_write=lambda: regenerate(data_dir, llm_dir))

@router.get("", response_model=list[Item], dependencies=[Depends(require_token)])
def list_items(type: str | None = None, status: str | None = None,
               tag: str | None = None, q: str | None = None, parent: str | None = None):
    return _store().list(type=type, status=status, tag=tag, query=q, parent=parent)

@router.get("/{id}", response_model=Item, dependencies=[Depends(require_token)])
def get_item(id: str):
    try: return _store().get(id)
    except ItemNotFound: raise HTTPException(404, "not found")

@router.post("", response_model=Item, status_code=201,
             dependencies=[Depends(require_token)])
def create_item(payload: ItemCreate):
    try: return _store().add(payload)
    except DuplicateId: raise HTTPException(409, "duplicate id")

@router.patch("/{id}", response_model=Item, dependencies=[Depends(require_token)])
def update_item(id: str, payload: ItemUpdate):
    try: return _store().update(id, payload)
    except ItemNotFound: raise HTTPException(404, "not found")

@router.delete("/{id}", status_code=204, dependencies=[Depends(require_token)])
def delete_item(id: str):
    try:
        _store().delete(id)
        return Response(status_code=204)
    except ItemNotFound: raise HTTPException(404, "not found")

@router.post("/{id}/complete", response_model=Item, dependencies=[Depends(require_token)])
def complete_item(id: str):
    try: return _store().complete(id)
    except ItemNotFound: raise HTTPException(404, "not found")
