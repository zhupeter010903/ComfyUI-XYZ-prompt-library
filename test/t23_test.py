"""T23 offline — Selection SQL + bulk favorite/tags (TASKS.md T23).

No ComfyUI. Covers ``repo.SelectionSpec`` / ``count_selection`` / subquery
path, ``service.bulk_set_favorite`` / ``bulk_edit_tags`` (WriteQueue + WS).

Run:
    python test/t23_test.py
    # or: pytest test/t23_test.py -v
Expected: ``T23 ALL TESTS PASSED``.
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


def _scratch_db_three() -> Tuple[Path, Path, int, int, int]:
    from gallery import db

    scratch = Path(tempfile.mkdtemp(prefix="xyz-t23-"))
    db_path = scratch / "gallery.sqlite"
    out = scratch / "out"
    out.mkdir()
    paths = [out / "a.png", out / "b.png", out / "c.png"]
    for p in paths:
        _make_png(p)

    conn = db.connect_write(db_path)
    try:
        db.migrate(conn)
        root = out.resolve().as_posix()
        fid = _insert_folder(conn, path=root, kind="output")
        ids: list[int] = []
        for i, p in enumerate(paths):
            st = p.stat()
            rel = p.name
            iid = _insert_image_min(
                conn,
                path=p.resolve().as_posix(),
                folder_id=fid,
                relative_path=rel,
                filename=rel,
                file_size=st.st_size,
                mtime_ns=st.st_mtime_ns,
                positive_prompt="x",
                workflow_present=0,
                favorite=0,
                tags_csv="t1,t2" if i == 0 else "t1",
            )
            ids.append(iid)
        conn.commit()
    finally:
        conn.close()
    return db_path, scratch, ids[0], ids[1], ids[2]


def test_count_explicit_and_all_except() -> None:
    from gallery import repo as g_repo

    db_path, scratch, i1, i2, i3 = _scratch_db_three()
    try:
        c1 = g_repo.count_selection(
            db_path=db_path,
            sel=g_repo.SelectionSpec(mode="explicit", explicit_ids=(i1, i2)),
        )
        assert c1 == 2, c1

        c2 = g_repo.count_selection(
            db_path=db_path,
            sel=g_repo.SelectionSpec(
                mode="all_except",
                filter=g_repo.FilterSpec(),
                excluded_ids=(i2,),
            ),
        )
        assert c2 == 2, c2

        tot, prev = g_repo.list_selection_ids_preview(
            db_path=db_path,
            sel=g_repo.SelectionSpec(
                mode="all_except",
                filter=g_repo.FilterSpec(),
                excluded_ids=(),
            ),
            limit=2,
        )
        assert tot == 3
        assert len(prev) == 2
        assert prev[0] < prev[1]
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def test_bulk_favorite_and_tags() -> None:
    import gallery as gallery_mod
    from gallery import repo as g_repo
    from gallery import service as g_service
    from gallery import ws_hub as g_ws

    db_path, scratch, i1, i2, i3 = _scratch_db_three()
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
            out = g_service.bulk_set_favorite(
                g_repo.SelectionSpec(mode="explicit", explicit_ids=(i1, i3,)),
                True,
                db_path=db_path,
            )
            assert out["affected"] == 2
            assert not out.get("failed")
            u = sqlite3.connect(str(db_path))
            try:
                assert int(
                    u.execute("SELECT favorite FROM image WHERE id=?", (i1,)).fetchone()[0]
                ) == 1
                assert int(
                    u.execute("SELECT favorite FROM image WHERE id=?", (i2,)).fetchone()[0]
                ) == 0
            finally:
                u.close()
            progs = [d for t, d in events if t == g_ws.BULK_PROGRESS]
            assert progs, events
            assert progs[0].get("done") in (0, 1)  # first is done=0 start echo

            g_service.bulk_edit_tags(
                g_repo.SelectionSpec(mode="explicit", explicit_ids=(i1,)),
                add=["t3"],
                remove=["t1"],
                db_path=db_path,
            )
        finally:
            g_ws.broadcast = orig  # type: ignore[assignment]
            wq.stop()
        u = sqlite3.connect(str(db_path))
        try:
            csv = str(u.execute("SELECT tags_csv FROM image WHERE id=?", (i1,)).fetchone()[0])
        finally:
            u.close()
        assert "t3" in csv
        assert "t1" not in csv
    finally:
        gallery_mod._write_queue = None
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def _run() -> None:
    test_count_explicit_and_all_except()
    test_bulk_favorite_and_tags()
    print("T23 ALL TESTS PASSED")


if __name__ == "__main__":
    _run()
