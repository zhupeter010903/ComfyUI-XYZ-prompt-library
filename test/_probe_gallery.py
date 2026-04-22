"""Ad-hoc SQLite probes for local gallery debugging — run manually; not CI."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = _PLUGIN_ROOT / "gallery_data" / "gallery.sqlite"


def q(conn, sql, *args):
    print(">>>", sql.strip())
    for r in conn.execute(sql, args).fetchall():
        print(dict(r))
    print()


def walk_count(root: Path) -> int:
    n = 0
    for _, _, files in os.walk(root):
        for f in files:
            if Path(f).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                n += 1
    return n


def main() -> None:
    if not DB_PATH.is_file():
        print(f"Missing DB at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    q(conn, "SELECT COUNT(*) AS n FROM image")
    q(conn, "SELECT COUNT(*) AS n FROM folder WHERE parent_id IS NOT NULL")
    q(
        conn,
        """
SELECT id, path, relative_path, positive_prompt, model, seed,
       workflow_present, favorite, tags_csv
  FROM image
 LIMIT 10
""",
    )
    q(
        conn,
        """
SELECT path, positive_prompt, model, seed, cfg, sampler, workflow_present
  FROM image
 LIMIT 5
""",
    )

    comfy_root = os.environ.get("COMFYUI_ROOT")
    if comfy_root:
        root = Path(comfy_root)
        out_n = walk_count(root / "output")
        in_n = walk_count(root / "input")
        print(f"disk: output={out_n}, input={in_n}, total={out_n + in_n}")
    else:
        print("Tip: set COMFYUI_ROOT to scan ComfyUI output/input image counts.")

    conn.close()


if __name__ == "__main__":
    main()
