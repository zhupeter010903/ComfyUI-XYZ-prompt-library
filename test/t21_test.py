"""T21 offline validation — ``/vocab/*``, ``repo.vocab_lookup``, junction filters.

No ComfyUI. Covers:
  * ``vocab_lookup`` prefix / empty-prefix ordering (usage_count DESC);
  * ``list_models_for_vocab`` (alphabetical) / ``model_vocab_label``;
  * ``list_images`` tag / prompt AND via ``image_tag`` / ``image_prompt_token``;
  * HTTP ``GET /xyz/gallery/vocab/{tags,prompts,models}`` + ``/images`` query.

Run:
    python test/t21_test.py
Or:
    pytest test/t21_test.py -q

Expected tail: ``T21 ALL TESTS PASSED``.
"""
from __future__ import annotations

import asyncio
import shutil
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


def _insert_folder(conn: sqlite3.Connection, *, path: str, kind: str) -> int:
    cur = conn.execute(
        "INSERT INTO folder(path, kind, parent_id, display_name, removable) "
        "VALUES (?, ?, ?, ?, ?)",
        (path, kind, None, kind, 0),
    )
    return int(cur.lastrowid)


def _insert_image(conn: sqlite3.Connection, **kw: object) -> int:
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
            "filename_lc": str(kw["filename"]).lower(),
            "ext": Path(str(kw["filename"])).suffix.lstrip(".").lower(),
            "width": kw.get("width", 32),
            "height": kw.get("height", 32),
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


def _bootstrap_db(scratch: Path) -> tuple[Path, int, int, int]:
    from gallery import db
    from gallery import vocab
    from gallery.repo import UpsertVocabAndLinksOp

    db_path = scratch / "gallery.sqlite"
    conn = db.connect_write(db_path)
    try:
        db.migrate(conn)
        root = _insert_folder(conn, path="/t21/out", kind="output")
        id_hi = _insert_image(
            conn,
            path="/t21/out/hi.png",
            folder_id=root,
            relative_path="hi.png",
            filename="hi.png",
            file_size=10,
            mtime_ns=1,
            positive_prompt="alpha, beta, gamma",
            tags_csv="foo,bar",
            model="model-b",
        )
        id_lo = _insert_image(
            conn,
            path="/t21/out/lo.png",
            folder_id=root,
            relative_path="lo.png",
            filename="lo.png",
            file_size=11,
            mtime_ns=2,
            positive_prompt="alpha, delta",
            tags_csv="foo",
            model="model-a",
        )
        id_both = _insert_image(
            conn,
            path="/t21/out/both.png",
            folder_id=root,
            relative_path="both.png",
            filename="both.png",
            file_size=12,
            mtime_ns=3,
            positive_prompt="beta, gamma",
            tags_csv="foo,bar",
            model="model-a",
        )
        conn.commit()
    finally:
        conn.close()

    conn = db.connect_write(db_path)
    try:
        for iid, pp, tags in (
            (id_hi, "alpha, beta, gamma", ["foo", "bar"]),
            (id_lo, "alpha, delta", ["foo"]),
            (id_both, "beta, gamma", ["foo", "bar"]),
        ):
            toks = list(vocab.normalize_prompt(pp, frozenset()))
            UpsertVocabAndLinksOp(
                image_id=iid,
                prompt_tokens=toks,
                tag_names=tags,
            ).apply(conn)
        conn.execute(
            "UPDATE tag SET usage_count = 99 WHERE name = 'foo' COLLATE NOCASE",
        )
        conn.execute(
            "UPDATE tag SET usage_count = 1 WHERE name = 'bar' COLLATE NOCASE",
        )
        conn.execute(
            "UPDATE prompt_token SET usage_count = 50 WHERE token = 'alpha' COLLATE NOCASE",
        )
        conn.execute(
            "UPDATE prompt_token SET usage_count = 10 WHERE token = 'beta' COLLATE NOCASE",
        )
        conn.commit()
    finally:
        conn.close()

    return db_path, id_hi, id_lo, id_both


def check_repo_vocab_lookup(db_path: Path) -> None:
    from gallery import repo

    rows = repo.vocab_lookup(db_path=db_path, kind="tags", prefix="", limit=5)
    assert rows and rows[0]["name"] == "foo", rows
    assert rows[0]["usage_count"] == 99

    rows_p = repo.vocab_lookup(db_path=db_path, kind="prompts", prefix="be", limit=10)
    names = [r["name"] for r in rows_p]
    assert "beta" in names, names


def check_repo_list_models(db_path: Path) -> None:
    from gallery import repo

    rows = repo.list_models_for_vocab(db_path=db_path)
    assert len(rows) == 2, rows
    assert rows[0]["model"] == "model-a" and rows[0]["usage_count"] == 2
    assert rows[0]["label"] == "model-a"
    assert rows[1]["model"] == "model-b" and rows[1]["usage_count"] == 1
    assert repo.model_vocab_label("animayume_v04.safetensors") == "animayume_v04"
    assert repo.model_vocab_label("Foo.CKPT") == "Foo"


def check_repo_list_images_junction(
    db_path: Path, id_hi: int, id_lo: int, id_both: int,
) -> None:
    from gallery import repo

    pg = repo.list_images(
        db_path=db_path,
        filter=repo.FilterSpec(tags_and=("foo", "bar")),
        limit=50,
    )
    got = {r.id for r in pg.items}
    assert got == {id_hi, id_both}, got

    pg2 = repo.list_images(
        db_path=db_path,
        filter=repo.FilterSpec(prompts_and=("alpha", "beta")),
        limit=50,
    )
    got2 = {r.id for r in pg2.items}
    assert got2 == {id_hi}, got2


def check_routes_vocab_and_parse(scratch: Path, db_path: Path) -> None:
    from gallery import routes

    fake = type("S", (), {"routes": web.RouteTableDef()})()
    routes._registered = False
    routes.DB_PATH = db_path
    routes.THUMBS_DIR = scratch / "thumbs"
    routes.THUMBS_DIR.mkdir(exist_ok=True)
    routes.register(fake)
    app = web.Application()
    app.add_routes(fake.routes)

    async def run_http() -> None:
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()
        try:
            r = await client.get("/xyz/gallery/vocab/tags?prefix=f&limit=5")
            assert r.status == 200
            data = await r.json()
            assert isinstance(data, list) and data[0]["name"] == "foo"

            r2 = await client.get("/xyz/gallery/vocab/models")
            assert r2.status == 200
            m = await r2.json()
            assert len(m) == 2 and m[0]["model"] == "model-a"
            assert m[0]["usage_count"] == 2 and m[0]["label"] == "model-a"

            r3 = await client.get(
                "/xyz/gallery/vocab/prompts?prefix=al&limit=10",
            )
            assert r3.status == 200
            p = await r3.json()
            assert any(x["name"] == "alpha" for x in p)

            r4 = await client.get(
                "/xyz/gallery/images?tag=foo&tag=bar&limit=50",
            )
            assert r4.status == 200
            body = await r4.json()
            ids = {it["id"] for it in body["items"]}
            assert len(ids) == 2
        finally:
            await client.close()
            await server.close()

    asyncio.run(run_http())


def main() -> None:
    scratch = Path(tempfile.mkdtemp(prefix="xyz-t21-run-"))
    try:
        db_path, id_hi, id_lo, id_both = _bootstrap_db(scratch)
        check_repo_vocab_lookup(db_path)
        print("T21 repo vocab_lookup OK")
        check_repo_list_models(db_path)
        print("T21 repo list_models_for_vocab OK")
        check_repo_list_images_junction(db_path, id_hi, id_lo, id_both)
        print("T21 repo list_images junction AND OK")
        check_routes_vocab_and_parse(scratch, db_path)
        print("T21 HTTP vocab + /images tag AND OK")
        print("\nT21 ALL TESTS PASSED")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_t21_offline_bundle(tmp_path: Path) -> None:
    """Pytest entry — same checks as ``python test/t21_test.py``."""
    db_path, id_hi, id_lo, id_both = _bootstrap_db(tmp_path)
    check_repo_vocab_lookup(db_path)
    check_repo_list_models(db_path)
    check_repo_list_images_junction(db_path, id_hi, id_lo, id_both)
    check_routes_vocab_and_parse(tmp_path, db_path)


if __name__ == "__main__":
    main()
