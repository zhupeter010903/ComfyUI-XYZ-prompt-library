#!/usr/bin/env python3
"""T38 integration probe — served ``index.html`` includes T38 theme CSS markers.

Does **not** start ComfyUI: uses the same aiohttp ``routes.register`` test harness
as ``test/t12_test.py``.

Run (from repo ``ComfyUI-XYZNodes``):
    python test/manual/t38_static_theme_probe.py

Prerequisites:
    Python env with ``aiohttp`` (same as ComfyUI / t10 harness).

Success (exit 0):
    T38 static probe OK: color-scheme + xyz tokens present in served HTML

Failure:
    AssertionError / non-zero exit with missing substring message.
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


class _FakeServer:
    def __init__(self) -> None:
        self.routes = web.RouteTableDef()


def _build_app():
    from gallery import routes as _routes

    fake = _FakeServer()
    _routes._registered = False
    _routes.register(fake)
    app = web.Application()
    app.add_routes(fake.routes)
    return app


async def _run() -> None:
    app = _build_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        r = await client.get("/xyz/gallery/static/index.html")
        assert r.status == 200, r.status
        text = await r.text()
        assert "color-scheme: dark" in text
        assert "color-scheme: light" in text
        assert "--xyz-on-accent:" in text
        assert ".dv-right::-webkit-scrollbar" in text
        assert "scrollbar-color: var(--border) var(--panel)" in text
    finally:
        await client.close()


def main() -> int:
    asyncio.run(_run())
    print("T38 static probe OK: color-scheme + xyz tokens present in served HTML")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
