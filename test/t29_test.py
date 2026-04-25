"""T29 offline tests — derivative path exclusion + mis-index cleanup (V1.1-F11)."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo


def _make_png(dst: Path) -> None:
    info = PngInfo()
    info.add_text("prompt", "{}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), "blue").save(dst, pnginfo=info)


def test_is_derivative_path_excluded() -> None:
    from gallery import indexer

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "output"
        root.mkdir()
        good = root / "sub" / "a.png"
        bad = root / "_thumbs" / "cache.png"
        nested = root / "a" / "_thumbs" / "x.png"
        _make_png(good)
        _make_png(bad)
        _make_png(nested)
        rp = str(root.resolve())
        assert not indexer.is_derivative_path_excluded(str(good.resolve()), rp)
        assert indexer.is_derivative_path_excluded(str(bad.resolve()), rp)
        assert indexer.is_derivative_path_excluded(str(nested.resolve()), rp)
        edge = root / "my_thumbs" / "z.png"
        _make_png(edge)
        assert not indexer.is_derivative_path_excluded(str(edge.resolve()), rp)


def test_thumbs_folder_row_path_excluded() -> None:
    """Folder-only ``…/output/_thumbs`` must match T29 exclusion (sidebar tree)."""
    from gallery import paths

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "output"
        root.mkdir()
        thumbs_dir = root / "_thumbs"
        thumbs_dir.mkdir()
        rp = str(root.resolve())
        assert paths.is_derivative_path_excluded(str(thumbs_dir.resolve()), rp)


def test_cold_scan_skips_thumbs_dir() -> None:
    from gallery import db, indexer, repo

    scratch = Path(tempfile.mkdtemp(prefix="xyz_t29_cold_"))
    try:
        db_path = scratch / "gallery.sqlite"
        root_dir = scratch / "out"
        conn = db.connect_write(db_path)
        try:
            db.migrate(conn)
        finally:
            conn.close()
        wq = repo.WriteQueue(db_path)
        wq.start()
        try:
            root_dir.mkdir()
            thumbs = root_dir / "_thumbs"
            thumbs.mkdir()
            _make_png(root_dir / "ok.png")
            _make_png(thumbs / "hidden.png")

            root_posix = root_dir.resolve().as_posix()
            wq.enqueue_write(
                repo.HIGH,
                repo.EnsureFolderOp(
                    path=root_posix, kind="output", removable=0,
                    display_name="out",
                ),
            ).result(timeout=5)
            rconn = db.connect_read(db_path)
            try:
                row = rconn.execute(
                    "SELECT id, path, kind FROM folder WHERE parent_id IS NULL",
                ).fetchone()
            finally:
                rconn.close()
            root = {"id": int(row["id"]), "path": row["path"], "kind": row["kind"]}
            summary = indexer.cold_scan(root, db_path=db_path, write_queue=wq)
            assert summary["enqueued"] == 1, summary
            time.sleep(0.4)
            rconn = db.connect_read(db_path)
            try:
                (n,) = rconn.execute("SELECT COUNT(*) FROM image").fetchone()
                rows = rconn.execute(
                    "SELECT path FROM image WHERE path LIKE '%/_thumbs/%'",
                ).fetchall()
            finally:
                rconn.close()
            assert n == 1, n
            assert len(rows) == 0, rows
        finally:
            wq.stop()
    finally:
        shutil_rmtree(scratch)


def test_index_one_skips_thumbs() -> None:
    from gallery import db, indexer, repo

    scratch = Path(tempfile.mkdtemp(prefix="xyz_t29_one_"))
    try:
        db_path = scratch / "gallery.sqlite"
        root_dir = scratch / "out"
        conn = db.connect_write(db_path)
        try:
            db.migrate(conn)
        finally:
            conn.close()
        wq = repo.WriteQueue(db_path)
        wq.start()
        try:
            root_dir.mkdir()
            bad = root_dir / "_thumbs" / "x.png"
            _make_png(bad)
            root_posix = root_dir.resolve().as_posix()
            wq.enqueue_write(
                repo.HIGH,
                repo.EnsureFolderOp(
                    path=root_posix, kind="output", removable=0,
                    display_name="out",
                ),
            ).result(timeout=5)
            rconn = db.connect_read(db_path)
            try:
                row = rconn.execute(
                    "SELECT id, path, kind FROM folder WHERE parent_id IS NULL",
                ).fetchone()
            finally:
                rconn.close()
            root = {"id": int(row["id"]), "path": row["path"], "kind": row["kind"]}
            iid = indexer.index_one(
                str(bad.resolve()), root=root, db_path=db_path, write_queue=wq,
            )
            assert iid is None
        finally:
            wq.stop()
    finally:
        shutil_rmtree(scratch)


def test_reconcile_drops_existing_file_under_thumbs() -> None:
    from gallery import db, indexer, repo

    scratch = Path(tempfile.mkdtemp(prefix="xyz_t29_rec_"))
    try:
        db_path = scratch / "gallery.sqlite"
        root_dir = scratch / "out"
        conn = db.connect_write(db_path)
        try:
            db.migrate(conn)
        finally:
            conn.close()
        wq = repo.WriteQueue(db_path)
        wq.start()
        try:
            root_dir.mkdir()
            bad = root_dir / "_thumbs" / "legacy.png"
            _make_png(bad)
            root_posix = root_dir.resolve().as_posix()
            wq.enqueue_write(
                repo.HIGH,
                repo.EnsureFolderOp(
                    path=root_posix, kind="output", removable=0,
                    display_name="out",
                ),
            ).result(timeout=5)
            rconn = db.connect_read(db_path)
            try:
                row = rconn.execute(
                    "SELECT id, path, kind FROM folder WHERE parent_id IS NULL",
                ).fetchone()
            finally:
                rconn.close()
            root = {"id": int(row["id"]), "path": row["path"], "kind": row["kind"]}
            folder_id = int(root["id"])
            posix_bad = bad.resolve().as_posix()
            wconn = db.connect_write(db_path)
            try:
                wconn.execute(
                    "INSERT INTO image (path, folder_id, relative_path, filename, "
                    "filename_lc, ext, file_size, mtime_ns, created_at, "
                    "workflow_present, indexed_at, version, metadata_sync_status) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        posix_bad, folder_id, "_thumbs/legacy.png", "legacy.png",
                        "legacy.png", "png", 1, 1, 1, 0, 1, 0, "ok",
                    ),
                )
                wconn.commit()
            finally:
                wconn.close()
            st = indexer.delta_scan(
                root, db_path=db_path, write_queue=wq, mode="light",
            )
            assert int(st.get("removed", 0)) >= 1, st
            time.sleep(0.4)
            rconn = db.connect_read(db_path)
            try:
                row = rconn.execute(
                    "SELECT id FROM image WHERE path = ?", (posix_bad,),
                ).fetchone()
            finally:
                rconn.close()
            assert row is None
        finally:
            wq.stop()
    finally:
        shutil_rmtree(scratch)


def shutil_rmtree(p: Path) -> None:
    import shutil

    shutil.rmtree(p, ignore_errors=True)


def main() -> None:
    test_is_derivative_path_excluded()
    test_cold_scan_skips_thumbs_dir()
    test_index_one_skips_thumbs()
    test_reconcile_drops_existing_file_under_thumbs()
    print("t29_test: all OK")


if __name__ == "__main__":
    main()
