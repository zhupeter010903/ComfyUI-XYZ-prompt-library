"""Offline tests for ``ReconcileFoldersUnderRootOp`` (folder tree ↔ disk)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def test_reconcile_adds_and_removes_subfolders() -> None:
    from gallery import db, repo

    scratch = Path(tempfile.mkdtemp(prefix="xyz_foldrec_"))
    try:
        db_path = scratch / "g.sqlite"
        conn = db.connect_write(db_path)
        try:
            db.migrate(conn)
        finally:
            conn.close()

        out = scratch / "out"
        out.mkdir()
        root_posix = out.resolve().as_posix()

        wq = repo.WriteQueue(db_path)
        wq.start()
        try:
            wq.enqueue_write(
                repo.HIGH,
                repo.EnsureFolderOp(
                    path=root_posix,
                    kind="output",
                    removable=0,
                    display_name="out",
                ),
            ).result(timeout=5)
            rconn = db.connect_read(db_path)
            try:
                row = rconn.execute(
                    "SELECT id FROM folder WHERE parent_id IS NULL",
                ).fetchone()
            finally:
                rconn.close()
            root_id = int(row[0])

            ghost = out / "gone"
            ghost.mkdir()
            ghost_posix = ghost.resolve().as_posix()
            wq.enqueue_write(
                repo.HIGH,
                repo.EnsureFolderOp(
                    path=ghost_posix,
                    kind="output",
                    removable=0,
                    display_name="gone",
                    parent_id=root_id,
                ),
            ).result(timeout=5)
            shutil.rmtree(ghost)

            newsub = out / "fresh_sub"
            newsub.mkdir()

            wq.enqueue_write(
                repo.LOW,
                repo.ReconcileFoldersUnderRootOp(
                    root_id=root_id,
                    root_path=root_posix,
                    root_kind="output",
                ),
            ).result(timeout=10)
        finally:
            wq.stop()

        r2 = db.connect_read(db_path)
        try:
            paths = {
                str(r[0])
                for r in r2.execute("SELECT path FROM folder").fetchall()
            }
        finally:
            r2.close()

        assert ghost_posix not in paths, paths
        assert (newsub.resolve().as_posix()) in paths, paths
    finally:
        try:
            os.chmod(scratch, 0o700)
            shutil.rmtree(scratch, ignore_errors=True)
        except Exception:
            pass


def main() -> None:
    test_reconcile_adds_and_removes_subfolders()
    print("t_folder_reconcile_test: OK")


if __name__ == "__main__":
    main()
