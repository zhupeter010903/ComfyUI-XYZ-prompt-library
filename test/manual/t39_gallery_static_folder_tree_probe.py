"""T39 — 集成探针（不启动 ComfyUI 主进程，仅 aiohttp 静态路由 + HTTP GET）。

同 T12 探针，验证 ``/xyz/gallery/static/...`` 下发的 FolderTree 与 index 含 T39 契约。

前置：无（仅 Python + aiohttp + 本包 gallery.routes）。

成功：退出 0 且输出 ``T39 GALLERY STATIC PROBE OK``。
失败：AssertionError 或 非 2xx 响应。

用法:
    python test/manual/t39_gallery_static_folder_tree_probe.py
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402


def _app():
    from gallery import routes as _routes

    class _Fake:
        def __init__(self) -> None:
            self.routes = web.RouteTableDef()

    fake = _Fake()
    _routes._registered = False
    _routes.register(fake)
    app = web.Application()
    app.add_routes(fake.routes)
    return app


async def _run() -> None:
    app = _app()
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            r1 = await client.get("/xyz/gallery/static/components/FolderTree.js")
            assert r1.status == 200, r1.status
            b1 = await r1.text()
            assert b1.count("<svg") >= 2, "expect folder + chevron inline SVGs"
            assert "stroke-width=\"1.5\"" in b1
            assert "ft-guide" in b1
            assert "M9.75 5.5" in b1 and "M5.5 9.75" in b1

            r2 = await client.get("/xyz/gallery")
            assert r2.status in (200, 304, 206), r2.status
            html = await r2.text()
            assert re.search(
                r"\.ft-node\.active\s*\{[^}]*0\.22", html, re.DOTALL
            ), "index: .ft-node.active T39 highlight"
            assert ".ft-guide::before" in html


def main() -> int:
    asyncio.run(_run())
    print("T39 GALLERY STATIC PROBE OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
