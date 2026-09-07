import json
import os
from pathlib import Path
from app.context_builder import regenerate
from app.store import ItemStore
from app.models import ItemCreate

def _seed(data_dir):
    s = ItemStore(data_dir / "items.json")
    s.add(ItemCreate(id="g1", type="guardrail",
                     title="Don't touch /etc/pve",
                     priority="high", tags=["pve"]))
    s.add(ItemCreate(id="g2", type="guardrail",
                     title="Soft preference",
                     priority="low", tags=["misc"]))
    s.add(ItemCreate(id="p1", type="note", title="Pinned thing",
                     pinned=True, body="important info"))
    s.add(ItemCreate(id="o1", type="objective", title="Migrate dispo",
                     status="in_progress"))
    s.add(ItemCreate(id="t1", type="task", title="Auto-fix sonarr",
                     status="open", priority="high", tags=["media"]))
    s.add(ItemCreate(id="t2", type="task", title="done thing",
                     status="done", priority="low"))
    s.add(ItemCreate(id="i1", type="issue", title="local-lvm 62%",
                     status="open", priority="med", tags=["storage"]))
    return s

def test_section_order(data_dir):
    _seed(data_dir)
    regenerate(data_dir, Path(os.environ["DASHBOARD_LLM_DIR"]))
    md = (Path(os.environ["DASHBOARD_LLM_DIR"]) / "context.md").read_text()
    g = md.index("## ⚠ Guardrails")
    p = md.index("## Pinned")
    o = md.index("## Objectives")
    t = md.index("## Open Tasks")
    i = md.index("## Open Issues")
    assert g < p < o < t < i

def test_guardrails_sorted_high_first(data_dir):
    _seed(data_dir)
    regenerate(data_dir, Path(os.environ["DASHBOARD_LLM_DIR"]))
    md = (Path(os.environ["DASHBOARD_LLM_DIR"]) / "context.md").read_text()
    g_section = md.split("## ⚠ Guardrails")[1].split("## ")[0]
    high_idx = g_section.index("Don't touch /etc/pve")
    low_idx = g_section.index("Soft preference")
    assert high_idx < low_idx

def test_done_tasks_excluded(data_dir):
    _seed(data_dir)
    regenerate(data_dir, Path(os.environ["DASHBOARD_LLM_DIR"]))
    md = (Path(os.environ["DASHBOARD_LLM_DIR"]) / "context.md").read_text()
    assert "Auto-fix sonarr" in md
    assert "done thing" not in md

def test_no_raw_json_fences(data_dir):
    _seed(data_dir)
    (data_dir / "system.json").write_text(json.dumps({
        "_meta": {"updated": "now"},
        "host": {"name": "helios", "cpu_usage_pct": 17.0, "ram_pct": 47.0,
                 "ram_used_gb": 7.2, "ram_total_gb": 15.4, "uptime": "8d 11h",
                 "kernel": "6.8.12-8-pve"},
        "storage": [{"name": "local", "pct": 27, "status": "ok"},
                    {"name": "local-lvm", "pct": 62, "status": "warning"}],
        "network": {"tailscale": "running", "dns_chain": "AdGuard → Unbound → Quad9/CF"}
    }))
    (data_dir / "services.json").write_text(json.dumps({
        "_meta": {"updated": "now"},
        "lxc": [{"id": 200, "name": "adguard", "ip": "192.0.2.20",
                 "ram_pct": 46, "disk_pct": 39, "uptime": "2d 0h",
                 "status": "running", "purpose": "DNS"}],
        "docker": [{"name": "jellyfin", "category": "media",
                    "status": "running (healthy)", "ports": ["8096"],
                    "purpose": "Media server"}],
        "domains": [{"domain": "service.example.com", "target": "192.0.2.10:80", "ssl": False}]
    }))
    regenerate(data_dir, Path(os.environ["DASHBOARD_LLM_DIR"]))
    md = (Path(os.environ["DASHBOARD_LLM_DIR"]) / "context.md").read_text()
    assert "```json" not in md
    assert "## Host" in md
    assert "helios" in md
    assert "kernel 6.8.12-8-pve" in md
    assert "local-lvm 62%" in md
    assert "## LXCs" in md
    assert "adguard" in md
    assert "## Docker" in md
    assert "### media" in md
    assert "jellyfin" in md
    assert "## Domains" in md

def test_empty_optional_sections_omitted(data_dir):
    _seed(data_dir)
    regenerate(data_dir, Path(os.environ["DASHBOARD_LLM_DIR"]))
    md = (Path(os.environ["DASHBOARD_LLM_DIR"]) / "context.md").read_text()
    assert "## Host" not in md
    assert "## LXCs" not in md
