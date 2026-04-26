"""Process-wide active Job registry (TASKS T44, SPEC §12.4 FR-Prog-4, §7.9).

`GET /xyz/gallery/jobs/active` reads the in-memory `running` / `queued` set only.
``bulk.*`` events carry ``job_id`` = ``bulk_id`` / ``plan_id``; index scans use
UUID job_ids with ``kind="index"``.  ``index`` and ``bulk`` 用 ``phase`` 分阶段。

Thread-safe: bulk / indexer / 后台 ``Thread`` 并发更新。
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

__all__ = [
    "sync_bulk_payload",
    "finish_bulk",
    "list_active",
    "reset_for_test",
    "start_index_job",
    "emit_index_progress",
    "emit_index_done",
    "new_job_id",
    "start_generic_job",
    "emit_job_progress",
    "emit_job_done",
]

_lock = threading.RLock()
# job_id -> summary row
_active: Dict[str, Dict[str, Any]] = {}


def new_job_id() -> str:
    return str(uuid.uuid4())


def _now_ms() -> int:
    return int(time.time() * 1000)


def reset_for_test() -> None:
    """Test-only: clear the registry (offline tests)."""
    with _lock:
        _active.clear()


def _upsert(jid: str, row: Dict[str, Any]) -> None:
    with _lock:
        cur = _active.get(jid, {})
        cur.update(row)
        cur["job_id"] = jid
        _active[jid] = cur


def _remove(jid: str) -> None:
    with _lock:
        _active.pop(jid, None)


def list_active() -> List[dict]:
    """``running`` / ``queued`` entries only (``terminal`` removed on completion)."""
    with _lock:
        return [dict(v) for v in _active.values()]


def sync_bulk_payload(data: dict) -> dict:
    """Ensure ``job_id`` + registry row for a ``bulk.*`` / ``BULK_*`` *progress* shape."""
    d = dict(data)
    bid = d.get("bulk_id") or d.get("plan_id")
    if bid is None:
        return d
    jid = str(bid)
    d["job_id"] = jid
    raw_t = d.get("total")
    try:
        t = int(raw_t) if raw_t is not None else 0
    except (TypeError, ValueError):
        t = 0
    _upsert(
        jid,
        {
            "status": "running",
            "kind": str(d.get("kind", "bulk")),
            "job_id": jid,
            "done": int(d.get("done", 0) or 0),
            "total": t,
            "phase": str(d.get("phase", "execute")),
            "plan_id": d.get("plan_id") or jid,
            "bulk_id": d.get("bulk_id") or jid,
            "updated_ms": _now_ms(),
        },
    )
    return d


def finish_bulk(data: dict) -> None:
    """After ``bulk.completed`` WS: drop registry entry."""
    d = dict(data) if data else {}
    bid = d.get("bulk_id") or d.get("plan_id")
    if bid is None:
        return
    _remove(str(bid))


# --- index / rescan (INDEX_PROGRESS in §7.9) ---------------------------------


def start_index_job(
    job_id: str, *, kind: str, root_id: int, phase: str, message: str = "",
    total: int = 0,
) -> None:
    """Register an index / delta / cold run before first ``index.progress``."""
    _upsert(
        job_id,
        {
            "status": "running",
            "kind": str(kind),
            "job_id": str(job_id),
            "root_id": int(root_id),
            "phase": str(phase),
            "done": 0,
            "total": int(total) if total else 0,
            "message": (message or "")[:512],
            "updated_ms": _now_ms(),
        },
    )


def start_generic_job(
    job_id: str, *, kind: str, done: int = 0, total: int = 0,
    phase: str = "", message: str = "",
) -> None:
    _upsert(
        job_id,
        {
            "status": "running",
            "kind": str(kind),
            "job_id": str(job_id),
            "done": int(done),
            "total": int(total) if total else 0,
            "phase": str(phase),
            "message": (message or "")[:512],
            "updated_ms": _now_ms(),
        },
    )


def emit_index_progress(
    job_id: str,
    *,
    done: int,
    total: int,
    root_id: int,
    phase: str,
    message: str = "",
) -> None:
    from . import ws_hub as _w

    msg = (message or "")[:512]
    _upsert(
        str(job_id),
        {
            "status": "running",
            "kind": "index",
            "job_id": str(job_id),
            "root_id": int(root_id),
            "done": int(done),
            "total": int(total) if total else 0,
            "phase": str(phase),
            "message": msg,
            "updated_ms": _now_ms(),
        },
    )
    _w.broadcast(
        _w.INDEX_PROGRESS,
        {
            "job_id": str(job_id),
            "kind": "index",
            "done": int(done),
            "total": int(total) if total else 0,
            "phase": str(phase),
            "message": msg,
            "root_id": int(root_id),
        },
    )
    _w.broadcast(
        _w.JOB_PROGRESS,
        {
            "job_id": str(job_id),
            "kind": "index",
            "done": int(done),
            "total": int(total) if total else 0,
            "phase": str(phase),
            "message": msg,
            "root_id": int(root_id),
        },
    )


def emit_index_done(
    job_id: str, *, root_id: int, phase: str, ok: int = 1, failed: int = 0,
) -> None:
    from . import ws_hub as _w

    jid = str(job_id)
    _remove(jid)
    _w.broadcast(
        _w.JOB_COMPLETED,
        {
            "job_id": jid,
            "kind": "index",
            "terminal": "ok" if not failed else "partial",
            "ok": int(ok),
            "fail": int(failed),
            "phase": str(phase),
            "root_id": int(root_id),
        },
    )


def emit_job_progress(
    job_id: str, *, kind: str, done: int, total: int, phase: str = "", message: str = "",
) -> None:
    from . import ws_hub as _w

    jid = str(job_id)
    t = int(total) if total else 0
    _upsert(
        jid,
        {
            "status": "running",
            "kind": str(kind),
            "job_id": jid,
            "done": int(done),
            "total": t,
            "phase": str(phase or ""),
            "message": (message or "")[:512],
            "updated_ms": _now_ms(),
        },
    )
    _w.broadcast(
        _w.JOB_PROGRESS,
        {
            "job_id": jid,
            "kind": str(kind),
            "done": int(done),
            "total": t,
            "phase": str(phase or ""),
            "message": (message or "")[:512],
        },
    )


def emit_job_done(
    job_id: str, *, kind: str, terminal: str, ok: int = 0, failed: int = 0, phase: str = "",
) -> None:
    from . import ws_hub as _w

    jid = str(job_id)
    _remove(jid)
    _w.broadcast(
        _w.JOB_COMPLETED,
        {
            "job_id": jid,
            "kind": str(kind),
            "terminal": str(terminal),
            "ok": int(ok),
            "fail": int(failed),
            "phase": str(phase or ""),
        },
    )
