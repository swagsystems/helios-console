# Helios Console

Helios Console is a self-hosted dashboard for tasks and service inventory. It keeps durable items in JSON and records execution runs in SQLite. A browser UI and authenticated REST/MCP endpoints work with the same data.

I built it to keep track of work on my homelab. The public edition includes an empty local setup and synthetic inventory; live service addresses and operational records are excluded.

## How it works

Items represent tasks, objectives, notes, issues, or guardrails. Runs hold steps and progress updates, with a watchdog that marks inactive work as stalled. Inventory views read local JSON snapshots.

The API is written in Python with FastAPI. The frontend uses JavaScript modules served by Nginx. Browser login exchanges an API token for an HttpOnly session cookie. Authentik integration is optional and requires your own configuration.

The Forge view retains the job and approval records used by the original project. This edition does not ship or start a host execution runner; queued jobs need an external integration to execute.

## Local setup

Requires Python 3 and Docker Compose.

```bash
git clone https://github.com/swagsystems/helios-console.git
cd helios-console
python3 scripts/init_demo.py
docker compose up --build
```

Open `http://localhost:8390` and sign in with the token stored in `.env`. The setup script creates local files without replacing existing state. Only the web service publishes a port, bound to loopback.

Local `data/` contains item and database state. `llm/` holds generated context output. Both directories are ignored by Git. The sample inventory is empty; this edition does not connect to a hypervisor or discover services automatically. The legacy refresh endpoint requires a separately supplied collector.

## Tests

```bash
cd api
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest -q
cd ..
node --test js/modules/runs.test.mjs
```

Tests cover item persistence, API authentication, execution records, and MCP responses. The browser session store is in memory, so an API restart signs users out. All token holders share administrative access; this is intended for trusted operators.

## License

[MIT](LICENSE). Local agent instructions, private inventory, and historical work plans are excluded from this edition.
