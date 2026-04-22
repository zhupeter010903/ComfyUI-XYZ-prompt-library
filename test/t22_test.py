# T22 — /xyz/gallery/index/status + ws_hub get_last_event_ts
# (aiohttp TestClient, scratch DB, no ComfyUI).
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import gallery.db as db
import gallery.routes as routes
import gallery.ws_hub as wh


class _FakeServer:
    """Same shape as test/t10_test ``_FakeServer`` (PromptServer.routes)."""

    def __init__(self) -> None:
        self.routes = web.RouteTableDef()


async def _run() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        dbp = tdp / "gallery.sqlite"
        c = db.connect_write(dbp)
        try:
            db.migrate(c)
        finally:
            c.close()
        routes.DB_PATH = dbp
        routes.DATA_DIR = tdp
        routes.THUMBS_DIR = tdp / "thumbs"
        routes.THUMBS_DIR.mkdir(parents=True, exist_ok=True)

        wh.reset_clients()
        assert wh.get_last_event_ts() == 0
        await wh.broadcast_await(wh.IMAGE_UPDATED, {"id": 1, "version": 1})
        tsv = wh.get_last_event_ts()
        assert tsv > 0

        fake = _FakeServer()
        routes._registered = False
        routes.register(fake)
        app = web.Application()
        app.add_routes(fake.routes)
        server = TestServer(app)
        client = TestClient(server)
        await client.start_server()
        try:
            r = await client.get("/xyz/gallery/index/status")
            assert r.status == 200, r.status
            j = await r.json()
            assert j.get("scanning") in (True, False)
            assert j.get("pending_events") == 0
            assert j.get("last_full_scan_at") is None
            assert "totals" in j
            assert j["totals"].get("images") == 0
            assert j.get("last_event_ts") == tsv
        finally:
            await client.close()
        wh.reset_clients()
    print("T22: index/status + ws last_event_ts OK")


def main() -> int:
    asyncio.run(_run())
    return 0


def test_t22_index_status_and_ws_ts() -> None:
    """Pytest entry (``pytest test/t22_test.py -q``)."""
    asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
