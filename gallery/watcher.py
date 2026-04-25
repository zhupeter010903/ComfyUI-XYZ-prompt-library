"""XYZ Image Gallery — per-root ``watchdog`` Observers + ``Coalescer`` (T20).

FS events (debounced + coalesced) hand off to ``indexer.index_one`` /
``indexer.delete_one``.  Overflow → ``indexer.delta_scan`` (SPEC §8.2 /
TASKS T20).  WS 广播经 ``service`` 薄封装。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .repo import WriteQueue  # noqa: F401

logger = logging.getLogger("xyz.gallery.watcher")

__all__ = [
    "Coalescer",
    "merge_watcher_state",
    "start_file_watchers",
    "stop_file_watchers",
    "start_heartbeat",
    "stop_heartbeat",
]

_IMAGE_EXTS: frozenset = frozenset({".png", ".jpg", ".jpeg", ".webp"})

# ---- T25: coalescer counters (reset when heartbeat writes audit stats) ----

_coalescer_events_seen: int = 0
_coalescer_rows_flushed: int = 0


def _note_coalescer_event() -> None:
    global _coalescer_events_seen
    _coalescer_events_seen += 1


def _note_coalescer_flush(n: int) -> None:
    global _coalescer_rows_flushed
    _coalescer_rows_flushed += int(n)


def snapshot_coalescer_stats_for_audit() -> Tuple[int, int]:
    """Return ``(events_seen, rows_flushed)`` since last snapshot and zero both."""
    global _coalescer_events_seen, _coalescer_rows_flushed
    ev, rw = _coalescer_events_seen, _coalescer_rows_flushed
    _coalescer_events_seen = 0
    _coalescer_rows_flushed = 0
    return ev, rw


def _fan_out_delta_scan_result(root: Dict[str, Any], st: Dict[str, Any]) -> None:
    """WS: deleted rows + optional drift envelope (T25)."""
    from . import service as _service
    from . import ws_hub as _ws_hub

    for iid in st.get("deleted_ids") or []:
        _service.broadcast_image_deleted(int(iid))
    ch = int(st.get("changed", 0))
    rm = int(st.get("removed", 0))
    if ch > 0 or rm > 0:
        _ws_hub.broadcast(
            _ws_hub.INDEX_DRIFT_DETECTED,
            {
                "root_id": int(root["id"]),
                "changed": ch,
                "removed": rm,
                "walked": int(st.get("walked", 0)),
            },
        )


def _is_image_name(name: str) -> bool:
    from . import metadata as _metadata

    if _metadata.is_gallery_atomic_temp_basename(name):
        return False
    ext = os.path.splitext(name)[1].lower()
    return ext in _IMAGE_EXTS


def _is_derivative_excluded_path(path: str, root_path: str) -> bool:
    from . import indexer as _indexer

    return _indexer.is_derivative_path_excluded(path, root_path)


# ---- SPEC 8.2 merge (created+modified → upsert; created+delete → drop) ----


def merge_watcher_state(
    prior: Optional[str], event: str,
) -> Optional[str]:
    """``event`` 与 ``merge`` 输入为 ``'u'``(upsert) 或 ``'d'``(delete)."""
    e = (event or "").lower()
    if e not in ("u", "d"):
        raise ValueError("merge_watcher_state: expected 'u' or 'd'")
    if prior is None:
        return e
    if prior == "u" and e == "d":
        return None
    if prior == "d" and e == "u":
        return "u"
    return e


# ---- one delta at a time per root ----------------------------------------


class _DeltaArmer:
    def __init__(self, *, root: Dict[str, Any], db_path: Any, write_queue: Any) -> None:
        self._root = root
        self._db_path = db_path
        self._write_queue = write_queue
        self._lock = threading.Lock()
        self._running = False
        self._pending_again = False

    def request(self) -> None:
        with self._lock:
            if self._running:
                self._pending_again = True
                return
            self._running = True
        t = threading.Thread(
            target=self._run, name="xyz-gallery-watcher-deltascan", daemon=True,
        )
        t.start()

    def _run(self) -> None:
        from . import indexer as _indexer
        while True:
            try:
                st = _indexer.delta_scan(
                    self._root, db_path=self._db_path, write_queue=self._write_queue,
                )
                _fan_out_delta_scan_result(self._root, st)
            except Exception:
                logger.exception("delta_scan failed (root_id=%s)", self._root.get("id"))
            with self._lock:
                if not self._pending_again:
                    self._running = False
                    return
                self._pending_again = False


@dataclass
class _Pending:
    act: str  # 'u' or 'd'
    path: str
    t_mono: float


class Coalescer:
    """In-memory coalescer: 250 ms 沉寂后刷出、每批 ≤50 条、≥500 溢出。"""

    DEBOUNCE_S: float = 0.25
    FLUSH_MAX: int = 50
    HIGH_WATERMARK: int = 500
    _TICK_S: float = 0.05

    def __init__(self, *, root: Dict[str, Any], db_path: Any, write_queue: Any, delta: _DeltaArmer) -> None:
        self._root = root
        self._db_path = db_path
        self._write_queue = write_queue
        self._delta = delta
        self._lock = threading.Lock()
        self._buf: Dict[str, _Pending] = {}
        self._stop = threading.Event()
        self._tick = threading.Thread(
            target=self._tick_loop, name="xyz-gallery-coalescer", daemon=True,
        )
        self._folder_mono: Optional[float] = None

    def start(self) -> None:
        self._tick.start()

    def request_stop(self) -> None:
        self._stop.set()

    def join_tick(self, timeout: Optional[float] = 2.0) -> None:
        self._tick.join(timeout=timeout)

    def add(self, key: str, last_path: str, ev: str) -> None:
        """``ev`` ∈ ``'u'`` (upsert) 或 ``'d'`` (delete).  ``key``= indexer 去重 key。"""
        _note_coalescer_event()
        do_overflow = False
        with self._lock:
            p = self._buf.get(key)
            prior = p.act if p is not None else None
            m = merge_watcher_state(prior, ev)
            if m is None:
                self._buf.pop(key, None)
            else:
                self._buf[key] = _Pending(
                    act=m, path=last_path, t_mono=time.monotonic())
            n = len(self._buf)
            if n >= self.HIGH_WATERMARK:
                self._buf.clear()
                do_overflow = True
        if do_overflow:
            from . import service as _service
            _service.broadcast_index_overflow(int(self._root["id"]))
            self._delta.request()
            logger.info("coalescer overflow → delta_scan (root_id=%s)", self._root.get("id"))

    def mark_folder_reconcile(self) -> None:
        with self._lock:
            self._folder_mono = time.monotonic()

    def _tick_loop(self) -> None:
        from . import indexer as _indexer
        from . import service as _service

        while not self._stop.is_set():
            if self._stop.wait(self._TICK_S):
                break
            now = time.monotonic()
            with self._lock:
                to_flush = [
                    (k, v) for k, v in self._buf.items()
                    if now - v.t_mono >= self.DEBOUNCE_S
                ]
                for k, _ in to_flush:
                    self._buf.pop(k, None)
            if to_flush:
                _note_coalescer_flush(len(to_flush))
            for i in range(0, len(to_flush), self.FLUSH_MAX):
                chunk = to_flush[i: i + self.FLUSH_MAX]
                for _k, pend in chunk:
                    if pend.act == "d":
                        iid = _indexer.delete_one(
                            pend.path, db_path=self._db_path, write_queue=self._write_queue,
                        )
                        if iid is not None:
                            _service.broadcast_image_deleted(int(iid))
                    else:
                        if not _is_image_name(os.path.basename(pend.path)):
                            continue
                        if _is_derivative_excluded_path(
                            pend.path, str(self._root["path"]),
                        ):
                            continue
                        iid = _indexer.index_one(
                            pend.path, root=self._root, db_path=self._db_path,
                            write_queue=self._write_queue,
                        )
                        if iid is not None:
                            _service.broadcast_image_upserted(int(iid))

            with self._lock:
                fm = self._folder_mono
                if fm is not None and now - fm >= self.DEBOUNCE_S:
                    self._folder_mono = None
                    do_folder = True
                else:
                    do_folder = False
            if do_folder:
                try:
                    _indexer.reconcile_folders_under_root(
                        self._root,
                        db_path=self._db_path,
                        write_queue=self._write_queue,
                    )
                except Exception:
                    logger.exception(
                        "folder reconcile failed root_id=%s", self._root.get("id"),
                    )

_OBS: List[Any] = []
_CLS: List[Coalescer] = []
_WSTARTED: bool = False
_HEARTBEAT: Optional["HeartbeatThread"] = None


class HeartbeatThread:
    """30 s light ``delta_scan`` per root + 5 min audit stats line (T25)."""

    INTERVAL_S: float = 30.0
    STATS_INTERVAL_S: float = 300.0

    def __init__(self, *, db_path: Any, write_queue: Any) -> None:
        self._db_path = db_path
        self._write_queue = write_queue
        self._stop = threading.Event()
        self._thr: Optional[threading.Thread] = None
        self._scans_done: int = 0
        self._drifts_found: int = 0

    def start(self) -> None:
        if self._thr is not None and self._thr.is_alive():
            return
        self._stop.clear()
        self._thr = threading.Thread(
            target=self._loop, name="xyz-gallery-heartbeat", daemon=True,
        )
        self._thr.start()

    def stop(self, *, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thr is not None:
            self._thr.join(timeout=timeout)
            self._thr = None

    def _loop(self) -> None:
        from . import audit as _audit
        from . import folders as _folders
        from . import indexer as _indexer
        import time as _time

        last_audit = _time.monotonic()
        while not self._stop.wait(self.INTERVAL_S):
            self._scans_done += 1
            try:
                roots = _folders.list_roots(db_path=self._db_path)
            except Exception:
                logger.exception("HeartbeatThread list_roots failed")
                roots = []
            for root in roots:
                try:
                    st = _indexer.delta_scan(
                        root,
                        db_path=self._db_path,
                        write_queue=self._write_queue,
                        mode="light",
                    )
                    _fan_out_delta_scan_result(root, st)
                    if int(st.get("changed", 0)) + int(st.get("removed", 0)) > 0:
                        self._drifts_found += 1
                except Exception:
                    logger.exception(
                        "HeartbeatThread delta_scan root_id=%s",
                        root.get("id"),
                    )
            now = _time.monotonic()
            if now - last_audit >= self.STATS_INTERVAL_S:
                last_audit = now
                ev, co = snapshot_coalescer_stats_for_audit()
                _audit.log_heartbeat_stats(
                    events_seen=ev,
                    rows_coalesced=co,
                    scans_done=self._scans_done,
                    drifts_found=self._drifts_found,
                )


def start_heartbeat(*, db_path: Any, write_queue: Any) -> None:
    global _HEARTBEAT
    if _HEARTBEAT is not None:
        return
    _HEARTBEAT = HeartbeatThread(db_path=db_path, write_queue=write_queue)
    _HEARTBEAT.start()
    logger.info("gallery HeartbeatThread started")


def stop_heartbeat() -> None:
    global _HEARTBEAT
    if _HEARTBEAT is None:
        return
    _HEARTBEAT.stop()
    _HEARTBEAT = None
    logger.info("gallery HeartbeatThread stopped")


def _in_root(path: str, root_path: str) -> bool:
    r = os.path.normcase(os.path.normpath(root_path))
    try:
        p = os.path.normcase(os.path.normpath(path))
    except (OSError, TypeError, ValueError):
        return False
    rds = r if (r.endswith(os.sep) or len(r) == 3) else (r + os.sep)
    return p == r or p.startswith(rds)


def _as_key(path: str) -> str:
    return os.path.normcase(os.path.realpath(str(path)))


def _make_handler(coalescer: Coalescer, root_path: str) -> Any:
    from watchdog.events import (
        FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent,
    )
    c = coalescer
    r = root_path

    def _dir_reconcile_if_tracked(dir_path: str) -> None:
        if not _in_root(dir_path, r):
            return
        probe = os.path.join(dir_path, ".__probe__.png")
        if _is_derivative_excluded_path(probe, r):
            return
        c.mark_folder_reconcile()

    class _H(FileSystemEventHandler):
        def on_moved(
            _self, event,  # noqa: N802
        ) -> None:  # type: ignore[no-untyped-def]
            if event.is_directory:
                src, dst = str(event.src_path or ""), str(event.dest_path or "")
                if src:
                    _dir_reconcile_if_tracked(src)
                if dst:
                    _dir_reconcile_if_tracked(dst)
                return
            src, dst = str(event.src_path or ""), str(event.dest_path or "")
            if src and _in_root(src, r):
                c.add(_as_key(src), src, "d")
            if dst and _in_root(dst, r) and not _is_derivative_excluded_path(
                dst, r,
            ) and _is_image_name(os.path.basename(dst)):
                c.add(_as_key(dst), dst, "u")

        def on_created(
            _self, event,  # noqa: N802
        ) -> None:  # type: ignore[no-untyped-def]
            if not isinstance(event, FileCreatedEvent):
                return
            if event.is_directory:
                _dir_reconcile_if_tracked(str(event.src_path))
                return
            p = str(event.src_path)
            if not _in_root(p, r) or _is_derivative_excluded_path(p, r):
                return
            if not _is_image_name(os.path.basename(p)):
                return
            c.add(_as_key(p), p, "u")

        def on_modified(
            _self, event,  # noqa: N802
        ) -> None:  # type: ignore[no-untyped-def]
            if not isinstance(event, FileModifiedEvent) or event.is_directory:
                return
            p = str(event.src_path)
            if not _in_root(p, r) or _is_derivative_excluded_path(p, r):
                return
            if not _is_image_name(os.path.basename(p)):
                return
            c.add(_as_key(p), p, "u")

        def on_deleted(
            _self, event,  # noqa: N802
        ) -> None:  # type: ignore[no-untyped-def]
            if not isinstance(event, FileDeletedEvent):
                return
            p = str(event.src_path)
            if not _in_root(p, r):
                return
            if event.is_directory:
                _dir_reconcile_if_tracked(p)
                return
            c.add(_as_key(p), p, "d")

    return _H()  # type: ignore[no-any-return]


def start_file_watchers(
    *, db_path: Any, write_queue: Any,
) -> None:
    global _WSTARTED
    if _WSTARTED:
        return
    try:
        from watchdog.observers import Observer
    except Exception:
        logger.warning("watchdog not importable; file watchers disabled")
        return
    from . import folders as _folders

    roots = _folders.list_roots(db_path=db_path)
    for root in roots:
        delta = _DeltaArmer(root=root, db_path=db_path, write_queue=write_queue)
        c = Coalescer(root=root, db_path=db_path, write_queue=write_queue, delta=delta)
        c.start()
        _CLS.append(c)
        rpath = str(root["path"])
        h = _make_handler(c, rpath)
        o = Observer()
        o.schedule(h, rpath, recursive=True)
        o.start()
        _OBS.append(o)
    _WSTARTED = True
    logger.info("file watcher started (%d root(s))", len(roots))


def stop_file_watchers() -> None:
    global _WSTARTED, _OBS, _CLS
    if not _WSTARTED:
        return
    for o in _OBS:
        try:
            o.stop()
        except Exception:
            logger.debug("Observer.stop", exc_info=True)
    for o in _OBS:
        try:
            o.join(timeout=1.0)
        except Exception:
            pass
    for c in _CLS:
        c.request_stop()
    for c in _CLS:
        c.join_tick()
    _OBS, _CLS = [], []
    _WSTARTED = False
