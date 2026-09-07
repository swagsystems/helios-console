import os
import tempfile
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    (tmp_path / "llm").mkdir()
    monkeypatch.setenv("DASHBOARD_DATA_DIR", str(d))
    monkeypatch.setenv("DASHBOARD_LLM_DIR", str(tmp_path / "llm"))
    monkeypatch.setenv("DASHBOARD_TOKEN", "testtoken")
    return d

@pytest.fixture
def client(data_dir):
    from app.main import app
    return TestClient(app)
