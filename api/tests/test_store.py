import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from app.store import ItemStore, ItemNotFound, DuplicateId
from app.models import ItemCreate, ItemUpdate

def test_empty_store_lists_nothing(data_dir):
    s = ItemStore(data_dir / "items.json")
    assert s.list() == []

def test_add_and_get(data_dir):
    s = ItemStore(data_dir / "items.json")
    item = s.add(ItemCreate(type="note", title="hi"))
    assert item.id
    got = s.get(item.id)
    assert got.title == "hi"

def test_add_with_explicit_id(data_dir):
    s = ItemStore(data_dir / "items.json")
    item = s.add(ItemCreate(id="my-id", type="task", title="t", status="open", priority="med"))
    assert item.id == "my-id"

def test_duplicate_id_rejected(data_dir):
    s = ItemStore(data_dir / "items.json")
    s.add(ItemCreate(id="x", type="note", title="a"))
    with pytest.raises(DuplicateId):
        s.add(ItemCreate(id="x", type="note", title="b"))

def test_update_partial(data_dir):
    s = ItemStore(data_dir / "items.json")
    item = s.add(ItemCreate(type="task", title="t", status="open", priority="low"))
    updated = s.update(item.id, ItemUpdate(status="in_progress"))
    assert updated.status.value == "in_progress"
    assert updated.title == "t"

def test_delete(data_dir):
    s = ItemStore(data_dir / "items.json")
    item = s.add(ItemCreate(type="note", title="x"))
    s.delete(item.id)
    with pytest.raises(ItemNotFound):
        s.get(item.id)

def test_complete_sets_status_and_completed(data_dir):
    s = ItemStore(data_dir / "items.json")
    item = s.add(ItemCreate(type="task", title="t", status="open", priority="med"))
    done = s.complete(item.id)
    assert done.status.value == "done"
    assert done.completed is not None

def test_list_filters(data_dir):
    s = ItemStore(data_dir / "items.json")
    s.add(ItemCreate(type="task", title="a", status="open", priority="high", tags=["media"]))
    s.add(ItemCreate(type="note", title="b", tags=["dispo"]))
    assert len(s.list(type="task")) == 1
    assert len(s.list(tag="media")) == 1
    assert len(s.list(query="b")) == 1

def test_atomic_write_persists(data_dir):
    path = data_dir / "items.json"
    s1 = ItemStore(path)
    s1.add(ItemCreate(id="x", type="note", title="hi"))
    s2 = ItemStore(path)
    assert s2.get("x").title == "hi"

def test_meta_updated_changes_on_write(data_dir):
    path = data_dir / "items.json"
    s = ItemStore(path)
    s.add(ItemCreate(id="x", type="note", title="a"))
    raw1 = json.loads(path.read_text())
    s.add(ItemCreate(id="y", type="note", title="b"))
    raw2 = json.loads(path.read_text())
    assert raw1["_meta"]["updated"] != raw2["_meta"]["updated"]

def test_reads_legacy_schema_1(data_dir):
    import json
    raw = {"_meta": {"updated": "2026-04-26T00:00:00Z", "schema": 1},
           "items": [{"id": "x", "type": "task", "title": "old",
                      "body": "", "status": "open", "priority": "med",
                      "tags": [], "parent": None, "pinned": False, "links": [],
                      "created": "2026-04-26T00:00:00Z",
                      "updated": "2026-04-26T00:00:00Z", "completed": None}]}
    (data_dir / "items.json").write_text(json.dumps(raw))
    s = ItemStore(data_dir / "items.json")
    assert len(s.list()) == 1
    s.add(ItemCreate(id="g", type="guardrail", title="g", priority="high"))
    raw_after = json.loads((data_dir / "items.json").read_text())
    assert raw_after["_meta"]["schema"] == 2


def test_concurrent_adds_do_not_lose_writes(data_dir):
    path = data_dir / "items.json"
    ItemStore(path)

    def add_one(i):
        return ItemStore(path).add(ItemCreate(id=f"item-{i}", type="note", title=f"n{i}")).id

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(add_one, range(40)))

    assert sorted(ids, key=lambda item_id: int(item_id.rsplit("-", 1)[1])) == [f"item-{i}" for i in range(40)]
    assert len(ItemStore(path).list(type="note")) == 40
