from contextlib import contextmanager
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .models_messages import Agent, AgentUpsert, AgentMessage, AgentMessageCreate


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agents (
    name TEXT PRIMARY KEY,
    aliases TEXT NOT NULL DEFAULT '[]',
    inbound_url TEXT,
    color TEXT NOT NULL DEFAULT '#888',
    kind TEXT NOT NULL DEFAULT 'agent'
);

CREATE TABLE IF NOT EXISTS agent_messages (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    sender TEXT NOT NULL,
    recipients TEXT NOT NULL DEFAULT '[]',
    body TEXT NOT NULL,
    thread_id TEXT,
    read_by TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_agent_messages_ts ON agent_messages(ts);
CREATE INDEX IF NOT EXISTS idx_agent_messages_sender ON agent_messages(sender);
"""

SEED_AGENTS = [
    {"name": "claude",  "aliases": ["opus", "opus47", "claude-code"], "color": "#d97757", "kind": "agent"},
    {"name": "codex",   "aliases": ["gpt", "openai"],                 "color": "#10a37f", "kind": "agent"},
    {"name": "hermes",  "aliases": ["deepseek", "h"],                  "color": "#7c5cff", "kind": "agent"},
    {"name": "user",    "aliases": ["me", "virgo", "human"],           "color": "#4a9eff", "kind": "user"},
]

MENTION_RE = re.compile(r"(?<![\w@])@([a-zA-Z][a-zA-Z0-9_-]{0,30})")


class MessageStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        c = sqlite3.connect(self.path, isolation_level=None, timeout=10.0)
        try:
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            with c:
                yield c
        finally:
            c.close()

    def _init_db(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA_SQL)
            for agent in SEED_AGENTS:
                c.execute(
                    "INSERT OR IGNORE INTO agents (name, aliases, color, kind) VALUES (?,?,?,?)",
                    (agent["name"], json.dumps(agent["aliases"]), agent["color"], agent["kind"]),
                )

    # --- agents ---

    def list_agents(self) -> List[Agent]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM agents ORDER BY name").fetchall()
        return [self._row_to_agent(r) for r in rows]

    def get_agent(self, name: str) -> Optional[Agent]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM agents WHERE name=?", (name,)).fetchone()
        return self._row_to_agent(row) if row else None

    def upsert_agent(self, payload: AgentUpsert) -> Agent:
        existing = self.get_agent(payload.name)
        merged = {
            "name": payload.name,
            "aliases": payload.aliases if payload.aliases is not None else (existing.aliases if existing else []),
            "inbound_url": payload.inbound_url if payload.inbound_url is not None else (existing.inbound_url if existing else None),
            "color": payload.color or (existing.color if existing else "#888"),
            "kind": payload.kind or (existing.kind if existing else "agent"),
        }
        with self._conn() as c:
            c.execute(
                "INSERT INTO agents (name, aliases, inbound_url, color, kind) VALUES (?,?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET aliases=excluded.aliases, inbound_url=excluded.inbound_url, "
                "color=excluded.color, kind=excluded.kind",
                (merged["name"], json.dumps(merged["aliases"]), merged["inbound_url"], merged["color"], merged["kind"]),
            )
        return self.get_agent(payload.name)

    def resolve(self, token: str) -> Optional[str]:
        """Resolve a name or alias to a canonical agent name (case-insensitive)."""
        if not token:
            return None
        t = token.lower().lstrip("@")
        with self._conn() as c:
            row = c.execute("SELECT name FROM agents WHERE lower(name)=?", (t,)).fetchone()
            if row:
                return row["name"]
            for r in c.execute("SELECT name, aliases FROM agents").fetchall():
                aliases = [a.lower() for a in json.loads(r["aliases"] or "[]")]
                if t in aliases:
                    return r["name"]
        return None

    # --- messages ---

    def parse_mentions(self, body: str) -> List[str]:
        # Strip fenced code blocks and inline code spans first so that
        # @-mentions inside docs/examples don't broadcast to those agents.
        cleaned = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
        cleaned = re.sub(r"`[^`\n]*`", "", cleaned)
        names: list[str] = []
        for token in MENTION_RE.findall(cleaned):
            if token.lower() == "all":
                with self._conn() as c:
                    rows = c.execute("SELECT name FROM agents WHERE kind='agent'").fetchall()
                names.extend(r["name"] for r in rows)
                continue
            resolved = self.resolve(token)
            if resolved and resolved not in names:
                names.append(resolved)
        return names

    def create_message(self, payload: AgentMessageCreate, default_recipient: Optional[str] = None) -> AgentMessage:
        sender = self.resolve(payload.sender) or payload.sender
        if payload.to:
            recipients = [self.resolve(r) or r for r in payload.to]
        else:
            recipients = self.parse_mentions(payload.body)
            if not recipients and default_recipient:
                recipients = [default_recipient]
        recipients = [r for r in recipients if r and r != sender]
        seen = set()
        recipients = [r for r in recipients if not (r in seen or seen.add(r))]

        mid = uuid.uuid4().hex[:12]
        ts = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            c.execute(
                "INSERT INTO agent_messages (id, ts, sender, recipients, body, thread_id, read_by) "
                "VALUES (?,?,?,?,?,?,?)",
                (mid, ts, sender, json.dumps(recipients), payload.body, payload.thread_id, json.dumps([sender])),
            )
        return self.get_message(mid)

    def get_message(self, mid: str) -> Optional[AgentMessage]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM agent_messages WHERE id=?", (mid,)).fetchone()
        return self._row_to_msg(row) if row else None

    def list_messages(
        self,
        recipient: Optional[str] = None,
        sender: Optional[str] = None,
        unread_for: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 100,
    ) -> List[AgentMessage]:
        sql = "SELECT * FROM agent_messages"
        clauses, args = [], []
        if sender:
            clauses.append("sender=?"); args.append(sender)
        if since:
            clauses.append("ts>?"); args.append(since)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY ts ASC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            rows = c.execute(sql, args).fetchall()
        msgs = [self._row_to_msg(r) for r in rows]
        if recipient:
            msgs = [m for m in msgs if recipient in m.recipients]
        if unread_for:
            msgs = [m for m in msgs if unread_for in m.recipients and unread_for not in m.read_by]
        return msgs

    def mark_read(self, mid: str, reader: str) -> Optional[AgentMessage]:
        msg = self.get_message(mid)
        if not msg:
            return None
        if reader in msg.read_by:
            return msg
        msg.read_by.append(reader)
        with self._conn() as c:
            c.execute("UPDATE agent_messages SET read_by=? WHERE id=?", (json.dumps(msg.read_by), mid))
        return msg

    def mark_all_read(self, reader: str) -> int:
        count = 0
        for msg in self.list_messages(unread_for=reader, limit=1000):
            self.mark_read(msg.id, reader)
            count += 1
        return count

    # --- helpers ---

    def _row_to_agent(self, row: sqlite3.Row) -> Agent:
        return Agent(
            name=row["name"],
            aliases=json.loads(row["aliases"] or "[]"),
            inbound_url=row["inbound_url"],
            color=row["color"],
            kind=row["kind"],
        )

    def _row_to_msg(self, row: sqlite3.Row) -> AgentMessage:
        return AgentMessage(
            id=row["id"],
            ts=row["ts"],
            sender=row["sender"],
            recipients=json.loads(row["recipients"] or "[]"),
            body=row["body"],
            thread_id=row["thread_id"],
            read_by=json.loads(row["read_by"] or "[]"),
        )
