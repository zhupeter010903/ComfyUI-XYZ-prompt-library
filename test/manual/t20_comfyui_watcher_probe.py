"""T20 半自动探针：在已启动 ComfyUI 且本插件已加载时运行 (独立进程, 不锁 gallery.sqlite 写端).

不自动执行: 在 PowerShell/终端:

  $env:PYTHONPATH = "E:\AI\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-XYZNodes"
  python test/manual/t20_comfyui_watcher_probe.py

可选: 在 Web / DevTools 先打开 ``/xyz/gallery`` 并接好 WS, 看 ``image.upserted`` / 漂移事件
(与 ``test/manual/t18_comfyui_ws_probe.js`` 同页同源).

步骤概要:
1. 记下 ComfyUI 控制台是否出现 ``file watcher started`` / 无 ``watchdog not importable``。
2. 向 ``output/``(或你注册的根) 复制/保存一张新 PNG(白名单扩展名), 1–3 s 内
   ``GET /xyz/gallery/images?limit=1&sort=time&dir=desc`` 能刷到新 id (或看 WS payload)。
3. 删除该文件: 同 id 从列表消失 / ``image.deleted``。
4. 大目录解压或批量拷 1000+ 小图: 日志中可出现 ``coalescer overflow`` + ``delta_scan``(降级路径)。

注意: 若与 ComfyUI 同时打开同一 ``gallery_data/gallery.sqlite``, 不要在本脚本里
 ``bootstrap`` 写库; 本脚本**只**做文件操作与只读 HTTP 读。
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

# ComfyUI 默认: 以 ``folder_paths.get_output_directory()`` 为 output 根 (本机路径).
# 与 DB `folder` 中 ``kind='output'`` 的 ``path`` 应一致; 本探测仅提示人工核对.
try:
    from folder_paths import get_output_directory
except Exception:  # pragma: no cover
    get_output_directory = None  # 未在 Comfy 进程内: 用环境变量/手工路径


def _out_root() -> Path:
    d = get_output_directory() if get_output_directory else os.environ.get(
        "COMFY_GALLERY_PROBE_OUTPUT",
    )
    if not d:
        print("Set COMFY_GALLERY_PROBE_OUTPUT to your Comfy output folder or run inside Comfy.")
        raise SystemExit(1)
    return Path(d).resolve()


def _get(base: str, path: str) -> tuple[int, str]:
    u = f"{base.rstrip('/')}{path}"
    with urllib.request.urlopen(u, timeout=30) as r:
        b = r.read()
        return r.status, b.decode("utf-8", "replace")

def main() -> None:
    out = _out_root()
    probe = out / f"_xyz_gallery_t20_{int(time.time())}.png"
    probe.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde\x00\x00\x00\x0bIDAT\x08\xd7c\xf8"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00IEND\xaeB`\x82",
    )
    print("Wrote:", probe, "(remove manually after test)")
    base = os.environ.get("GALLERY_HTTP", "http://127.0.0.1:8188/xyz/gallery")
    if get_output_directory is None:
        print("get_output_directory unavailable: skip HTTP check; use browser gallery.")
        return
    st, _ = _get(base, f"/images?limit=2&sort=time&dir=desc")
    if st == 200:
        print("GET /images ok (watcher+index 可能尚未完成; 多等几秒后刷新)")
    else:
        print("HTTP status:", st, "(is ComfyUI on 127.0.0.1:8188?)")


if __name__ == "__main__":
    main()
