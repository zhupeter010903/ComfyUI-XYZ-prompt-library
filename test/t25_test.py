"""T25 offline — bulk delete, audit log, ``delta_scan`` orphan reconcile (TASKS.md T25).

No ComfyUI.

Run:
    python test/t25_test.py
    # or: pytest test/t25_test.py -v
Expected: ``T25 ALL TESTS PASSED``.
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


def _insert_folder(
    conn: sqlite3.Connection,
    *,
    path: str,
    kind: str,
    parent_id: int | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO folder(path, kind, parent_id, display_name, removable) "
        "VALUES (?, ?, ?, ?, ?)",
        (path, kind, parent_id, kind, 0),
    )
    return int(cur.lastrowid)


def _insert_image_min(conn: sqlite3.Connection, **kw: object) -> int:
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
    img = Image.new("RGB", (4, 4), "red")
    info = PngInfo()
    info.add_text("workflow", json.dumps({"n": 1}), zip=False)
    img.save(dst, format="PNG", pnginfo=info)


def _scratch_delete_two() -> Tuple[Path, Path, int, int, int]:
    """``db_path``, ``scratch``, ``root_id``, ``img_a``, ``img_b``."""
    from gallery import db

    scratch = Path(tempfile.mkdtemp(prefix="xyz-t25-"))
    db_path = scratch / "gallery.sqlite"
    root_dir = scratch / "out"
    root_dir.mkdir()
    pa = root_dir / "a.png"
    pb = root_dir / "b.png"
    _make_png(pa)
    _make_png(pb)

    conn = db.connect_write(db_path)
    try:
        db.migrate(conn)
        rid = _insert_folder(conn, path=root_dir.resolve().as_posix(), kind="output")
        sta = pa.stat()
        stb = pb.stat()
        ia = _insert_image_min(
            conn,
            path=pa.resolve().as_posix(),
            folder_id=rid,
            relative_path="a.png",
            filename="a.png",
            file_size=sta.st_size,
            mtime_ns=sta.st_mtime_ns,
            positive_prompt="x",
            workflow_present=0,
            favorite=0,
        )
        ib = _insert_image_min(
            conn,
            path=pb.resolve().as_posix(),
            folder_id=rid,
            relative_path="b.png",
            filename="b.png",
            file_size=stb.st_size,
            mtime_ns=stb.st_mtime_ns,
            positive_prompt="x",
            workflow_present=0,
            favorite=0,
        )
        conn.commit()
    finally:
        conn.close()
    return db_path, scratch, rid, ia, ib


def test_audit_configure_and_log() -> None:
    from gallery import audit as g_audit

    d = Path(tempfile.mkdtemp(prefix="xyz-t25-audit-"))
    try:
        g_audit.configure(data_dir=d)
        g_audit.log_event("unit_test", "actor-x", {"n": 1})
        logf = d / "gallery_audit.log"
        assert logf.is_file()
        line = logf.read_text(encoding="utf-8").strip().splitlines()[-1]
        obj = json.loads(line)
        assert obj["kind"] == "unit_test"
        assert obj["actor"] == "actor-x"
        assert obj["data"]["n"] == 1
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_preflight_delete_empty_raises() -> None:
    from gallery import repo as g_repo
    from gallery import service as g_service
    from gallery.service import PreflightMoveError

    db_path, scratch, _rid, _ia, _ib = _scratch_delete_two()
    try:
        sel = g_repo.SelectionSpec(mode="explicit", explicit_ids=(99999,))
        try:
            g_service.preflight_delete(sel, db_path=db_path)
        except PreflightMoveError as exc:
            assert exc.code == "invalid_body"
        else:
            raise AssertionError("expected PreflightMoveError")
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def test_bulk_delete_execute() -> None:
    import gallery as gallery_mod
    from gallery import indexer as g_indexer
    from gallery import repo as g_repo
    from gallery import service as g_service
    from gallery import ws_hub as g_ws

    db_path, scratch, rid, ia, ib = _scratch_delete_two()
    try:
        wq = g_repo.WriteQueue(db_path)
        wq.start()
        gallery_mod._write_queue = wq
        events: list[tuple[str, dict]] = []
        orig = g_ws.broadcast

        def _cap(ty: str, data: dict | None = None) -> None:
            events.append((ty, dict(data or {})))
            orig(ty, data)

        g_ws.broadcast = _cap  # type: ignore[assignment]
        try:
            sel = g_repo.SelectionSpec(mode="explicit", explicit_ids=(ia, ib))
            pre = g_service.preflight_delete(sel, db_path=db_path)
            assert pre["plan_id"]
            assert pre["total"] == 2
            assert pre["total_bytes"] > 0

            out = g_service.execute_delete(
                pre["plan_id"], db_path=db_path, actor="test-client",
            )
            assert out["deleted"] == 2
            assert not out.get("failed")

            assert not (Path(scratch) / "out" / "a.png").exists()
            assert not (Path(scratch) / "out" / "b.png").exists()

            conn = sqlite3.connect(str(db_path))
            try:
                n = conn.execute("SELECT COUNT(*) FROM image WHERE id IN (?,?)", (ia, ib)).fetchone()[0]
            finally:
                conn.close()
            assert n == 0

            root = {"id": rid, "path": str(Path(scratch) / "out")}
            st = g_indexer.delta_scan(root, db_path=db_path, write_queue=wq)
            assert st.get("removed", 0) == 0
        finally:
            g_ws.broadcast = orig  # type: ignore[assignment]
            wq.stop()
            gallery_mod._write_queue = None

        kinds = [d.get("kind") for _, d in events if d.get("kind")]
        assert "delete" in kinds
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def test_delta_scan_removes_stale_row() -> None:
    from gallery import db
    from gallery import indexer as g_indexer
    from gallery import repo as g_repo

    scratch = Path(tempfile.mkdtemp(prefix="xyz-t25-stale-"))
    db_path = scratch / "gallery.sqlite"
    root_dir = scratch / "r"
    root_dir.mkdir()
    ghost = root_dir / "gone.png"
    _make_png(ghost)
    conn = db.connect_write(db_path)
    try:
        db.migrate(conn)
        rid = _insert_folder(conn, path=root_dir.resolve().as_posix(), kind="output")
        st = ghost.stat()
        _insert_image_min(
            conn,
            path=ghost.resolve().as_posix(),
            folder_id=rid,
            relative_path="gone.png",
            filename="gone.png",
            file_size=st.st_size,
            mtime_ns=st.st_mtime_ns,
            positive_prompt="x",
            workflow_present=0,
            favorite=0,
        )
        conn.commit()
    finally:
        conn.close()
    ghost.unlink()

    wq = g_repo.WriteQueue(db_path)
    wq.start()
    try:
        root = {"id": rid, "path": str(root_dir.resolve())}
        st = g_indexer.delta_scan(root, db_path=db_path, write_queue=wq)
        assert int(st.get("removed", 0)) >= 1
        assert len(st.get("deleted_ids", [])) >= 1
        rconn = db.connect_read(db_path)
        try:
            n = rconn.execute("SELECT COUNT(*) FROM image").fetchone()[0]
        finally:
            rconn.close()
        assert n == 0
    finally:
        wq.stop()
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def main() -> None:
    test_audit_configure_and_log()
    print("t25 #1 audit OK")
    test_preflight_delete_empty_raises()
    print("t25 #2 preflight empty OK")
    test_bulk_delete_execute()
    print("t25 #3 bulk delete OK")
    test_delta_scan_removes_stale_row()
    print("t25 #4 delta reconcile OK")
    print("T25 ALL TESTS PASSED")


if __name__ == "__main__":
    main()
