#!/usr/bin/env python3
"""Insert many unused ``tag`` rows to exercise Settings → Tag management paging.

Does **not** start ComfyUI. Opens ``gallery.sqlite`` directly.

Example:
    python test/manual/seed_gallery_admin_tags_for_pagination.py \\
        --db E:/AI/ComfyUI-aki-v2/ComfyUI/custom_nodes/ComfyUI-XYZNodes/gallery_data/gallery.sqlite \\
        --count 55

Uses ``INSERT OR IGNORE`` so re-runs are safe; names are ``paging_seed_<n>``.
(Settings UI lists **10** tags per page — e.g. ``--count 35`` yields four pages.)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Path to gallery.sqlite",
    )
    p.add_argument(
        "--count",
        type=int,
        default=45,
        help="Number of tags to add (default: 45)",
    )
    p.add_argument(
        "--prefix",
        default="paging_seed_",
        help="Name prefix for each tag (default: paging_seed_)",
    )
    args = p.parse_args()
    db_path: Path = args.db
    n = max(1, min(int(args.count), 50_000))
    prefix = str(args.prefix or "paging_seed_")

    if not db_path.is_file():
        print(f"FAIL: database file not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        added = 0
        for i in range(n):
            name = f"{prefix}{i:05d}"
            cur = conn.execute(
                "INSERT OR IGNORE INTO tag(name, usage_count) VALUES (?, 0)",
                (name,),
            )
            added += int(cur.rowcount)
        conn.commit()
    finally:
        conn.close()

    print(f"OK: attempted {n} inserts, new rows this run: {added} (ignored = duplicate names)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
