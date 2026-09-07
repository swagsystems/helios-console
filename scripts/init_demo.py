"""Create local demo state without overwriting existing files."""
import json
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]

def write_new(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x") as stream:
            stream.write(content)
        path.chmod(0o600)
    except FileExistsError:
        pass

write_new(root / ".env", "DASHBOARD_TOKEN=" + secrets.token_urlsafe(32) + "\n")
write_new(root / "data/items.json", json.dumps({"_meta": {"schema": 2, "updated": "2026-01-01T00:00:00Z"}, "items": []}))
for name, value in {"system.json": {"host": {"name": "demo-host"}, "storage": [], "network": {}}, "services.json": {"lxc": [], "docker": [], "domains": []}, "cron.json": {"jobs": []}}.items():
    write_new(root / "data" / name, json.dumps(value))
(root / "llm").mkdir(exist_ok=True)
print("Local configuration is ready. The login token is in .env.")
