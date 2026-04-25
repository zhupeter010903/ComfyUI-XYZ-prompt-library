# T29 maintenance: remove ``image`` rows whose path lies under a derivative
# cache directory (``_thumbs`` segment under a registered root, V1.1-F11).
#
# Stop ComfyUI first — this opens ``gallery.sqlite`` for writing with
# ``BEGIN IMMEDIATE`` per row (same pattern as ``cleanup_gallery_temp_png_rows.py``).
#
# Run from plugin root ``ComfyUI-XYZNodes``:
#   python test/manual/t29_purge_derivative_index_rows.py --dry-run
#   python test/manual/t29_purge_derivative_index_rows.py
#
# Custom DB:
#   python test/manual/t29_purge_derivative_index_rows.py --db "E:/path/gallery.sqlite" --dry-run
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parents[2]
if str(_PLUGIN) not in sys.path:
    sys.path.insert(0, str(_PLUGIN))

import gallery  # noqa: E402
from gallery import db as dbs  # noqa: E402
from gallery import indexer  # noqa: E402
from gallery import repo  # noqa: E402


def _collect_targets(db_path: Path) -> list[tuple[int, str, str]]:
    """Return ``(image_id, path, root_path)`` rows to purge."""
    conn = dbs.connect_read(db_path)
    try:
        rows = conn.execute(
            "SELECT i.id AS iid, i.path AS ipath, f.path AS rpath "
            "FROM image i "
            "JOIN folder f ON i.folder_id = f.id "
            "WHERE f.parent_id IS NULL",
        ).fetchall()
    finally:
        conn.close()
    out: list[tuple[int, str, str]] = []
    for r in rows:
        p = str(r["ipath"])
        root = str(r["rpath"])
        if indexer.is_derivative_path_excluded(p, root):
            out.append((int(r["iid"]), p, root))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Purge DB rows indexed under _thumbs (derivative cache).",
    )
    ap.add_argument("--db", type=Path, default=None, help="gallery.sqlite path")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching rows only",
    )
    args = ap.parse_args()

    db_path = (args.db or gallery.DB_PATH).resolve()
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2

    matches = _collect_targets(db_path)
    if not matches:
        print("No image rows under excluded derivative paths. Nothing to do.")
        return 0

    print(f"Found {len(matches)} row(s):\n")
    for iid, p, root in matches:
        print(f"  id={iid}  root={root!r}  path={p!r}")
    if args.dry_run:
        print("\n[--dry-run] No changes. Re-run without --dry-run after stopping ComfyUI.")
        return 0

    conn = dbs.connect_write(db_path)
    removed = 0
    try:
        for _iid, posix_path, _root in matches:
            conn.execute("BEGIN IMMEDIATE")
            try:
                iid2 = repo.DeleteImageOp(path=posix_path).apply(conn)
            except Exception as exc:  # noqa: BLE001
                conn.execute("ROLLBACK")
                print(f"FAILED path={posix_path!r}: {exc}", file=sys.stderr)
                return 1
            conn.execute("COMMIT")
            if iid2 is not None:
                removed += 1
    finally:
        conn.close()

    print(f"\nRemoved {removed} row(s). On-disk files under _thumbs were not touched.")
    print("Done. Start ComfyUI when finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
