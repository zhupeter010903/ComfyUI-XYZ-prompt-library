"""T19 offline validation — PATCH / resync / ``service.update_image`` (TASKS.md).

No ComfyUI runtime. Covers ``UpdateImageOp`` / ``ResyncMetadataOp``,
``service.update_image`` / ``resync_image``, ``version`` monotonicity,
and ``metadata_sync`` WS notifications after PNG sync.

Run:
    python test/t19_test.py
Expected tail: ``T19 ALL TESTS PASSED``.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Tuple

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from PIL import Image  # noqa: E402
from PIL.PngImagePlugin import PngInfo  # noqa: E402


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


def _make_png(dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (8, 8), "blue")
    info = PngInfo()
    info.add_text("workflow", json.dumps({"n": 1}), zip=False)
    img.save(dst, format="PNG", pnginfo=info)


def _scratch_db_with_png() -> Tuple[Path, Path, int]:
    from gallery import db

    scratch = Path(tempfile.mkdtemp(prefix="xyz-t19-"))
    db_path = scratch / "gallery.sqlite"
    out_dir = scratch / "out"
    out_dir.mkdir()
    png = out_dir / "a.png"
    _make_png(png)

    conn = db.connect_write(db_path)
    try:
        db.migrate(conn)
        root_path = out_dir.resolve().as_posix()
        fid = _insert_folder(conn, path=root_path, kind="output")
        posix_img = png.resolve().as_posix()
        st = png.stat()
        iid = _insert_image(
            conn,
            path=posix_img,
            folder_id=fid,
            relative_path="a.png",
            filename="a.png",
            file_size=st.st_size,
            mtime_ns=st.st_mtime_ns,
            positive_prompt="a red cat",
            workflow_present=1,
            favorite=0,
            tags_csv="alpha,beta",
        )
        conn.commit()
    finally:
        conn.close()

    # Vocab links for tags (mirror indexer): enqueue UpsertImageOp is heavy;
    # minimal INSERTs for tag + image_tag so UpdateImageOp tag path runs.
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("INSERT OR IGNORE INTO tag(name, usage_count) VALUES ('alpha', 0)")
        conn.execute("INSERT OR IGNORE INTO tag(name, usage_count) VALUES ('beta', 0)")
        ra = conn.execute("SELECT id FROM tag WHERE name='alpha' COLLATE NOCASE").fetchone()
        rb = conn.execute("SELECT id FROM tag WHERE name='beta' COLLATE NOCASE").fetchone()
        assert ra and rb
        conn.execute(
            "INSERT INTO image_tag(image_id, tag_id) VALUES (?, ?)",
            (iid, int(ra[0])),
        )
        conn.execute(
            "INSERT INTO image_tag(image_id, tag_id) VALUES (?, ?)",
            (iid, int(rb[0])),
        )
        conn.execute(
            "UPDATE tag SET usage_count = usage_count + 1 WHERE id IN (?, ?)",
            (int(ra[0]), int(rb[0])),
        )
        conn.commit()
    finally:
        conn.close()

    return db_path, scratch, iid


def test_update_image_bumps_version_and_pending() -> None:
    import gallery as gallery_mod
    from gallery import repo as g_repo
    from gallery import service as g_service

    db_path, scratch, iid = _scratch_db_with_png()
    try:
        wq = g_repo.WriteQueue(db_path)
        wq.start()
        gallery_mod._write_queue = wq
        events: list[tuple[str, dict]] = []

        from gallery import ws_hub as g_ws

        orig = g_ws.broadcast

        def _cap(ty: str, data: dict | None = None) -> None:
            events.append((ty, dict(data or {})))
            orig(ty, data)

        g_ws.broadcast = _cap  # type: ignore[assignment]

        try:
            rec = g_service.update_image(
                iid, {"favorite": True}, db_path=db_path,
            )
            assert rec.favorite is True
            assert rec.version == 1
            assert rec.sync_status == "pending"
        finally:
            g_ws.broadcast = orig  # type: ignore[assignment]

        wq.stop()
        assert any(t == g_ws.IMAGE_UPDATED for t, _ in events), events
        upd = [d for t, d in events if t == g_ws.IMAGE_UPDATED][0]
        assert upd["id"] == iid and upd["version"] == 1
    finally:
        gallery_mod._write_queue = None
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)


def test_sequential_patches_version_monotonic() -> None:
    import gallery as gallery_mod
    from gallery import repo as g_repo
    from gallery import service as g_service

    db_path, scratch, iid = _scratch_db_with_png()
    try:
        wq = g_repo.WriteQueue(db_path)
        wq.start()
        gallery_mod._write_queue = wq
        for n in range(1, 6):
            g_service.update_image(
                iid, {"favorite": (n % 2) == 0}, db_path=db_path,
            )
            row = sqlite3.connect(str(db_path)).execute(
                "SELECT version FROM image WHERE id=?", (iid,),
            ).fetchone()
            assert int(row[0]) == n, (n, row)
        wq.stop()
    finally:
        gallery_mod._write_queue = None
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)


def test_resync_no_version_bump() -> None:
    import gallery as gallery_mod
    from gallery import repo as g_repo
    from gallery import service as g_service

    db_path, scratch, iid = _scratch_db_with_png()
    try:
        wq = g_repo.WriteQueue(db_path)
        wq.start()
        gallery_mod._write_queue = wq
        g_service.update_image(iid, {"favorite": True}, db_path=db_path)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE image SET metadata_sync_status='failed', "
                "metadata_sync_retry_count=2, "
                "metadata_sync_next_retry_at=1, "
                "metadata_sync_last_error='boom' WHERE id=?",
                (iid,),
            )
            conn.commit()
        finally:
            conn.close()

        g_service.resync_image(iid, db_path=db_path)
        row = sqlite3.connect(str(db_path)).execute(
            "SELECT version, metadata_sync_status, metadata_sync_retry_count, "
            "metadata_sync_last_error FROM image WHERE id=?",
            (iid,),
        ).fetchone()
        assert int(row[0]) == 1, "version must not bump on /resync"
        assert row[1] == "pending"
        assert int(row[2]) == 0
        assert row[3] is None
        wq.stop()
    finally:
        gallery_mod._write_queue = None
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)


def test_update_image_tags_csv_and_vocab() -> None:
    import gallery as gallery_mod
    from gallery import repo as g_repo
    from gallery import service as g_service

    db_path, scratch, iid = _scratch_db_with_png()
    try:
        wq = g_repo.WriteQueue(db_path)
        wq.start()
        gallery_mod._write_queue = wq
        g_service.update_image(
            iid, {"tags": ["cat", "dog"]}, db_path=db_path,
        )
        conn = sqlite3.connect(str(db_path))
        try:
            (csv,) = conn.execute(
                "SELECT tags_csv FROM image WHERE id=?", (iid,),
            ).fetchone()
            assert "cat" in (csv or "") and "dog" in (csv or "")
            ntags = conn.execute(
                "SELECT COUNT(*) FROM image_tag WHERE image_id=?", (iid,),
            ).fetchone()[0]
            assert int(ntags) == 2
        finally:
            conn.close()
        wq.stop()
    finally:
        gallery_mod._write_queue = None
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)


def test_parse_patch_errors() -> None:
    import gallery.service as g_svc

    try:
        g_svc._parse_patch({})
    except ValueError as exc:
        assert "favorite" in str(exc).lower() or "tags" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError")

    try:
        g_svc._parse_patch({"extra": 1})
    except ValueError as exc:
        assert "unknown" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError")


def test_metadata_sync_broadcasts_ok() -> None:
    """``attempt_sync_write`` emits ``image.sync_status_changed`` on PNG success."""
    import gallery as gallery_mod
    from gallery import metadata_sync as g_sync
    from gallery import repo as g_repo

    db_path, scratch, iid = _scratch_db_with_png()
    try:
        wq = g_repo.WriteQueue(db_path)
        wq.start()
        gallery_mod._write_queue = wq

        events: list = []
        from gallery import ws_hub as g_ws

        orig = g_ws.broadcast

        def _cap(ty: str, data: dict | None = None) -> None:
            events.append((ty, dict(data or {})))
            orig(ty, data)

        g_ws.broadcast = _cap  # type: ignore[assignment]
        try:
            fut = wq.enqueue_write(
                g_repo.HIGH,
                g_repo.UpdateImageOp(
                    image_id=iid,
                    favorite=1,
                    normalized_tags=None,
                ),
            )
            ver = int(fut.result(timeout=10.0))
            g_sync.attempt_sync_write(db_path, wq, iid, ver)
        finally:
            g_ws.broadcast = orig  # type: ignore[assignment]

        wq.stop()

        ok_msgs = [
            d for t, d in events
            if t == g_ws.IMAGE_SYNC_STATUS_CHANGED and d.get("sync_status") == "ok"
        ]
        assert ok_msgs, events
        assert ok_msgs[-1]["version"] == ver
    finally:
        gallery_mod._write_queue = None
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)


def main() -> None:
    test_update_image_bumps_version_and_pending()
    test_sequential_patches_version_monotonic()
    test_resync_no_version_bump()
    test_update_image_tags_csv_and_vocab()
    test_parse_patch_errors()
    test_metadata_sync_broadcasts_ok()
    print("T19 ALL TESTS PASSED")


if __name__ == "__main__":
    main()
