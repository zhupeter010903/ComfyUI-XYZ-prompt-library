"""
T20: D2 探针 + 可自动化的 D3 子项（本机 Comfy 已开，默认 http://127.0.0.1:8188/xyz/gallery）.

  python test/t20_d3_automated_live.py

不访问 Comfy 控制台; 不压测「1000+ 文件」、不点浏览器 UI/多 Tab。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

_BASE = (os.environ.get("GALLERY_HTTP") or "http://127.0.0.1:8188/xyz/gallery").rstrip("/")
_MINI_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0bIDAT\x08\xd7c\xf8"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _get(path: str) -> tuple[int, Any]:
    u = f"{_BASE}{path}" if path.startswith("/") else f"{_BASE}/{path}"
    req = urllib.request.Request(u, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return r.status, json.loads(r.read().decode("utf-8", "replace"))


def _get_raw(path: str) -> tuple[int, Optional[bytes], str]:
    u = f"{_BASE}{path}" if path.startswith("/") else f"{_BASE}/{path}"
    req = urllib.request.Request(u, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            return r.status, r.read(), ""
    except urllib.error.HTTPError as e:
        return e.code, None, e.reason


def _patch_image(image_id: int, body: dict) -> tuple[int, Any]:
    p = f"/image/{image_id}"
    u = f"{_BASE}{p}" if p.startswith("/") else f"{_BASE}/{p}"
    b = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        u, data=b, method="PATCH", headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return r.status, json.loads(r.read().decode("utf-8", "replace"))


def _out_root() -> str:
    st, tree = _get("/folders")
    if st != 200 or not isinstance(tree, list):
        raise RuntimeError(f"folders: {st}")
    for n in tree:
        if n.get("kind") == "output" and n.get("parent_id") in (None, 0, ""):
            return str(n["path"])
    for n in tree:
        if n.get("kind") == "output":
            return str(n["path"])
    raise RuntimeError("no output root in /folders")


def _out_dir_path() -> Path:
    # DB 存 POSIX; Python Path 在 Windows 上接受 E:/a/b
    return Path(_out_root()).resolve()


def _find_image_id(filename: str, tries: int = 120) -> Optional[int]:
    for i in range(tries):
        st, data = _get(f"/images?limit=80&sort=time&dir=desc")
        if st != 200 or not isinstance(data, dict):
            time.sleep(0.5)
            continue
        for it in data.get("items") or []:
            if it.get("filename") == filename:
                return int(it["id"])
        if i and i % 20 == 0:
            print(f"  … still waiting for {filename!r} in /images (try {i+1}/{tries})")
        time.sleep(0.5)
    return None


def _ws_url() -> str:
    p = urlparse(_BASE)
    if p.scheme == "http":
        return f"ws://{p.netloc}{p.path.rstrip('/')}/ws" if p.path else "ws://127.0.0.1:8188/xyz/gallery/ws"
    return f"wss://{p.netloc}{p.path.rstrip('/')}/ws"


def main() -> int:
    print("BASE:", _BASE)
    st, _ = _get("/folders")
    assert st == 200, st
    print("  OK  GET /folders 200")
    pdir = _out_dir_path()
    if not pdir.is_dir():
        print("  FAIL: output not a directory:", pdir, file=sys.stderr)
        return 2
    name = f"_d3_auto_t20_{int(time.time())}.png"
    fp = pdir / name
    fp.write_bytes(_MINI_PNG)
    print("Wrote", fp)
    new_id = _find_image_id(name)
    if not new_id:
        print("  FAIL: file not in /images in time (watcher/indexer)", file=sys.stderr)
        try:
            fp.unlink()
        except OSError:  # noqa: S110
            pass
        return 2
    print("  OK  new image id =", new_id, "(D3#2)")

    # WS ping
    wu = _ws_url()
    try:
        import aiohttp
    except ImportError:
        aiohttp = None  # type: ignore[assignment]
    if aiohttp:
        async def _p() -> str:
            async with aiohttp.ClientSession() as s:
                async with s.ws_connect(wu) as w:
                    await w.send_str('{"type":"ping"}')
                    m = await w.receive(timeout=10.0)
                    if m.type == aiohttp.WSMsgType.TEXT:
                        return m.data
                    return str(m)
        t = asyncio.run(_p())
        if "pong" in t.lower() or "type" in t:
            print("  OK  WebSocket (D2/T18):", t[: 160], "…" if len(t) > 160 else "")
        else:
            print("  !   WebSocket response:", t[: 200], file=sys.stderr)
    else:
        print("  !   skip WS (aiohttp missing)")

    try:
        pst, pbody = _patch_image(new_id, {"favorite": True})
        g = pbody.get("gallery") or {}
        if pst == 200 and "error" not in pbody:
            print("  OK  PATCH (D3#5 lite) sync_status=", g.get("sync_status"), "version=", g.get(  # noqa: E501
                "version",
            ))
        else:
            print("  !  PATCH", pst, pbody, file=sys.stderr)
    except Exception as e:  # noqa: S110
        print("  !  PATCH", e, file=sys.stderr)

    # delete file → row gone
    try:
        fp.unlink()
    except OSError as e:
        print("  !  unlink", e, file=sys.stderr)
    for _ in range(35):
        c, _, _ = _get_raw(f"/image/{new_id}")
        if c == 404:
            print("  OK  /image/404 after delete (D3#3)")
            return 0
        time.sleep(0.35)
    c2, b2, _ = _get_raw(f"/image/{new_id}")
    if c2 == 404:
        print("  OK  /image/404 after delete (D3#3)")
        return 0
    print("  !  /image/ still", c2, "after file delete; leave manual check", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as e:
        print("URLError (Comfy 未监听/地址错):", e, file=sys.stderr)
        sys.exit(3)
