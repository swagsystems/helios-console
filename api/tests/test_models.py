import pytest
from pydantic import ValidationError
from app.models import Item, ItemType, ItemStatus, ItemPriority

def test_minimal_note_valid():
    i = Item(id="x", type="note", title="hello")
    assert i.type == ItemType.note
    assert i.status is None

def test_task_requires_status():
    i = Item(id="x", type="task", title="t", status="open", priority="med")
    assert i.status == ItemStatus.open

def test_invalid_type_rejected():
    with pytest.raises(ValidationError):
        Item(id="x", type="bogus", title="t")

def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        Item(id="x", type="note", title="t", weird=1)

def test_guardrail_type_valid():
    i = Item(id="g1", type="guardrail", title="No prod writes", priority="high", tags=["safety"])
    assert i.type == ItemType.guardrail
    assert i.priority == ItemPriority.high
