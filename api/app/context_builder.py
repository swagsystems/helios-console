import json
from pathlib import Path
from typing import Iterable
from .store import ItemStore
from .models import Item

PRIORITY_ORDER = {"high": 0, "med": 1, "low": 2, None: 3}
DOCKER_CATEGORY_ORDER = ["media", "monitoring", "infra", "apps", "dev", "other"]


def _prio(p):
    return PRIORITY_ORDER.get(p.value if p else None, 3)


def _section(title: str, lines: Iterable[str]) -> str:
    lines = list(lines)
    if not lines:
        return ""
    return f"## {title}\n\n" + "\n".join(lines) + "\n\n"


def _guardrails(items):
    gs = sorted(
        (i for i in items if i.type.value == "guardrail"),
        key=lambda i: (_prio(i.priority), i.id),
    )
    out = []
    for g in gs:
        prio = g.priority.value if g.priority else "?"
        tags = f"  _({', '.join(g.tags)})_" if g.tags else ""
        out.append(f"- **[{prio}]** {g.title}{tags}")
    return _section("⚠ Guardrails", out)


def _pinned(items):
    ps = [i for i in items if i.type.value == "note" and i.pinned]
    ps.sort(key=lambda i: i.id)
    out = [f"- **{p.title}** — {p.body}" for p in ps]
    return _section("Pinned", out)


def _objectives(items):
    os_ = [i for i in items if i.type.value == "objective"]
    out = [f"- {o.title} ({o.status.value if o.status else '-'})" for o in os_]
    return _section("Objectives", out)


def _open_tasks(items):
    ts = sorted(
        [i for i in items if i.type.value == "task" and i.status and i.status.value != "done"],
        key=lambda i: (_prio(i.priority), i.created),
    )
    out = []
    for t in ts:
        prio = t.priority.value if t.priority else "?"
        tags = f"  _({', '.join(t.tags)})_" if t.tags else ""
        out.append(f"- [{prio}] {t.title}{tags}")
    return _section("Open Tasks", out)


def _open_issues(items):
    ts = sorted(
        [i for i in items if i.type.value == "issue" and i.status and i.status.value != "done"],
        key=lambda i: (_prio(i.priority), i.created),
    )
    out = []
    for t in ts:
        prio = t.priority.value if t.priority else "?"
        tags = f"  _({', '.join(t.tags)})_" if t.tags else ""
        out.append(f"- [{prio}] {t.title}{tags}")
    return _section("Open Issues", out)


def _host(data_dir: Path) -> str:
    p = data_dir / "system.json"
    if not p.exists():
        return ""
    d = json.loads(p.read_text())
    h = d.get("host", {})
    storage = d.get("storage", [])
    net = d.get("network", {})
    storage_line = " · ".join(
        f"{s['name']} {s.get('pct', '?')}%" + (" ⚠" if s.get("status") not in ("ok", None) else "")
        for s in storage
    )
    lines = [
        f"{h.get('name', '?')} — kernel {h.get('kernel', '?')}",
        f"CPU {h.get('cpu_usage_pct', '?')}% · RAM {h.get('ram_pct', '?')}% "
        f"({h.get('ram_used_gb', '?')}/{h.get('ram_total_gb', '?')} GB) · "
        f"uptime {h.get('uptime', '?')}",
    ]
    if storage_line:
        lines.append(f"Storage: {storage_line}")
    if net.get("dns_chain"):
        lines.append(f"DNS: {net['dns_chain']}")
    if net.get("tailscale"):
        lines.append(f"Tailscale: {net['tailscale']}")
    return "## Host\n\n" + "\n".join(lines) + "\n\n"


def _lxcs(data_dir: Path) -> str:
    p = data_dir / "services.json"
    if not p.exists():
        return ""
    d = json.loads(p.read_text())
    lxc = sorted(d.get("lxc", []), key=lambda x: x.get("id", 0))
    if not lxc:
        return ""
    rows = ["| ID | Name | IP | RAM | Disk | Up | Purpose |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for l in lxc:
        rows.append(
            f"| {l.get('id', '?')} | {l.get('name', '?')} | {l.get('ip', '?')} | "
            f"{l.get('ram_pct', '?')}% | {l.get('disk_pct', '?')}% | "
            f"{l.get('uptime', '?')} | {l.get('purpose', '')} |"
        )
    return "## LXCs\n\n" + "\n".join(rows) + "\n\n"


def _docker(data_dir: Path) -> str:
    p = data_dir / "services.json"
    if not p.exists():
        return ""
    d = json.loads(p.read_text())
    containers = d.get("docker", [])
    if not containers:
        return ""
    by_cat = {}
    for c in containers:
        by_cat.setdefault(c.get("category", "other"), []).append(c)
    parts = ["## Docker\n"]
    for cat in DOCKER_CATEGORY_ORDER:
        if cat not in by_cat:
            continue
        parts.append(f"### {cat}\n")
        for c in sorted(by_cat[cat], key=lambda x: x.get("name", "")):
            ports = ", ".join(f":{port}" for port in c.get("ports", []))
            ports_part = f", {ports}" if ports else ""
            purpose = c.get("purpose") or ""
            purpose_part = f" — {purpose}" if purpose else ""
            parts.append(f"- {c.get('name', '?')} ({c.get('status', '?')}{ports_part}){purpose_part}")
        parts.append("")
    for cat in by_cat:
        if cat in DOCKER_CATEGORY_ORDER:
            continue
        parts.append(f"### {cat}\n")
        for c in sorted(by_cat[cat], key=lambda x: x.get("name", "")):
            ports = ", ".join(f":{port}" for port in c.get("ports", []))
            ports_part = f", {ports}" if ports else ""
            purpose = c.get("purpose") or ""
            purpose_part = f" — {purpose}" if purpose else ""
            parts.append(f"- {c.get('name', '?')} ({c.get('status', '?')}{ports_part}){purpose_part}")
        parts.append("")
    return "\n".join(parts) + "\n"


def _domains(data_dir: Path) -> str:
    p = data_dir / "services.json"
    if not p.exists():
        return ""
    d = json.loads(p.read_text())
    doms = d.get("domains", [])
    if not doms:
        return ""
    rows = ["| Domain | Target | SSL |",
            "| --- | --- | --- |"]
    for dom in doms:
        ssl = "✓" if dom.get("ssl") else "—"
        rows.append(f"| {dom.get('domain', '?')} | {dom.get('target', '?')} | {ssl} |")
    return "## Domains\n\n" + "\n".join(rows) + "\n\n"


def regenerate(data_dir: Path, llm_dir: Path) -> None:
    data_dir = Path(data_dir)
    llm_dir = Path(llm_dir)
    llm_dir.mkdir(parents=True, exist_ok=True)
    items = ItemStore(data_dir / "items.json").list()
    p = data_dir / "items.json"
    raw = json.loads(p.read_text()) if p.exists() else {}
    updated = raw.get("_meta", {}).get("updated", "")

    parts = [
        "# Helios Dashboard — Agent Context\n",
        "> Generated from dashboard data after each write.\n",
    ]
    if updated:
        parts.append(f"> Updated: {updated}\n")
    parts.append("\n")
    parts.append(_guardrails(items))
    parts.append(_pinned(items))
    parts.append(_objectives(items))
    parts.append(_open_tasks(items))
    parts.append(_open_issues(items))
    parts.append(_host(data_dir))
    parts.append(_lxcs(data_dir))
    parts.append(_docker(data_dir))
    parts.append(_domains(data_dir))

    (llm_dir / "context.md").write_text("".join(parts))
