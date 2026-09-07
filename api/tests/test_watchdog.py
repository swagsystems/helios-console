import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def runs_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RUNS_STALL_MIN", "30")
    monkeypatch.setenv("RUNS_STALL_NOSTEPS_MIN", "10")
    monkeypatch.setenv("RUNS_ABANDON_HRS", "24")
    # init schema via store
    from app.store_runs import RunStore
    RunStore(tmp_path / "runs.db")
    return tmp_path / "runs.db"


def _insert(db, run_id, status, hb_minutes_ago, with_steps=False):
    now = datetime.now(timezone.utc)
    hb = (now - timedelta(minutes=hb_minutes_ago)).isoformat()
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO runs (id,goal,provider,status,current_step,context_blob,created,updated,last_heartbeat) "
                  "VALUES (?,?,?,?,?,?,?,?,?)",
                  (run_id, "g", "p", status, 0, "{}", now.isoformat(), now.isoformat(), hb))
        if with_steps:
            c.execute("INSERT INTO steps (run_id,idx,title,status,output) VALUES (?,?,?,?,?)",
                      (run_id, 0, "s", "in_progress", ""))


def _status(db, run_id):
    with sqlite3.connect(db) as c:
        return c.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()[0]


def test_active_with_steps_stays_until_30m(runs_db):
    # reload module to pick up env
    import importlib
    from app import watchdog
    importlib.reload(watchdog)

    _insert(runs_db, "fresh", "active", 5, with_steps=True)
    _insert(runs_db, "stale", "active", 31, with_steps=True)
    out = watchdog.sweep_once()
    assert out["stalled"] == 1
    assert _status(runs_db, "fresh") == "active"
    assert _status(runs_db, "stale") == "stalled"


def test_active_no_steps_stalls_at_10m(runs_db):
    import importlib
    from app import watchdog
    importlib.reload(watchdog)

    _insert(runs_db, "young", "active", 5, with_steps=False)
    _insert(runs_db, "old",   "active", 11, with_steps=False)
    out = watchdog.sweep_once()
    assert out["stalled"] == 1
    assert _status(runs_db, "young") == "active"
    assert _status(runs_db, "old") == "stalled"


def test_stalled_abandoned_after_24h(runs_db):
    import importlib
    from app import watchdog
    importlib.reload(watchdog)

    _insert(runs_db, "recent_stall", "stalled", 60)
    _insert(runs_db, "ancient", "stalled", 60 * 25)
    out = watchdog.sweep_once()
    assert out["abandoned"] == 1
    assert _status(runs_db, "recent_stall") == "stalled"
    assert _status(runs_db, "ancient") == "abandoned"


def test_completed_runs_untouched(runs_db):
    import importlib
    from app import watchdog
    importlib.reload(watchdog)

    _insert(runs_db, "done", "completed", 60 * 48)
    out = watchdog.sweep_once()
    assert out == {"stalled": 0, "abandoned": 0}
    assert _status(runs_db, "done") == "completed"
