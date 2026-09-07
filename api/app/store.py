import fcntl
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Callable

from .models import Item, ItemCreate, ItemUpdate, ItemStatus

log = logging.getLogger(__name__)

class ItemNotFound(Exception): ...
class DuplicateId(Exception): ...

SCHEMA = 2

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

class ItemStore:
    def __init__(self, path: Path, on_write: Optional[Callable[[], None]] = None):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.on_write = on_write
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_raw({"_meta": {"updated": _now(), "schema": SCHEMA}, "items": []})

    def _read_raw(self) -> dict:
        with open(self.path, "r") as f:
            return json.load(f)

    def _write_raw_unlocked(self, raw: dict) -> None:
        raw["_meta"]["updated"] = _now()
        raw["_meta"]["schema"] = SCHEMA
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w") as f:
            json.dump(raw, f, indent=2)
        os.replace(tmp, self.path)

    def _run_on_write(self) -> None:
        if self.on_write:
            try:
                self.on_write()
            except Exception:
                log.exception("post-write context regeneration failed")

    def _write_raw(self, raw: dict) -> None:
        with open(self.lock_path, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                self._write_raw_unlocked(raw)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
        self._run_on_write()

    def _mutate_raw(self, mutate: Callable[[dict], object]) -> object:
        """Run a read-modify-write mutation while holding the item-store lock."""
        with open(self.lock_path, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                raw = self._read_raw()
                result = mutate(raw)
                self._write_raw_unlocked(raw)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
        self._run_on_write()
        return result

    def list(self, type: Optional[str] = None, status: Optional[str] = None,
             tag: Optional[str] = None, query: Optional[str] = None,
             parent: Optional[str] = None) -> List[Item]:
        raw = self._read_raw()
        items = [Item(**it) for it in raw["items"]]
        if type: items = [i for i in items if i.type.value == type]
        if status: items = [i for i in items if i.status and i.status.value == status]
        if tag: items = [i for i in items if tag in i.tags]
        if parent: items = [i for i in items if i.parent == parent]
        if query:
            q = query.lower()
            items = [i for i in items if q in i.title.lower() or q in i.body.lower()]
        return items

    def get(self, id: str) -> Item:
        for it in self._read_raw()["items"]:
            if it["id"] == id:
                return Item(**it)
        raise ItemNotFound(id)

    def add(self, payload: ItemCreate) -> Item:
        def mutate(raw: dict) -> Item:
            new_id = payload.id or uuid.uuid4().hex[:12]
            if any(it["id"] == new_id for it in raw["items"]):
                raise DuplicateId(new_id)
            item = Item(
                id=new_id,
                type=payload.type, title=payload.title, body=payload.body,
                status=payload.status, priority=payload.priority,
                tags=list(payload.tags), parent=payload.parent,
                pinned=payload.pinned, links=list(payload.links),
            )
            raw["items"].append(item.model_dump(mode="json"))
            return item
        return self._mutate_raw(mutate)

    def update(self, id: str, payload: ItemUpdate) -> Item:
        def mutate(raw: dict) -> Item:
            for idx, it in enumerate(raw["items"]):
                if it["id"] == id:
                    merged = {**it, **{k: v for k, v in payload.model_dump(exclude_unset=True, mode="json").items()}}
                    merged["updated"] = _now()
                    if "status" in payload.model_fields_set and payload.status != ItemStatus.done:
                        merged["completed"] = None
                    raw["items"][idx] = Item(**merged).model_dump(mode="json")
                    return Item(**raw["items"][idx])
            raise ItemNotFound(id)
        return self._mutate_raw(mutate)

    def delete(self, id: str) -> None:
        def mutate(raw: dict) -> None:
            n = len(raw["items"])
            raw["items"] = [it for it in raw["items"] if it["id"] != id]
            if len(raw["items"]) == n:
                raise ItemNotFound(id)
        self._mutate_raw(mutate)

    def complete(self, id: str) -> Item:
        def mutate(raw: dict) -> Item:
            for idx, it in enumerate(raw["items"]):
                if it["id"] == id:
                    it["status"] = "done"
                    it["completed"] = _now()
                    it["updated"] = _now()
                    raw["items"][idx] = Item(**it).model_dump(mode="json")
                    return Item(**raw["items"][idx])
            raise ItemNotFound(id)
        return self._mutate_raw(mutate)
