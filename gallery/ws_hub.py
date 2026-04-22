"""WebSocket fan-out hub for live gallery updates (TASKS T18).

SPEC §7.9 wire envelope: ``{"type": <string>, "data": <object>, "ts": <epoch_ms>}``.

``broadcast`` is **fire-and-forget** (ARCHITECTURE §4.4): safe to call from
async request handlers via ``create_task``, and thread-safe when the aiohttp
event loop has been captured (first successful WS ``prepare``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from concurrent.futures import Future as CFuture
from typing import Any, Dict, Optional, Set

from aiohttp import web

logger = logging.getLogger("xyz.gallery.ws_hub")

# ---- event type constants (TASKS T18; data shapes filled by later tasks) ---

IMAGE_UPSERTED = "image.upserted"
IMAGE_UPDATED = "image.updated"
IMAGE_DELETED = "image.deleted"
FOLDER_CHANGED = "folder.changed"
INDEX_PROGRESS = "index.progress"
VOCAB_CHANGED = "vocab.changed"
IMAGE_SYNC_STATUS_CHANGED = "image.sync_status_changed"
BULK_PROGRESS = "bulk.progress"
BULK_COMPLETED = "bulk.completed"
INDEX_DRIFT_DETECTED = "index.drift_detected"

__all__ = [
    "IMAGE_UPSERTED",
    "IMAGE_UPDATED",
    "IMAGE_DELETED",
    "FOLDER_CHANGED",
    "INDEX_PROGRESS",
    "VOCAB_CHANGED",
    "IMAGE_SYNC_STATUS_CHANGED",
    "BULK_PROGRESS",
    "BULK_COMPLETED",
    "INDEX_DRIFT_DETECTED",
    "get_last_event_ts",
    "broadcast",
    "broadcast_await",
    "reset_clients",
    "add_client",
    "remove_client",
]

_clients_lock = threading.Lock()
_clients: Set[web.WebSocketResponse] = set()
_event_loop: Optional[asyncio.AbstractEventLoop] = None
_last_event_ms: int = 0


def reset_clients() -> None:
    """Clear connection registry (offline tests only)."""
    global _event_loop, _last_event_ms
    with _clients_lock:
        _clients.clear()
    _event_loop = None
    _last_event_ms = 0


async def add_client(ws: web.WebSocketResponse) -> None:
    global _event_loop
    if _event_loop is None:
        _event_loop = asyncio.get_running_loop()
    with _clients_lock:
        _clients.add(ws)


async def remove_client(ws: web.WebSocketResponse) -> None:
    with _clients_lock:
        _clients.discard(ws)


def _envelope(event_type: str, data: Dict[str, Any]) -> str:
    global _last_event_ms
    ts = int(time.time() * 1000)
    _last_event_ms = ts
    payload = {
        "type": event_type,
        "data": data,
        "ts": ts,
    }
    return json.dumps(payload, separators=(",", ":"))


def get_last_event_ts() -> int:
    """Monotonic last broadcast time (ms), for ``GET /index/status`` (T22)."""
    return int(_last_event_ms)


async def _broadcast_coro(event_type: str, data: Dict[str, Any]) -> None:
    text = _envelope(event_type, data)
    with _clients_lock:
        targets = list(_clients)
    dead: list[web.WebSocketResponse] = []
    for ws in targets:
        if ws.closed:
            dead.append(ws)
            continue
        try:
            await ws.send_str(text)
        except Exception:
            logger.debug("ws send failed; dropping socket", exc_info=True)
            dead.append(ws)
    if dead:
        with _clients_lock:
            for ws in dead:
                _clients.discard(ws)


def _schedule_broadcast(event_type: str, data: Dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = _event_loop
        if loop is None:
            logger.debug("ws broadcast skipped (no event loop yet)")
            return

        def _log_exc(fut: CFuture[Any]) -> None:
            exc = fut.exception()
            if exc:
                logger.warning("ws broadcast task failed: %s", exc)

        fut = asyncio.run_coroutine_threadsafe(
            _broadcast_coro(event_type, data), loop)
        fut.add_done_callback(_log_exc)
        return

    task = loop.create_task(_broadcast_coro(event_type, data))

    def _done(t: asyncio.Task[Any]) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.warning("ws broadcast task failed: %s", exc)

    task.add_done_callback(_done)


def broadcast(event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
    """Fan-out one event to every connected tab (thread-safe).

    Must not block the event loop for heavy work — this only schedules
    JSON sends. Callers that already sit on the loop get a background
    ``Task``; worker threads use ``run_coroutine_threadsafe`` once
    ``_event_loop`` has been captured by the first WS handshake.
    """
    _schedule_broadcast(event_type, dict(data) if data else {})


async def broadcast_await(
        event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
    """Same fan-out as ``broadcast`` but awaitable (strict ordering for tests)."""
    await _broadcast_coro(event_type, dict(data) if data else {})
