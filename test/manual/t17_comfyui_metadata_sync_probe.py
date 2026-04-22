"""T17 半自动：探测 metadata_sync Worker 是否能把 ``pending`` 写回 ``ok``。

默认假设：与 **已执行** ``gallery.setup()`` 的 ComfyUI **同一进程**（极少见）。

常见用法：在 **另一终端** 用本仓库 Python 跑本脚本时，进程不同，``gallery._write_queue``
仍为 ``None``。此时请使用 ``--bootstrap`` 在本地 **仅** 拉起 ``WriteQueue`` + 后台线程
（会访问插件目录下的 ``gallery_data/gallery.sqlite``）。

**警告**：若 ComfyUI 正在使用同一数据库，``--bootstrap`` 会形成第二个写队列，违反
单写者设计，可能导致异常；探测前请 **关闭 ComfyUI** 或改用副本库。

用法::

  cd E:\\AI\\ComfyUI-aki-v2\\ComfyUI\\custom_nodes\\ComfyUI-XYZNodes
  python test/manual/t17_comfyui_metadata_sync_probe.py --bootstrap
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

# ``gallery`` 包在插件根下，不在 stdlib；与 ``test/t17_test.py`` 相同技巧。
_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def _maybe_bootstrap(*, bootstrap: bool) -> None:
    import gallery
    from gallery import db as gallery_db
    from gallery import DB_PATH

    if gallery._write_queue is not None:
        return
    if not bootstrap:
        print(
            "gallery._write_queue 为 None：当前 Python 进程里尚未执行 gallery.setup()。\n"
            "另开终端跑本脚本时无法复用 ComfyUI 内存中的队列。\n"
            "请关闭 ComfyUI 后执行：\n"
            f"  python {Path(__file__).as_posix()} --bootstrap\n"
            "或在 ComfyUI 源码树内设置 PYTHONPATH 后自行扩展本脚本（不推荐）。",
            file=sys.stderr,
        )
        raise SystemExit(2)
    print(
        "[probe] --bootstrap: migrate + start_background_services() "
        f"on DB {DB_PATH}",
        flush=True,
    )
    conn = gallery_db.connect_write(DB_PATH)
    try:
        gallery_db.migrate(conn)
    finally:
        conn.close()
    gallery.start_background_services()
    if gallery._write_queue is None:
        print("[probe] bootstrap failed: _write_queue still None", file=sys.stderr)
        raise SystemExit(3)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--bootstrap",
        action="store_true",
        help="migrate + start_background_services（无 ComfyUI 同进程时使用）",
    )
    args = ap.parse_args()

    import gallery
    from gallery import DB_PATH
    from gallery import metadata_sync

    _maybe_bootstrap(bootstrap=args.bootstrap)

    assert gallery._write_queue is not None

    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            "SELECT id, version, path, ext FROM image WHERE lower(ext)='png' LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not row:
        print("库中无 PNG 的 image 行，无法探测", file=sys.stderr)
        raise SystemExit(4)
    image_id, ver = int(row[0]), int(row[1])
    print("probe image_id=", image_id, "version=", ver, "path=", row[2], flush=True)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            "UPDATE image SET metadata_sync_status='pending' WHERE id=?",
            (image_id,),
        )
        conn.commit()
    finally:
        conn.close()
    metadata_sync.notify(image_id, ver)
    for i in range(30):
        time.sleep(0.2)
        conn = sqlite3.connect(str(DB_PATH))
        try:
            st, v, err = conn.execute(
                "SELECT metadata_sync_status, version, metadata_sync_last_error "
                "FROM image WHERE id=?",
                (image_id,),
            ).fetchone()
        finally:
            conn.close()
        print(i, "status=", st, "version=", v, "err=", err, flush=True)
        if st == "ok":
            print("T17 probe: sync reached ok", flush=True)
            return
    print("T17 probe: timeout — 检查只读 PNG / 日志 xyz.gallery.metadata_sync", flush=True)


if __name__ == "__main__":
    main()
