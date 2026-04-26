"""T24 offline — bulk move preflight/execute + ``UpdateImagePathOp`` (TASKS.md T24).

No ComfyUI. Covers ``repo.fetch_selection_move_sources`` / ``UpdateImagePathOp``,
``service.preflight_move`` / ``execute_move`` / ``move_single_image`` with a
real ``WriteQueue``.

Run:
    python test/t24_test.py
    # or: pytest test/t24_test.py -v
Expected: ``T24 ALL TESTS PASSED``.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Tuple
from unittest import mock

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
    img = Image.new("RGB", (4, 4), "blue")
    info = PngInfo()
    info.add_text("workflow", json.dumps({"n": 1}), zip=False)
    img.save(dst, format="PNG", pnginfo=info)


def _scratch_two_roots_move() -> Tuple[Path, Path, int, int, int, int, int]:
    """``db_path``, ``scratch``, ``root_a_id``, ``root_b_id``, ``img1``, ``img2``, ``dup_id``."""
    from gallery import db

    scratch = Path(tempfile.mkdtemp(prefix="xyz-t24-"))
    db_path = scratch / "gallery.sqlite"
    root_a = scratch / "vol_a"
    root_b = scratch / "vol_b"
    root_a.mkdir()
    root_b.mkdir()
    p1 = root_a / "dup.png"
    p2 = root_a / "other.png"
    _make_png(p1)
    _make_png(p2)
    blocker = root_b / "dup.png"
    _make_png(blocker)

    conn = db.connect_write(db_path)
    try:
        db.migrate(conn)
        fa = root_a.resolve().as_posix()
        fb = root_b.resolve().as_posix()
        id_a = _insert_folder(conn, path=fa, kind="output")
        id_b = _insert_folder(conn, path=fb, kind="custom")
        st1 = p1.stat()
        i1 = _insert_image_min(
            conn,
            path=p1.resolve().as_posix(),
            folder_id=id_a,
            relative_path="dup.png",
            filename="dup.png",
            file_size=st1.st_size,
            mtime_ns=st1.st_mtime_ns,
            positive_prompt="x",
            workflow_present=0,
            favorite=0,
        )
        st2 = p2.stat()
        i2 = _insert_image_min(
            conn,
            path=p2.resolve().as_posix(),
            folder_id=id_a,
            relative_path="other.png",
            filename="other.png",
            file_size=st2.st_size,
            mtime_ns=st2.st_mtime_ns,
            positive_prompt="x",
            workflow_present=0,
            favorite=0,
        )
        conn.commit()
    finally:
        conn.close()
    return db_path, scratch, id_a, id_b, i1, i2, id_b


def test_fetch_selection_move_sources() -> None:
    from gallery import repo as g_repo

    db_path, scratch, _ra, _rb, i1, i2, _ = _scratch_two_roots_move()
    try:
        rows = g_repo.fetch_selection_move_sources(
            db_path=db_path,
            sel=g_repo.SelectionSpec(mode="explicit", explicit_ids=(i1, i2)),
        )
        assert len(rows) == 2
        assert rows[0][0] == i1
        assert rows[0][3] == "dup.png"
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def test_update_image_path_op() -> None:
    from gallery import db
    from gallery import repo as g_repo

    db_path, scratch, id_a, id_b, i1, _i2, _ = _scratch_two_roots_move()
    try:
        wq = g_repo.WriteQueue(db_path)
        wq.start()
        try:
            new_path = (Path(scratch) / "vol_b" / "moved.png").resolve().as_posix()
            import shutil as sh
            sh.copy2(
                str(Path(scratch) / "vol_a" / "dup.png"),
                str(Path(scratch) / "vol_b" / "moved.png"),
            )
            st = Path(new_path).stat()
            op = g_repo.UpdateImagePathOp(
                image_id=i1,
                path=new_path,
                folder_id=id_b,
                relative_path="moved.png",
                filename="moved.png",
                filename_lc="moved.png",
                ext="png",
                file_size=int(st.st_size),
                mtime_ns=int(st.st_mtime_ns),
                refresh_sync=True,
            )
            ver = int(wq.enqueue_write(g_repo.MID, op).result(timeout=5.0))
            assert ver >= 1
        finally:
            wq.stop()
        conn = db.connect_read(db_path)
        try:
            row = conn.execute(
                "SELECT path, folder_id, relative_path, metadata_sync_status, version "
                "FROM image WHERE id=?",
                (i1,),
            ).fetchone()
            assert row is not None
            assert row["folder_id"] == id_b
            assert str(row["path"]).endswith("moved.png")
            assert row["metadata_sync_status"] == "pending"
        finally:
            conn.close()
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def test_execute_move_keeps_metadata_sync_ok() -> None:
    """Pure on-disk move: row path/version update without PNG metadata_sync queue."""
    import gallery as gallery_mod
    from gallery import db
    from gallery import repo as g_repo
    from gallery import service as g_service

    db_path, scratch, _id_a, id_b, _i1, i2, _ = _scratch_two_roots_move()
    try:
        wq = g_repo.WriteQueue(db_path)
        wq.start()
        gallery_mod._write_queue = wq
        try:
            sel = g_repo.SelectionSpec(mode="explicit", explicit_ids=(i2,))
            plan = g_service.preflight_move(sel, id_b, db_path=db_path)
            out = g_service.execute_move(plan["plan_id"], None, db_path=db_path)
            assert int(out.get("moved", 0)) >= 1
            rconn = db.connect_read(db_path)
            try:
                row = rconn.execute(
                    "SELECT metadata_sync_status, path FROM image WHERE id=?",
                    (i2,),
                ).fetchone()
            finally:
                rconn.close()
            assert row is not None
            assert (row["metadata_sync_status"] or "ok") == "ok"
            assert "vol_b" in str(row["path"])
        finally:
            wq.stop()
            gallery_mod._write_queue = None
    finally:
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)


def test_preflight_conflict_and_execute() -> None:
    import gallery as gallery_mod
    from gallery import repo as g_repo
    from gallery import service as g_service
    from gallery import ws_hub as g_ws

    db_path, scratch, _id_a, id_b, i1, i2, _ = _scratch_two_roots_move()
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
            sel = g_repo.SelectionSpec(mode="explicit", explicit_ids=(i1,))
            plan = g_service.preflight_move(sel, id_b, db_path=db_path)
            assert plan["plan_id"]
            assert len(plan["mappings"]) == 1
            m0 = plan["mappings"][0]
            assert m0["conflict"] == "renamed"
            assert "(1).png" in m0["dst"] or m0["dst"].endswith("dup (1).png")

            out = g_service.execute_move(
                plan["plan_id"], None, db_path=db_path,
            )
            assert out["moved"] == 1
            assert not out.get("failed")
            dst_disk = Path(m0["dst"])
            assert dst_disk.is_file()
            assert not (Path(scratch) / "vol_a" / "dup.png").exists()
        finally:
            g_ws.broadcast = orig  # type: ignore[assignment]
            wq.stop()
            gallery_mod._write_queue = None

        kinds = [d.get("kind") for _, d in events if d.get("kind")]
        assert "move" in kinds
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def test_preflight_insufficient_space() -> None:
    from gallery import repo as g_repo
    from gallery import service as g_service
    from gallery.service import PreflightMoveError

    db_path, scratch, _id_a, id_b, i1, i2, _ = _scratch_two_roots_move()
    try:
        du = mock.Mock(free=100, used=1, total=101)

        def _fake_du(_path: str):
            return du

        with mock.patch("gallery.service.shutil.disk_usage", side_effect=_fake_du):
            sel = g_repo.SelectionSpec(mode="explicit", explicit_ids=(i1, i2))
            try:
                g_service.preflight_move(sel, id_b, db_path=db_path)
            except PreflightMoveError as e:
                assert "space" in str(e).lower()
            else:
                raise AssertionError("expected PreflightMoveError")
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def test_move_single_collision_suggestion() -> None:
    import gallery as gallery_mod
    from gallery import repo as g_repo
    from gallery import service as g_service
    from gallery.service import PreflightMoveError

    db_path, scratch, _id_a, id_b, i1, _i2, _ = _scratch_two_roots_move()
    try:
        wq = g_repo.WriteQueue(db_path)
        wq.start()
        gallery_mod._write_queue = wq
        try:
            try:
                g_service.move_single_image(i1, id_b, None, db_path=db_path)
            except PreflightMoveError as e:
                assert e.details.get("suggested_name")
            else:
                raise AssertionError("expected collision PreflightMoveError")
        finally:
            wq.stop()
            gallery_mod._write_queue = None
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def _run() -> None:
    test_fetch_selection_move_sources()
    test_update_image_path_op()
    test_execute_move_keeps_metadata_sync_ok()
    test_preflight_conflict_and_execute()
    test_preflight_insufficient_space()
    test_move_single_collision_suggestion()
    print("T24 ALL TESTS PASSED")


if __name__ == "__main__":
    _run()
