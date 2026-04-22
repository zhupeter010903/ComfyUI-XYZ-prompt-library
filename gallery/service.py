"""XYZ Image Gallery — use-case orchestration (T19).

PATCH / resync flows: sandbox → ``WriteQueue(HIGH)`` → WS fan-out →
``metadata_sync.notify`` (ARCHITECTURE §4.3 / §4.8).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple

from . import folders as _folders
from . import metadata_sync as _metadata_sync
from . import paths as _paths
from . import repo as _repo
from . import vocab as _vocab
from . import ws_hub as _ws_hub

__all__ = [
    "update_image",
    "resync_image",
    "broadcast_image_upserted",
    "broadcast_image_deleted",
    "broadcast_index_overflow",
]


def _write_queue_handle() -> _repo.WriteQueue:
    from . import _write_queue as wq  # noqa: WPS433 — lazy init (routes pattern)

    if wq is None:
        raise RuntimeError("gallery WriteQueue is not started")
    return wq


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
