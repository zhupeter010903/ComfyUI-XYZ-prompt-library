"""T10 offline validation script — HTTP read endpoints.

Mirrors TASKS.md T10 acceptance set (folders / images / thumb / raw /
workflow.json) on an in-process aiohttp server backed by a scratch DB,
scratch thumbs dir, and scratch PNG files on disk. No real
``gallery_data/`` is touched and ComfyUI core modules are not needed.

Style matches test/t07_test.py / test/t08_test.py / test/t09_test.py:
each assertion block is standalone and prints an ``OK`` line; ``main``
runs them sequentially under a single ``tempfile.TemporaryDirectory``.

Run:
    python test/t10_test.py
Expected tail: ``T10 ALL TESTS PASSED``.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

# Put plugin root on sys.path so ``import gallery`` resolves without
# needing to run from inside ComfyUI.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from PIL import Image  # noqa: E402
from PIL.PngImagePlugin import PngInfo  # noqa: E402


# ---- fixture ------------------------------------------------------------

def _make_png(dst: Path, *, workflow_json: str = None,
              color: str = "red", size=(64, 64)) -> Dict[str, int]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    if workflow_json is not None:
        info = PngInfo()
        info.add_text("workflow", workflow_json)
        img.save(dst, format="PNG", pnginfo=info)
    else:
        img.save(dst, format="PNG")
    st = dst.stat()
    return {"size": int(st.st_size), "mtime_ns": int(st.st_mtime_ns)}


def _insert_folder(conn: sqlite3.Connection, *, path: str, kind: str,
                   parent_id=None, display_name=None,
                   removable: int = 0) -> int:
    cur = conn.execute(
        "INSERT INTO folder(path, kind, parent_id, display_name, removable) "
        "VALUES (?, ?, ?, ?, ?)",
        (path, kind, parent_id, display_name, removable),
    )
    return int(cur.lastrowid)


def _insert_image(conn: sqlite3.Connection, **kw) -> int:
    # Test-only shortcut (production writes go through WriteQueue).
    cur = conn.execute(
        "INSERT INTO image("
        "path, folder_id, relative_path, filename, filename_lc, ext, "
        "width, height, file_size, mtime_ns, created_at, "
        "positive_prompt, negative_prompt, model, seed, cfg, sampler, scheduler, "
        "workflow_present, favorite, tags_csv, indexed_at"
        ") VALUES ("
        ":path, :folder_id, :relative_path, :filename, :filename_lc, :ext, "
        ":width, :height, :file_size, :mtime_ns, :created_at, "
        ":positive_prompt, :negative_prompt, :model, :seed, :cfg, "
        ":sampler, :scheduler, :workflow_present, :favorite, :tags_csv, "
        ":indexed_at)",
        {
            "path": kw["path"],
            "folder_id": kw["folder_id"],
            "relative_path": kw["relative_path"],
            "filename": kw["filename"],
            "filename_lc": kw["filename"].lower(),
            "ext": Path(kw["filename"]).suffix.lstrip(".").lower(),
            "width": kw.get("width", 64),
            "height": kw.get("height", 64),
            "file_size": kw["file_size"],
            "mtime_ns": kw["mtime_ns"],
            "created_at": kw["created_at"],
            "positive_prompt": kw.get("positive_prompt"),
            "negative_prompt": kw.get("negative_prompt"),
            "model": kw.get("model"),
            "seed": kw.get("seed"),
            "cfg": kw.get("cfg"),
            "sampler": kw.get("sampler"),
            "scheduler": kw.get("scheduler"),
            "workflow_present": int(kw.get("workflow_present", 0)),
            "favorite": kw.get("favorite"),
            "tags_csv": kw.get("tags_csv"),
            "indexed_at": int(time.time()),
        },
    )
    return int(cur.lastrowid)


def _bootstrap(scratch: Path) -> Dict[str, Any]:
    """Create scratch DB + PNG files + registered-root rows.

    Returns a bag of ids / paths reused across the test cases.
    """
    import gallery as _g
    from gallery import db

    db_path = scratch / "gallery.sqlite"
    conn = db.connect_write(db_path)
    try:
        db.migrate(conn)
    finally:
        conn.close()

    out_root_dir = scratch / "output"
    cst_root_dir = scratch / "custom"
    out_root_dir.mkdir()
    cst_root_dir.mkdir()
    (cst_root_dir / "sub").mkdir()
    outside_dir = scratch / "outside"
    outside_dir.mkdir()

    WORKFLOW = json.dumps({
        "nodes": [{"id": 1, "type": "KSampler"}],
        "links": [],
    })

    a_stat = _make_png(out_root_dir / "a.png",
                       workflow_json=WORKFLOW, color="red")
    b_stat = _make_png(out_root_dir / "b.png", color="green")
    c_stat = _make_png(cst_root_dir / "sub" / "c.png", color="blue")
    # Outside the registered roots — raw/workflow MUST 403.
    x_stat = _make_png(outside_dir / "x.png", color="orange")

    out_root_posix = out_root_dir.resolve().as_posix()
    cst_root_posix = cst_root_dir.resolve().as_posix()

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        out_root = _insert_folder(
            conn, path=out_root_posix, kind="output",
            removable=0, display_name="output",
        )
        cst_root = _insert_folder(
            conn, path=cst_root_posix, kind="custom",
            removable=1, display_name="custom",
        )
        cst_sub = _insert_folder(
            conn, path=cst_root_posix + "/sub", kind="custom",
            parent_id=cst_root, removable=0, display_name="sub",
        )

        id_a = _insert_image(
            conn,
            path=(out_root_dir / "a.png").resolve().as_posix(),
            folder_id=out_root, relative_path="a.png", filename="a.png",
            file_size=a_stat["size"], mtime_ns=a_stat["mtime_ns"],
            created_at=100, model="sdxl",
            positive_prompt="a cat on a mat",
            favorite=1, tags_csv="cat,cute",
            workflow_present=1,
        )
        id_b = _insert_image(
            conn,
            path=(out_root_dir / "b.png").resolve().as_posix(),
            folder_id=out_root, relative_path="b.png", filename="b.png",
            file_size=b_stat["size"], mtime_ns=b_stat["mtime_ns"],
            created_at=200, model="sd15",
            positive_prompt="ocean waves",
            favorite=0, tags_csv="ocean",
            workflow_present=0,
        )
        id_c = _insert_image(
            conn,
            path=(cst_root_dir / "sub" / "c.png").resolve().as_posix(),
            folder_id=cst_root, relative_path="sub/c.png",
            filename="c.png",
            file_size=c_stat["size"], mtime_ns=c_stat["mtime_ns"],
            created_at=300, model="sdxl",
            positive_prompt="a mountain landscape",
            favorite=1, tags_csv="landscape,mountain",
            workflow_present=0,
        )
        # Intentionally outside any registered root — raw/workflow → 403.
        id_outside = _insert_image(
            conn,
            path=(outside_dir / "x.png").resolve().as_posix(),
            folder_id=out_root,  # lie so the filter joins cleanly
            relative_path="x.png", filename="x.png",
            file_size=x_stat["size"], mtime_ns=x_stat["mtime_ns"],
            created_at=400, workflow_present=0,
        )
        # Non-Latin filename to exercise Content-Disposition filename* encoding.
        unicode_name = "cat_\u732b.png"
        u_file = out_root_dir / unicode_name
        u_stat = _make_png(u_file, color="yellow")
        id_unicode = _insert_image(
            conn,
            path=u_file.resolve().as_posix(),
            folder_id=out_root, relative_path=unicode_name,
            filename=unicode_name,
            file_size=u_stat["size"], mtime_ns=u_stat["mtime_ns"],
            created_at=500, workflow_present=0,
        )
        conn.commit()
    finally:
        conn.close()

    thumbs_dir = scratch / "thumbs"
    thumbs_dir.mkdir()

    return {
        "db_path": db_path,
        "thumbs_dir": thumbs_dir,
        "out_root": out_root,
        "cst_root": cst_root,
        "cst_sub": cst_sub,
        "id_a": id_a, "id_b": id_b, "id_c": id_c,
        "id_outside": id_outside, "id_unicode": id_unicode,
        "out_root_dir": out_root_dir,
        "workflow_json": WORKFLOW,
    }


# ---- app wiring ---------------------------------------------------------

class _FakeServer:
    """Minimal stand-in for PromptServer.instance — only exposes .routes."""

    def __init__(self) -> None:
        self.routes = web.RouteTableDef()


def _build_app(ref: Dict[str, Any]):
    """Monkey-patch module globals and build an aiohttp app.

    gallery/routes.py imports DB_PATH / THUMBS_DIR via ``from . import …``
    at module-load time, so the test must mutate ``routes.DB_PATH`` itself
    (not ``gallery.DB_PATH``). ``_current_write_queue()`` does a fresh
    ``from . import _write_queue`` on every call, so a single patch on
    the package attribute suffices for that one.
    """
    import gallery as _g
    from gallery import routes, repo

    # Repoint I/O to scratch.
    routes.DB_PATH = ref["db_path"]
    routes.THUMBS_DIR = ref["thumbs_dir"]
    # Real WriteQueue — thumb generation enqueues InsertThumbCacheOp.
    wq = repo.WriteQueue(ref["db_path"])
    wq.start()
    _g._write_queue = wq
    ref["_wq"] = wq

    # Fresh RouteTableDef per test run — ``register()`` is idempotent
    # (_registered flag), so reset that too.
    fake = _FakeServer()
    routes._registered = False
    routes.register(fake)

    app = web.Application()
    app.add_routes(fake.routes)
    return app


# ---- test cases ---------------------------------------------------------

async def _assert_folders(client: TestClient, ref: Dict[str, Any]) -> None:
    r = await client.get("/xyz/gallery/folders")
    assert r.status == 200, r.status
    data = await r.json()
    assert isinstance(data, list) and len(data) == 2, data
    kinds = sorted(node["kind"] for node in data)
    assert kinds == ["custom", "output"], kinds
    # Every root node without include_counts leaves counts None.
    for node in data:
        assert node["image_count_self"] is None
        assert node["image_count_recursive"] is None
    print("T10 folders (no counts) OK")

    r = await client.get("/xyz/gallery/folders?include_counts=true")
    data = await r.json()
    out = next(n for n in data if n["kind"] == "output")
    # 3 rows carry folder_id=out_root: a.png, b.png, unicode, x.png
    # a/b/unicode live at root (relative_path no '/'), x.png lies flat too.
    assert out["image_count_self"] == 4, out
    assert out["image_count_recursive"] == 4, out
    cst = next(n for n in data if n["kind"] == "custom")
    assert cst["image_count_self"] == 0, cst  # c.png is one level deeper
    assert cst["image_count_recursive"] == 1, cst
    assert len(cst["children"]) == 1
    assert cst["children"][0]["image_count_self"] == 1
    print("T10 folders (with counts) OK")


async def _assert_list_and_cursor(client: TestClient, ref: Dict[str, Any]
                                  ) -> None:
    # Full list, sort by time asc, paged in groups of 2.
    seen = []
    cursor = None
    pages = 0
    while True:
        qs = f"sort=time&dir=asc&limit=2"
        if cursor:
            qs += "&cursor=" + cursor
        r = await client.get("/xyz/gallery/images?" + qs)
        assert r.status == 200
        data = await r.json()
        for item in data["items"]:
            assert item["id"] not in seen
            seen.append(item["id"])
            # Nested shape spot-check.
            assert "folder" in item and "size" in item and "metadata" in item
            assert item["thumb_url"].startswith("/xyz/gallery/thumb/")
            assert "?v=" in item["thumb_url"]
            assert item["raw_url"] == f"/xyz/gallery/raw/{item['id']}"
        pages += 1
        cursor = data["next_cursor"]
        if cursor is None:
            break
    # Five images total (a, b, c, outside, unicode).
    assert len(seen) == 5, seen
    assert pages >= 3
    print(f"T10 list + cursor OK ({pages} pages, {len(seen)} items)")


async def _assert_filters(client: TestClient, ref: Dict[str, Any]) -> None:
    # favorite=yes → id_a + id_c (both favorite=1).
    r = await client.get("/xyz/gallery/images?favorite=yes&sort=time&dir=asc")
    ids = [it["id"] for it in (await r.json())["items"]]
    assert ref["id_a"] in ids and ref["id_c"] in ids
    assert ref["id_b"] not in ids
    print("T10 filter favorite=yes OK")

    # model=sd15 → only id_b
    r = await client.get("/xyz/gallery/images?model=sd15")
    ids = [it["id"] for it in (await r.json())["items"]]
    assert ids == [ref["id_b"]], ids
    print("T10 filter model OK")

    # folder_id=custom (cst_root) non-recursive → 0 items (c is in sub/)
    r = await client.get(
        f"/xyz/gallery/images?folder_id={ref['cst_root']}&recursive=false"
    )
    data = await r.json()
    assert data["items"] == [], data
    # recursive=true → pulls c.png
    r = await client.get(
        f"/xyz/gallery/images?folder_id={ref['cst_root']}&recursive=true"
    )
    ids = [it["id"] for it in (await r.json())["items"]]
    assert ids == [ref["id_c"]], ids
    print("T10 filter folder_id + recursive OK")

    # Date range: after=1970-01-01, before=epoch-of-250 → ids with
    # created_at in [0, 250) = a(100), b(200). Convert 250 sec → an
    # ISO date the parser accepts.
    from datetime import datetime, timezone
    # Use ``Z`` suffix rather than ``+00:00``: a literal ``+`` in a URL
    # query string decodes to space, which would corrupt the ISO value.
    before_iso = datetime.fromtimestamp(250, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    r = await client.get(
        "/xyz/gallery/images?date_after=1970-01-01&"
        f"date_before={before_iso}&sort=time&dir=asc"
    )
    ids = [it["id"] for it in (await r.json())["items"]]
    assert ids == [ref["id_a"], ref["id_b"]], ids
    print("T10 filter date range OK")

    # Invalid sort → 400 envelope.
    r = await client.get("/xyz/gallery/images?sort=bogus")
    assert r.status == 400
    body = await r.json()
    assert "error" in body and body["error"]["code"] == "invalid_query"
    print("T10 invalid sort → 400 envelope OK")


async def _assert_count(client: TestClient, ref: Dict[str, Any]) -> None:
    r = await client.get("/xyz/gallery/images/count")
    data = await r.json()
    assert data["total"] == 5, data
    assert data["approximate"] is False, data
    r = await client.get("/xyz/gallery/images/count?favorite=yes")
    data = await r.json()
    assert data["total"] == 2, data
    print("T10 images/count OK")


async def _assert_single_and_404(client: TestClient, ref: Dict[str, Any]
                                 ) -> None:
    from gallery.routes import _metadata_positive_prompt_normalized

    r = await client.get(f"/xyz/gallery/image/{ref['id_a']}")
    assert r.status == 200
    data = await r.json()
    assert data["filename"] == "a.png"
    assert data["folder"]["kind"] == "output"
    assert data["metadata"]["has_workflow"] is True
    assert data["metadata"]["positive_prompt"] == "a cat on a mat"
    assert data["metadata"]["positive_prompt_normalized"] == _metadata_positive_prompt_normalized(
        "a cat on a mat"
    )
    assert data["gallery"]["favorite"] is True
    assert "cat" in data["gallery"]["tags"]
    assert data["gallery"]["sync_status"] == "ok"
    assert data["gallery"]["version"] == 0
    print("T10 image detail nested shape OK")

    r = await client.get("/xyz/gallery/image/999999")
    assert r.status == 404
    body = await r.json()
    assert body["error"]["code"] == "not_found"
    print("T10 image 404 envelope OK")


async def _assert_neighbors(client: TestClient, ref: Dict[str, Any]
                            ) -> None:
    # sort=time asc → order is a(100), b(200), c(300), x(400), u(500).
    # Anchor = b → prev=a, next=c.
    r = await client.get(
        f"/xyz/gallery/image/{ref['id_b']}/neighbors?sort=time&dir=asc"
    )
    data = await r.json()
    assert data == {"prev_id": ref["id_a"], "next_id": ref["id_c"]}, data
    # Edge anchor (first) → prev=None.
    r = await client.get(
        f"/xyz/gallery/image/{ref['id_a']}/neighbors?sort=time&dir=asc"
    )
    data = await r.json()
    assert data["prev_id"] is None
    assert data["next_id"] == ref["id_b"]
    print("T10 neighbors OK")


async def _assert_thumb(client: TestClient, ref: Dict[str, Any]) -> None:
    r = await client.get(f"/xyz/gallery/thumb/{ref['id_a']}")
    assert r.status == 200
    assert r.headers["Cache-Control"] == (
        "public, max-age=31536000, immutable"
    )
    body = await r.read()
    assert body[:4] == b"RIFF" and b"WEBP" in body[:16], body[:16]
    # Generated file landed under THUMBS_DIR/<2-char-shard>/*.webp.
    produced = list((ref["thumbs_dir"]).rglob("*.webp"))
    assert len(produced) >= 1, produced
    # Second call hits the cached .webp — must still return 200 + header.
    r = await client.get(f"/xyz/gallery/thumb/{ref['id_a']}")
    assert r.status == 200
    print("T10 thumb (generate + cache header) OK")


async def _assert_raw_and_range(client: TestClient, ref: Dict[str, Any]
                                ) -> None:
    r = await client.get(f"/xyz/gallery/raw/{ref['id_a']}")
    assert r.status == 200
    assert r.headers.get("Content-Disposition") == "inline"
    full = await r.read()
    assert full[:8] == b"\x89PNG\r\n\x1a\n"

    # HTTP Range: first 10 bytes.
    r = await client.get(
        f"/xyz/gallery/raw/{ref['id_a']}", headers={"Range": "bytes=0-9"},
    )
    assert r.status == 206, r.status
    cr = r.headers.get("Content-Range", "")
    assert cr.startswith("bytes 0-9/"), cr
    partial = await r.read()
    assert partial == full[:10]
    print("T10 raw + HTTP Range OK")

    # Download variant → attachment disposition including ASCII + utf-8 form.
    r = await client.get(f"/xyz/gallery/raw/{ref['id_a']}/download")
    assert r.status == 200
    disp = r.headers.get("Content-Disposition", "")
    assert disp.startswith("attachment; filename=")
    assert "a.png" in disp
    # Unicode filename — both filename= (ASCII-stripped) and filename*=
    r = await client.get(f"/xyz/gallery/raw/{ref['id_unicode']}/download")
    disp = r.headers.get("Content-Disposition", "")
    assert "filename*=UTF-8''" in disp, disp
    print("T10 raw download + unicode Content-Disposition OK")

    # Sandbox: id_outside has path outside any registered root → 403.
    r = await client.get(f"/xyz/gallery/raw/{ref['id_outside']}")
    assert r.status == 403, r.status
    body = await r.json()
    assert body["error"]["code"] == "sandbox"
    print("T10 raw sandbox → 403 OK")


async def _assert_workflow(client: TestClient, ref: Dict[str, Any]) -> None:
    r = await client.get(f"/xyz/gallery/image/{ref['id_a']}/workflow.json")
    assert r.status == 200
    text = await r.text()
    assert text == ref["workflow_json"], text
    assert r.content_type == "application/json"
    print("T10 workflow.json returns PNG chunk verbatim OK")

    # id_b has workflow_present=0 → 404 "no_workflow" even though on
    # disk the PNG exists. (Semantic 404, not I/O 404.)
    r = await client.get(f"/xyz/gallery/image/{ref['id_b']}/workflow.json")
    assert r.status == 404
    body = await r.json()
    assert body["error"]["code"] == "no_workflow"
    print("T10 workflow.json 404 when workflow_present=0 OK")


async def _assert_spa_and_static(client: TestClient, ref: Dict[str, Any]
                                 ) -> None:
    r = await client.get("/xyz/gallery")
    assert r.status == 200
    assert "text/html" in r.headers["Content-Type"]
    # Traversal rejection — a literal "../" in the path is rejected
    # by the SPA-root containment check.
    r = await client.get("/xyz/gallery/static/%2e%2e%2fboot.ini")
    # Either 400 (traversal rejected) or 404 (resolves inside root but
    # file missing). Both are safe outcomes — never 200.
    assert r.status in (400, 404), r.status
    print("T10 SPA shell + static traversal guard OK")


# ---- runner -------------------------------------------------------------

async def _run_all(ref: Dict[str, Any]) -> None:
    app = _build_app(ref)
    async with TestServer(app) as srv:
        async with TestClient(srv) as client:
            await _assert_folders(client, ref)
            await _assert_list_and_cursor(client, ref)
            await _assert_filters(client, ref)
            await _assert_count(client, ref)
            await _assert_single_and_404(client, ref)
            await _assert_neighbors(client, ref)
            await _assert_thumb(client, ref)
            await _assert_raw_and_range(client, ref)
            await _assert_workflow(client, ref)
            await _assert_spa_and_static(client, ref)


def main() -> None:
    scratch = Path(tempfile.mkdtemp(prefix="xyz_t10_"))
    try:
        ref = _bootstrap(scratch)
        try:
            asyncio.run(_run_all(ref))
        finally:
            wq = ref.get("_wq")
            if wq is not None:
                wq.stop(timeout=1.0)
        print("T10 ALL TESTS PASSED")
    finally:
        # Best-effort cleanup; on Windows a lingering SQLite handle can
        # briefly hold the file — retry once.
        for _ in range(2):
            try:
                shutil.rmtree(scratch)
                break
            except OSError:
                time.sleep(0.2)


if __name__ == "__main__":
    main()
