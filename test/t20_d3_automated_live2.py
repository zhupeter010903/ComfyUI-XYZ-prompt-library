"""
不依赖新文件: 用已有 /images 首个 id 测 PATCH + WS, 与 GET /image/{id}（T20 进程已跑时做补充）.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.request
from typing import Any
from urllib.parse import urlparse

_BASE = (os.environ.get("GALLERY_HTTP") or "http://127.0.0.1:8188/xyz/gallery").rstrip("/")


def _get(path: str) -> tuple[int, Any]:
    u = f"{_BASE}{path}"
    with urllib.request.urlopen(u, timeout=30) as r:  # noqa: S310
        return r.status, json.loads(r.read().decode("utf-8", "replace"))


def _patch(iid: int) -> tuple[int, Any]:
    u = f"{_BASE}/image/{iid}"
    b = json.dumps({"favorite": True}).encode("utf-8")
    req = urllib.request.Request(
        u, data=b, method="PATCH", headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return r.status, json.loads(r.read().decode("utf-8", "replace"))


def main() -> int:
    st, j = _get("/images?limit=1&sort=time&dir=desc")
    if st != 200 or not j.get("items"):
        print("No images in DB or HTTP error:", st, file=sys.stderr)
        return 2
    iid = int(j["items"][0]["id"])
    print("Using existing image id:", iid)
    pst, body = _patch(iid)
    g = (body or {}).get("gallery") or {}
    print("PATCH 200" if pst == 200 else f"PATCH {pst}", "gallery.version=", g.get("version"), "sync=", g.get(  # noqa: E501
        "sync_status",
    ))

    p = urlparse(_BASE)
    wu = f"ws://{p.netloc}{p.path.rstrip('/')}/ws" if p.scheme == "http" else f"wss://{p.netloc}{p.path.rstrip('/')}/ws"
    try:
        import aiohttp
    except ImportError:
        print("aiohttp missing, skip WS")
        return 0
    async def w() -> None:
        async with aiohttp.ClientSession() as s:
            async with s.ws_connect(wu) as c:
                await c.send_str('{"type":"ping"}')
                m = await c.receive(timeout=10.0)
                t = m.data or ""
                print("WS text:", t[: 200], "…" if len(t) > 200 else "")

    asyncio.run(w())
    return 0


if __name__ == "__main__":
    sys.exit(main())
