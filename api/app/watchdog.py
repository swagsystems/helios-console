"""Periodic sweep that ages out runs whose agent stopped updating them.

Three-stage decay so brief stalls aren't punished but truly forgotten
runs are auto-closed without manual cleanup:

  active   →  stalled    when last_heartbeat is older than STALL_AFTER
  stalled  →  abandoned  when last_heartbeat is older than ABANDON_AFTER

A run with zero steps gets a much shorter stall window because it
indicates the agent opened a run and immediately moved on without
adding work — almost always the orphan case.
"""
from __future__ import annotations
import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("dashboard.watchdog")

STALL_AFTER = timedelta(minutes=int(os.environ.get("RUNS_STALL_MIN", "30")))
STALL_AFTER_NOSTEPS = timedelta(minutes=int(os.environ.get("RUNS_STALL_NOSTEPS_MIN", "10")))
ABANDON_AFTER = timedelta(hours=int(os.environ.get("RUNS_ABANDON_HRS", "24")))
SWEEP_INTERVAL = int(os.environ.get("RUNS_SWEEP_SEC", "60"))


def _db_path() -> Path:
    return Path(os.environ.get("DASHBOARD_DATA_DIR", "/opt/dashboard/data")) / "runs.db"


def sweep_once() -> dict:
    """Run one sweep pass. Returns counts of state transitions."""
    p = _db_path()
    if not p.exists():
        return {"stalled": 0, "abandoned": 0}
    now = datetime.now(timezone.utc)
    stall_cutoff = (now - STALL_AFTER).isoformat()
    stall_cutoff_nosteps = (now - STALL_AFTER_NOSTEPS).isoformat()
    abandon_cutoff = (now - ABANDON_AFTER).isoformat()

    with sqlite3.connect(p, isolation_level=None, timeout=10.0) as c:
        c.row_factory = sqlite3.Row
        cur = c.execute("""
            UPDATE runs SET status='stalled', updated=?
             WHERE status='active'
               AND last_heartbeat < ?
               AND id IN (SELECT run_id FROM steps GROUP BY run_id)
        """, (now.isoformat(), stall_cutoff))
        stalled_with = cur.rowcount or 0
        cur = c.execute("""
            UPDATE runs SET status='stalled', updated=?
             WHERE status='active'
               AND last_heartbeat < ?
               AND id NOT IN (SELECT run_id FROM steps)
        """, (now.isoformat(), stall_cutoff_nosteps))
        stalled_without = cur.rowcount or 0
        cur = c.execute("""
            UPDATE runs SET status='abandoned', updated=?
             WHERE status='stalled'
               AND last_heartbeat < ?
        """, (now.isoformat(), abandon_cutoff))
        abandoned = cur.rowcount or 0

    out = {"stalled": stalled_with + stalled_without, "abandoned": abandoned}
    if out["stalled"] or out["abandoned"]:
        log.info("watchdog swept: %s", out)
    return out


async def watchdog_loop() -> None:
    while True:
        try:
            sweep_once()
        except Exception as e:  # never let the loop die
            log.warning("watchdog error: %s", e)
        await asyncio.sleep(SWEEP_INTERVAL)
