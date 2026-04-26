"""T40 — 集成探针（aiohttp TestServer 静态拉取，**不** 启动 ComfyUI）。

验证 ``/xyz/gallery/static/...`` 可下发 `IconButton.js`；`index.html` 含 ``.ib`` token；
`DetailView.js` / `app.js` 已去掉 ``&larr; Back|Home`` 裸字链模式。

用法:
    python test/manual/t40_gallery_static_iconbutton_probe.py

成功：退出 0 且 ``T40 GALLERY STATIC ICON PROBE OK``。

前置：Python + aiohttp，与本仓库同路径（`sys.path` 含插件根，供 ``gallery.routes``）。

失败：断言失败或非 2xx（静态未注册）。
"""
from __future__ import annotations

import asyncio
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
            r = await client.get("/xyz/gallery/static/components/IconButton.js")
            assert r.status == 200, (r.status, r)
            ib = await r.text()
            assert "export const IconButton" in ib
            assert "stroke-width=\"1.5\"" in ib
            assert "M15.75 19.5L8.25 12l7.5-7.5" in ib

            r2 = await client.get("/xyz/gallery/static/views/DetailView.js")
            assert r2.status == 200, r2.status
            dv = await r2.text()
            assert "IconButton" in dv
            assert "&larr; Back" not in dv
            assert 'href="#/"' in dv

            r3 = await client.get("/xyz/gallery/static/app.js")
            assert r3.status == 200, r3.status
            aj = await r3.text()
            assert "IconButton" in aj
            assert "&larr; Home" not in aj

            r4 = await client.get("/xyz/gallery")
            assert r4.status in (200, 304, 206), r4.status
            html = await r4.text()
            assert "T40" in html or ".ib {" in html
            assert ".ib {" in html
            assert ".ib-ico" in html
            assert ".ib-sr-only" in html


def main() -> int:
    asyncio.run(_run())
    print("T40 GALLERY STATIC ICON PROBE OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
