"""Outbound fanout: per-recipient inbound webhooks + broadcast urls.

Telegram is no longer mirrored from here — the userbot bridge owns Telegram I/O
and is registered as a broadcast url.

Security: does NOT forward the master DASHBOARD_TOKEN to listeners.
Listeners that need auth should use their own scoped tokens.
"""

import logging
import os
from typing import Iterable

from .models_messages import AgentMessage
from .store_messages import MessageStore

log = logging.getLogger("dashboard.fanout")


def _broadcast_urls() -> list[str]:
    raw = os.environ.get("DASHBOARD_BROADCAST_URLS", "")
    return [u.strip() for u in raw.split(",") if u.strip()]


def _listener_token(url: str) -> str:
    """Look up a scoped token for a specific listener URL.
    Set via DASHBOARD_LISTENER_TOKENS: url1=token1,url2=token2
    Returns empty string if no token is configured for this URL."""
    raw = os.environ.get("DASHBOARD_LISTENER_TOKENS", "")
    if not raw:
        return ""
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        if k.strip() == url:
            return v.strip()
    return ""


def fanout(msg: AgentMessage, store: MessageStore) -> None:
    try:
        import httpx
    except Exception:
        log.warning("httpx unavailable; skipping fanout for %s", msg.id)
        return

    payload = msg.model_dump()
    # Never forward the master DASHBOARD_TOKEN — each listener gets its own scoped token if configured
    base_headers = {"Content-Type": "application/json"}

    with httpx.Client(timeout=5.0) as client:
        # Per-recipient direct delivery
        for recipient in msg.recipients:
            agent = store.get_agent(recipient)
            if not agent or not agent.inbound_url:
                continue
            headers = dict(base_headers)
            token = _listener_token(agent.inbound_url)
            if token:
                headers["Authorization"] = f"Bearer {token}"
            try:
                client.post(agent.inbound_url, json=payload, headers=headers)
            except Exception as exc:
                log.warning("inbound webhook %s failed: %s", recipient, exc)

        # Broadcast delivery
        for url in _broadcast_urls():
            headers = dict(base_headers)
            token = _listener_token(url)
            if token:
                headers["Authorization"] = f"Bearer {token}"
            try:
                client.post(url, json=payload, headers=headers)
            except Exception as exc:
                log.warning("broadcast url %s failed: %s", url, exc)
