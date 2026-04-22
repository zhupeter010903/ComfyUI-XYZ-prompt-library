# T22 — live ComfyUI probe: GET /xyz/gallery/index/status + WS ping/pong.
# Requires: ComfyUI running with this plugin loaded (same host you pass in).
#
# Run (example):
#   python test/manual/t22_comfyui_gallery_probe.py --base http://127.0.0.1:8188
#
# Success: exit 0, prints JSON summary.
# Failure: non-zero exit, stderr/stdout has HTTP status or assert message.
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Dict
from urllib.parse import urljoin, urlparse, urlunparse

import aiohttp


def _http_base(s: str) -> str:
    s = s.rstrip("/")
    if not s.startswith("http://") and not s.startswith("https://"):
        s = "http://" + s
    return s


def _ws_url_from_http(http_base: str) -> str:
    p = urlparse(http_base)
    scheme = "wss" if p.scheme == "https" else "ws"
    return urlunparse((scheme, p.netloc, "/xyz/gallery/ws", "", "", ""))


async def _run(base: str) -> int:
    http_b = _http_base(base)
    status_url = urljoin(http_b + "/", "xyz/gallery/index/status")
    async with aiohttp.ClientSession() as sess:
        async with sess.get(status_url) as r:
            text = await r.text()
            assert r.status == 200, f"GET index/status: {r.status} {text[:200]}"
            st: Dict[str, Any] = json.loads(text)
    for k in ("scanning", "pending_events", "totals", "last_event_ts"):
        assert k in st, f"missing key {k!r} in {st!r}"
    assert isinstance(st["totals"], dict)
    assert "images" in st["totals"]

    ws_url = _ws_url_from_http(http_b)
    async with aiohttp.ClientSession() as sess:
        async with sess.ws_connect(ws_url, timeout=20) as ws:
            await ws.send_str("ping")
            msg = await ws.receive(timeout=10)
            assert msg.type == aiohttp.WSMsgType.TEXT, msg
            o = json.loads(msg.data)
            assert o.get("type") == "pong", o

    print("OK: index/status + ws pong", json.dumps(st, indent=2)[:800])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base",
        default="http://127.0.0.1:8188",
        help="ComfyUI root (scheme + host + optional port), default 127.0.0.1:8188",
    )
    args = ap.parse_args()
    try:
        return asyncio.run(_run(args.base))
    except AssertionError as e:
        print("ASSERT:", e, file=sys.stderr)
        return 1
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
