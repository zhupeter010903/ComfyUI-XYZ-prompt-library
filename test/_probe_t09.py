"""T09 probe against the real gallery.sqlite (read-only).

Does not mutate anything.  Verifies that the new read APIs return
sensible shapes on the 4317-image production DB and that EXPLAIN
QUERY PLAN of the list_images SQL hits the expected indexes.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from gallery import repo  # noqa: E402


def main() -> None:
    db_path = _PLUGIN_ROOT / "gallery_data" / "gallery.sqlite"
    if not db_path.is_file():
        print(f"no prod DB at {db_path} — skipping probe")
        return

    t0 = time.perf_counter()
    pg = repo.list_images(db_path=db_path, limit=50)
    dt = (time.perf_counter() - t0) * 1000
    print(f"list_images default (time/desc): {len(pg.items)} items, "
          f"total={pg.total} (approx={pg.total_approximate}), {dt:.1f} ms")

    if pg.next_cursor:
        t0 = time.perf_counter()
        pg2 = repo.list_images(
            db_path=db_path, cursor=pg.next_cursor, limit=50)
        dt = (time.perf_counter() - t0) * 1000
        print(f"  page 2: {len(pg2.items)} items, {dt:.1f} ms")
        # No overlap with page 1.
        ids1 = {r.id for r in pg.items}
        ids2 = {r.id for r in pg2.items}
        assert ids1.isdisjoint(ids2), "page overlap"

    if pg.items:
        t0 = time.perf_counter()
        rec = repo.get_image(pg.items[0].id, db_path=db_path)
        dt = (time.perf_counter() - t0) * 1000
        print(f"get_image({pg.items[0].id}): {rec.filename!r}, {dt:.1f} ms")

        t0 = time.perf_counter()
        nb = repo.neighbors(pg.items[0].id, db_path=db_path)
        dt = (time.perf_counter() - t0) * 1000
        print(f"neighbors({pg.items[0].id}): "
              f"prev={nb.prev_id} next={nb.next_id}, {dt:.1f} ms")

    t0 = time.perf_counter()
    tree = repo.folder_tree(db_path=db_path, include_counts=True)
    dt = (time.perf_counter() - t0) * 1000

    def _count_nodes(ns):
        n = len(ns)
        for x in ns:
            n += _count_nodes(x.children)
        return n
    print(f"folder_tree (with counts): {len(tree)} roots, "
          f"{_count_nodes(tree)} nodes total, {dt:.1f} ms")
    for r in tree:
        print(f"  {r.display_name:<12} self={r.image_count_self} "
              f"recursive={r.image_count_recursive}")

    # EXPLAIN on a realistic list_images query.
    conn = sqlite3.connect(str(db_path))
    try:
        plan = conn.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT image.id FROM image LEFT JOIN folder "
            "ON folder.id = image.folder_id "
            "WHERE image.folder_id = ? AND image.favorite = 1 "
            "ORDER BY image.created_at DESC, image.id DESC LIMIT 50",
            (tree[0].id if tree else 1,),
        ).fetchall()
        print("EXPLAIN (folder + favorite, time desc):")
        for row in plan:
            print("  " + str(row[3]))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
