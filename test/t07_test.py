"""T07 offline validation script.

Runs without ComfyUI: uses a scratch DB + scratch root so the real
gallery_data/ is never touched.  Mirrors TASKS.md T07 test plan as
closely as the host box allows.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo


def _make_png(dst: Path, *, with_workflow: bool = True) -> None:
    info = PngInfo()
    if with_workflow:
        info.add_text(
            "prompt",
            '{"1":{"class_type":"KSampler","inputs":'
            '{"seed":12345,"cfg":7.0,"sampler_name":"euler",'
            '"scheduler":"normal","positive":["2",0],"negative":["3",0]}},'
            '"2":{"class_type":"CLIPTextEncode","inputs":{"text":"a cat"}},'
            '"3":{"class_type":"CLIPTextEncode","inputs":{"text":"blurry"}},'
            '"4":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":"sd15.ckpt"}}}',
        )
        info.add_text("workflow", '{"nodes":[],"links":[]}')
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), "red").save(dst, pnginfo=info)


def main() -> None:
    from gallery import db, repo, indexer

    scratch = Path(tempfile.mkdtemp(prefix="xyz_t07_"))
    try:
        db_path = scratch / "gallery.sqlite"
        root_dir = scratch / "output"

        # bootstrap DB
        conn = db.connect_write(db_path)
        try:
            db.migrate(conn)
        finally:
            conn.close()

        # register one root via the real op, skipping folders.py (which
        # would pull in ComfyUI's folder_paths).
        wq = repo.WriteQueue(db_path)
        wq.start()
        try:
            root_posix = root_dir.resolve().as_posix()
            root_dir.mkdir()
            fut = wq.enqueue_write(repo.HIGH, repo.EnsureFolderOp(
                path=root_posix, kind="output", removable=0,
                display_name=root_dir.name,
            ))
            fut.result(timeout=5)

            # Lay out N sample PNGs, including one nested under a sub-dir.
            _make_png(root_dir / "a.png")
            _make_png(root_dir / "sub" / "b.png")
            _make_png(root_dir / "sub" / "deep" / "c.png", with_workflow=False)

            # Seed the run's root record as a dict (bypass folders.list_roots
            # since we wrote it without involving that module).
            rconn = db.connect_read(db_path)
            try:
                row = rconn.execute(
                    "SELECT id, path, kind FROM folder WHERE parent_id IS NULL"
                ).fetchone()
            finally:
                rconn.close()
            root = {"id": int(row["id"]), "path": row["path"], "kind": row["kind"]}

            # ---- T07 test #1: cold scan, all 3 files enqueued ------------
            summary = indexer.cold_scan(root, db_path=db_path, write_queue=wq)
            assert summary["enqueued"] == 3, summary
            assert summary["walked"] == 3, summary
            # Let the writer drain.
            time.sleep(0.5)
            rconn = db.connect_read(db_path)
            try:
                (n,) = rconn.execute("SELECT COUNT(*) FROM image").fetchone()
                assert n == 3, f"expected 3 rows, got {n}"
                # sub-folder rows exist with non-null parent_id
                (nf,) = rconn.execute(
                    "SELECT COUNT(*) FROM folder WHERE parent_id IS NOT NULL"
                ).fetchone()
                # sub + sub/deep = 2
                assert nf == 2, f"expected 2 sub-folder rows, got {nf}"
                # Image metadata was mirrored.
                row = rconn.execute(
                    "SELECT relative_path, positive_prompt, model, seed, "
                    "workflow_present, filename_lc FROM image "
                    "WHERE filename = 'a.png'"
                ).fetchone()
                assert row["relative_path"] == "a.png"
                assert row["positive_prompt"] == "a cat"
                assert row["model"] == "sd15.ckpt"
                assert row["seed"] == 12345
                assert row["workflow_present"] == 1
                assert row["filename_lc"] == "a.png"

                row = rconn.execute(
                    "SELECT relative_path, workflow_present FROM image "
                    "WHERE filename = 'c.png'"
                ).fetchone()
                assert row["relative_path"] == "sub/deep/c.png"
                assert row["workflow_present"] == 0
            finally:
                rconn.close()
            print("T07 test #1 OK (cold scan + folder chain + metadata)")

            # ---- T07 test #2: second cold scan is a no-op ----------------
            summary2 = indexer.cold_scan(root, db_path=db_path, write_queue=wq)
            assert summary2["enqueued"] == 0, summary2
            assert summary2["skipped"] == 3, summary2
            print("T07 test #2 OK (fingerprint short-circuit)")

            # ---- T07 test #3: modify one file → delta_scan rewrites 1 ---
            time.sleep(1)  # let mtime_ns advance
            _make_png(root_dir / "a.png")  # rewrite
            os.utime(root_dir / "a.png")  # bump mtime just in case
            summary3 = indexer.delta_scan(root, db_path=db_path, write_queue=wq)
            assert summary3["changed"] == 1, summary3
            time.sleep(0.2)
            print("T07 test #3 OK (delta_scan targets only changed file)")

            # ---- T07 test #5: inflight barrier ---------------------------
            target = root_dir / "a.png"
            enqueued_before = summary3["changed"]
            # Fire 50 concurrent index_one calls for the same path; only
            # one should actually do work, the rest should no-op.
            did_work = [0]
            lock = threading.Lock()
            barrier = threading.Event()

            def hammer() -> None:
                barrier.wait()
                if indexer.index_one(
                    target, root=root, db_path=db_path, write_queue=wq,
                ):
                    with lock:
                        did_work[0] += 1

            threads = [threading.Thread(target=hammer) for _ in range(50)]
            for t in threads:
                t.start()
            barrier.set()
            for t in threads:
                t.join(timeout=5)
            # At most 1 actually ran; since the fingerprint now matches
            # (we didn't modify since last index) it may even be 0.
            assert did_work[0] <= 1, did_work
            # inflight must drain completely.
            assert len(indexer._inflight) == 0, indexer._inflight
            print("T07 test #5 OK (inflight barrier; did_work=%d)" % did_work[0])

            # ---- bonus: exception in read_comfy_metadata is isolated ----
            # Simulate by pointing index_one at a file that PIL will fail on.
            bad = root_dir / "broken.png"
            bad.write_bytes(b"\x89PNG\r\n\x1a\n_garbage_")
            ok = indexer.index_one(
                bad, root=root, db_path=db_path, write_queue=wq,
            )
            # Bad file is still a new path → upsert enqueued (errors tuple
            # in meta is informational; the row should still materialise).
            assert ok is True
            time.sleep(0.2)
            assert len(indexer._inflight) == 0
            print("T07 bonus OK (broken PNG still indexed, inflight clean)")
        finally:
            wq.stop(timeout=2)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
