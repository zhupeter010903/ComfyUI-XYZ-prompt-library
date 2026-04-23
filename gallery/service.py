"""XYZ Image Gallery — use-case orchestration (T19).

PATCH / resync flows: sandbox → ``WriteQueue(HIGH)`` → WS fan-out →
``metadata_sync.notify`` (ARCHITECTURE §4.3 / §4.8).
"""

from __future__ import annotations

import errno
import logging
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from . import audit as _audit
from . import db as _db
from . import folders as _folders
from . import metadata_sync as _metadata_sync
from . import paths as _paths
from . import repo as _repo
from . import vocab as _vocab
from . import ws_hub as _ws_hub

logger = logging.getLogger("xyz.gallery.service")

BULK_HIGH_IF_TOTAL_LEQ: int = 64

__all__ = [
    "update_image",
    "resync_image",
    "broadcast_image_upserted",
    "broadcast_image_deleted",
    "broadcast_index_overflow",
    "bulk_set_favorite",
    "bulk_edit_tags",
    "preflight_move",
    "execute_move",
    "move_single_image",
    "preflight_delete",
    "execute_delete",
    "delete_single_image",
    "PreflightMoveError",
]

_PLAN_TTL_SEC = 300.0
_plan_lock = threading.Lock()
_plans: Dict[str, "_MovePlanRecord"] = {}
_delete_plans: Dict[str, "_DeletePlanRecord"] = {}


class PreflightMoveError(Exception):
    """Validated client-facing move preflight failure (HTTP 4xx mapping)."""

    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.code = str(code)
        self.details = dict(details) if details else {}


@dataclass
class _MoveMapping:
    image_id: int
    src: str
    dst: str
    conflict: str  # "clean" | "renamed"


@dataclass
class _MovePlanRecord:
    mappings: List[_MoveMapping] = field(default_factory=list)
    expires_at: float = 0.0
    total_bytes: int = 0
    target_folder_id: int = 0


@dataclass
class _DeletePlanRecord:
    rows: List[Tuple[int, str]] = field(default_factory=list)
    expires_at: float = 0.0
    total_bytes: int = 0


def _plan_gc_locked() -> None:
    now = time.monotonic()
    dead = [k for k, v in _plans.items() if v.expires_at <= now]
    for k in dead:
        del _plans[k]
    dead_d = [k for k, v in _delete_plans.items() if v.expires_at <= now]
    for k in dead_d:
        del _delete_plans[k]


def _store_put(plan_id: str, rec: _MovePlanRecord) -> None:
    with _plan_lock:
        _plan_gc_locked()
        _plans[plan_id] = rec


def _store_get(plan_id: str) -> Optional[_MovePlanRecord]:
    with _plan_lock:
        _plan_gc_locked()
        rec = _plans.get(plan_id)
        if rec is None:
            return None
        if rec.expires_at <= time.monotonic():
            del _plans[plan_id]
            return None
        return rec


def _store_pop(plan_id: str) -> Optional[_MovePlanRecord]:
    with _plan_lock:
        _plan_gc_locked()
        rec = _plans.pop(plan_id, None)
        if rec is None:
            return None
        if rec.expires_at <= time.monotonic():
            return None
        return rec


def _delete_store_put(plan_id: str, rec: _DeletePlanRecord) -> None:
    with _plan_lock:
        _plan_gc_locked()
        _delete_plans[plan_id] = rec


def _delete_store_pop(plan_id: str) -> Optional[_DeletePlanRecord]:
    with _plan_lock:
        _plan_gc_locked()
        rec = _delete_plans.pop(plan_id, None)
        if rec is None:
            return None
        if rec.expires_at <= time.monotonic():
            return None
        return rec


def _next_free_name(filename: str, taken_lower: set) -> str:
    """Pick ``stem (n).ext`` not present in ``taken_lower`` (case-insensitive)."""
    p = Path(filename)
    stem, ext = p.stem, p.suffix
    base = filename
    if base.lower() not in taken_lower:
        return base
    n = 1
    while True:
        cand = f"{stem} ({n}){ext}"
        if cand.lower() not in taken_lower:
            return cand
        n += 1


def _target_dir_path(*, db_path: Path, target_folder_id: int) -> str:
    conn = _db.connect_read(db_path)
    try:
        row = conn.execute(
            "SELECT path FROM folder WHERE id = ?", (int(target_folder_id),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise PreflightMoveError("not_found", f"folder id={target_folder_id} not found")
    raw = str(row["path"])
    p = Path(raw).resolve(strict=False)
    if not p.is_dir():
        raise PreflightMoveError(
            "bad_path", f"target folder is not a directory: {raw!r}",
        )
    return p.as_posix()


def _listdir_lower(dir_path: str) -> set:
    try:
        names = os.listdir(dir_path)
    except OSError as exc:
        raise PreflightMoveError(
            "bad_path", f"cannot list target directory: {exc}",
        ) from exc
    return {n.lower() for n in names}


def _physical_move(src: str, dst: str) -> None:
    dst_parent = Path(dst).parent
    dst_parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(src, dst)
    except OSError as exc:
        if not _is_cross_device(exc):
            raise
        shutil.copy2(src, dst)
        if Path(src).stat().st_size != Path(dst).stat().st_size:
            try:
                os.unlink(dst)
            except OSError:
                pass
            raise RuntimeError("cross-device copy size mismatch") from exc
        os.unlink(src)


def _is_cross_device(exc: OSError) -> bool:
    if exc.errno == errno.EXDEV:
        return True
    if getattr(exc, "winerror", None) == 17:
        return True
    return False


def _fields_for_moved_file(
    dst_posix: str, roots: List[Mapping[str, Any]],
) -> Tuple[int, str, str, str, str, str, int, int]:
    """Return folder_id, path, relative_path, filename, filename_lc, ext, mtime_ns, file_size."""
    st = Path(dst_posix).stat()
    file_size = int(st.st_size)
    mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
    resolved = Path(dst_posix).resolve(strict=False)
    path_posix = resolved.as_posix()
    filename = resolved.name
    ext = resolved.suffix.lower().lstrip(".")
    filename_lc = filename.lower()
    root_paths = [str(r["path"]) for r in roots]
    _paths.assert_inside_root(path_posix, root_paths)
    for r in roots:
        rp = Path(str(r["path"])).resolve(strict=False)
        try:
            rel = resolved.relative_to(rp).as_posix()
        except ValueError:
            continue
        return (
            int(r["id"]),
            path_posix,
            rel,
            filename,
            filename_lc,
            ext,
            mtime_ns,
            file_size,
        )
    raise _paths.SandboxError(
        f"path {path_posix!r} is not inside any registered root"
    )


def preflight_move(
    sel: _repo.SelectionSpec,
    target_folder_id: int,
    *,
    db_path: Path,
) -> dict:
    """Phase-1 bulk move: sandbox, disk budget, name simulation → ``plan_id``."""
    rows = _repo.fetch_selection_move_sources(db_path=db_path, sel=sel)
    if not rows:
        raise PreflightMoveError("invalid_body", "selection resolves to zero images")

    target_dir = _target_dir_path(db_path=db_path, target_folder_id=target_folder_id)
    roots = _folders.list_roots(db_path=db_path)
    root_paths = [str(r["path"]) for r in roots]
    _paths.assert_inside_root(target_dir, root_paths)

    if not os.access(target_dir, os.W_OK):
        raise PreflightMoveError(
            "bad_path", f"target folder not writable: {target_dir!r}",
        )

    total_bytes = 0
    for _i, _p, fs, _fn in rows:
        total_bytes += int(fs) if fs is not None else 0

    du = shutil.disk_usage(target_dir)
    free_bytes = int(du.free)
    if total_bytes > free_bytes * 0.95:
        raise PreflightMoveError(
            "invalid_body",
            "insufficient free space on target volume "
            f"(need ~{total_bytes} bytes, ~{free_bytes} bytes free)",
            {"total_bytes": total_bytes, "free_bytes": free_bytes},
        )

    taken = _listdir_lower(target_dir)
    mappings: List[_MoveMapping] = []
    unresolved: List[dict] = []

    for image_id, src, _fs, orig_fn in rows:
        try:
            _paths.assert_inside_root(src, root_paths)
        except _paths.SandboxError as exc:
            raise PreflightMoveError(
                "sandbox", str(exc), {"id": int(image_id)},
            ) from exc

        src_res = Path(src).resolve(strict=False)
        candidate = orig_fn
        if candidate.lower() in taken:
            candidate = _next_free_name(orig_fn, taken)
        dst = str(Path(target_dir) / candidate)
        dst_res = Path(dst).resolve(strict=False)
        if src_res == dst_res:
            continue
        taken.add(candidate.lower())
        conflict = "clean" if candidate == orig_fn else "renamed"
        mappings.append(
            _MoveMapping(
                image_id=int(image_id),
                src=src_res.as_posix(),
                dst=dst_res.as_posix(),
                conflict=conflict,
            ),
        )

    if not mappings:
        raise PreflightMoveError("invalid_body", "nothing to move (all targets match sources)")

    plan_id = uuid.uuid4().hex
    rec = _MovePlanRecord(
        mappings=mappings,
        expires_at=time.monotonic() + _PLAN_TTL_SEC,
        total_bytes=total_bytes,
        target_folder_id=int(target_folder_id),
    )
    _store_put(plan_id, rec)

    wire_maps = [
        {
            "id": m.image_id,
            "src": m.src,
            "dst": m.dst,
            "conflict": m.conflict,
        }
        for m in mappings
    ]
    return {
        "plan_id": plan_id,
        "total_bytes": total_bytes,
        "free_bytes": free_bytes,
        "mappings": wire_maps,
        "unresolved_conflicts": unresolved,
    }


def _apply_rename_overrides(
    plan: _MovePlanRecord, overrides: Optional[Mapping[str, Any]],
) -> _MovePlanRecord:
    if not overrides:
        return plan
    target_dir = str(Path(plan.mappings[0].dst).parent.as_posix())
    new_maps: List[_MoveMapping] = []
    for m in plan.mappings:
        key = str(m.image_id)
        name = overrides.get(key)
        if name is None:
            name = overrides.get(m.image_id)
        if name is None:
            new_maps.append(m)
            continue
        if not isinstance(name, str) or not name.strip():
            raise PreflightMoveError("invalid_body", f"empty rename for id={m.image_id}")
        base = Path(name).name
        dst = str(Path(target_dir) / base)
        new_maps.append(
            _MoveMapping(
                image_id=m.image_id,
                src=m.src,
                dst=Path(dst).resolve(strict=False).as_posix(),
                conflict="renamed",
            ),
        )
    return _MovePlanRecord(
        mappings=new_maps,
        expires_at=plan.expires_at,
        total_bytes=plan.total_bytes,
        target_folder_id=plan.target_folder_id,
    )


def _re_check_plan_disk(plan: _MovePlanRecord) -> None:
    for m in plan.mappings:
        par = Path(m.dst).parent
        if not par.is_dir():
            raise PreflightMoveError(
                "bad_path", f"target directory missing: {str(par)!r}",
            )
        dst_p = Path(m.dst)
        if dst_p.exists():
            if dst_p.resolve(strict=False) != Path(m.src).resolve(strict=False):
                raise PreflightMoveError(
                    "invalid_body",
                    f"destination blocked by existing file: {m.dst!r}",
                    {"id": m.image_id},
                )


def execute_move(
    plan_id: str,
    rename_overrides: Optional[Mapping[str, Any]],
    *,
    db_path: Path,
    actor: str = "unknown",
) -> dict:
    raw = _store_pop(plan_id)
    if raw is None:
        raise PreflightMoveError("not_found", "unknown or expired plan_id")

    plan = _apply_rename_overrides(raw, rename_overrides)
    roots = _folders.list_roots(db_path=db_path)
    root_paths = [str(r["path"]) for r in roots]
    for m in plan.mappings:
        try:
            _paths.assert_inside_root(m.src, root_paths)
            _paths.assert_inside_root(m.dst, root_paths)
        except _paths.SandboxError as exc:
            raise PreflightMoveError("sandbox", str(exc)) from exc

    _re_check_plan_disk(plan)

    wq = _write_queue_handle()
    total = len(plan.mappings)
    ok_count = 0
    failed: List[dict] = []

    _ws_hub.broadcast(
        _ws_hub.BULK_PROGRESS,
        {
            "plan_id": plan_id,
            "bulk_id": plan_id,
            "done": 0,
            "total": total,
            "kind": "move",
        },
    )

    for i, m in enumerate(plan.mappings):
        try:
            if Path(m.src).resolve(strict=False) == Path(m.dst).resolve(strict=False):
                ok_count += 1
            else:
                _physical_move(m.src, m.dst)
                (
                    folder_id,
                    path_posix,
                    rel,
                    filename,
                    filename_lc,
                    ext,
                    mtime_ns,
                    file_size,
                ) = _fields_for_moved_file(m.dst, roots)
                fut = wq.enqueue_write(
                    _repo.MID,
                    _repo.UpdateImagePathOp(
                        image_id=m.image_id,
                        path=path_posix,
                        folder_id=folder_id,
                        relative_path=rel,
                        filename=filename,
                        filename_lc=filename_lc,
                        ext=ext,
                        file_size=file_size,
                        mtime_ns=mtime_ns,
                        refresh_sync=True,
                    ),
                )
                ver = int(fut.result(timeout=120.0))
                ok_count += 1
                _ws_hub.broadcast(
                    _ws_hub.IMAGE_UPDATED,
                    {
                        "id": int(m.image_id),
                        "version": ver,
                        "moved_to": path_posix,
                    },
                )
                _metadata_sync.notify(int(m.image_id), ver)
        except Exception as exc:  # noqa: BLE001
            failed.append(
                {
                    "id": int(m.image_id),
                    "code": "internal",
                    "message": str(exc),
                },
            )
            logger.exception("execute_move failed id=%s", m.image_id)
        _ws_hub.broadcast(
            _ws_hub.BULK_PROGRESS,
            {
                "plan_id": plan_id,
                "bulk_id": plan_id,
                "done": i + 1,
                "total": total,
                "kind": "move",
            },
        )
        if (i + 1) % 50 == 0:
            time.sleep(0)

    _ws_hub.broadcast(
        _ws_hub.BULK_COMPLETED,
        {
            "plan_id": plan_id,
            "bulk_id": plan_id,
            "done": total,
            "total": total,
            "kind": "move",
            "failed": failed,
        },
    )
    logger.info(
        "bulk move completed plan_id=%s ok=%s failed=%s",
        plan_id, ok_count, len(failed),
    )
    _audit.log_event(
        "bulk_move_completed",
        actor,
        {
            "plan_id": plan_id,
            "moved": ok_count,
            "failed": len(failed),
            "total": total,
        },
    )
    return {"moved": ok_count, "failed": failed, "plan_id": plan_id}


def move_single_image(
    image_id: int,
    target_folder_id: int,
    rename: Optional[str],
    *,
    db_path: Path,
) -> _repo.ImageRecord:
    """Move one image; 409-style collision surfaced as ``PreflightMoveError``."""
    rec = _repo.get_image(int(image_id), db_path=db_path)
    if rec is None:
        raise KeyError(f"image {image_id} not found")

    roots = _folders.list_roots(db_path=db_path)
    root_paths = [r["path"] for r in roots]
    _paths.assert_inside_root(rec.path, root_paths)

    target_dir = _target_dir_path(db_path=db_path, target_folder_id=target_folder_id)
    _paths.assert_inside_root(target_dir, root_paths)

    if not os.access(target_dir, os.W_OK):
        raise PreflightMoveError(
            "bad_path", f"target folder not writable: {target_dir!r}",
        )

    src_res = Path(rec.path).resolve(strict=False)
    dst_name = (rename or rec.filename).strip()
    if not dst_name or dst_name != Path(dst_name).name:
        raise PreflightMoveError("invalid_body", "rename must be a plain filename")
    dst = str(Path(target_dir) / dst_name)
    dst_res = Path(dst).resolve(strict=False)

    if src_res != dst_res:
        if dst_res.exists():
            taken = _listdir_lower(target_dir)
            suggested = _next_free_name(dst_name, taken)
            raise PreflightMoveError(
                "invalid_body",
                f"destination exists: {dst_res.as_posix()!r}",
                {"suggested_name": suggested},
            )

    du = shutil.disk_usage(target_dir)
    if int(rec.file_size or 0) > int(du.free) * 0.95:
        raise PreflightMoveError(
            "invalid_body",
            "insufficient free space on target volume",
            {"total_bytes": int(rec.file_size or 0), "free_bytes": int(du.free)},
        )

    if src_res == dst_res:
        out = _repo.get_image(int(image_id), db_path=db_path)
        if out is None:
            raise RuntimeError(f"image {image_id} missing")
        return out

    _physical_move(src_res.as_posix(), dst_res.as_posix())
    (
        folder_id,
        path_posix,
        rel,
        filename,
        filename_lc,
        ext,
        mtime_ns,
        file_size,
    ) = _fields_for_moved_file(dst_res.as_posix(), roots)

    wq = _write_queue_handle()
    fut = wq.enqueue_write(
        _repo.MID,
        _repo.UpdateImagePathOp(
            image_id=int(image_id),
            path=path_posix,
            folder_id=folder_id,
            relative_path=rel,
            filename=filename,
            filename_lc=filename_lc,
            ext=ext,
            file_size=file_size,
            mtime_ns=mtime_ns,
            refresh_sync=True,
        ),
    )
    ver = int(fut.result(timeout=120.0))
    _ws_hub.broadcast(
        _ws_hub.IMAGE_UPDATED,
        {"id": int(image_id), "version": ver, "moved_to": path_posix},
    )
    _metadata_sync.notify(int(image_id), ver)

    out = _repo.get_image(int(image_id), db_path=db_path)
    if out is None:
        raise RuntimeError(f"image {image_id} vanished after move")
    return out


def preflight_delete(sel: _repo.SelectionSpec, *, db_path: Path) -> dict:
    """Two-phase bulk delete — phase 1: sandbox + size tally + ``plan_id``."""
    rows = _repo.fetch_selection_move_sources(db_path=db_path, sel=sel)
    if not rows:
        raise PreflightMoveError(
            "invalid_body", "selection resolves to zero images",
        )

    roots = _folders.list_roots(db_path=db_path)
    root_paths = [str(r["path"]) for r in roots]
    plan_rows: List[Tuple[int, str]] = []
    total_bytes = 0
    for image_id, path, fs, _fn in rows:
        try:
            _paths.assert_inside_root(path, root_paths)
        except _paths.SandboxError as exc:
            raise PreflightMoveError(
                "sandbox", str(exc), {"id": int(image_id)},
            ) from exc
        total_bytes += int(fs or 0)
        plan_rows.append((int(image_id), str(path)))

    plan_id = uuid.uuid4().hex
    _delete_store_put(
        plan_id,
        _DeletePlanRecord(
            rows=plan_rows,
            expires_at=time.monotonic() + _PLAN_TTL_SEC,
            total_bytes=int(total_bytes),
        ),
    )
    return {
        "plan_id": plan_id,
        "total": len(plan_rows),
        "total_bytes": int(total_bytes),
    }


def execute_delete(plan_id: str, *, db_path: Path, actor: str = "unknown") -> dict:
    """Phase-2 bulk delete: unlink then ``DeleteImageOp`` per row (T25)."""
    raw = _delete_store_pop(plan_id)
    if raw is None:
        raise PreflightMoveError("not_found", "unknown or expired plan_id")

    wq = _write_queue_handle()
    roots = _folders.list_roots(db_path=db_path)
    root_paths = [str(r["path"]) for r in roots]
    total = len(raw.rows)
    failed: List[dict] = []
    ok_count = 0
    bid = plan_id

    _ws_hub.broadcast(
        _ws_hub.BULK_PROGRESS,
        {
            "plan_id": bid,
            "bulk_id": bid,
            "done": 0,
            "total": total,
            "kind": "delete",
        },
    )

    for i, (image_id, path) in enumerate(raw.rows):
        try:
            _paths.assert_inside_root(path, root_paths)
            p = Path(path)
            if p.is_file():
                os.unlink(str(p))
            fut = wq.enqueue_write(
                _repo.MID,
                _repo.DeleteImageOp(path=p.as_posix()),
            )
            did = fut.result(timeout=120.0)
            if did is not None:
                broadcast_image_deleted(int(did))
                ok_count += 1
        except Exception as exc:  # noqa: BLE001
            failed.append(
                {
                    "id": int(image_id),
                    "code": "internal",
                    "message": str(exc),
                },
            )
            logger.exception("execute_delete id=%s", image_id)
        _ws_hub.broadcast(
            _ws_hub.BULK_PROGRESS,
            {
                "plan_id": bid,
                "bulk_id": bid,
                "done": i + 1,
                "total": total,
                "kind": "delete",
            },
        )
        if (i + 1) % 50 == 0:
            time.sleep(0)

    _ws_hub.broadcast(
        _ws_hub.BULK_COMPLETED,
        {
            "plan_id": bid,
            "bulk_id": bid,
            "done": total,
            "total": total,
            "kind": "delete",
            "failed": failed,
        },
    )
    _audit.log_event(
        "bulk_delete_completed",
        actor,
        {
            "plan_id": bid,
            "deleted": ok_count,
            "failed": len(failed),
            "total_bytes": raw.total_bytes,
        },
    )
    return {"deleted": ok_count, "failed": failed, "plan_id": bid}


def delete_single_image(
    image_id: int,
    *,
    db_path: Path,
    actor: str = "unknown",
) -> dict:
    """Delete one on-disk file then DB row via ``DeleteImageOp`` (T25)."""
    rec = _repo.get_image(int(image_id), db_path=db_path)
    if rec is None:
        raise KeyError(f"image {image_id} not found")

    roots = _folders.list_roots(db_path=db_path)
    root_paths = [str(r["path"]) for r in roots]
    _paths.assert_inside_root(rec.path, root_paths)

    p = Path(rec.path)
    posix_path = p.as_posix()
    if p.is_file():
        try:
            os.unlink(str(p))
        except OSError as exc:
            raise PreflightMoveError(
                "bad_path", str(exc), {"id": int(image_id)},
            ) from exc

    wq = _write_queue_handle()
    fut = wq.enqueue_write(
        _repo.MID,
        _repo.DeleteImageOp(path=posix_path),
    )
    did = fut.result(timeout=120.0)
    if did is not None:
        broadcast_image_deleted(int(did))
    _audit.log_event(
        "image_delete",
        actor,
        {"id": int(image_id), "path": posix_path},
    )
    return {"id": int(image_id), "removed_row": did is not None}


def _write_queue_handle() -> _repo.WriteQueue:
    from . import _write_queue as wq  # noqa: WPS433 — lazy init (routes pattern)

    if wq is None:
        raise RuntimeError("gallery WriteQueue is not started")
    return wq


def _bulk_priority(n_rows: int) -> int:
    return _repo.HIGH if n_rows <= BULK_HIGH_IF_TOTAL_LEQ else _repo.MID


def _tags_from_csv(tags_csv: Optional[str]) -> Tuple[str, ...]:
    if not tags_csv:
        return ()
    return tuple(t for t in str(tags_csv).split(",") if t)


def _merge_tag_lists(
    current: Tuple[str, ...],
    add: List[str],
    remove: List[str],
) -> List[str]:
    rset = {_vocab.normalize_tag(x) for x in remove}
    rset.discard("")
    out = [t for t in current if _vocab.normalize_tag(t) not in rset]
    seen = {_vocab.normalize_tag(t) for t in out}
    for a in add:
        nt = _vocab.normalize_tag(a)
        if nt and nt not in seen:
            out.append(nt)
            seen.add(nt)
    return out


def _parse_patch(body: Any) -> Tuple[Optional[int], Optional[List[str]]]:
    """Return ``(favorite_int_or_none, normalized_tags_or_none)``.

    ``normalized_tags`` is ``None`` when the wire body omits ``tags``;
    otherwise a (possibly empty) list of normalised unique tag strings.
    ``favorite`` is ``None`` when omitted, else ``0`` or ``1``.
    """
    if not isinstance(body, Mapping):
        raise ValueError("PATCH body must be a JSON object")
    unknown = set(body.keys()) - {"favorite", "tags"}
    if unknown:
        raise ValueError(f"unknown PATCH fields: {sorted(unknown)!r}")

    fav_raw = body.get("favorite", None)
    favorite: Optional[int] = None
    if "favorite" in body:
        if fav_raw is True:
            favorite = 1
        elif fav_raw is False:
            favorite = 0
        elif fav_raw in (0, 1):
            favorite = int(fav_raw)
        else:
            raise ValueError("favorite must be a boolean or 0/1")

    normalized_tags: Optional[List[str]] = None
    if "tags" in body:
        raw_tags = body["tags"]
        if raw_tags is None:
            raw_tags = []
        if not isinstance(raw_tags, list):
            raise ValueError("tags must be an array of strings")
        seen: set[str] = set()
        out: List[str] = []
        for item in raw_tags:
            if not isinstance(item, str):
                raise ValueError("each tag must be a string")
            nt = _vocab.normalize_tag(item)
            if not nt or nt in seen:
                continue
            seen.add(nt)
            out.append(nt)
        normalized_tags = out

    if favorite is None and normalized_tags is None:
        raise ValueError("PATCH body must set favorite and/or tags")

    return favorite, normalized_tags


def update_image(
    image_id: int,
    body: Any,
    *,
    db_path: Path,
) -> _repo.ImageRecord:
    """Apply gallery fields; bump ``version``; broadcast; ``notify`` worker."""
    rec = _repo.get_image(int(image_id), db_path=db_path)
    if rec is None:
        raise KeyError(f"image {image_id} not found")

    roots = _folders.list_roots(db_path=db_path)
    root_paths = [r["path"] for r in roots]
    _paths.assert_inside_root(rec.path, root_paths)

    favorite, normalized_tags = _parse_patch(body)

    wq = _write_queue_handle()
    op = _repo.UpdateImageOp(
        image_id=int(image_id),
        favorite=favorite,
        normalized_tags=normalized_tags,
        bump_version=True,
        refresh_sync=True,
    )
    fut = wq.enqueue_write(_repo.HIGH, op)
    new_version = int(fut.result(timeout=30.0))

    data: dict = {"id": int(image_id), "version": new_version}
    if favorite is not None:
        data["favorite"] = bool(favorite)
    if normalized_tags is not None:
        data["tags"] = list(normalized_tags)

    _ws_hub.broadcast(_ws_hub.IMAGE_UPDATED, data)
    _metadata_sync.notify(int(image_id), new_version)

    out = _repo.get_image(int(image_id), db_path=db_path)
    if out is None:
        raise RuntimeError(f"image {image_id} vanished after PATCH")
    return out


def resync_image(image_id: int, *, db_path: Path) -> _repo.ImageRecord:
    """Clear sync retry fields only (no ``version`` bump); ``notify`` worker."""
    rec = _repo.get_image(int(image_id), db_path=db_path)
    if rec is None:
        raise KeyError(f"image {image_id} not found")

    roots = _folders.list_roots(db_path=db_path)
    root_paths = [r["path"] for r in roots]
    _paths.assert_inside_root(rec.path, root_paths)

    wq = _write_queue_handle()
    fut = wq.enqueue_write(_repo.HIGH, _repo.ResyncMetadataOp(image_id=int(image_id)))
    ver = int(fut.result(timeout=30.0))

    _ws_hub.broadcast(
        _ws_hub.IMAGE_SYNC_STATUS_CHANGED,
        {"id": int(image_id), "sync_status": "pending", "version": ver},
    )
    _metadata_sync.notify(int(image_id), ver)

    out = _repo.get_image(int(image_id), db_path=db_path)
    if out is None:
        raise RuntimeError(f"image {image_id} vanished after resync")
    return out


def broadcast_image_upserted(image_id: int) -> None:
    """T20 watcher: indexer wrote a row; notify WS (SPEC 7.9 信封)."""
    _ws_hub.broadcast(_ws_hub.IMAGE_UPSERTED, {"id": int(image_id)})


def broadcast_image_deleted(image_id: int) -> None:
    _ws_hub.broadcast(_ws_hub.IMAGE_DELETED, {"id": int(image_id)})


def broadcast_index_overflow(root_id: int) -> None:
    """T20: Coalescer 触顶 → 降级 delta_scan; 用漂移事件可观测 (前端 T22+)."""
    _ws_hub.broadcast(
        _ws_hub.INDEX_DRIFT_DETECTED,
        {"root_id": int(root_id), "reason": "coalescer_high_watermark"},
    )


def bulk_set_favorite(
    sel: _repo.SelectionSpec,
    value: bool,
    *,
    db_path: Path,
) -> dict:
    """Apply favorite to every image in ``sel``; one op / tx + per-id WS (T23)."""
    rows = _repo.fetch_selection_id_paths(db_path=db_path, sel=sel)
    total = len(rows)
    bulk_id = str(uuid.uuid4())
    if total == 0:
        _ws_hub.broadcast(
            _ws_hub.BULK_COMPLETED,
            {
                "bulk_id": bulk_id, "done": 0, "total": 0, "kind": "favorite",
            },
        )
        return {"affected": 0, "bulk_id": bulk_id}

    pr = _bulk_priority(total)
    roots = _folders.list_roots(db_path=db_path)
    root_paths = [r["path"] for r in roots]
    wq = _write_queue_handle()
    _ws_hub.broadcast(
        _ws_hub.BULK_PROGRESS,
        {
            "bulk_id": bulk_id, "done": 0, "total": total, "kind": "favorite",
        },
    )
    failed: List[dict] = []
    ok_count = 0
    for i, (image_id, path) in enumerate(rows):
        try:
            _paths.assert_inside_root(path, root_paths)
            fut = wq.enqueue_write(
                pr,
                _repo.UpdateImageOp(
                    image_id=int(image_id),
                    favorite=1 if value else 0,
                    normalized_tags=None,
                    bump_version=True,
                    refresh_sync=True,
                ),
            )
            ver = int(fut.result(timeout=120.0))
        except (KeyError, _paths.SandboxError) as e:
            code = "sandbox" if isinstance(e, _paths.SandboxError) else "not_found"
            failed.append(
                {"id": int(image_id), "code": code, "message": str(e)},
            )
            logger.warning("bulk_set_favorite id=%s: %s", image_id, e)
        except Exception as e:  # noqa: BLE001
            failed.append(
                {
                    "id": int(image_id),
                    "code": "internal",
                    "message": str(e),
                },
            )
            logger.exception("bulk_set_favorite id=%s", image_id)
        else:
            ok_count += 1
            _ws_hub.broadcast(
                _ws_hub.IMAGE_UPDATED,
                {
                    "id": int(image_id),
                    "version": ver,
                    "favorite": bool(value),
                },
            )
            _metadata_sync.notify(int(image_id), ver)
        _ws_hub.broadcast(
            _ws_hub.BULK_PROGRESS,
            {
                "bulk_id": bulk_id,
                "done": i + 1,
                "total": total,
                "kind": "favorite",
            },
        )
    _ws_hub.broadcast(
        _ws_hub.BULK_COMPLETED,
        {
            "bulk_id": bulk_id,
            "done": total,
            "total": total,
            "kind": "favorite",
            "failed": failed,
        },
    )
    return {
        "affected": ok_count, "failed": failed, "bulk_id": bulk_id,
    }


def bulk_edit_tags(
    sel: _repo.SelectionSpec,
    add: List[str],
    remove: List[str],
    *,
    db_path: Path,
) -> dict:
    """Add/remove normalised tags on every image in ``sel`` (T23)."""
    add_n = [_vocab.normalize_tag(x) for x in add]
    add_n = [x for x in add_n if x]
    rem_n = [_vocab.normalize_tag(x) for x in remove]
    rem_n = [x for x in rem_n if x]
    if not add_n and not rem_n:
        raise ValueError("add/remove must contain at least one non-empty tag")

    rows = _repo.fetch_selection_id_path_tags_csv(db_path=db_path, sel=sel)
    total = len(rows)
    bulk_id = str(uuid.uuid4())
    if total == 0:
        _ws_hub.broadcast(
            _ws_hub.BULK_COMPLETED,
            {"bulk_id": bulk_id, "done": 0, "total": 0, "kind": "tags"},
        )
        return {"affected": 0, "bulk_id": bulk_id}

    pr = _bulk_priority(total)
    roots = _folders.list_roots(db_path=db_path)
    root_paths = [r["path"] for r in roots]
    wq = _write_queue_handle()
    _ws_hub.broadcast(
        _ws_hub.BULK_PROGRESS,
        {
            "bulk_id": bulk_id, "done": 0, "total": total, "kind": "tags",
        },
    )
    failed: List[dict] = []
    ok_count = 0
    for i, (image_id, path, tags_csv) in enumerate(rows):
        try:
            _paths.assert_inside_root(path, root_paths)
        except _paths.SandboxError as e:
            failed.append(
                {"id": int(image_id), "code": "sandbox", "message": str(e)},
            )
            logger.warning("bulk_edit_tags sandbox id=%s: %s", image_id, e)
            _ws_hub.broadcast(
                _ws_hub.BULK_PROGRESS,
                {
                    "bulk_id": bulk_id,
                    "done": i + 1,
                    "total": total,
                    "kind": "tags",
                },
            )
            continue
        cur = _tags_from_csv(tags_csv)
        new_list = _merge_tag_lists(cur, add_n, rem_n)
        if list(cur) == new_list:
            _ws_hub.broadcast(
                _ws_hub.BULK_PROGRESS,
                {
                    "bulk_id": bulk_id,
                    "done": i + 1,
                    "total": total,
                    "kind": "tags",
                },
            )
            continue
        try:
            fut = wq.enqueue_write(
                pr,
                _repo.UpdateImageOp(
                    image_id=int(image_id),
                    favorite=None,
                    normalized_tags=new_list,
                    bump_version=True,
                    refresh_sync=True,
                ),
            )
            ver = int(fut.result(timeout=120.0))
        except (KeyError, _paths.SandboxError) as e:
            code = "sandbox" if isinstance(e, _paths.SandboxError) else "not_found"
            failed.append(
                {"id": int(image_id), "code": code, "message": str(e)},
            )
            logger.warning("bulk_edit_tags op id=%s: %s", image_id, e)
        except Exception as e:  # noqa: BLE001
            failed.append(
                {
                    "id": int(image_id),
                    "code": "internal",
                    "message": str(e),
                },
            )
            logger.exception("bulk_edit_tags id=%s", image_id)
        else:
            ok_count += 1
            _ws_hub.broadcast(
                _ws_hub.IMAGE_UPDATED,
                {
                    "id": int(image_id),
                    "version": ver,
                    "tags": list(new_list),
                },
            )
            _metadata_sync.notify(int(image_id), ver)
        _ws_hub.broadcast(
            _ws_hub.BULK_PROGRESS,
            {
                "bulk_id": bulk_id,
                "done": i + 1,
                "total": total,
                "kind": "tags",
            },
        )
    _ws_hub.broadcast(
        _ws_hub.BULK_COMPLETED,
        {
            "bulk_id": bulk_id,
            "done": total,
            "total": total,
            "kind": "tags",
            "failed": failed,
        },
    )
    return {
        "affected": ok_count, "failed": failed, "bulk_id": bulk_id,
    }
