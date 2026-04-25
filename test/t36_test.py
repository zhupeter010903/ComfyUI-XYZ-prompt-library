"""T36 offline — gallery preferences shape, filter_visibility merge, admin tags HTTP.

Run:
    pytest test/t36_test.py -q
Expected: all passed.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from aiohttp import web

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def test_patch_gallery_preferences_partial_filter_visibility_merges() -> None:
    from gallery import folders

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        cfg = {
            "roots": [],
            "filter_visibility": {
                "name": True,
                "metadata_presence": True,
                "prompt_mode": True,
                "prompt_tokens": True,
                "tags": True,
                "favorite": False,
                "model": True,
                "dates": True,
            },
        }
        (d / "gallery_config.json").write_text(
            json.dumps(cfg, indent=2), encoding="utf-8",
        )
        out = folders.patch_gallery_preferences(
            data_dir=d,
            body={"filter_visibility": {"name": False}},
        )
        assert out["filter_visibility"]["name"] is False
        assert out["filter_visibility"]["favorite"] is False
        disk = json.loads((d / "gallery_config.json").read_text(encoding="utf-8"))
        assert disk["filter_visibility"]["name"] is False
        assert disk["filter_visibility"]["favorite"] is False


def test_sanitize_download_basename_prefix_and_theme() -> None:
    from gallery import folders

    assert folders._sanitize_download_basename_prefix("a b") == "ab"
    assert folders._sanitize_download_basename_prefix("ok-1._x") == "ok-1._x"
    assert folders.normalize_theme("bogus") == "dark"
    assert folders.normalize_theme("LIGHT") == "light"


class _FakeSrv:
    def __init__(self) -> None:
        self.routes = web.RouteTableDef()


async def _admin_tags_http_async(tmp: Path) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    import gallery as gallery_pkg
    from gallery import db as gallery_db
    from gallery import repo
    from gallery import routes as gallery_routes

    cfg = {
        "roots": [],
        "developer_mode": True,
        "theme": "dark",
        "download_basename_prefix": "pre",
        "filter_visibility": {
            "name": True,
            "metadata_presence": True,
            "prompt_mode": True,
            "prompt_tokens": True,
            "tags": True,
            "favorite": True,
            "model": True,
            "dates": True,
        },
    }
    (tmp / "gallery_config.json").write_text(json.dumps(cfg), encoding="utf-8")

    gallery_routes._registered = False
    fake = _FakeSrv()
    gallery_routes.register(fake)
    app = web.Application()
    app.add_routes(fake.routes)

    db_path = tmp / "gallery.sqlite"
    gallery_routes.DB_PATH = db_path
    gallery_routes.DATA_DIR = tmp
    gallery_routes.THUMBS_DIR = tmp / "thumbs"

    conn = gallery_db.connect_write(db_path)
    try:
        gallery_db.migrate(conn)
        conn.execute(
            "INSERT INTO tag(name, usage_count) VALUES ('orphan_unused', 0), ('in_use', 1)",
        )
        conn.commit()
    finally:
        conn.close()

    wq = repo.WriteQueue(db_path)
    wq.start()
    gallery_pkg._write_queue = wq
    try:
        async with TestServer(app) as srv:
            async with TestClient(srv) as client:
                r = await client.get("/xyz/gallery/admin/tags?q=orph&limit=10&offset=0")
                assert r.status == 200
                jtags = await r.json()
                rows = jtags.get("tags") if isinstance(jtags, dict) else jtags
                assert isinstance(rows, list)
                assert any(row.get("name") == "orphan_unused" for row in rows)
                assert int(jtags.get("total", 0)) >= 1

                r2 = await client.post(
                    "/xyz/gallery/admin/tags/delete",
                    data=json.dumps({"name": "orphan_unused"}),
                    headers={"Content-Type": "application/json"},
                )
                assert r2.status == 200

                r3 = await client.get("/xyz/gallery/preferences")
                assert r3.status == 200
                j = await r3.json()
                assert j.get("developer_mode") is True
                assert j.get("download_basename_prefix") == "pre"
                fv = j.get("filter_visibility") or {}
                assert fv.get("name") is True

                r4 = await client.patch(
                    "/xyz/gallery/preferences",
                    data=json.dumps({"theme": "light", "download_basename_prefix": "x@y"}),
                    headers={"Content-Type": "application/json"},
                )
                assert r4.status == 200
                j4 = await r4.json()
                assert j4.get("theme") == "light"
                assert j4.get("download_basename_prefix") == "xy"
    finally:
        wq.stop()


def test_admin_tags_delete_and_preferences_http() -> None:
    with tempfile.TemporaryDirectory() as td:
        asyncio.run(_admin_tags_http_async(Path(td)))


def test_list_tags_admin_pagination_and_total() -> None:
    from gallery import db as gallery_db
    from gallery import repo

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "g.sqlite"
        conn = gallery_db.connect_write(db_path)
        try:
            gallery_db.migrate(conn)
            for i in range(25):
                conn.execute(
                    "INSERT OR IGNORE INTO tag(name, usage_count) VALUES (?, 0)",
                    (f"z_page_{i:03d}",),
                )
            conn.commit()
        finally:
            conn.close()

        p0 = repo.list_tags_admin(
            db_path=db_path, query="", limit=10, offset=0, sort_key="name", sort_dir="asc",
        )
        assert p0["total"] == 25
        assert len(p0["tags"]) == 10
        p1 = repo.list_tags_admin(
            db_path=db_path, query="", limit=10, offset=10, sort_key="name", sort_dir="asc",
        )
        assert p1["total"] == 25
        assert len(p1["tags"]) == 10
        p2 = repo.list_tags_admin(
            db_path=db_path, query="", limit=10, offset=20, sort_key="name", sort_dir="asc",
        )
        assert p2["total"] == 25
        assert len(p2["tags"]) == 5


def test_get_gallery_preferences_defaults_when_config_missing() -> None:
    from gallery import folders

    with tempfile.TemporaryDirectory() as td:
        p = folders.get_gallery_preferences(data_dir=Path(td))
        assert p["download_variant"] == "full"
        assert p.get("download_prompt_each_time") is False
        assert p["developer_mode"] is False
        assert p["theme"] == "dark"
        assert p["download_basename_prefix"] == ""
        fv = p["filter_visibility"]
        assert fv["name"] is True and fv["dates"] is True
