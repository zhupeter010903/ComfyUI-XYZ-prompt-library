"""T33 offline tests — folder HTTP + repo subtree relocate / unindex.

Run:
    python test/t33_folder_ops_test.py
Expected tail: ``T33 ALL TESTS PASSED``.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402


def _insert_folder(conn, *, path, kind, parent_id=None, display_name=None, removable=0):
    cur = conn.execute(
        "INSERT INTO folder(path, kind, parent_id, display_name, removable) "
        "VALUES (?, ?, ?, ?, ?)",
        (path, kind, parent_id, display_name, removable),
    )
    return int(cur.lastrowid)


def _insert_image(conn, **kw):
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
            "width": kw.get("width", 8),
            "height": kw.get("height", 8),
            "file_size": kw["file_size"],
            "mtime_ns": kw["mtime_ns"],
            "created_at": kw.get("created_at", 1),
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


def _bootstrap(scratch: Path) -> dict:
    import gallery as _g
    from gallery import db

    db_path = scratch / "gallery.sqlite"
    conn = db.connect_write(db_path)
    try:
        db.migrate(conn)
    finally:
        conn.close()

    out_dir = scratch / "output"
    out_dir.mkdir()
    sub = out_dir / "sub_a"
    sub.mkdir()
    (sub / "keep.txt").write_text("x", encoding="utf-8")

    out_posix = out_dir.resolve().as_posix()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        rid = _insert_folder(
            conn, path=out_posix, kind="output",
            removable=0, display_name="output",
        )
        sid = _insert_folder(
            conn, path=sub.resolve().as_posix(), kind="output",
            parent_id=rid, removable=0, display_name="sub_a",
        )
        st = (sub / "keep.txt").stat()
        _insert_image(
            conn,
            path=(sub / "keep.txt").resolve().as_posix(),
            folder_id=rid,
            relative_path="sub_a/keep.txt",
            filename="keep.txt",
            file_size=int(st.st_size),
            mtime_ns=int(st.st_mtime_ns),
        )
        conn.commit()
    finally:
        conn.close()

    thumbs = scratch / "thumbs"
    thumbs.mkdir()
    return {
        "db_path": db_path,
        "thumbs_dir": thumbs,
        "out_root_id": rid,
        "sub_folder_id": sid,
        "out_dir": out_dir,
        "sub_dir": sub,
    }


class _FakeServer:
    def __init__(self) -> None:
        self.routes = web.RouteTableDef()


def _build_app(ref: dict):
    import gallery as _g
    from gallery import routes, repo

    routes.DB_PATH = ref["db_path"]
    routes.THUMBS_DIR = ref["thumbs_dir"]
    wq = repo.WriteQueue(ref["db_path"])
    wq.start()
    _g._write_queue = wq
    ref["_wq"] = wq
    fake = _FakeServer()
    routes._registered = False
    routes.register(fake)
    app = web.Application()
    app.add_routes(fake.routes)
    return app


async def _assert_mkdir_rename_move_delete(client: TestClient, ref: dict) -> None:
    rid = ref["out_root_id"]
    r = await client.post(f"/xyz/gallery/folders/{rid}/mkdir", json={"name": "t33_new"})
    assert r.status == 201, await r.text()
    new_path = (ref["out_dir"] / "t33_new").resolve()
    assert new_path.is_dir()

    from gallery import repo as _repo

    rows = _repo.fetch_folder_row(db_path=ref["db_path"], folder_id=rid)
    assert rows is not None
    conn = sqlite3.connect(str(ref["db_path"]))
    try:
        row = conn.execute(
            "SELECT id FROM folder WHERE path = ?", (new_path.as_posix(),),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    new_id = int(row[0])

    r = await client.patch(f"/xyz/gallery/folders/{new_id}", json={"name": "t33_ren"})
    assert r.status == 200, await r.text()
    ren_path = (ref["out_dir"] / "t33_ren").resolve()
    assert ren_path.is_dir()

    r = await client.post(
        f"/xyz/gallery/folders/{new_id}/move",
        json={"parent_id": ref["sub_folder_id"]},
    )
    assert r.status == 200, await r.text()
    moved = (ref["sub_dir"] / "t33_ren").resolve()
    assert moved.is_dir()

    r = await client.delete(f"/xyz/gallery/folders/{new_id}")
    assert r.status == 204, await r.text()
    assert not moved.exists()
    print("T33 mkdir / rename / move / delete OK")


async def _assert_delete_builtin_forbidden(client: TestClient, ref: dict) -> None:
    r = await client.delete(f"/xyz/gallery/folders/{ref['out_root_id']}")
    assert r.status == 403
    print("T33 DELETE built-in root forbidden OK")


async def _assert_post_folders_bad_path(client: TestClient) -> None:
    ghost = Path("Z:/__nonexistent_gallery_path_t33__").as_posix()
    r = await client.post("/xyz/gallery/folders", json={"path": ghost})
    assert r.status == 404, await r.text()
    print("T33 POST /folders missing path → 404 OK")


async def _assert_rescan_scheduled(client: TestClient, ref: dict) -> None:
    r = await client.post(f"/xyz/gallery/folders/{ref['out_root_id']}/rescan", json={})
    assert r.status == 200, await r.text()
    body = await r.json()
    assert body.get("scheduled") is True
    print("T33 rescan scheduled OK")


def _assert_repo_relocate(scratch: Path) -> None:
    from gallery import db, repo

    dp = scratch / "r.sqlite"
    conn = db.connect_write(dp)
    try:
        db.migrate(conn)
    finally:
        conn.close()

    root = scratch / "rroot"
    a = root / "a"
    b = root / "b"
    a.mkdir(parents=True)
    f = a / "f.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n")
    st = f.stat()

    conn = sqlite3.connect(str(dp))
    try:
        rid = _insert_folder(conn, path=root.resolve().as_posix(), kind="custom",
                             removable=1, display_name="r")
        aid = _insert_folder(
            conn, path=a.resolve().as_posix(), kind="custom",
            parent_id=rid, removable=0, display_name="a",
        )
        _insert_image(
            conn,
            path=f.resolve().as_posix(),
            folder_id=rid,
            relative_path="a/f.png",
            filename="f.png",
            file_size=int(st.st_size),
            mtime_ns=int(st.st_mtime_ns),
        )
        conn.commit()
    finally:
        conn.close()

    b.mkdir()
    os.rename(str(a.resolve()), str(b / "a"))

    wq = repo.WriteQueue(dp)
    wq.start()
    try:
        op = repo.RelocateFolderSubtreeDbOp(
            root_id=rid,
            root_path=root.resolve().as_posix(),
            old_prefix=a.resolve().as_posix(),
            new_prefix=(b / "a").resolve().as_posix(),
        )
        wq.enqueue_write(repo.MID, op).result(timeout=30.0)
    finally:
        wq.stop()

    conn = sqlite3.connect(str(dp))
    try:
        row = conn.execute(
            "SELECT path, relative_path FROM image WHERE filename = ?",
            ("f.png",),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert "b/a" in str(row[1]).replace("\\\\", "/")
    print("T33 repo RelocateFolderSubtreeDbOp OK")


async def _main_async() -> None:
    with tempfile.TemporaryDirectory() as td:
        scratch = Path(td)
        ref = _bootstrap(scratch)
        app = _build_app(ref)
        server = TestServer(app)
        client = TestClient(server)
        await client.start_server()
        try:
            await _assert_mkdir_rename_move_delete(client, ref)
            await _assert_delete_builtin_forbidden(client, ref)
            await _assert_post_folders_bad_path(client)
            await _assert_rescan_scheduled(client, ref)
        finally:
            await client.close()
            ref["_wq"].stop()
            # Rescan runs in a daemon thread; give it time to release the DB
            # before Windows removes the temp dir.
            time.sleep(2.0)

    with tempfile.TemporaryDirectory() as td2:
        _assert_repo_relocate(Path(td2))

    print("T33 ALL TESTS PASSED")


def main() -> None:
    asyncio.run(_main_async())


def test_t33_folder_ops_offline() -> None:
    """Pytest entry — same checks as ``python test/t33_folder_ops_test.py``."""
    main()


if __name__ == "__main__":
    main()
