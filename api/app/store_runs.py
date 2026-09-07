from contextlib import contextmanager
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .models_runs import (
    Run, RunCreate, RunUpdate, RunStatus,
    Step, StepCreate, StepUpdate, StepStatus,
)


class RunNotFound(Exception): ...
class StepNotFound(Exception): ...


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'unknown',
    model TEXT,
    session_label TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    current_step INTEGER NOT NULL DEFAULT 0,
    context_blob TEXT NOT NULL DEFAULT '{}',
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    last_heartbeat TEXT NOT NULL,
    parent_run TEXT,
    item_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_updated ON runs(updated);

CREATE TABLE IF NOT EXISTS steps (
    run_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    output TEXT NOT NULL DEFAULT '',
    started TEXT,
    finished TEXT,
    PRIMARY KEY (run_id, idx),
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provider_model(run: Run) -> str:
    return f"{run.provider}/{run.model}" if run.model else run.provider


# Touch a run's freshness and revive it if the watchdog marked it stalled —
# any step/heartbeat activity proves the agent is back.
_TOUCH_RUN_SQL = (
    "UPDATE runs SET updated=?, last_heartbeat=?, "
    "status=CASE WHEN status='stalled' THEN 'active' ELSE status END WHERE id=?"
)


class RunStore:
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
            c.execute("PRAGMA foreign_keys=ON")
            with c:
                yield c
        finally:
            c.close()

    def _init_db(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA_SQL)
            columns = {row["name"] for row in c.execute("PRAGMA table_info(runs)").fetchall()}
            if "model" not in columns:
                c.execute("ALTER TABLE runs ADD COLUMN model TEXT")

    # --- runs ---

    def create_run(self, payload: RunCreate) -> Run:
        rid = payload.id or uuid.uuid4().hex[:12]
        now = _now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO runs (id, goal, provider, model, session_label, status, current_step, "
                "context_blob, created, updated, last_heartbeat, parent_run, item_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, payload.goal, payload.provider, payload.model, payload.session_label,
                 RunStatus.active.value, 0, json.dumps(payload.context_blob),
                 now, now, now, payload.parent_run, payload.item_id),
            )
        return self.get_run(rid)

    def get_run(self, run_id: str) -> Run:
        with self._conn() as c:
            row = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise RunNotFound(run_id)
            steps = [self._row_to_step(r) for r in
                     c.execute("SELECT * FROM steps WHERE run_id=? ORDER BY idx", (run_id,)).fetchall()]
        return self._row_to_run(row, steps)

    def list_runs(self, status: Optional[str] = None, limit: int = 50,
                  provider: Optional[str] = None, model: Optional[str] = None) -> List[Run]:
        sql = "SELECT * FROM runs"
        clauses, args = [], []
        if status:
            clauses.append("status=?"); args.append(status)
        if provider:
            clauses.append("provider=?"); args.append(provider)
        if model:
            clauses.append("model=?"); args.append(model)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            rows = c.execute(sql, args).fetchall()
            out = []
            for row in rows:
                steps = [self._row_to_step(r) for r in
                         c.execute("SELECT * FROM steps WHERE run_id=? ORDER BY idx", (row["id"],)).fetchall()]
                out.append(self._row_to_run(row, steps))
        return out

    def count_runs(self) -> dict[str, int]:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]
            active = c.execute("SELECT COUNT(*) AS n FROM runs WHERE status=?", (RunStatus.active.value,)).fetchone()["n"]
        return {"total": total, "active": active, "previous": total - active}

    def update_run(self, run_id: str, payload: RunUpdate) -> Run:
        sets, args = [], []
        data = payload.model_dump(exclude_unset=True)
        if "status" in data:
            sets.append("status=?"); args.append(data["status"].value if hasattr(data["status"], "value") else data["status"])
        if "model" in data:
            sets.append("model=?"); args.append(data["model"])
        if "current_step" in data:
            sets.append("current_step=?"); args.append(data["current_step"])
        if "context_blob" in data:
            sets.append("context_blob=?"); args.append(json.dumps(data["context_blob"]))
        if "item_id" in data:
            sets.append("item_id=?"); args.append(data["item_id"])
        if not sets:
            return self.get_run(run_id)
        if "status" not in data:
            # Context/progress writes prove the agent is alive; un-stall it.
            sets.append("status=CASE WHEN status='stalled' THEN 'active' ELSE status END")
        sets.append("updated=?"); args.append(_now())
        args.append(run_id)
        with self._conn() as c:
            cur = c.execute(f"UPDATE runs SET {', '.join(sets)} WHERE id=?", args)
            if cur.rowcount == 0:
                raise RunNotFound(run_id)
        return self.get_run(run_id)

    def heartbeat(self, run_id: str) -> Run:
        now = _now()
        with self._conn() as c:
            cur = c.execute(_TOUCH_RUN_SQL, (now, now, run_id))
            if cur.rowcount == 0:
                raise RunNotFound(run_id)
        return self.get_run(run_id)

    def delete_run(self, run_id: str) -> None:
        with self._conn() as c:
            cur = c.execute("DELETE FROM runs WHERE id=?", (run_id,))
            if cur.rowcount == 0:
                raise RunNotFound(run_id)

    # --- steps ---

    def add_step(self, run_id: str, payload: StepCreate) -> Step:
        with self._conn() as c:
            # BEGIN IMMEDIATE serializes the MAX(idx) read with the insert so
            # concurrent add_step calls can't claim the same idx.
            c.execute("BEGIN IMMEDIATE")
            try:
                row = c.execute("SELECT id FROM runs WHERE id=?", (run_id,)).fetchone()
                if not row:
                    raise RunNotFound(run_id)
                r = c.execute("SELECT COALESCE(MAX(idx)+1, 0) AS next FROM steps WHERE run_id=?", (run_id,)).fetchone()
                idx = r["next"]
                now = _now()
                started = now if payload.status == StepStatus.in_progress else None
                finished = now if payload.status in (StepStatus.done, StepStatus.failed, StepStatus.skipped) else None
                c.execute(
                    "INSERT INTO steps (run_id, idx, title, status, output, started, finished) VALUES (?,?,?,?,?,?,?)",
                    (run_id, idx, payload.title, payload.status.value, payload.output, started, finished),
                )
                c.execute(_TOUCH_RUN_SQL, (now, now, run_id))
                c.execute("COMMIT")
            except BaseException:
                c.execute("ROLLBACK")
                raise
            return self._get_step(c, run_id, idx)

    def update_step(self, run_id: str, idx: int, payload: StepUpdate) -> Step:
        data = payload.model_dump(exclude_unset=True)
        sets, args = [], []
        now = _now()
        if "title" in data:
            sets.append("title=?"); args.append(data["title"])
        if "output" in data:
            sets.append("output=?"); args.append(data["output"])
        if "status" in data:
            new_status = data["status"].value if hasattr(data["status"], "value") else data["status"]
            sets.append("status=?"); args.append(new_status)
            if new_status == StepStatus.in_progress.value:
                sets.append("started=COALESCE(started, ?)"); args.append(now)
            if new_status in (StepStatus.done.value, StepStatus.failed.value, StepStatus.skipped.value):
                sets.append("finished=?"); args.append(now)
        if not sets:
            with self._conn() as c:
                return self._get_step(c, run_id, idx)
        args.extend([run_id, idx])
        with self._conn() as c:
            cur = c.execute(f"UPDATE steps SET {', '.join(sets)} WHERE run_id=? AND idx=?", args)
            if cur.rowcount == 0:
                raise StepNotFound(f"{run_id}:{idx}")
            c.execute(_TOUCH_RUN_SQL, (now, now, run_id))
            return self._get_step(c, run_id, idx)

    # --- helpers ---

    def _get_step(self, c: sqlite3.Connection, run_id: str, idx: int) -> Step:
        row = c.execute("SELECT * FROM steps WHERE run_id=? AND idx=?", (run_id, idx)).fetchone()
        if not row:
            raise StepNotFound(f"{run_id}:{idx}")
        return self._row_to_step(row)

    @staticmethod
    def _row_to_step(row: sqlite3.Row) -> Step:
        return Step(idx=row["idx"], title=row["title"], status=row["status"],
                    output=row["output"], started=row["started"], finished=row["finished"])

    @staticmethod
    def _row_to_run(row: sqlite3.Row, steps: List[Step]) -> Run:
        return Run(
            id=row["id"], goal=row["goal"], provider=row["provider"], model=row["model"],
            session_label=row["session_label"], status=row["status"],
            current_step=row["current_step"],
            context_blob=json.loads(row["context_blob"] or "{}"),
            steps=steps, created=row["created"], updated=row["updated"],
            last_heartbeat=row["last_heartbeat"],
            parent_run=row["parent_run"], item_id=row["item_id"],
        )

    def build_resume_prompt(self, run_id: str) -> str:
        run = self.get_run(run_id)
        lines = [
            f"# Resume run {run.id}",
            f"**Goal:** {run.goal}",
            f"**Status:** {run.status.value}  •  **Provider/model was:** {_provider_model(run)}",
            f"**Last heartbeat:** {run.last_heartbeat}",
            "",
            "## Steps",
        ]
        for s in run.steps:
            mark = {"done": "[x]", "in_progress": "[~]", "failed": "[!]",
                    "skipped": "[-]", "pending": "[ ]"}[s.status.value]
            lines.append(f"- {mark} ({s.idx}) {s.title}")
            if s.output and s.status.value in ("done", "failed"):
                lines.append(f"      → {s.output[:200]}")
        lines += ["", "## Resume context", "```json",
                  json.dumps(run.context_blob, indent=2), "```", "",
                  f"Continue this run by calling `dashboard.update_step` on run `{run.id}` "
                  f"starting at step {run.current_step}. Save progress with `save_context`."]
        return "\n".join(lines)
