"""T20 offline — ``merge_watcher_state`` / ``DeleteImageOp`` / coalescer overflow.

Run: ``python test/t20_test.py``
No ComfyUI, no real FS observer (``watchdog`` 仅作 Coalescer 等纯逻辑;
``start_file_watchers`` 不在本脚本冷启动, 由半自动 Comfy 场景测).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest.mock as mock
from pathlib import Path
from typing import Any, Dict

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from gallery import db as gallery_db
from gallery import repo as gallery_repo
from gallery import service as gallery_service
from gallery import ws_hub
from gallery import watcher as gallery_watcher


def _make_wq(db_path: Path) -> "gallery_repo.WriteQueue":
    wq = gallery_repo.WriteQueue(db_path)
    wq.start()
    return wq


def _scratch_with_root(tmp: Path) -> tuple[Path, Path, Dict[str, Any], Any]:
    """空库 + 一条根 + WriteQueue. root dict 可喂 ``index_one``/Coalescer."""
    dbs = tmp / "gallery.sqlite"
    dbs.touch()
    c = gallery_db.connect_write(dbs)
    try:
        gallery_db.migrate(c)
        c.execute(
            "INSERT INTO folder (path, kind, parent_id, display_name, removable) "
            "VALUES (?, 'output', NULL, 'o', 0)", (str(tmp / "r").replace("\\", "/"),),
        )
        rid = int(c.execute("SELECT last_insert_rowid()").fetchone()[0])
    finally:
        c.close()
    (tmp / "r").mkdir()
    wq = _make_wq(dbs)
    root = {
        "id": rid, "path": (tmp / "r").as_posix(), "kind": "output",
    }
    return dbs, tmp, root, wq


def _merge_cases() -> None:
    m = gallery_watcher.merge_watcher_state
    assert m(None, "u") == "u"
    assert m(None, "d") == "d"
    assert m("u", "u") == "u"
    assert m("u", "d") is None
    assert m("d", "u") == "u"
    assert m("d", "d") == "d"
    # ValueError
    try:
        m("u", "x")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
    print("T20 merge_watcher_state OK")


def _delete_op() -> None:
    th = Path(tempfile.mkdtemp())
    try:
        dbs, rdir, root, wq = _scratch_with_root(th)
        f = rdir / "r" / "x.png"
        f.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
            b"\x90wS\xde\x00\x00\x00\x0bIDAT\x08\xd7c\xf8"
            b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00IEND\xaeB`\x82",
        )
        from gallery import indexer as gidx

        iid = gidx.index_one(
            f, root=root, db_path=dbs, write_queue=wq,
        )
        assert iid and iid > 0
        conn = gallery_db.connect_read(dbs)
        try:
            row = conn.execute("SELECT 1 FROM image WHERE id=?", (iid,)).fetchone()
        finally:
            conn.close()
        assert row
        f.unlink()
        iid2 = gidx.delete_one(
            f, db_path=dbs, write_queue=wq,
        )
        assert iid2 == iid
        conn = gallery_db.connect_read(dbs)
        try:
            n = conn.execute("SELECT COUNT(*) AS n FROM image WHERE id=?", (iid,)).fetchone()["n"]
        finally:
            conn.close()
        assert int(n) == 0
    finally:
        wq.stop(timeout=2.0)
        shutil.rmtree(th, ignore_errors=True)
    print("T20 delete_one + DeleteImageOp path OK")


def _coalescer_high_water() -> None:
    th = Path(tempfile.mkdtemp())
    try:
        dbs, rdir, root, wq = _scratch_with_root(th)

        class TDelta:
            def __init__(self) -> None:
                self.n = 0

            def request(self) -> None:
                self.n += 1

        class TCoal(gallery_watcher.Coalescer):
            HIGH_WATERMARK = 2
            _TICK_S = 0.2

        td = TDelta()
        c = TCoal(root=root, db_path=dbs, write_queue=wq, delta=td)
        with mock.patch("gallery.service.broadcast_index_overflow", autospec=True) as pfx:
            c.add("A", (rdir / "r" / "a").as_posix(), "u")
            c.add("B", (rdir / "r" / "b").as_posix(), "u")
            c.add("C", (rdir / "r" / "c").as_posix(), "u")
            assert pfx.call_count == 1
        assert td.n == 1
    finally:
        wq.stop(timeout=2.0)
        shutil.rmtree(th, ignore_errors=True)
    print("T20 coalescer overflow OK")


def _service_not_raises() -> None:
    """WS 无环时仍不发崩 (skip)."""
    ws_hub.reset_clients()
    gallery_service.broadcast_image_upserted(1)
    gallery_service.broadcast_image_deleted(2)
    gallery_service.broadcast_index_overflow(1)
    print("T20 service broadcast smoke OK")


def _debounce_drain() -> None:
    """Coalescer 启动后：短 debounce + 合法 PNG，tick 后应能 ``index_one`` 落行。"""
    th = Path(tempfile.mkdtemp())
    try:
        dbs, rdir, root, wq = _scratch_with_root(th)

        class TDelta:
            def request(self) -> None:  # noqa: D401
                pass

        class TCoal(gallery_watcher.Coalescer):
            DEBOUNCE_S = 0.05
            _TICK_S = 0.04

        fp = (rdir / "r" / "z.png")
        fp.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
            b"\x90wS\xde\x00\x00\x00\x0bIDAT\x08\xd7c\xf8"
            b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00IEND\xaeB`\x82",
        )
        c = TCoal(root=root, db_path=dbs, write_queue=wq, delta=TDelta())
        c.start()
        c.add("ZKEY", str(fp), "u")
        time.sleep(0.4)
        c.request_stop()
        c.join_tick(timeout=3.0)
        pposix = str(fp.resolve().as_posix())
        rconn = gallery_db.connect_read(dbs)
        try:
            n2 = int(
                rconn.execute(
                    "SELECT COUNT(*) AS n FROM image WHERE path=?",
                    (pposix,),
                ).fetchone()["n"]
            )
        finally:
            rconn.close()
        assert n2 >= 1, "expected at least one row after debounce flush"
    finally:
        wq.stop(timeout=2.0)
        shutil.rmtree(th, ignore_errors=True)
    print("T20 coalescer debounce + tick flush OK")


def main() -> None:
    _merge_cases()
    _delete_op()
    _coalescer_high_water()
    _service_not_raises()
    _debounce_drain()
    print("T20 ALL TESTS PASSED.")


if __name__ == "__main__":
    main()
