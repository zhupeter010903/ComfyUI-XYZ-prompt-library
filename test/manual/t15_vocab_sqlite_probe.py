"""T15 semi-automatic probe (do not run in CI).

Purpose: after a real ComfyUI session has run the gallery cold scan against
``gallery_data/gallery.sqlite``, inspect vocab tables without starting the UI.

Usage (PowerShell, from ``ComfyUI-XYZNodes`` plugin root)::

    python test/manual/t15_vocab_sqlite_probe.py "E:\\path\\to\\gallery_data\\gallery.sqlite"

Prerequisites:
  * Schema migrated to user_version >= 3 (T15).
  * Indexer has enqueued at least one ``UpsertImageOp`` with non-empty prompts
    or xyz_gallery tags so ``prompt_token`` / ``tag`` are non-empty.

This script does **not** import ComfyUI; it only uses ``sqlite3``.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python t15_vocab_sqlite_probe.py <path-to-gallery.sqlite>")
        sys.exit(2)
    db = Path(sys.argv[1])
    if not db.is_file():
        print(f"not a file: {db}")
        sys.exit(1)
    conn = sqlite3.connect(str(db))
    try:
        (uv,) = conn.execute("PRAGMA user_version").fetchone()
        print("user_version:", uv)
        counts = [
            ("tag", "SELECT COUNT(*) FROM tag"),
            ("image_tag", "SELECT COUNT(*) FROM image_tag"),
            ("prompt_token", "SELECT COUNT(*) FROM prompt_token"),
            ("image_prompt_token", "SELECT COUNT(*) FROM image_prompt_token"),
        ]
        for label, sql in counts:
            (n,) = conn.execute(sql).fetchone()
            print(f"{label}: {n} rows")
        print("sample prompt_token:", conn.execute(
            "SELECT token, usage_count FROM prompt_token ORDER BY usage_count DESC LIMIT 5"
        ).fetchall())
        print("sample tag:", conn.execute(
            "SELECT name, usage_count FROM tag ORDER BY usage_count DESC LIMIT 5"
        ).fetchall())
    finally:
        conn.close()


if __name__ == "__main__":
    main()
