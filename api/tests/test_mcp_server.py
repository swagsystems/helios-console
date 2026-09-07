import json

import pytest
from fastapi.testclient import TestClient

from app.mcp_server import build_server
from app.store import ItemStore
from app.models import ItemCreate


async def _call_json(server, name: str, arguments: dict | None = None):
    result = await server.call_tool(name, arguments or {})
    contents = result[0] if isinstance(result, tuple) else result
    assert contents, f"{name} returned no content"
    return json.loads(contents[0].text)


async def test_list_items_tool(data_dir):
    s = ItemStore(data_dir / "items.json")
    s.add(ItemCreate(id="x", type="task", title="hi", status="open", priority="med"))
    server = build_server()
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert {"list_items", "add_item", "get_item", "update_item", "delete_item",
            "complete_task", "get_system", "get_services", "get_context_md",
            "start_run", "add_step", "update_step", "save_context", "heartbeat",
            "finish_run", "list_active_runs", "get_run", "get_resume"} <= names


async def test_list_items_defaults_to_compact_paginated_payload(data_dir):
    s = ItemStore(data_dir / "items.json")
    s.add(ItemCreate(id="a", type="task", title="first", body="x" * 80, status="open", priority="high"))
    s.add(ItemCreate(id="b", type="task", title="second", body="short", status="open", priority="low"))

    payload = await _call_json(build_server(), "list_items", {"type": "task", "limit": 1, "body_chars": 20})

    assert payload["total"] == 2
    assert payload["limit"] == 1
    assert payload["truncated"] is True
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["id"] == "a"
    assert item["title"] == "first"
    assert "body" not in item
    assert item["body_preview"].endswith("chars]")


async def test_get_item_remains_full_detail(data_dir):
    s = ItemStore(data_dir / "items.json")
    s.add(ItemCreate(id="full", type="note", title="detail", body="full body", tags=["x"]))

    payload = await _call_json(build_server(), "get_item", {"id": "full"})

    assert payload["body"] == "full body"
    assert payload["tags"] == ["x"]


async def test_run_tools_return_compact_payloads(data_dir):
    server = build_server()
    start = await _call_json(server, "start_run", {
        "goal": "check compact returns",
        "provider": "pytest",
        "model": "gpt-test",
        "context_blob": {"large": "x" * 500, "next": "continue"},
    })
    run_id = start["id"]

    assert start["goal"] == "check compact returns"
    assert start["provider_model"] == "pytest/gpt-test"
    assert "context_blob" not in start
    assert start["context_keys"] == ["large", "next"]

    step = await _call_json(server, "add_step", {
        "run_id": run_id,
        "title": "long output",
        "status": "done",
        "output": "y" * 1000,
    })
    assert "output" not in step
    assert len(step["output_preview"]) < 320
    assert step["output_preview"].endswith("chars]")

    listed = await _call_json(server, "list_active_runs", {"include_steps": True})
    assert listed["runs"][0]["id"] == run_id
    assert "context_blob" not in listed["runs"][0]

    detail = await _call_json(server, "get_run", {"run_id": run_id, "include_context": True, "output_chars": 25})
    assert detail["context_blob"]["next"] == "continue"
    assert detail["recent_steps"][0]["output_preview"].endswith("chars]")


async def test_system_and_services_default_to_summaries(data_dir):
    (data_dir / "system.json").write_text(json.dumps({
        "_meta": {"updated": "now"},
        "host": {"name": "helios", "kernel": "k", "cpu_usage_pct": 12, "extra": "drop"},
        "storage": [{"name": "local", "type": "dir", "pct": 30, "status": "ok", "used_gb": 20}],
        "network": {"tailscale": "running"},
    }))
    (data_dir / "services.json").write_text(json.dumps({
        "_meta": {"updated": "now"},
        "lxc": [{"id": 202, "name": "docker", "ip": "192.0.2.10", "ram_pct": 46, "ignored": "drop"}],
        "docker": [{"name": "dashboard", "status": "running", "category": "other", "ports": [8390], "ignored": "drop"}],
        "domains": [{"domain": "dashboard.example.com", "target": "192.0.2.10", "ssl": True}],
    }))
    server = build_server()

    system = await _call_json(server, "get_system")
    services = await _call_json(server, "get_services")

    assert system["host"] == {"name": "helios", "kernel": "k", "cpu_usage_pct": 12}
    assert system["storage"] == [{"name": "local", "type": "dir", "pct": 30, "status": "ok"}]
    assert services["docker_counts"] == {"other": 1}
    assert services["docker_total"] == 1
    assert services["domains_count"] == 1
    assert "docker" not in services
    with_containers = await _call_json(server, "get_services", {"include_containers": True})
    assert with_containers["docker"] == [{"name": "dashboard", "status": "running", "category": "other", "ports": [8390]}]


def test_streamable_http_tools_list_is_stateless(data_dir):
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/mcp/",
            headers={
                "Authorization": "Bearer testtoken",
                "Accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    assert response.status_code == 200
    assert "list_items" in response.text
    assert "mcp-session-id" not in response.headers


async def test_mcp_tools_emit_safety_annotations(data_dir):
    server = build_server()
    tools = {tool.name: tool for tool in await server.list_tools()}

    read_tool = tools["get_context_md"]
    assert read_tool.annotations is not None
    assert read_tool.annotations.readOnlyHint is True
    assert read_tool.annotations.idempotentHint is True
    assert read_tool.annotations.destructiveHint is False
    assert read_tool.annotations.openWorldHint is False

    write_tool = tools["add_item"]
    assert write_tool.annotations is not None
    assert write_tool.annotations.readOnlyHint is False
    assert write_tool.annotations.idempotentHint is False
    assert write_tool.annotations.destructiveHint is False
    assert write_tool.annotations.openWorldHint is False

    delete_tool = tools["delete_item"]
    assert delete_tool.annotations is not None
    assert delete_tool.annotations.readOnlyHint is False
    assert delete_tool.annotations.idempotentHint is False
    assert delete_tool.annotations.destructiveHint is True
    assert delete_tool.annotations.openWorldHint is False
