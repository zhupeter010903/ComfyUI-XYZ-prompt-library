"""T17 offline validation — ``write_xyz_chunks`` + metadata sync ops (TASKS.md).

No ComfyUI runtime. Covers PNG round-trip, ``SetSyncStatusOp`` /
``SetSyncFailedOp`` / ``SetSyncHardFailedOp``, and
``metadata_sync.attempt_sync_write`` version gating.

Run:
    python test/t17_test.py
Expected tail: ``T17 ALL TESTS PASSED``.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from PIL import Image  # noqa: E402
from PIL.PngImagePlugin import PngInfo  # noqa: E402


def _make_png(dst: Path, *, workflow_json: str | None = None) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (32, 32), "red")
    if workflow_json is not None:
        info = PngInfo()
        info.add_text("workflow", workflow_json)
        info.add_text("xyz_gallery.tags", "oldtag", zip=False)
        info.add_text("xyz_gallery.favorite", "0", zip=False)
        img.save(dst, format="PNG", pnginfo=info)
    else:
        img.save(dst, format="PNG")


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


def test_write_xyz_chunks_roundtrip() -> None:
    from gallery import metadata

    wf = json.dumps({"nodes": [], "links": []})
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.png"
        _make_png(p, workflow_json=wf)
        m0 = metadata.read_comfy_metadata(p)
        assert m0.has_workflow is True
        assert m0.tags == "oldtag"
        metadata.write_xyz_chunks(p, "cat,dog", 1)
        m1 = metadata.read_comfy_metadata(p)
        assert m1.tags == "cat,dog"
        assert m1.favorite == "1"
        assert m1.has_workflow is True
        assert m1.positive_prompt is None
        wf2 = metadata.read_workflow_chunk(p)
        assert wf2 == wf
    print("OK test_write_xyz_chunks_roundtrip")


def test_write_xyz_chunks_clears_mirror_when_none() -> None:
    from gallery import metadata

    wf = json.dumps({"a": 1})
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "y.png"
        _make_png(p, workflow_json=wf)
        metadata.write_xyz_chunks(p, None, None)
        m = metadata.read_comfy_metadata(p)
        assert m.tags is None
        assert m.favorite is None
        assert metadata.read_workflow_chunk(p) == wf
    print("OK test_write_xyz_chunks_clears_mirror_when_none")


def test_write_xyz_chunks_atomic_staging_dir() -> None:
    from gallery import metadata

    wf = json.dumps({"n": 1})
    with tempfile.TemporaryDirectory() as td:
        img_dir = Path(td) / "library"
        img_dir.mkdir()
        staging = Path(td) / "staging_atomic"
        staging.mkdir()
        p = img_dir / "z.png"
        _make_png(p, workflow_json=wf)
        metadata.write_xyz_chunks(p, "solo", 0, atomic_staging_dir=staging)
        assert metadata.read_comfy_metadata(p).tags == "solo"
        assert not any(
            n.is_file()
            and n.name.startswith(metadata.GALLERY_ATOMIC_TMP_PREFIX)
            and n.name.lower().endswith(".png")
            for n in img_dir.iterdir()
        )
        assert not any(staging.glob(f"{metadata.GALLERY_ATOMIC_TMP_PREFIX}*.png"))


def test_set_sync_ops() -> None:
    from gallery import db
    from gallery import repo

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "gallery.sqlite"
        conn = db.connect_write(db_path)
        try:
            db.migrate(conn)
        finally:
            conn.close()
        wq = repo.WriteQueue(db_path)
        wq.start()
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                rid = _insert_folder(conn, path="/tmp/root", kind="output")
                st = os.stat(__file__)
                iid = _insert_image(
                    conn,
                    path="/tmp/root/a.png",
                    folder_id=rid,
                    relative_path="a.png",
                    filename="a.png",
                    file_size=st.st_size,
                    mtime_ns=int(st.st_mtime_ns),
                    tags_csv="t",
                    favorite=0,
                )
                conn.execute(
                    "UPDATE image SET metadata_sync_status = 'pending', "
                    "version = 2, metadata_sync_retry_count = 0 "
                    "WHERE id = ?",
                    (iid,),
                )
                conn.commit()
            finally:
                conn.close()

            fut = wq.enqueue_write(
                repo.LOW,
                repo.SetSyncStatusOp(image_id=iid, expected_version=2),
            )
            fut.result(timeout=5.0)
            rconn = db.connect_read(db_path)
            try:
                row = rconn.execute(
                    "SELECT metadata_sync_status, version FROM image WHERE id = ?",
                    (iid,),
                ).fetchone()
            finally:
                rconn.close()
            assert row["metadata_sync_status"] == "ok"
            assert int(row["version"]) == 2

            fut_sz = wq.enqueue_write(
                repo.HIGH,
                repo.SetSyncStatusOp(
                    image_id=iid,
                    expected_version=2,
                    refresh_file_size=42,
                    refresh_mtime_ns=99,
                ),
            )
            fut_sz.result(timeout=5.0)
            rconn = db.connect_read(db_path)
            try:
                row_sz = rconn.execute(
                    "SELECT file_size, mtime_ns FROM image WHERE id = ?",
                    (iid,),
                ).fetchone()
            finally:
                rconn.close()
            assert int(row_sz["file_size"]) == 42
            assert int(row_sz["mtime_ns"]) == 99

            fut2 = wq.enqueue_write(
                repo.LOW,
                repo.SetSyncStatusOp(image_id=iid, expected_version=1),
            )
            fut2.result(timeout=5.0)
            rconn = db.connect_read(db_path)
            try:
                row2 = rconn.execute(
                    "SELECT metadata_sync_status FROM image WHERE id = ?",
                    (iid,),
                ).fetchone()
            finally:
                rconn.close()
            assert row2["metadata_sync_status"] == "ok"

            now = int(time.time())
            fut3 = wq.enqueue_write(
                repo.LOW,
                repo.SetSyncFailedOp(
                    image_id=iid,
                    expected_version=2,
                    error="boom",
                    now=now,
                ),
            )
            fut3.result(timeout=5.0)
            rconn = db.connect_read(db_path)
            try:
                row3 = rconn.execute(
                    "SELECT metadata_sync_status, metadata_sync_retry_count, "
                    "metadata_sync_next_retry_at, metadata_sync_last_error "
                    "FROM image WHERE id = ?",
                    (iid,),
                ).fetchone()
            finally:
                rconn.close()
            assert row3["metadata_sync_status"] == "failed"
            assert int(row3["metadata_sync_retry_count"]) == 1
            assert row3["metadata_sync_last_error"] == "boom"
            assert int(row3["metadata_sync_next_retry_at"]) == now + 5

            fut4 = wq.enqueue_write(
                repo.LOW,
                repo.SetSyncHardFailedOp(
                    image_id=iid,
                    expected_version=2,
                    error="not png",
                ),
            )
            fut4.result(timeout=5.0)
            rconn = db.connect_read(db_path)
            try:
                row4 = rconn.execute(
                    "SELECT metadata_sync_retry_count, metadata_sync_next_retry_at "
                    "FROM image WHERE id = ?",
                    (iid,),
                ).fetchone()
            finally:
                rconn.close()
            assert int(row4["metadata_sync_retry_count"]) == 3
            assert row4["metadata_sync_next_retry_at"] is None
        finally:
            wq.stop()
    print("OK test_set_sync_ops")


def test_attempt_sync_version_skip_and_success() -> None:
    from gallery import db
    from gallery import metadata_sync
    from gallery import repo
    from gallery import metadata

    wf = json.dumps({"nodes": [{"id": 1}], "links": []})
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "gallery.sqlite"
        png_path = Path(td) / "out" / "a.png"
        _make_png(png_path, workflow_json=wf)
        st = png_path.stat()

        conn = db.connect_write(db_path)
        try:
            db.migrate(conn)
        finally:
            conn.close()

        wq = repo.WriteQueue(db_path)
        wq.start()
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                rid = _insert_folder(
                    conn, path=Path(td).joinpath("out").resolve().as_posix(),
                    kind="output",
                )
                iid = _insert_image(
                    conn,
                    path=png_path.resolve().as_posix(),
                    folder_id=rid,
                    relative_path="a.png",
                    filename="a.png",
                    file_size=int(st.st_size),
                    mtime_ns=int(st.st_mtime_ns),
                    tags_csv="alpha,beta",
                    favorite=1,
                )
                conn.execute(
                    "UPDATE image SET metadata_sync_status = 'pending', "
                    "version = 5 WHERE id = ?",
                    (iid,),
                )
                conn.commit()
            finally:
                conn.close()

            metadata_sync.attempt_sync_write(
                Path(db_path), wq, iid, 4,
            )
            m_mid = metadata.read_comfy_metadata(png_path)
            assert m_mid.tags == "oldtag"

            metadata_sync.attempt_sync_write(
                Path(db_path), wq, iid, 5,
            )
            m_after = metadata.read_comfy_metadata(png_path)
            assert m_after.tags == "alpha,beta"
            assert m_after.favorite == "1"
            assert m_after.has_workflow is True

            rconn = db.connect_read(db_path)
            try:
                row = rconn.execute(
                    "SELECT metadata_sync_status, version FROM image WHERE id = ?",
                    (iid,),
                ).fetchone()
            finally:
                rconn.close()
            assert row["metadata_sync_status"] == "ok"
            assert int(row["version"]) == 5
        finally:
            wq.stop()
    print("OK test_attempt_sync_version_skip_and_success")


def test_attempt_sync_non_png_hard_fail() -> None:
    from gallery import db
    from gallery import metadata_sync
    from gallery import repo

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "gallery.sqlite"
        jpg = Path(td) / "x.jpg"
        Image.new("RGB", (4, 4), "blue").save(jpg, format="JPEG")
        st = jpg.stat()

        conn = db.connect_write(db_path)
        try:
            db.migrate(conn)
        finally:
            conn.close()

        wq = repo.WriteQueue(db_path)
        wq.start()
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                rid = _insert_folder(conn, path=Path(td).as_posix(), kind="output")
                iid = _insert_image(
                    conn,
                    path=jpg.resolve().as_posix(),
                    folder_id=rid,
                    relative_path="x.jpg",
                    filename="x.jpg",
                    file_size=int(st.st_size),
                    mtime_ns=int(st.st_mtime_ns),
                    tags_csv="a",
                    favorite=0,
                )
                conn.execute(
                    "UPDATE image SET metadata_sync_status = 'pending', "
                    "version = 1 WHERE id = ?",
                    (iid,),
                )
                conn.commit()
            finally:
                conn.close()

            metadata_sync.attempt_sync_write(Path(db_path), wq, iid, 1)
            rconn = db.connect_read(db_path)
            try:
                row = rconn.execute(
                    "SELECT metadata_sync_status, metadata_sync_retry_count, "
                    "metadata_sync_last_error FROM image WHERE id = ?",
                    (iid,),
                ).fetchone()
            finally:
                rconn.close()
            assert row["metadata_sync_status"] == "failed"
            assert int(row["metadata_sync_retry_count"]) == 3
            assert "PNG" in (row["metadata_sync_last_error"] or "")
        finally:
            wq.stop()
    print("OK test_attempt_sync_non_png_hard_fail")


def main() -> None:
    test_write_xyz_chunks_roundtrip()
    test_write_xyz_chunks_clears_mirror_when_none()
    test_write_xyz_chunks_atomic_staging_dir()
    test_set_sync_ops()
    test_attempt_sync_version_skip_and_success()
    test_attempt_sync_non_png_hard_fail()
    print("T17 ALL TESTS PASSED")


if __name__ == "__main__":
    main()
