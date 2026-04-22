"""Seed N fake ``image`` rows so D3.2 manual QA can stress the
VirtualGrid window / rAF / IntersectionObserver wiring.

Why a direct writer connection, not ``repo.WriteQueue``:
  * This script is a **dev-only seed** run with ComfyUI shut down, so
    the single-writer invariant (PROJECT_STATE §4 #15) is preserved —
    this process is the sole writer for its lifetime.
  * ``repo.UpsertImageOp`` requires a real root-folder chain (path,
    kind, ``_ensure_folder_chain`` walk) and fires one transaction per
    row. For 50 000 rows that's slow and noisy. We just open one
    ``db.connect_write`` connection, INSERT OR IGNORE a throwaway root,
    then ``executemany`` inside one BEGIN/COMMIT — finishes in < 2 s.
  * All fake rows use ``filename LIKE 't13_fake_%'`` so cleanup is a
    two-line SQL (see bottom of docstring).

Usage (ComfyUI must NOT be running):
    cd <ComfyUI root>
    python custom_nodes\\ComfyUI-XYZNodes\\test\\manual\\t13_fake_50k.py

Then start ComfyUI and open
    http://<host>:<port>/xyz/gallery/
The MainView should render N total images; scroll to confirm the
``.vg-window`` DOM node count stays bounded (see D3.2 checklist).

Cleanup (run against ``gallery_data/gallery.sqlite``):
    DELETE FROM image  WHERE filename LIKE 't13_fake_%';
    DELETE FROM folder WHERE path = '/__t13_fake_root__';

Note: thumbnails for fake rows don't exist on disk, so ``/thumb/<id>``
will 404 or produce a placeholder. That's expected — we're stressing
VirtualGrid's DOM bounds + pagination, not the thumb pipeline.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
_PLUGIN_ROOT = _HERE.parent.parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from gallery import db as _db  # noqa: E402
from gallery import DB_PATH  # noqa: E402  — <plugin>/gallery_data/gallery.sqlite

N = 50_000
FAKE_ROOT_PATH = "/__t13_fake_root__"
FAKE_ROOT_KIND = "output"


def _ensure_fake_root(conn) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO folder(path, kind, parent_id, display_name, removable) "
        "VALUES (?, ?, NULL, ?, 0)",
        (FAKE_ROOT_PATH, FAKE_ROOT_KIND, "t13_fake_root"),
    )
    row = conn.execute(
        "SELECT id FROM folder WHERE path = ?", (FAKE_ROOT_PATH,),
    ).fetchone()
    assert row is not None, "fake root folder insert failed"
    return int(row[0])


def _rows(folder_id: int, base_epoch: int):
    now_epoch = int(time.time())
    for i in range(N):
        filename = f"t13_fake_{i:06d}.png"
        path = f"{FAKE_ROOT_PATH}/{filename}"
        created_at = base_epoch - i
        mtime_ns = created_at * 1_000_000_000
        yield (
            path, folder_id, filename, filename, filename.lower(), "png",
            64, 64, 1024, mtime_ns, created_at,
            None, None, "fake-model", None, None, None, None,
            0, None, None, now_epoch,
        )


def main() -> None:
    assert DB_PATH.parent.exists(), (
        f"gallery_data/ not found at {DB_PATH.parent}. "
        f"Start ComfyUI at least once so the plugin can create it."
    )
    conn = _db.connect_write(DB_PATH)
    try:
        _db.migrate(conn)
        folder_id = _ensure_fake_root(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.executemany(
                "INSERT OR IGNORE INTO image("
                "path, folder_id, relative_path, filename, filename_lc, ext, "
                "width, height, file_size, mtime_ns, created_at, "
                "positive_prompt, negative_prompt, model, seed, cfg, sampler, scheduler, "
                "workflow_present, favorite, tags_csv, indexed_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                _rows(folder_id, base_epoch=int(time.time())),
            )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        (total,) = conn.execute(
            "SELECT COUNT(*) FROM image WHERE filename LIKE 't13_fake_%'",
        ).fetchone()
        print(f"seeded fake rows: {total} (target {N}) into folder_id={folder_id}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
