from contextlib import contextmanager
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .models_forge import (
    ForgeAgent,
    ForgeApproval,
    ForgeApprovalCreate,
    ForgeApprovalUpdate,
    ForgeEvent,
    ForgeEventCreate,
    ForgeJob,
    ForgeJobCreate,
    ForgeRunnerClaim,
    ForgeRunnerJobUpdate,
    ForgeRunnerRecover,
    ForgeRunnerRecoverResult,
    ForgeJobStatus,
    ForgeJobUpdate,
)


class ForgeJobNotFound(Exception): ...
class ForgeApprovalNotFound(Exception): ...
class ForgeApprovalConflict(Exception): ...


AGENTS = [
    ForgeAgent(
        name="claude",
        role="orchestrator",
        label="Claude",
        description="Routes work, decomposes jobs, and manages approval flow.",
        color="#d97757",
        default_for=["auto", "planning", "coordination"],
    ),
    ForgeAgent(
        name="codex",
        role="worker",
        label="Codex",
        description="Primary repo, terminal, and implementation worker.",
        color="#10a37f",
        default_for=["code", "tests", "shell"],
    ),
    ForgeAgent(
        name="codex-xhigh",
        role="reviewer",
        label="Codex xhigh",
        description="Top reviewer for risky autonomous approvals and orchestration checks.",
        color="#38bdf8",
        default_for=["review", "approval", "risk"],
    ),
    ForgeAgent(
        name="hermes",
        role="homelab",
        label="Hermes",
        description="Local homelab context, scripts, wiki, and dashboard-aware helper.",
        color="#7c5cff",
        default_for=["homelab", "memory", "local"],
    ),
    ForgeAgent(
        name="kimi",
        role="specialist",
        label="Kimi",
        description="Optional specialist or fallback agent.",
        color="#f59e0b",
        default_for=["fallback"],
    ),
]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS forge_jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    mode TEXT NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    selected_agent TEXT NOT NULL,
    cwd TEXT NOT NULL,
    autonomy TEXT NOT NULL,
    dashboard_run_id TEXT,
    runner_id TEXT,
    runner_pid INTEGER,
    runner_session_id TEXT,
    runner_started TEXT,
    runner_ended TEXT,
    runner_log_path TEXT,
    runner_error TEXT,
    runner_heartbeat TEXT,
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_forge_jobs_updated ON forge_jobs(updated);
CREATE INDEX IF NOT EXISTS idx_forge_jobs_status ON forge_jobs(status);

CREATE TABLE IF NOT EXISTS forge_events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    actor TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (job_id) REFERENCES forge_jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_forge_events_job_ts ON forge_events(job_id, ts);

CREATE TABLE IF NOT EXISTS forge_approvals (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    action TEXT NOT NULL,
    risk TEXT NOT NULL,
    authority TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    rollback TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    reviewer TEXT,
    note TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES forge_jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_forge_approvals_job ON forge_approvals(job_id);
CREATE INDEX IF NOT EXISTS idx_forge_approvals_status ON forge_approvals(status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _title(prompt: str) -> str:
    line = " ".join(prompt.strip().split())
    return line[:80] if line else "Untitled Forge job"


class ForgeStore:
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
            self._migrate_jobs_schema(c)

    def _migrate_jobs_schema(self, c: sqlite3.Connection) -> None:
        existing = {row["name"] for row in c.execute("PRAGMA table_info(forge_jobs)").fetchall()}
        columns = {
            "runner_pid": "INTEGER",
            "runner_id": "TEXT",
            "runner_session_id": "TEXT",
            "runner_started": "TEXT",
            "runner_ended": "TEXT",
            "runner_log_path": "TEXT",
            "runner_error": "TEXT",
            "runner_heartbeat": "TEXT",
        }
        for name, ddl in columns.items():
            if name not in existing:
                c.execute(f"ALTER TABLE forge_jobs ADD COLUMN {name} {ddl}")

    def list_agents(self) -> List[ForgeAgent]:
        return AGENTS

    def create_job(self, payload: ForgeJobCreate, dashboard_run_id: Optional[str] = None) -> ForgeJob:
        jid = uuid.uuid4().hex[:12]
        now = _now()
        selected = payload.selected_agent or ("claude" if payload.mode.value == "auto" else "codex")
        with self._conn() as c:
            c.execute(
                "INSERT INTO forge_jobs "
                "(id,title,prompt,mode,job_type,status,selected_agent,cwd,autonomy,dashboard_run_id,created,updated) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    jid,
                    _title(payload.prompt),
                    payload.prompt,
                    payload.mode.value,
                    payload.job_type.value,
                    ForgeJobStatus.queued.value,
                    selected,
                    payload.cwd,
                    payload.autonomy.value,
                    dashboard_run_id,
                    now,
                    now,
                ),
            )
            self._insert_event(
                c,
                jid,
                ForgeEventCreate(
                    kind="job_created",
                    actor="forge",
                    body=f"Queued for {selected}.",
                    payload={"mode": payload.mode.value, "job_type": payload.job_type.value},
                ),
            )
        return self.get_job(jid)

    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> List[ForgeJob]:
        sql = "SELECT * FROM forge_jobs"
        args: list[object] = []
        if status:
            sql += " WHERE status=?"
            args.append(status)
        sql += " ORDER BY updated DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            rows = c.execute(sql, args).fetchall()
        return [self._row_to_job(row) for row in rows]

    def get_job(self, job_id: str) -> ForgeJob:
        with self._conn() as c:
            row = c.execute("SELECT * FROM forge_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise ForgeJobNotFound(job_id)
        return self._row_to_job(row)

    def update_job(self, job_id: str, payload: ForgeJobUpdate) -> ForgeJob:
        data = payload.model_dump(exclude_unset=True)
        if not data:
            return self.get_job(job_id)
        sets, args = [], []
        for key, value in data.items():
            sets.append(f"{key}=?")
            args.append(value.value if hasattr(value, "value") else value)
        sets.append("updated=?")
        args.append(_now())
        args.append(job_id)
        with self._conn() as c:
            cur = c.execute(f"UPDATE forge_jobs SET {', '.join(sets)} WHERE id=?", args)
            if cur.rowcount == 0:
                raise ForgeJobNotFound(job_id)
            self._insert_event(
                c,
                job_id,
                ForgeEventCreate(kind="status", actor="forge", body="Job updated.", payload=data),
            )
        return self.get_job(job_id)

    def claim_next_job(self, payload: ForgeRunnerClaim) -> Optional[ForgeJob]:
        now = _now()
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                sql = "SELECT id FROM forge_jobs WHERE status=?"
                args: list[object] = [ForgeJobStatus.queued.value]
                if payload.supported_agents:
                    placeholders = ",".join("?" for _ in payload.supported_agents)
                    sql += f" AND selected_agent IN ({placeholders})"
                    args.extend(payload.supported_agents)
                if payload.job_types:
                    placeholders = ",".join("?" for _ in payload.job_types)
                    sql += f" AND job_type IN ({placeholders})"
                    args.extend(item.value if hasattr(item, "value") else item for item in payload.job_types)
                sql += " ORDER BY created ASC LIMIT 1"
                row = c.execute(sql, args).fetchone()
                if not row:
                    c.execute("COMMIT")
                    return None
                job_id = row["id"]
                c.execute(
                    "UPDATE forge_jobs SET status=?, runner_id=?, runner_session_id=?, runner_started=?, "
                    "runner_heartbeat=?, updated=? WHERE id=? AND status=?",
                    (
                        ForgeJobStatus.waiting.value,
                        payload.runner_id,
                        payload.runner_id,
                        now,
                        now,
                        now,
                        job_id,
                        ForgeJobStatus.queued.value,
                    ),
                )
                self._insert_event(
                    c,
                    job_id,
                    ForgeEventCreate(
                        kind="status",
                        actor="forge-runner",
                        body=f"Runner {payload.runner_id} claimed job.",
                        payload={"status": ForgeJobStatus.waiting.value, "runner_id": payload.runner_id},
                    ),
                )
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
        return self.get_job(job_id)

    def recover_stale_jobs(self, payload: ForgeRunnerRecover) -> ForgeRunnerRecoverResult:
        cutoff = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - payload.stale_after_seconds, timezone.utc).isoformat()
        now = _now()
        statuses = (ForgeJobStatus.running.value, ForgeJobStatus.waiting.value)
        with self._conn() as c:
            rows = c.execute(self._stale_jobs_sql(), (payload.runner_id, statuses[0], statuses[1], cutoff)).fetchall()
            for row in rows:
                job_id = row["id"]
                c.execute(
                    "UPDATE forge_jobs SET status=?, runner_id=NULL, runner_pid=NULL, runner_session_id=NULL, "
                    "runner_started=NULL, runner_ended=NULL, runner_error=?, runner_heartbeat=NULL, updated=? "
                    "WHERE id=?",
                    (ForgeJobStatus.queued.value, "stale runner recovered", now, job_id),
                )
                self._insert_event(
                    c,
                    job_id,
                    ForgeEventCreate(
                        kind="status",
                        actor="forge-runner",
                        body=f"Recovered stale runner {payload.runner_id}; re-queued job.",
                        payload={"recovered": True, "runner_id": payload.runner_id},
                    ),
                )
        return ForgeRunnerRecoverResult(recovered=len(rows))

    def list_stale_job_ids(self, payload: ForgeRunnerRecover) -> List[str]:
        cutoff = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - payload.stale_after_seconds, timezone.utc).isoformat()
        statuses = (ForgeJobStatus.running.value, ForgeJobStatus.waiting.value)
        with self._conn() as c:
            rows = c.execute(self._stale_jobs_sql(), (payload.runner_id, statuses[0], statuses[1], cutoff)).fetchall()
        return [row["id"] for row in rows]

    @staticmethod
    def _stale_jobs_sql() -> str:
        return (
            "SELECT id FROM forge_jobs WHERE runner_id=? AND status IN (?,?) "
            "AND (runner_heartbeat IS NULL OR runner_heartbeat < ?)"
        )

    def update_runner_job(self, job_id: str, payload: ForgeRunnerJobUpdate) -> ForgeJob:
        data = payload.model_dump(exclude_unset=True)
        heartbeat = bool(data.pop("runner_heartbeat", False))
        sets, args = [], []
        status = data.get("status")
        for key, value in data.items():
            sets.append(f"{key}=?")
            args.append(value.value if hasattr(value, "value") else value)
        now = _now()
        if heartbeat:
            sets.append("runner_heartbeat=?")
            args.append(now)
        if status in {ForgeJobStatus.completed, ForgeJobStatus.failed, ForgeJobStatus.cancelled}:
            sets.append("runner_ended=?")
            args.append(now)
        if not sets:
            return self.get_job(job_id)
        sets.append("updated=?")
        args.append(now)
        args.append(job_id)
        with self._conn() as c:
            cur = c.execute(f"UPDATE forge_jobs SET {', '.join(sets)} WHERE id=?", args)
            if cur.rowcount == 0:
                raise ForgeJobNotFound(job_id)
            event_payload = {key: (value.value if hasattr(value, "value") else value) for key, value in data.items()}
            if heartbeat:
                event_payload["runner_heartbeat"] = now
            self._insert_event(
                c,
                job_id,
                ForgeEventCreate(
                    kind="status",
                    actor="forge-runner",
                    body="Runner updated job.",
                    payload=event_payload,
                ),
            )
        return self.get_job(job_id)

    def stop_job(self, job_id: str) -> ForgeJob:
        with self._conn() as c:
            row = c.execute("SELECT status FROM forge_jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise ForgeJobNotFound(job_id)
            if row["status"] in {ForgeJobStatus.completed.value, ForgeJobStatus.failed.value}:
                return self.get_job(job_id)
            if row["status"] != ForgeJobStatus.cancelled.value:
                c.execute(
                    "UPDATE forge_jobs SET status=?, runner_error=?, updated=? WHERE id=?",
                    (ForgeJobStatus.cancelled.value, "stop requested", _now(), job_id),
                )
            self._insert_event(
                c,
                job_id,
                ForgeEventCreate(
                    kind="status",
                    actor="forge",
                    body="Graceful stop requested.",
                    payload={"status": ForgeJobStatus.cancelled.value},
                ),
            )
        return self.get_job(job_id)

    def delete_job(self, job_id: str) -> None:
        with self._conn() as c:
            cur = c.execute("DELETE FROM forge_jobs WHERE id=?", (job_id,))
            if cur.rowcount == 0:
                raise ForgeJobNotFound(job_id)

    def list_events(self, job_id: str) -> List[ForgeEvent]:
        self.get_job(job_id)
        with self._conn() as c:
            rows = c.execute("SELECT * FROM forge_events WHERE job_id=? ORDER BY ts ASC", (job_id,)).fetchall()
        return [self._row_to_event(row) for row in rows]

    def add_event(self, job_id: str, payload: ForgeEventCreate) -> ForgeEvent:
        self.get_job(job_id)
        with self._conn() as c:
            event = self._insert_event(c, job_id, payload)
            c.execute("UPDATE forge_jobs SET updated=? WHERE id=?", (_now(), job_id))
        return event

    def create_approval(self, job_id: str, payload: ForgeApprovalCreate) -> ForgeApproval:
        self.get_job(job_id)
        aid = uuid.uuid4().hex[:12]
        now = _now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO forge_approvals "
                "(id,job_id,action,risk,authority,target,rollback,status,reviewer,note,created,updated) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    aid,
                    job_id,
                    payload.action,
                    payload.risk.value,
                    payload.authority.value,
                    payload.target,
                    payload.rollback,
                    "pending",
                    None,
                    "",
                    now,
                    now,
                ),
            )
            self._insert_event(
                c,
                job_id,
                ForgeEventCreate(
                    kind="approval_requested",
                    actor="forge",
                    body=payload.action,
                    payload={"approval_id": aid, "risk": payload.risk.value, "authority": payload.authority.value},
                ),
            )
        return self.get_approval(aid)

    def get_approval(self, approval_id: str) -> ForgeApproval:
        with self._conn() as c:
            row = c.execute("SELECT * FROM forge_approvals WHERE id=?", (approval_id,)).fetchone()
        if not row:
            raise ForgeApprovalNotFound(approval_id)
        return self._row_to_approval(row)

    def list_approvals(self, job_id: str) -> List[ForgeApproval]:
        self.get_job(job_id)
        with self._conn() as c:
            rows = c.execute("SELECT * FROM forge_approvals WHERE job_id=? ORDER BY created ASC", (job_id,)).fetchall()
        return [self._row_to_approval(row) for row in rows]

    def update_approval(self, approval_id: str, payload: ForgeApprovalUpdate) -> ForgeApproval:
        now = _now()
        with self._conn() as c:
            row = c.execute("SELECT * FROM forge_approvals WHERE id=?", (approval_id,)).fetchone()
            if not row:
                raise ForgeApprovalNotFound(approval_id)
            if row["status"] != "pending":
                raise ForgeApprovalConflict("approval already resolved")
            if payload.status.value == "approved" and (
                row["risk"] == "hard_stop" or row["authority"] == "blocked"
            ):
                raise ForgeApprovalConflict("hard-stop approval cannot be approved")
            c.execute(
                "UPDATE forge_approvals SET status=?, reviewer=?, note=?, updated=? WHERE id=?",
                (payload.status.value, payload.reviewer, payload.note, now, approval_id),
            )
            if payload.status.value in {"denied", "cancelled"}:
                c.execute(
                    "UPDATE forge_jobs SET status=?, updated=? WHERE id=?",
                    (ForgeJobStatus.cancelled.value, now, row["job_id"]),
                )
            self._insert_event(
                c,
                row["job_id"],
                ForgeEventCreate(
                    kind="approval_resolved",
                    actor=payload.reviewer or "forge",
                    body=f"Request {payload.status.value}: {approval_id}",
                    payload={"approval_id": approval_id, "status": payload.status.value, "note": payload.note},
                ),
            )
        return self.get_approval(approval_id)

    def _insert_event(self, c: sqlite3.Connection, job_id: str, payload: ForgeEventCreate) -> ForgeEvent:
        eid = uuid.uuid4().hex[:12]
        ts = _now()
        c.execute(
            "INSERT INTO forge_events (id,job_id,ts,kind,actor,body,payload) VALUES (?,?,?,?,?,?,?)",
            (eid, job_id, ts, payload.kind.value, payload.actor, payload.body, json.dumps(payload.payload)),
        )
        return ForgeEvent(id=eid, job_id=job_id, ts=ts, **payload.model_dump())

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> ForgeJob:
        return ForgeJob(**dict(row))

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> ForgeEvent:
        data = dict(row)
        data["payload"] = json.loads(data["payload"] or "{}")
        return ForgeEvent(**data)

    @staticmethod
    def _row_to_approval(row: sqlite3.Row) -> ForgeApproval:
        return ForgeApproval(**dict(row))
