"""HTTP routes for the XYZ Image Gallery (T02 placeholder + T10 read endpoints).

T18 adds ``GET /xyz/gallery/ws`` (WebSocket) — see ``gallery/ws_hub.py``.

T19 adds ``PATCH /xyz/gallery/image/{id}``, ``POST …/resync``, and a
``DELETE`` stub — see ``gallery/service.py``.

T21 adds ``GET /xyz/gallery/vocab/{tags,prompts,models}`` for autocomplete
and model vocab (``repo.vocab_lookup`` / ``list_models_for_vocab``).

T22 adds ``GET /xyz/gallery/index/status`` for focus reconciliation
(SPEC §7.8 / §7.9).

T10 scope (TASKS.md T10):
  * SPA shell + static assets (``/xyz/gallery`` + ``/static/*``).
  * Read-only data endpoints backed by ``repo`` read APIs (T09):
      - ``GET /xyz/gallery/folders``
      - ``GET /xyz/gallery/images`` (+ cursor + filter + sort)
      - ``GET /xyz/gallery/images/count``
      - ``GET /xyz/gallery/image/{id}``
      - ``GET /xyz/gallery/image/{id}/neighbors``
  * Binary endpoints:
      - ``GET /xyz/gallery/thumb/{id}``   (delegates to ``thumbs.request``)
      - ``GET /xyz/gallery/raw/{id}`` + ``/raw/{id}/download``  (HTTP Range)
      - ``GET /xyz/gallery/image/{id}/workflow.json``
  * Unified error envelope per SPEC §7.10.

Boundary notes (ARCHITECTURE §2.1 / AI_RULES R5.5 / R7.1):
  * No direct SQL here — all reads go through ``repo``; the request
    handler wraps each call in ``loop.run_in_executor`` (SPEC C-2).
  * ``thumbs.request`` is the only generation entry-point (§4.4); this
    module never opens PIL or writes .webp bytes directly.
  * Workflow chunk extraction goes through ``metadata.read_workflow_chunk``
    — same reason (PIL / PNG-text knowledge stays in ``metadata``).
  * Sandbox (``paths.assert_inside_root``) guards the raw/workflow
    binary paths against DB-side drift.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aiohttp import web

from . import DATA_DIR, DB_PATH, THUMBS_DIR
from . import vocab as _vocab
from . import folders as _folders
from . import indexer as _indexer
from . import metadata as _metadata
from . import paths as _paths
from . import repo as _repo
from . import service as _service
from . import thumbs as _thumbs
from . import ws_hub as _ws_hub

logger = logging.getLogger("xyz.gallery.routes")

_SPA_DIR: Path = Path(__file__).resolve().parent.parent / "js" / "gallery_dist"
_PLACEHOLDER_HTML = (
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    "<title>XYZ Gallery</title></head>"
    "<body>Hello Gallery</body></html>"
)
# SPEC §7.4 verbatim — the cache key already varies by mtime_ns via the
# ?v=... suffix on thumb_url, so "immutable" is honest here.
_THUMB_CACHE_HEADER = "public, max-age=31536000, immutable"

_TRUE_TOKENS = ("1", "true", "yes", "on")

_registered: bool = False


__all__ = ["register"]


# ---- response helpers ----------------------------------------------------

def _error(status: int, code: str, message: str,
           details: Optional[dict] = None) -> web.Response:
    env: dict = {"error": {"code": code, "message": message}}
    if details is not None:
        env["error"]["details"] = details
    return web.json_response(env, status=status)


def _iso(ts: Optional[int]) -> Optional[str]:
    if ts is None:
        return None
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _parse_iso_date(text: Optional[str]) -> Optional[int]:
    # SPEC §6.2 FilterSpec date_* fields are ISO-date on the wire, but
    # repo.FilterSpec takes epoch seconds (image.created_at is int sec).
    # Bare dates (YYYY-MM-DD) are interpreted as midnight UTC — this is
    # the only sensible default with no user tz on the wire.
    if not text:
        return None
    t = text.strip()
    if not t:
        return None
    if len(t) == 10 and t.count("-") == 2:
        t = t + "T00:00:00+00:00"
    else:
        t = t.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except ValueError as exc:
        raise ValueError(f"invalid ISO date {text!r}: {exc}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _is_true(query, key: str, default: bool = False) -> bool:
    raw = query.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_TOKENS


def _serialize_image(rec: _repo.ImageRecord) -> dict:
    v_suffix = f"?v={rec.mtime_ns}" if rec.mtime_ns is not None else ""
    return {
        "id": rec.id,
        "path": rec.path,
        "folder": {
            "id": rec.folder_id,
            "kind": rec.folder_kind,
            "display_name": rec.folder_display_name,
            "relative_dir": rec.relative_dir,
        },
        "filename": rec.filename,
        "ext": rec.ext,
        "size": {
            "width": rec.width,
            "height": rec.height,
            "bytes": rec.file_size,
        },
        "created_at": _iso(rec.created_at),
        "metadata": {
            "positive_prompt": rec.positive_prompt,
            "negative_prompt": rec.negative_prompt,
            "model": rec.model,
            "seed": rec.seed,
            "cfg": rec.cfg,
            "sampler": rec.sampler,
            "scheduler": rec.scheduler,
            "has_workflow": rec.has_workflow,
        },
        "gallery": {
            "favorite": rec.favorite,
            "tags": list(rec.tags),
            "sync_status": rec.sync_status,
            "version": rec.version,
        },
        "thumb_url": f"/xyz/gallery/thumb/{rec.id}{v_suffix}",
        "raw_url": f"/xyz/gallery/raw/{rec.id}",
    }


def _serialize_folder(node: _repo.FolderNode) -> dict:
    return {
        "id": node.id,
        "path": node.path,
        "kind": node.kind,
        "display_name": node.display_name,
        "parent_id": node.parent_id,
        "removable": node.removable,
        "children": [_serialize_folder(c) for c in node.children],
        "image_count_self": node.image_count_self,
        "image_count_recursive": node.image_count_recursive,
    }


def _prompt_extra_stopwords() -> frozenset:
    """Mirror ``indexer`` / ``gallery_config.json`` prompt_stopwords (T15)."""
    try:
        cfg = DATA_DIR / "gallery_config.json"
        if not cfg.is_file():
            return frozenset()
        blob = json.loads(cfg.read_text(encoding="utf-8"))
        arr = blob.get("prompt_stopwords", [])
        return frozenset(str(x).lower() for x in arr if x)
    except Exception:
        return frozenset()


def _parse_filter(query) -> _repo.FilterSpec:
    fav = query.get("favorite", "all")
    if fav not in ("all", "yes", "no"):
        raise ValueError(f"invalid favorite: {fav!r}")
    fid_raw = query.get("folder_id")
    try:
        folder_id = int(fid_raw) if fid_raw not in (None, "") else None
    except ValueError as exc:
        raise ValueError(f"invalid folder_id: {fid_raw!r}") from exc
    extra_sw = _prompt_extra_stopwords()
    tags_and_list: list[str] = []
    for t in query.getall("tag", []):
        nt = _vocab.normalize_tag(t)
        if nt:
            tags_and_list.append(nt)
    tags_and = tuple(dict.fromkeys(tags_and_list))

    prompts_and_list: list[str] = []
    for p in query.getall("prompt", []):
        s = str(p).strip()
        if not s:
            continue
        prompts_and_list.extend(_vocab.normalize_prompt(s, extra_sw))
    prompts_and = tuple(dict.fromkeys(prompts_and_list))

    return _repo.FilterSpec(
        name=(query.get("name") or None),
        favorite=fav,
        model=(query.get("model") or None),
        date_after=_parse_iso_date(query.get("date_after")),
        date_before=_parse_iso_date(query.get("date_before")),
        folder_id=folder_id,
        recursive=_is_true(query, "recursive", default=False),
        tags_and=tags_and,
        prompts_and=prompts_and,
    )


def _parse_sort(query) -> _repo.SortSpec:
    # repo.SortSpec validates key/dir in __post_init__; we bubble the
    # ValueError up to the 400 branch of the caller.
    return _repo.SortSpec(
        key=query.get("sort", "time"),
        dir=query.get("dir", "desc"),
    )


def _parse_limit(query) -> int:
    raw = query.get("limit")
    if raw in (None, ""):
        return _repo.DEFAULT_PAGE_SIZE
    try:
        v = int(raw)
    except ValueError as exc:
        raise ValueError(f"invalid limit: {raw!r}") from exc
    return max(1, min(v, _repo.MAX_PAGE_SIZE))


async def _run(fn, *args, **kwargs):
    # C-2: non-trivial reads / disk work must not block the event loop.
    # repo's read APIs are sync and open a short-lived connection each.
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


def _current_write_queue():
    # Resolved at call-time — gallery._write_queue is None until
    # start_background_services() runs (PROJECT_STATE §5 C-T04); a
    # module-top `from . import _write_queue` would capture that None
    # permanently.
    from . import _write_queue as wq
    return wq


def _content_disposition_attachment(filename: str, fallback_id: int) -> str:
    # RFC 5987 / 6266: both old-browser (ASCII filename=) and modern
    # filename*= (UTF-8 percent-encoded) forms. Non-ASCII filenames are
    # common in Chinese locales (C-5 folder content) so we must not ship
    # a raw high-byte filename= header.
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or (
        f"image_{fallback_id}"
    )
    ascii_name = ascii_name.replace('"', "").replace("\\", "")
    quoted = urllib.parse.quote(filename, safe="")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'


# ---- handlers -------------------------------------------------------------

async def _serve_spa(_request: web.Request) -> web.Response:
    # T10 allows a placeholder body until T11 ships gallery_dist/. If
    # T11 has landed we serve the real shell from disk.
    index = _SPA_DIR / "index.html"
    if index.is_file():
        return web.FileResponse(str(index))
    return web.Response(text=_PLACEHOLDER_HTML, content_type="text/html")


async def _serve_static(request: web.Request) -> web.Response:
    tail = request.match_info.get("tail", "")
    if not tail:
        return _error(404, "not_found", "empty static path")
    spa_root = _SPA_DIR.resolve(strict=False)
    candidate = (_SPA_DIR / tail).resolve(strict=False)
    try:
        candidate.relative_to(spa_root)
    except ValueError:
        return _error(400, "bad_path", "traversal rejected")
    if not candidate.is_file():
        return _error(404, "not_found", f"static file not found: {tail}")
    return web.FileResponse(str(candidate))


async def _get_folders(request: web.Request) -> web.Response:
    include_counts = _is_true(request.query, "include_counts", default=False)
    try:
        tree = await _run(
            _repo.folder_tree,
            db_path=DB_PATH, include_counts=include_counts,
        )
    except Exception as exc:
        logger.exception("folder_tree failed")
        return _error(500, "internal", str(exc))
    return web.json_response([_serialize_folder(n) for n in tree])


async def _list_images(request: web.Request) -> web.Response:
    try:
        flt = _parse_filter(request.query)
        srt = _parse_sort(request.query)
        limit = _parse_limit(request.query)
    except ValueError as exc:
        return _error(400, "invalid_query", str(exc))
    cursor = request.query.get("cursor") or None
    try:
        page = await _run(
            _repo.list_images,
            db_path=DB_PATH, filter=flt, sort=srt,
            cursor=cursor, limit=limit,
        )
    except ValueError as exc:
        return _error(400, "invalid_cursor", str(exc))
    except Exception as exc:
        logger.exception("list_images failed")
        return _error(500, "internal", str(exc))
    return web.json_response({
        "items": [_serialize_image(r) for r in page.items],
        "next_cursor": page.next_cursor,
        "total_estimate": page.total,
        "total_approximate": page.total_approximate,
    })


async def _images_count(request: web.Request) -> web.Response:
    try:
        flt = _parse_filter(request.query)
    except ValueError as exc:
        return _error(400, "invalid_query", str(exc))
    try:
        # Reuse list_images' bounded count path rather than adding a
        # second codepath — limit=1 keeps the row materialisation tiny
        # and the total / total_approximate fields are the whole point.
        page = await _run(
            _repo.list_images,
            db_path=DB_PATH, filter=flt, limit=1,
        )
    except Exception as exc:
        logger.exception("images_count failed")
        return _error(500, "internal", str(exc))
    return web.json_response(
        {"total": page.total, "approximate": page.total_approximate}
    )


def _read_index_status() -> dict:
    page = _repo.list_images(
        db_path=DB_PATH,
        filter=_repo.FilterSpec(),
        sort=_repo.SortSpec(),
        cursor=None,
        limit=1,
    )
    return {
        "scanning": _indexer.is_cold_scanning(),
        "pending_events": 0,
        "last_full_scan_at": None,
        "totals": {
            "images": page.total,
            "approximate": page.total_approximate,
        },
        "last_event_ts": _ws_hub.get_last_event_ts(),
    }


async def _get_index_status(request: web.Request) -> web.Response:
    try:
        return web.json_response(await _run(_read_index_status))
    except Exception as exc:
        logger.exception("index_status failed")
        return _error(500, "internal", str(exc))


def _parse_vocab_limit(query) -> int:
    raw = query.get("limit")
    if raw in (None, ""):
        return _repo.VOCAB_LOOKUP_DEFAULT_LIMIT
    try:
        v = int(raw)
    except ValueError as exc:
        raise ValueError(f"invalid limit: {raw!r}") from exc
    return max(1, min(v, _repo.VOCAB_LOOKUP_MAX_LIMIT))


async def _get_vocab_tags(request: web.Request) -> web.Response:
    try:
        limit = _parse_vocab_limit(request.query)
    except ValueError as exc:
        return _error(400, "invalid_query", str(exc))
    prefix = request.query.get("prefix", "")
    try:
        rows = await _run(
            _repo.vocab_lookup,
            db_path=DB_PATH, kind="tags", prefix=prefix, limit=limit,
        )
    except ValueError as exc:
        return _error(400, "invalid_query", str(exc))
    except Exception as exc:
        logger.exception("vocab_lookup tags failed")
        return _error(500, "internal", str(exc))
    return web.json_response(list(rows))


async def _get_vocab_prompts(request: web.Request) -> web.Response:
    try:
        limit = _parse_vocab_limit(request.query)
    except ValueError as exc:
        return _error(400, "invalid_query", str(exc))
    prefix = request.query.get("prefix", "")
    try:
        rows = await _run(
            _repo.vocab_lookup,
            db_path=DB_PATH, kind="prompts", prefix=prefix, limit=limit,
        )
    except ValueError as exc:
        return _error(400, "invalid_query", str(exc))
    except Exception as exc:
        logger.exception("vocab_lookup prompts failed")
        return _error(500, "internal", str(exc))
    return web.json_response(list(rows))


async def _get_vocab_models(request: web.Request) -> web.Response:
    try:
        models = await _run(_repo.list_models_for_vocab, db_path=DB_PATH)
    except Exception as exc:
        logger.exception("list_models_for_vocab failed")
        return _error(500, "internal", str(exc))
    return web.json_response(list(models))


async def _get_image(request: web.Request) -> web.Response:
    image_id = int(request.match_info["id"])
    try:
        rec = await _run(_repo.get_image, image_id, db_path=DB_PATH)
    except Exception as exc:
        logger.exception("get_image failed")
        return _error(500, "internal", str(exc))
    if rec is None:
        return _error(404, "not_found", f"image {image_id} not found")
    return web.json_response(_serialize_image(rec))


async def _image_neighbors(request: web.Request) -> web.Response:
    image_id = int(request.match_info["id"])
    try:
        flt = _parse_filter(request.query)
        srt = _parse_sort(request.query)
    except ValueError as exc:
        return _error(400, "invalid_query", str(exc))
    try:
        nb = await _run(
            _repo.neighbors, image_id,
            db_path=DB_PATH, filter=flt, sort=srt,
        )
    except Exception as exc:
        logger.exception("neighbors failed")
        return _error(500, "internal", str(exc))
    return web.json_response({"prev_id": nb.prev_id, "next_id": nb.next_id})


async def _get_thumb(request: web.Request) -> web.StreamResponse:
    image_id = int(request.match_info["id"])
    wq = _current_write_queue()
    if wq is None:
        return _error(503, "not_ready", "gallery write queue not started")
    try:
        path = await _run(
            _thumbs.request, image_id,
            db_path=DB_PATH, thumbs_dir=THUMBS_DIR, write_queue=wq,
        )
    except Exception as exc:
        logger.exception("thumb request failed")
        return _error(500, "internal", str(exc))
    if path is None or not Path(path).is_file():
        return _error(404, "not_found",
                      f"thumbnail unavailable for image {image_id}")
    return web.FileResponse(
        str(path),
        headers={"Cache-Control": _THUMB_CACHE_HEADER},
    )


async def _serve_raw(request: web.Request, *, as_attachment: bool
                     ) -> web.StreamResponse:
    image_id = int(request.match_info["id"])
    try:
        rec = await _run(_repo.get_image, image_id, db_path=DB_PATH)
    except Exception as exc:
        logger.exception("get_image for raw failed")
        return _error(500, "internal", str(exc))
    if rec is None:
        return _error(404, "not_found", f"image {image_id} not found")
    try:
        roots = await _run(_folders.list_roots, db_path=DB_PATH)
        root_paths = [r["path"] for r in roots]
        await _run(_paths.assert_inside_root, rec.path, root_paths)
    except _paths.SandboxError as exc:
        return _error(403, "sandbox", str(exc))
    disk_path = Path(rec.path)
    if not disk_path.is_file():
        return _error(404, "not_found",
                      f"file missing on disk: image {image_id}")
    headers: dict = {}
    if as_attachment:
        headers["Content-Disposition"] = _content_disposition_attachment(
            rec.filename, image_id,
        )
    else:
        headers["Content-Disposition"] = "inline"
    # aiohttp's FileResponse handles HTTP Range natively (200 / 206 +
    # Content-Range + byte slicing) — TASKS T10 test #2.
    return web.FileResponse(str(disk_path), headers=headers)


async def _get_raw_inline(request: web.Request) -> web.StreamResponse:
    return await _serve_raw(request, as_attachment=False)


async def _get_raw_download(request: web.Request) -> web.StreamResponse:
    return await _serve_raw(request, as_attachment=True)


def _ws_pong_envelope() -> str:
    # Same shape as SPEC §7.9 (type / data / ts) — application-level ping.
    return json.dumps(
        {"type": "pong", "data": {}, "ts": int(time.time() * 1000)},
        separators=(",", ":"),
    )


async def _ws_handler(request: web.Request) -> web.WebSocketResponse:
    """SPEC §7.9 — server → client push; client may send text ``ping``."""
    from . import ws_hub as _ws_hub

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    await _ws_hub.add_client(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                raw = msg.data.strip()
                if raw.lower() == "ping":
                    await ws.send_str(_ws_pong_envelope())
                    continue
                if raw.startswith("{"):
                    try:
                        obj = json.loads(msg.data)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict) and obj.get("type") == "ping":
                        await ws.send_str(_ws_pong_envelope())
            elif msg.type in (
                web.WSMsgType.CLOSE,
                web.WSMsgType.CLOSING,
                web.WSMsgType.ERROR,
            ):
                break
    finally:
        await _ws_hub.remove_client(ws)
    return ws


async def _get_workflow(request: web.Request) -> web.Response:
    image_id = int(request.match_info["id"])
    try:
        rec = await _run(_repo.get_image, image_id, db_path=DB_PATH)
    except Exception as exc:
        logger.exception("get_image for workflow failed")
        return _error(500, "internal", str(exc))
    if rec is None:
        return _error(404, "not_found", f"image {image_id} not found")
    if not rec.has_workflow:
        # §4 #23: workflow_present=0 → 404 even if the PNG is sitting
        # right there. The detail UI disables the button in that case.
        return _error(404, "no_workflow",
                      f"image {image_id} has no workflow")
    try:
        roots = await _run(_folders.list_roots, db_path=DB_PATH)
        root_paths = [r["path"] for r in roots]
        await _run(_paths.assert_inside_root, rec.path, root_paths)
    except _paths.SandboxError as exc:
        return _error(403, "sandbox", str(exc))
    try:
        text = await _run(_metadata.read_workflow_chunk, rec.path)
    except Exception as exc:
        logger.exception("workflow extraction failed")
        return _error(500, "internal", str(exc))
    if not text:
        return _error(404, "no_workflow",
                      f"workflow chunk absent for {image_id}")
    return web.Response(
        text=text, content_type="application/json",
        headers={
            "Content-Disposition": _content_disposition_attachment(
                f"workflow_{image_id}.json", image_id,
            )
        },
    )


async def _patch_image(request: web.Request) -> web.Response:
    image_id = int(request.match_info["id"])
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        return _error(400, "invalid_body", f"invalid JSON: {exc}")
    try:
        rec = await _run(
            _service.update_image, image_id, body, db_path=DB_PATH,
        )
    except KeyError as exc:
        return _error(404, "not_found", str(exc))
    except ValueError as exc:
        return _error(400, "invalid_body", str(exc))
    except _paths.SandboxError as exc:
        return _error(403, "sandbox", str(exc))
    except RuntimeError as exc:
        msg = str(exc)
        if "WriteQueue is not started" in msg or "not started" in msg:
            return _error(503, "not_ready", msg)
        logger.exception("update_image failed")
        return _error(500, "internal", msg)
    except Exception as exc:
        logger.exception("update_image failed")
        return _error(500, "internal", str(exc))
    return web.json_response(_serialize_image(rec))


async def _post_resync(request: web.Request) -> web.Response:
    image_id = int(request.match_info["id"])
    try:
        rec = await _run(_service.resync_image, image_id, db_path=DB_PATH)
    except KeyError as exc:
        return _error(404, "not_found", str(exc))
    except _paths.SandboxError as exc:
        return _error(403, "sandbox", str(exc))
    except RuntimeError as exc:
        msg = str(exc)
        if "WriteQueue is not started" in msg or "not started" in msg:
            return _error(503, "not_ready", msg)
        logger.exception("resync_image failed")
        return _error(500, "internal", msg)
    except Exception as exc:
        logger.exception("resync_image failed")
        return _error(500, "internal", str(exc))
    return web.json_response(_serialize_image(rec))


async def _delete_image_stub(request: web.Request) -> web.Response:
    image_id = int(request.match_info.get("id", "0"))
    return _error(
        501,
        "not_implemented",
        f"DELETE /xyz/gallery/image/{image_id} is not implemented (T25)",
    )


# ---- registration --------------------------------------------------------

def register(server) -> None:
    """Register gallery HTTP routes onto the host PromptServer.

    ``server`` is ComfyUI's ``PromptServer`` (or any object with a
    ``routes`` attribute compatible with ``aiohttp.web.RouteTableDef``).
    Idempotent: a second call is a no-op.
    """
    global _registered
    if _registered:
        return
    routes = server.routes

    routes.get("/xyz/gallery")(_serve_spa)
    routes.get(r"/xyz/gallery/static/{tail:.*}")(_serve_static)
    routes.get("/xyz/gallery/folders")(_get_folders)
    routes.get("/xyz/gallery/vocab/tags")(_get_vocab_tags)
    routes.get("/xyz/gallery/vocab/prompts")(_get_vocab_prompts)
    routes.get("/xyz/gallery/vocab/models")(_get_vocab_models)
    routes.get("/xyz/gallery/index/status")(_get_index_status)
    routes.get("/xyz/gallery/images")(_list_images)
    routes.get("/xyz/gallery/images/count")(_images_count)
    routes.get(r"/xyz/gallery/image/{id:\d+}")(_get_image)
    routes.get(r"/xyz/gallery/image/{id:\d+}/neighbors")(_image_neighbors)
    routes.get(r"/xyz/gallery/image/{id:\d+}/workflow.json")(_get_workflow)
    routes.patch(r"/xyz/gallery/image/{id:\d+}")(_patch_image)
    routes.post(r"/xyz/gallery/image/{id:\d+}/resync")(_post_resync)
    routes.delete(r"/xyz/gallery/image/{id:\d+}")(_delete_image_stub)
    routes.get(r"/xyz/gallery/thumb/{id:\d+}")(_get_thumb)
    routes.get(r"/xyz/gallery/raw/{id:\d+}")(_get_raw_inline)
    routes.get(r"/xyz/gallery/raw/{id:\d+}/download")(_get_raw_download)
    routes.get("/xyz/gallery/ws")(_ws_handler)

    _registered = True
    logger.info(
        "XYZ Gallery routes registered (/xyz/gallery + vocab + read + "
        "write stub + ws)"
    )
