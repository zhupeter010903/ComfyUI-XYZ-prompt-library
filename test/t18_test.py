"""T18 offline validation — WebSocket hub + ``GET /xyz/gallery/ws``.

No ComfyUI process required. Mirrors TASKS.md T18 acceptance themes:
connect / broadcast fan-out / disconnect cleanup / high-volume send.

Run:
    python test/t18_test.py
Expected tail: ``T18 ALL TESTS PASSED``.
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402


class _FakeServer:
    def __init__(self) -> None:
        self.routes = web.RouteTableDef()


def _scratch_db(scratch: Path) -> None:
    from gallery import db

    p = scratch / "gallery.sqlite"
    p.touch()
    conn = db.connect_write(p)
    try:
        db.migrate(conn)
    finally:
        conn.close()


def _build_app(scratch: Path) -> web.Application:
    import gallery as g
    from gallery import routes, repo

    routes.DB_PATH = scratch / "gallery.sqlite"
    routes.THUMBS_DIR = scratch / "thumbs"
    routes.THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    wq = repo.WriteQueue(routes.DB_PATH)
    wq.start()
    g._write_queue = wq

    from gallery import ws_hub as wh

    wh.reset_clients()
    fake = _FakeServer()
    routes._registered = False
    routes.register(fake)
    app = web.Application()
    app.add_routes(fake.routes)
    app["xyz_write_queue"] = wq
    return app


async def _drain(ws, timeout: float = 2.0) -> dict[str, Any]:
    msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
    assert msg.type == web.WSMsgType.TEXT, msg
    return json.loads(msg.data)


async def _test_connect_and_broadcast(app: web.Application) -> None:
    from gallery import ws_hub as wh

    async with TestServer(app) as srv:
        async with TestClient(srv) as client:
            ws = await client.ws_connect("/xyz/gallery/ws")
            try:
                wh.broadcast("test", {"hello": 1})
                await asyncio.sleep(0.05)
                body = await _drain(ws)
                assert body["type"] == "test", body
                assert body["data"] == {"hello": 1}, body
                assert isinstance(body["ts"], int) and body["ts"] > 0
            finally:
                await ws.close()
    print("T18 connect + broadcast envelope OK")


async def _test_two_clients_fanout(app: web.Application) -> None:
    from gallery import ws_hub as wh

    async with TestServer(app) as srv:
        async with TestClient(srv) as client:
            a = await client.ws_connect("/xyz/gallery/ws")
            b = await client.ws_connect("/xyz/gallery/ws")
            try:
                wh.broadcast("image.updated", {"id": 42})
                await asyncio.sleep(0.05)
                ba = await _drain(a)
                bb = await _drain(b)
                assert ba == bb, (ba, bb)
                assert ba["type"] == "image.updated"
                assert ba["data"]["id"] == 42
            finally:
                await a.close()
                await b.close()
    print("T18 two-tab fan-out OK")


async def _test_disconnect_cleanup(app: web.Application) -> None:
    from gallery import ws_hub as wh

    async with TestServer(app) as srv:
        async with TestClient(srv) as client:
            a = await client.ws_connect("/xyz/gallery/ws")
            b = await client.ws_connect("/xyz/gallery/ws")
            try:
                await a.close()
                await asyncio.sleep(0.05)
                wh.broadcast("after_close", {"k": "v"})
                await asyncio.sleep(0.05)
                lone = await _drain(b)
                assert lone["type"] == "after_close"
            finally:
                await b.close()
    print("T18 dead socket cleanup OK")


async def _test_text_ping(app: web.Application) -> None:
    async with TestServer(app) as srv:
        async with TestClient(srv) as client:
            ws = await client.ws_connect("/xyz/gallery/ws")
            try:
                await ws.send_str("ping")
                pong = await _drain(ws)
                assert pong["type"] == "pong"
                assert pong["data"] == {}
                await ws.send_str(json.dumps({"type": "ping"}))
                pong2 = await _drain(ws)
                assert pong2["type"] == "pong"
            finally:
                await ws.close()
    print("T18 application ping → pong OK")


async def _test_1000_broadcasts(app: web.Application) -> None:
    from gallery import ws_hub as wh

    async with TestServer(app) as srv:
        async with TestClient(srv) as client:
            ws = await client.ws_connect("/xyz/gallery/ws")
            try:
                for i in range(1000):
                    await wh.broadcast_await("stress", {"i": i})
                for i in range(1000):
                    body = await _drain(ws, timeout=30.0)
                    assert body["type"] == "stress"
                    assert body["data"]["i"] == i
            finally:
                await ws.close()
    print("T18 1000 sequential broadcasts OK")


async def _test_threadsafe_broadcast(app: web.Application) -> None:
    from gallery import ws_hub as wh

    async with TestServer(app) as srv:
        async with TestClient(srv) as client:
            ws = await client.ws_connect("/xyz/gallery/ws")
            try:

                def _worker() -> None:
                    time.sleep(0.05)
                    wh.broadcast("from_thread", {"ok": True})

                threading.Thread(target=_worker, daemon=True).start()
                body = await _drain(ws, timeout=3.0)
                assert body["type"] == "from_thread"
                assert body["data"] == {"ok": True}
            finally:
                await ws.close()
    print("T18 thread-safe broadcast OK")


async def _run_all(scratch: Path) -> None:
    app = _build_app(scratch)
    try:
        await _test_connect_and_broadcast(app)
        await _test_two_clients_fanout(app)
        await _test_disconnect_cleanup(app)
        await _test_text_ping(app)
        await _test_1000_broadcasts(app)
        await _test_threadsafe_broadcast(app)
    finally:
        wq = app.get("xyz_write_queue")
        if wq is not None:
            wq.stop(timeout=1.0)
        from gallery import ws_hub as wh

        wh.reset_clients()


def main() -> None:
    import tempfile

    scratch = Path(tempfile.mkdtemp(prefix="xyz_t18_"))
    try:
        _scratch_db(scratch)
        asyncio.run(_run_all(scratch))
        print("T18 ALL TESTS PASSED")
    finally:
        import shutil

        for _ in range(2):
            try:
                shutil.rmtree(scratch)
                break
            except OSError:
                time.sleep(0.2)


if __name__ == "__main__":
    main()
