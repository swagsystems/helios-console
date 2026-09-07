import json
import os
from collections import Counter
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings
from mcp.types import ToolAnnotations

from .models import ItemCreate, ItemUpdate
from .store import ItemStore

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)

DEFAULT_ITEM_LIMIT = 20
MAX_ITEM_LIMIT = 200
DEFAULT_BODY_CHARS = 0
DEFAULT_STEP_OUTPUT_CHARS = 240
MAX_STEP_LIMIT = 50


def _data_dir() -> Path:
    return Path(os.environ.get("DASHBOARD_DATA_DIR", "/opt/dashboard/data"))


def _llm_dir() -> Path:
    return Path(os.environ.get("DASHBOARD_LLM_DIR", "/opt/dashboard/llm"))


def _store() -> ItemStore:
    data_dir = _data_dir()
    llm_dir = _llm_dir()
    from .context_builder import regenerate

    return ItemStore(data_dir / "items.json", on_write=lambda: regenerate(data_dir, llm_dir))


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(minimum, min(maximum, n))


def _truncate(value: object, max_chars: int | None) -> str:
    text = "" if value is None else str(value)
    if max_chars is None or max_chars <= 0 or len(text) <= max_chars:
        return text
    shown = text[:max_chars].rstrip()
    return f"{shown}… [+{len(text) - len(shown)} chars]"


def _item_summary(item, body_chars: int = DEFAULT_BODY_CHARS) -> dict:
    out = {
        "id": item.id,
        "type": _enum_value(item.type),
        "title": item.title,
    }
    if item.status is not None:
        out["status"] = _enum_value(item.status)
    if item.priority is not None:
        out["priority"] = _enum_value(item.priority)
    if item.tags:
        out["tags"] = item.tags
    if item.parent:
        out["parent"] = item.parent
    if item.pinned:
        out["pinned"] = True
    if item.links:
        out["links_count"] = len(item.links)
    if item.completed:
        out["completed"] = item.completed
    if body_chars and item.body:
        out["body_preview"] = _truncate(item.body, body_chars)
    return out


def _step_summary(step, output_chars: int = DEFAULT_STEP_OUTPUT_CHARS) -> dict:
    out = {
        "idx": step.idx,
        "title": step.title,
        "status": _enum_value(step.status),
    }
    if step.started:
        out["started"] = step.started
    if step.finished:
        out["finished"] = step.finished
    if output_chars and step.output:
        out["output_preview"] = _truncate(step.output, output_chars)
    return out


def _run_summary(run, *, include_context: bool = False,
                 step_limit: int = 5, output_chars: int = DEFAULT_STEP_OUTPUT_CHARS) -> dict:
    counts = Counter(_enum_value(step.status) for step in run.steps)
    out = {
        "id": run.id,
        "goal": run.goal,
        "provider": run.provider,
        "status": _enum_value(run.status),
        "current_step": run.current_step,
        "created": run.created,
        "updated": run.updated,
        "last_heartbeat": run.last_heartbeat,
        "step_counts": {"total": len(run.steps), **dict(counts)},
    }
    if run.session_label:
        out["session_label"] = run.session_label
    if run.model:
        out["model"] = run.model
        out["provider_model"] = f"{run.provider}/{run.model}"
    if run.parent_run:
        out["parent_run"] = run.parent_run
    if run.item_id:
        out["item_id"] = run.item_id
    if run.steps:
        current = next((step for step in run.steps if step.idx == run.current_step), run.steps[-1])
        out["current"] = _step_summary(current, output_chars=0)
    if step_limit:
        limit = _bounded_int(step_limit, 5, 1, MAX_STEP_LIMIT)
        out["recent_steps"] = [_step_summary(step, output_chars=output_chars) for step in run.steps[-limit:]]
        if len(run.steps) > limit:
            out["steps_truncated"] = len(run.steps) - limit
    if include_context:
        out["context_blob"] = run.context_blob
    elif run.context_blob:
        out["context_keys"] = sorted(run.context_blob.keys())[:20]
    return out


def _load_snapshot(name: str) -> dict:
    path = _data_dir() / name
    return json.loads(path.read_text()) if path.exists() else {}


def _system_summary(data: dict) -> dict:
    host = data.get("host") or {}
    return {
        "updated": (data.get("_meta") or {}).get("updated"),
        "host": {
            key: host.get(key)
            for key in ("name", "kernel", "cpu_cores", "cpu_usage_pct", "ram_used_gb", "ram_total_gb", "ram_pct", "uptime")
            if host.get(key) is not None
        },
        "storage": [
            {key: item.get(key) for key in ("name", "type", "pct", "status") if item.get(key) is not None}
            for item in data.get("storage", [])
        ],
        "network": data.get("network") or {},
    }


def _docker_summary(container: dict) -> dict:
    return {
        key: container.get(key)
        for key in ("name", "status", "category", "ports", "purpose")
        if container.get(key) not in (None, [], "")
    }


def _domain_summary(domain: dict) -> dict:
    return {key: domain.get(key) for key in ("domain", "target", "ssl") if domain.get(key) is not None}


def _services_summary(data: dict, *, include_containers: bool = False, include_domains: bool = False) -> dict:
    docker = data.get("docker", [])
    domains = data.get("domains", [])
    docker_counts = Counter(container.get("category", "other") for container in docker)
    attention = [
        _docker_summary(container)
        for container in docker
        if "running" not in str(container.get("status", "")).lower()
    ]
    out = {
        "updated": (data.get("_meta") or {}).get("updated"),
        "lxc": [
            {
                key: lxc.get(key)
                for key in ("id", "name", "ip", "status", "ram_pct", "disk_pct", "uptime", "purpose")
                if lxc.get(key) is not None
            }
            for lxc in data.get("lxc", [])
        ],
        "docker_counts": dict(sorted(docker_counts.items())),
        "docker_total": len(docker),
        "docker_attention": attention,
        "domains_count": len(domains),
    }
    if include_containers:
        out["docker"] = [_docker_summary(container) for container in docker]
    if include_domains:
        out["domains"] = [_domain_summary(domain) for domain in domains]
    return out


def build_server() -> FastMCP:
    mcp = FastMCP(
        "helios-dashboard",
        streamable_http_path="/",
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @mcp.tool(annotations=READ_ONLY)
    def list_items(type: str | None = None, status: str | None = None,
                   tag: str | None = None, query: str | None = None,
                   parent: str | None = None, limit: int = DEFAULT_ITEM_LIMIT,
                   offset: int = 0, full: bool = False,
                   body_chars: int = DEFAULT_BODY_CHARS) -> dict:
        """Search dashboard items. Compact by default; use get_item for full body. Filter first, then page with limit/offset."""
        items = _store().list(type=type, status=status, tag=tag, query=query, parent=parent)
        total = len(items)
        offset = _bounded_int(offset, 0, 0, max(total, 0))
        limit = _bounded_int(limit, DEFAULT_ITEM_LIMIT, 1, MAX_ITEM_LIMIT)
        page = items[offset: offset + limit]
        body_chars = _bounded_int(body_chars, DEFAULT_BODY_CHARS, 0, 4000)
        return {
            "items": [i.model_dump(mode="json") if full else _item_summary(i, body_chars=body_chars) for i in page],
            "total": total,
            "offset": offset,
            "limit": limit,
            "truncated": offset + limit < total,
        }

    @mcp.tool(annotations=READ_ONLY)
    def get_item(id: str) -> dict:
        """Get one dashboard item with full body and links."""
        return _store().get(id).model_dump(mode="json")

    @mcp.tool(annotations=WRITE)
    def add_item(type: str, title: str, body: str = "", status: str | None = None,
                 priority: str | None = None, tags: list[str] | None = None,
                 parent: str | None = None, pinned: bool = False,
                 links: list[dict] | None = None) -> dict:
        """Create an objective, task, issue, note, or guardrail. Returns a compact item summary."""
        item = _store().add(ItemCreate(
            type=type, title=title, body=body, status=status, priority=priority,
            tags=tags or [], parent=parent, pinned=pinned, links=links or [],
        ))
        return _item_summary(item)

    @mcp.tool(annotations=WRITE)
    def update_item(id: str, fields: dict) -> dict:
        """Patch fields on an item. Returns a compact summary; call get_item if you need the full body."""
        return _item_summary(_store().update(id, ItemUpdate(**fields)))

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_item(id: str) -> dict:
        """Delete an item."""
        _store().delete(id)
        return {"ok": True, "id": id}

    @mcp.tool(annotations=WRITE)
    def complete_task(id: str) -> dict:
        """Mark a task or issue done. Returns a compact item summary."""
        return _item_summary(_store().complete(id))

    @mcp.tool(annotations=READ_ONLY)
    def get_system(full: bool = False) -> dict:
        """Return host system status. Default is compact; set full=true for raw system.json."""
        data = _load_snapshot("system.json")
        return data if full else _system_summary(data)

    @mcp.tool(annotations=READ_ONLY)
    def get_services(full: bool = False, include_containers: bool = False, include_domains: bool = False) -> dict:
        """Return LXC/Docker/domain status. Compact by default; opt into raw/full lists only when needed."""
        data = _load_snapshot("services.json")
        return data if full else _services_summary(data, include_containers=include_containers, include_domains=include_domains)

    @mcp.tool(annotations=READ_ONLY)
    def get_context_md(max_chars: int = 16000) -> str:
        """Return the generated agent context bundle. max_chars=0 returns the full file."""
        path = _llm_dir() / "context.md"
        text = path.read_text() if path.exists() else ""
        max_chars = _bounded_int(max_chars, 16000, 0, 200000)
        return _truncate(text, max_chars) if max_chars else text

    # --- runs (live agent execution tracking) ---

    def _run_store():
        from .store_runs import RunStore

        return RunStore(_data_dir() / "runs.db")

    @mcp.tool(annotations=WRITE)
    def start_run(goal: str, provider: str = "unknown", model: str | None = None,
                  session_label: str | None = None,
                  parent_run: str | None = None,
                  item_id: str | None = None,
                  context_blob: dict | None = None) -> dict:
        """Start a visible Live Run for multi-step work. Save the returned id; update steps and finish it when done."""
        from .models_runs import RunCreate

        run = _run_store().create_run(RunCreate(
            goal=goal, provider=provider, model=model, session_label=session_label,
            parent_run=parent_run, item_id=item_id, context_blob=context_blob or {},
        ))
        return _run_summary(run, step_limit=0)

    @mcp.tool(annotations=WRITE)
    def add_step(run_id: str, title: str, status: str = "pending", output: str = "") -> dict:
        """Append a Live Run step. Use status in_progress when starting, done/failed/skipped when finishing."""
        from .models_runs import StepCreate

        step = _run_store().add_step(run_id, StepCreate(title=title, status=status, output=output))
        return _step_summary(step)

    @mcp.tool(annotations=WRITE)
    def update_step(run_id: str, idx: int,
                    status: str | None = None,
                    output: str | None = None,
                    title: str | None = None) -> dict:
        """Update one Live Run step. Output is echoed back as a preview to avoid giant tool results."""
        from .models_runs import StepUpdate

        fields = {k: v for k, v in (("status", status), ("output", output), ("title", title)) if v is not None}
        step = _run_store().update_step(run_id, idx, StepUpdate(**fields))
        return _step_summary(step)

    @mcp.tool(annotations=WRITE)
    def save_context(run_id: str, context_blob: dict, current_step: int | None = None) -> dict:
        """Replace a run's resume context. Store concise state: last decision, files touched, and next action."""
        from .models_runs import RunUpdate

        fields = {"context_blob": context_blob}
        if current_step is not None:
            fields["current_step"] = current_step
        return _run_summary(_run_store().update_run(run_id, RunUpdate(**fields)), step_limit=0)

    @mcp.tool(annotations=WRITE)
    def heartbeat(run_id: str) -> dict:
        """Mark a run alive and return a compact status."""
        return _run_summary(_run_store().heartbeat(run_id), step_limit=0)

    @mcp.tool(annotations=WRITE)
    def finish_run(run_id: str, status: str = "completed") -> dict:
        """Close a run. Status: completed, failed, or abandoned."""
        from .models_runs import RunUpdate

        return _run_summary(_run_store().update_run(run_id, RunUpdate(status=status)), step_limit=5)

    @mcp.tool(annotations=READ_ONLY)
    def list_active_runs(limit: int = 10, include_steps: bool = False) -> dict:
        """List active/stalled runs as compact summaries. Use get_run for details or get_resume for handoff."""
        limit = _bounded_int(limit, 10, 1, 50)
        store = _run_store()
        active = store.list_runs(status="active", limit=limit)
        stalled = store.list_runs(status="stalled", limit=limit)
        runs = active + stalled
        return {
            "runs": [_run_summary(r, step_limit=5 if include_steps else 0, output_chars=120) for r in runs[:limit]],
            "total_returned": min(len(runs), limit),
            "limit": limit,
            "truncated": len(runs) > limit,
        }

    @mcp.tool(annotations=READ_ONLY)
    def get_run(run_id: str, include_context: bool = False,
                step_limit: int = 20, output_chars: int = 600) -> dict:
        """Get one Live Run. Compact by default; include_context=true only when resuming/debugging."""
        step_limit = _bounded_int(step_limit, 20, 0, MAX_STEP_LIMIT)
        output_chars = _bounded_int(output_chars, 600, 0, 4000)
        return _run_summary(
            _run_store().get_run(run_id),
            include_context=include_context,
            step_limit=step_limit,
            output_chars=output_chars,
        )

    @mcp.tool(annotations=READ_ONLY)
    def get_resume(run_id: str) -> str:
        """Return a prompt-ready handoff bundle for resuming this run in another session/provider."""
        return _run_store().build_resume_prompt(run_id)

    return mcp
