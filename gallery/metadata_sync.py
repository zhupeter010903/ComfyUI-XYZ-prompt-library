"""XYZ Image Gallery — asynchronous PNG ``xyz_gallery.*`` mirror writer (T17).

Drains ``notify(image_id, version)`` hints plus a periodic patrol over
``metadata_sync_status != 'ok'``, calls :func:`metadata.write_xyz_chunks`,
then records outcomes via ``repo.WriteQueue``: successful PNG writes use
``HIGH`` :class:`repo.SetSyncStatusOp` so ``file_size`` / ``mtime_ns`` match
disk before the file watcher debounce fires, avoiding redundant upserts.
Failures remain ``LOW`` (ARCHITECTURE §4.6 / §4.8).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from . import db as _db
from . import metadata as _metadata
from . import repo as _repo

logger = logging.getLogger("xyz.gallery.metadata_sync")

__all__ = [
    "start_metadata_sync_worker",
    "stop_metadata_sync_worker",
    "notify",
    "queue_many",
]

_POLL_SEC = 1.0
_PATROL_LIMIT = 32

_stop = threading.Event()
_wake = threading.Event()
_thread: Optional[threading.Thread] = None
_thread_lock = threading.Lock()

_notify_lock = threading.Lock()
_pending: Dict[int, int] = {}

_db_path: Optional[Path] = None
_write_queue: Any = None


def _broadcast_sync_status(*, image_id: int, version: int, sync_status: str) -> None:
    from . import ws_hub as _ws_hub

    _ws_hub.broadcast(
        _ws_hub.IMAGE_SYNC_STATUS_CHANGED,
        {"id": int(image_id), "sync_status": sync_status, "version": int(version)},
    )


def start_metadata_sync_worker(*, db_path: Any, write_queue: Any) -> None:
    """Start the daemon thread (idempotent). Must run after ``WriteQueue.start``."""
    global _db_path, _write_queue, _thread
    _db_path = Path(db_path)
    _write_queue = write_queue
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop.clear()
        _thread = threading.Thread(
            target=_worker_loop,
            name="xyz-gallery-metadata-sync",
            daemon=True,
        )
        _thread.start()
        # Thread.name is not echoed to the ComfyUI console by default — log
        # explicitly so QA can grep ``xyz-gallery-metadata-sync`` (TASKS T17).
        logger.info(
            "metadata_sync worker started (thread_name=%r ident=%s)",
            _thread.name,
            _thread.ident,
        )


def stop_metadata_sync_worker(timeout: float = 0.5) -> bool:
    """Signal shutdown and join; mirrors thumbs flusher lifecycle (§4 #17)."""
    global _thread
    _stop.set()
    _wake.set()
    with _thread_lock:
        t = _thread
    if t is None:
        return True
    t.join(timeout=timeout)
    joined = not t.is_alive()
    if joined:
        with _thread_lock:
            _thread = None
    return joined


def notify(image_id: int, version: int) -> None:
    """Wake the worker; ``version`` is the authoritative ``image.version`` snapshot."""
    with _notify_lock:
        cur = _pending.get(int(image_id))
        if cur is None or int(version) >= cur:
            _pending[int(image_id)] = int(version)
    _wake.set()


def queue_many(updates: Dict[int, int]) -> None:
    """Merge many ``(image_id, version)`` into ``_pending`` in one lock + one wake (T44).

    The worker still calls ``attempt_sync_write`` for each id on a tick; this
    only reduces
    redundant event-loop wakes from N ``notify`` calls in bulk / tag admin loops.
    """
    if not updates:
        return
    with _notify_lock:
        for iid, ver in updates.items():
            ii, vv = int(iid), int(ver)
            old = _pending.get(ii)
            if old is None:
                _pending[ii] = vv
            else:
                _pending[ii] = max(int(old), vv)
    _wake.set()


def _worker_loop() -> None:
    while not _stop.is_set():
        triggered = _wake.wait(timeout=_POLL_SEC)
        if triggered:
            _wake.clear()
        if _stop.is_set():
            break
        try:
            _tick()
        except Exception:
            logger.exception("metadata_sync tick failed")


def _tick() -> None:
    if _db_path is None or _write_queue is None:
        return
    merged: Dict[int, int] = {}
    with _notify_lock:
        for iid, ver in _pending.items():
            merged[iid] = ver
        _pending.clear()
    now = int(time.time())
    conn = _db.connect_read(_db_path)
    try:
        rows = conn.execute(
            "SELECT id, version FROM image WHERE "
            "(metadata_sync_status = 'pending') "
            "OR ("
            " metadata_sync_status = 'failed' "
            " AND metadata_sync_retry_count < 3 "
            " AND metadata_sync_next_retry_at IS NOT NULL "
            " AND metadata_sync_next_retry_at <= ?"
            ")"
            " ORDER BY id LIMIT ?",
            (now, _PATROL_LIMIT),
        ).fetchall()
    finally:
        conn.close()
    for r in rows:
        iid, ver = int(r[0]), int(r[1])
        merged[iid] = max(merged.get(iid, -1), ver)
    for iid, ver in merged.items():
        try:
            attempt_sync_write(_db_path, _write_queue, iid, ver)
        except Exception:  # noqa: BLE001
            logger.exception(
                "metadata_sync: attempt_sync_write failed id=%s ver=%s",
                iid, ver,
            )


def attempt_sync_write(
    db_path: Path,
    write_queue: Any,
    image_id: int,
    task_version: int,
) -> None:
    """One sync attempt for tests and internal worker use (TASKS T17)."""

    conn = _db.connect_read(db_path)
    try:
        row = conn.execute(
            "SELECT id, version, path, ext, favorite, tags_csv, "
            "metadata_sync_status, metadata_sync_retry_count, "
            "metadata_sync_next_retry_at "
            "FROM image WHERE id = ?",
            (int(image_id),),
        ).fetchone()
        if row is None:
            return
        if int(row["version"]) != int(task_version):
            return
        st = row["metadata_sync_status"]
        if st not in ("pending", "failed"):
            return
        if st == "failed":
            nra = row["metadata_sync_next_retry_at"]
            rc = int(row["metadata_sync_retry_count"] or 0)
            if rc >= 3 or nra is None or int(nra) > int(time.time()):
                return
        ext = (row["ext"] or "").lower()
        path = str(row["path"])
        pre = conn.execute(
            "SELECT version, favorite, tags_csv FROM image WHERE id = ?",
            (int(image_id),),
        ).fetchone()
        if pre is None or int(pre["version"]) != int(task_version):
            return
        tags_csv = pre["tags_csv"]
        fav = pre["favorite"]
    finally:
        conn.close()

    fav_arg = None if fav is None else int(fav)

    if ext != "png":
        fut = write_queue.enqueue_write(
            _repo.LOW,
            _repo.SetSyncHardFailedOp(
                image_id=int(image_id),
                expected_version=int(task_version),
                error="metadata sync requires PNG (xyz_gallery chunks)",
            ),
        )
        fut.result(timeout=30.0)
        _broadcast_sync_status(
            image_id=int(image_id),
            version=int(task_version),
            sync_status="failed",
        )
        return

    try:
        staging = Path(db_path).parent / ".xyz_gallery_atomic"
        _metadata.write_xyz_chunks(
            path,
            tags_csv,
            fav_arg,
            atomic_staging_dir=staging,
        )
    except Exception as exc:
        logger.warning(
            "metadata_sync write failed id=%s ver=%s: %s",
            image_id,
            task_version,
            exc,
        )
        fut = write_queue.enqueue_write(
            _repo.LOW,
            _repo.SetSyncFailedOp(
                image_id=int(image_id),
                expected_version=int(task_version),
                error=str(exc),
                now=int(time.time()),
            ),
        )
        fut.result(timeout=30.0)
        _broadcast_sync_status(
            image_id=int(image_id),
            version=int(task_version),
            sync_status="failed",
        )
        return

    st_disk = os.stat(path)
    mtime_ns = int(getattr(st_disk, "st_mtime_ns", int(st_disk.st_mtime * 1e9)))
    fut = write_queue.enqueue_write(
        _repo.HIGH,
        _repo.SetSyncStatusOp(
            image_id=int(image_id),
            expected_version=int(task_version),
            refresh_file_size=int(st_disk.st_size),
            refresh_mtime_ns=mtime_ns,
        ),
    )
    fut.result(timeout=30.0)
    _broadcast_sync_status(
        image_id=int(image_id),
        version=int(task_version),
        sync_status="ok",
    )
