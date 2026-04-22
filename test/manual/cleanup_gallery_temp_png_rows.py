# One-off maintenance: remove image rows (and on-disk files) for atomic-write
# temp files ``.xyz_gallery_*.png`` that were indexed before watcher/indexer
# ignored that pattern.
#
# IMPORTANT: Stop ComfyUI first. This script uses a direct write connection
# to ``gallery_data/gallery.sqlite``; running while the gallery
# ``WriteQueue`` is active can cause ``database is locked`` or race with
# HTTP/indexing.
#
# Run from the plugin root (ComfyUI-XYZNodes):
#   python test/manual/cleanup_gallery_temp_png_rows.py --dry-run
#   python test/manual/cleanup_gallery_temp_png_rows.py
#
# Custom DB (optional):
#   python test/manual/cleanup_gallery_temp_png_rows.py --db "E:/path/gallery.sqlite"
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parents[2]
if str(_PLUGIN) not in sys.path:
    sys.path.insert(0, str(_PLUGIN))

import gallery  # noqa: E402
from gallery import db as dbs  # noqa: E402
from gallery import metadata  # noqa: E402
from gallery import repo  # noqa: E402


def _collect_paths(db_path: Path) -> list[tuple[int, str]]:
    conn = dbs.connect_read(db_path)
    try:
        rows = conn.execute("SELECT id, path FROM image").fetchall()
    finally:
        conn.close()
    out: list[tuple[int, str]] = []
    for r in rows:
        iid = int(r["id"])
        p = str(r["path"])
        base = os.path.basename(p.replace("\\", "/"))
        if metadata.is_gallery_atomic_temp_basename(base):
            out.append((iid, p))
    return out


def _delete_one(conn, posix_path: str) -> int | None:
    return repo.DeleteImageOp(path=posix_path).apply(conn)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Remove indexed .xyz_gallery_*.png rows (and optional on-disk file).",
    )
    ap.add_argument(
        "--db",
        type=Path,
        default=None,
        help=f"Path to gallery.sqlite (default: {gallery.DB_PATH})",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list matching rows, do not delete",
    )
    ap.add_argument(
        "--no-unlink",
        action="store_true",
        help="Do not delete the file on disk (DB row still removed)",
    )
    args = ap.parse_args()

    db_path = (args.db or gallery.DB_PATH).resolve()
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2

    matches = _collect_paths(db_path)
    if not matches:
        print("No image rows with .xyz_gallery_*.png basename. Nothing to do.")
        return 0

    print(f"Found {len(matches)} row(s) to remove:\n")
    for iid, p in matches:
        print(f"  id={iid}  path={p!r}")
    if args.dry_run:
        print("\n[--dry-run] No changes made. Run without --dry-run after stopping ComfyUI.")
        return 0

    conn = dbs.connect_write(db_path)
    removed: list[str] = []
    try:
        for _iid, posix_path in matches:
            conn.execute("BEGIN IMMEDIATE")
            try:
                iid2 = _delete_one(conn, posix_path)
            except Exception as exc:  # noqa: BLE001
                conn.execute("ROLLBACK")
                print(f"FAILED id={_iid}: {exc}", file=sys.stderr)
                return 1
            conn.execute("COMMIT")
            if iid2 is not None:
                removed.append(posix_path)
    finally:
        conn.close()

    print(f"\nRemoved {len(removed)} row(s) from database.")

    if not args.no_unlink:
        for posix_path in removed:
            p = Path(posix_path)
            try:
                if p.is_file() and p.stat().st_size >= 0:
                    p.unlink()
                    print(f"  deleted file: {p}")
            except OSError as e:
                print(f"  could not delete file (optional): {p} ({e})", file=sys.stderr)

    print("Done. Start ComfyUI when finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
