"""XYZ Image Gallery — cold scan + delta scan + single-file index path (T07).

Scope (per TASKS.md T07 + PROJECT_STATE §7):

* ``cold_scan(root)`` — background full-walk of a registered root at
  startup; per-file ``(size, mtime_ns)`` fingerprint short-circuit so
  warm restarts are ~free (C-3 / NFR-8).
* ``delta_scan(root, mode='light')`` — same fingerprint comparison
  without the Pillow decode; differences hand off to ``index_one``.
  Exposed here for T20 watcher heartbeat and T25 drift checks; not
  called anywhere in T07 itself but part of the module contract.
* ``index_one(path)`` — single-file path (used by ``cold_scan`` itself
  and, later, by watcher callbacks).
* ``_inflight`` + ``_inflight_lock`` — module-wide de-duplication
  barrier keyed on ``os.path.realpath + os.path.normcase`` (TASKS T07
  UPDATED / T20 UPDATED).  Released unconditionally in ``finally``.

Boundaries:
* No HTTP / no routes.
* All writes go through ``repo.enqueue_write(...)`` (ARCHITECTURE §4.6).
  Fingerprint pre-reads use ``db.connect_read`` — never a write handle.
* Consumes ``metadata.read_comfy_metadata`` as a pure function; does
  NOT reach into PIL behind its back (PROJECT_STATE §7 note 8).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

from PIL import Image, UnidentifiedImageError

from . import db as _db
from . import metadata as _metadata
from . import repo as _repo

logger = logging.getLogger("xyz.gallery.indexer")

__all__ = [
    "cold_scan",
    "delta_scan",
    "index_one",
    "schedule_cold_scan_all",
]

_PathLike = Union[str, Path]

# Image file extensions recognised by the indexer. Narrow on purpose:
# adding RAW / video / etc. is a future task, not T07.
_IMAGE_EXTS: frozenset = frozenset({".png", ".jpg", ".jpeg", ".webp"})

# inflight barrier (TASKS T07 UPDATED): dedupes concurrent requests
# targeting the same physical file across cold_scan / index_one / the
# future watcher callback (T20). Keys are ``normcase(realpath(path))``.
_inflight: Set[str] = set()
_inflight_lock: threading.Lock = threading.Lock()


def _normalise_key(path: _PathLike) -> str:
    # realpath collapses symlinks; normcase handles Windows case / slash
    # differences. Together they prevent two "different looking" paths
    # from slipping past the dedup barrier.
    return os.path.normcase(os.path.realpath(str(path)))


def _claim(key: str) -> bool:
    """Try to add ``key`` to inflight. Returns True iff we won the slot."""
    with _inflight_lock:
        if key in _inflight:
            return False
        _inflight.add(key)
    return True


def _release(key: str) -> None:
    with _inflight_lock:
        _inflight.discard(key)


# -- fingerprint / existing-row lookup --------------------------------------

def _load_fingerprints(
    db_path: _PathLike, folder_id: int
) -> Dict[str, Tuple[int, int]]:
    """Return ``{path: (file_size, mtime_ns)}`` for images under ``folder_id``.

    Pre-loaded once per cold_scan so the per-file short-circuit is a
    plain dict lookup instead of 50 000 single-row SELECTs.
    """
    conn = _db.connect_read(db_path)
    try:
        rows = conn.execute(
            "SELECT path, file_size, mtime_ns FROM image WHERE folder_id = ?",
            (folder_id,),
        ).fetchall()
    finally:
        conn.close()
    out: Dict[str, Tuple[int, int]] = {}
    for r in rows:
        if r["file_size"] is None or r["mtime_ns"] is None:
            continue
        out[r["path"]] = (int(r["file_size"]), int(r["mtime_ns"]))
    return out


def _load_single_fingerprint(
    db_path: _PathLike, posix_path: str
) -> Optional[Tuple[int, int]]:
    conn = _db.connect_read(db_path)
    try:
        row = conn.execute(
            "SELECT file_size, mtime_ns FROM image WHERE path = ?",
            (posix_path,),
        ).fetchone()
    finally:
        conn.close()
    if row is None or row["file_size"] is None or row["mtime_ns"] is None:
        return None
    return int(row["file_size"]), int(row["mtime_ns"])


# -- parsing helpers --------------------------------------------------------

def _is_image(name: str) -> bool:
    ext = os.path.splitext(name)[1].lower()
    return ext in _IMAGE_EXTS


def _read_dims(path: str) -> Tuple[Optional[int], Optional[int]]:
    # PIL Image.open is lazy: .size is read from the header without
    # decoding pixels, so this is cheap (~0.3 ms on a typical PNG).
    # T06's read_comfy_metadata does not expose dimensions, and widening
    # its contract is explicitly off-limits (PROJECT_STATE §7 note 8).
    try:
        with Image.open(path) as img:
            w, h = img.size
            return int(w), int(h)
    except (UnidentifiedImageError, OSError, ValueError):
        return None, None


def _normalise_tags_csv(raw: Optional[str]) -> Optional[str]:
    # Per PROJECT_STATE §4 #24: tags mirror normalisation lives at exactly
    # one point in T07 (here), NOT in metadata.py. Full vocab-level
    # normalisation (stopwords / weight stripping) is T15's job; this is
    # the strict minimum: trim, lower-case, split on commas.
    if raw is None:
        return None
    parts = [t.strip().lower() for t in str(raw).split(",") if t.strip()]
    return ",".join(parts) if parts else None


def _normalise_favorite(raw: Optional[str]) -> Optional[int]:
    # Same scoping rule as tags: PNG chunk is a raw str; we decide the
    # 0/1 mapping here (and only here).
    if raw is None:
        return None
    v = str(raw).strip().lower()
    if v in ("1", "true", "yes", "t", "y"):
        return 1
    if v in ("0", "false", "no", "f", "n"):
        return 0
    return None


def _build_upsert_op(
    *, abs_path: str, root: Dict[str, Any], stat_result: os.stat_result,
    meta: _metadata.ComfyMeta,
) -> _repo.UpsertImageOp:
    # Store paths as POSIX absolute strings — invariant §4 #9.
    posix_path = Path(abs_path).as_posix()
    root_posix = str(root["path"])  # already POSIX from T05
    # relative_path is POSIX relative to the root.  Path.relative_to
    # handles platform separators; as_posix normalises the result.
    rel = Path(abs_path).resolve(strict=False).relative_to(
        Path(root_posix).resolve(strict=False)
    ).as_posix()
    filename = os.path.basename(posix_path)
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    width, height = _read_dims(abs_path)
    now = int(time.time())
    return _repo.UpsertImageOp(
        path=posix_path,
        folder_id=int(root["id"]),
        root_path=root_posix,
        root_kind=str(root["kind"]),
        relative_path=rel,
        filename=filename,
        filename_lc=filename.lower(),
        ext=ext,
        width=width,
        height=height,
        file_size=int(stat_result.st_size),
        mtime_ns=int(stat_result.st_mtime_ns),
        # SPEC §6.1: created_at epoch seconds; preferred ComfyUI metadata
        # creation date, fallback ctime. T06 does not surface a creation
        # timestamp, so fall back to mtime — a deliberate MVP choice
        # (AI_RULES R4.3).
        created_at=int(stat_result.st_mtime),
        positive_prompt=meta.positive_prompt,
        negative_prompt=meta.negative_prompt,
        model=meta.model,
        seed=meta.seed,
        cfg=meta.cfg,
        sampler=meta.sampler,
        scheduler=meta.scheduler,
        workflow_present=1 if meta.has_workflow else 0,
        favorite=_normalise_favorite(meta.favorite),
        tags_csv=_normalise_tags_csv(meta.tags),
        indexed_at=now,
    )


# -- cold / delta scans -----------------------------------------------------

def _iter_image_files(root_path: str) -> Iterable[str]:
    # os.walk with onerror logging: permission errors etc. should not
    # abort the entire scan. Broken symlinks are filtered by followlinks=False.
    def _onerror(exc: OSError) -> None:
        logger.warning("walk error under %s: %s", root_path, exc)

    for dirpath, _dirnames, filenames in os.walk(root_path, onerror=_onerror):
        for name in filenames:
            if _is_image(name):
                yield os.path.join(dirpath, name)


# Progress reporting batch size per TASKS T07 ("每 500 条触发一次进度统计").
_PROGRESS_BATCH: int = 500


def cold_scan(
    root: Dict[str, Any], *, db_path: _PathLike, write_queue
) -> Dict[str, int]:
    """Walk one registered root once, enqueuing upserts for any diffs.

    ``root`` is a dict with keys ``id``, ``path``, ``kind`` (the shape
    returned by ``folders.list_roots`` and friends).  Runs synchronously
    in whatever thread calls it — the top-level startup wrapper
    (``schedule_cold_scan_all``) is what actually backgrounds it.

    Returns a summary dict ``{walked, skipped, enqueued, errors}`` mostly
    for logging / later telemetry hooks.
    """
    root_path = str(root["path"])
    root_id = int(root["id"])

    if not os.path.isdir(root_path):
        logger.warning("cold_scan: root path not a directory: %s", root_path)
        return {"walked": 0, "skipped": 0, "enqueued": 0, "errors": 0}

    fingerprints = _load_fingerprints(db_path, root_id)

    walked = 0
    skipped = 0
    enqueued = 0
    errors = 0

    for abs_path in _iter_image_files(root_path):
        walked += 1
        key = _normalise_key(abs_path)
        if not _claim(key):
            skipped += 1
            continue
        try:
            try:
                st = os.stat(abs_path)
            except OSError as exc:
                errors += 1
                logger.debug("stat failed for %s: %s", abs_path, exc)
                continue

            posix_path = Path(abs_path).as_posix()
            cached = fingerprints.get(posix_path)
            if cached is not None and cached == (
                int(st.st_size), int(st.st_mtime_ns)
            ):
                skipped += 1
                continue

            meta = _metadata.read_comfy_metadata(abs_path)
            # NB: meta.errors being non-empty is NOT a reason to skip the
            # row — we still want the image indexed (filename / size /
            # dims) even if its prompt chunks are corrupt. PROJECT_STATE
            # §4 #22: errors are informational; a single broken PNG must
            # never stall the cold scan (NFR-1).
            try:
                op = _build_upsert_op(
                    abs_path=abs_path, root=root,
                    stat_result=st, meta=meta,
                )
            except Exception:
                errors += 1
                logger.exception("failed to build op for %s", abs_path)
                continue

            write_queue.enqueue_write(_repo.LOW, op)
            enqueued += 1

            if enqueued and enqueued % _PROGRESS_BATCH == 0:
                logger.info(
                    "cold_scan progress (root=%s): walked=%d enqueued=%d skipped=%d",
                    root_path, walked, enqueued, skipped,
                )
        except Exception:
            errors += 1
            logger.exception("indexer error for %s", abs_path)
        finally:
            _release(key)

    logger.info(
        "cold_scan done (root=%s): walked=%d enqueued=%d skipped=%d errors=%d",
        root_path, walked, enqueued, skipped, errors,
    )
    return {
        "walked": walked, "skipped": skipped,
        "enqueued": enqueued, "errors": errors,
    }


def index_one(
    path: _PathLike, *, root: Dict[str, Any],
    db_path: _PathLike, write_queue,
) -> bool:
    """Index a single file. Returns True iff an upsert was enqueued.

    Used by ``cold_scan`` internally only indirectly; exposed for the
    T20 watcher callback (TASKS T20 UPDATED explicitly forbids watcher
    from inventing its own dedup, so it will call back into here).

    The inflight barrier is released on EVERY return path (including
    "no-op because fingerprint matched") so that later calls for the
    same path are never silently suppressed — test #5 in TASKS T07.
    """
    abs_path = str(path)
    key = _normalise_key(abs_path)
    if not _claim(key):
        return False
    try:
        try:
            st = os.stat(abs_path)
        except OSError:
            return False

        posix_path = Path(abs_path).as_posix()
        cached = _load_single_fingerprint(db_path, posix_path)
        if cached is not None and cached == (
            int(st.st_size), int(st.st_mtime_ns)
        ):
            return False

        meta = _metadata.read_comfy_metadata(abs_path)
        op = _build_upsert_op(
            abs_path=abs_path, root=root,
            stat_result=st, meta=meta,
        )
        write_queue.enqueue_write(_repo.LOW, op)
        return True
    finally:
        _release(key)


def delta_scan(
    root: Dict[str, Any], *, db_path: _PathLike, write_queue,
    mode: str = "light",
) -> Dict[str, int]:
    """Light delta scan: ``(size, mtime_ns)`` comparison, no PIL decode.

    Only files that actually differ are handed off to ``index_one``
    (where the full ``read_comfy_metadata`` path runs).  Deletion
    reconciliation is intentionally out of scope for T07 — that is
    T20 / T25's heartbeat territory (AI_RULES R1.2).
    """
    if mode != "light":
        raise ValueError(f"delta_scan: unknown mode {mode!r}")

    root_path = str(root["path"])
    root_id = int(root["id"])
    if not os.path.isdir(root_path):
        return {"walked": 0, "changed": 0, "errors": 0}

    fingerprints = _load_fingerprints(db_path, root_id)
    walked = 0
    changed = 0
    errors = 0

    for abs_path in _iter_image_files(root_path):
        walked += 1
        try:
            st = os.stat(abs_path)
        except OSError:
            errors += 1
            continue
        posix_path = Path(abs_path).as_posix()
        cached = fingerprints.get(posix_path)
        if cached is not None and cached == (
            int(st.st_size), int(st.st_mtime_ns)
        ):
            continue
        try:
            if index_one(
                abs_path, root=root,
                db_path=db_path, write_queue=write_queue,
            ):
                changed += 1
        except Exception:
            errors += 1
            logger.exception("delta_scan index_one failed for %s", abs_path)

    return {"walked": walked, "changed": changed, "errors": errors}


# -- startup orchestration --------------------------------------------------

def _load_roots(db_path: _PathLike) -> List[Dict[str, Any]]:
    conn = _db.connect_read(db_path)
    try:
        rows = conn.execute(
            "SELECT id, path, kind FROM folder WHERE parent_id IS NULL"
        ).fetchall()
    finally:
        conn.close()
    return [
        {"id": int(r["id"]), "path": str(r["path"]), "kind": str(r["kind"])}
        for r in rows
    ]


def _cold_scan_all_worker(db_path: _PathLike, write_queue) -> None:
    try:
        roots = _load_roots(db_path)
    except Exception:
        logger.exception("indexer: failed to load roots; aborting cold scan")
        return
    for root in roots:
        try:
            cold_scan(root, db_path=db_path, write_queue=write_queue)
        except Exception:
            logger.exception(
                "indexer: cold_scan crashed for root %s", root.get("path"),
            )


def schedule_cold_scan_all(
    *, db_path: _PathLike, write_queue,
) -> threading.Thread:
    """Fire-and-forget background cold scan of every registered root.

    Single worker thread per TASKS T07 ("第一版单线程解析"); ProcessPool
    fan-out is T27's scope and must not leak forward here
    (AI_RULES R1.2).
    """
    t = threading.Thread(
        target=_cold_scan_all_worker,
        args=(db_path, write_queue),
        name="xyz-gallery-indexer-coldscan",
        daemon=True,
    )
    t.start()
    return t
