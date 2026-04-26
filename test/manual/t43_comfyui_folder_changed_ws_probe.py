# T43 — live ComfyUI probe: after HTTP mkdir, expect WS ``folder.changed`` with ``root_id``.
# Exercises indexer reconcile → ws_hub path (TASKS T43 integration; does not drive a browser).
#
# Prerequisites:
#   * ComfyUI running with ComfyUI-XYZNodes loaded.
#   * Writable default output root (mkdir allowed).
#
# Run::
#   python test/manual/t43_comfyui_folder_changed_ws_probe.py --base http://127.0.0.1:8188
#
# Success (exit 0): prints ``OK: folder.changed root_id=...`` and optional cleanup note.
# Failure: non-zero; ``ASSERT:`` / ``ERROR:`` on stderr or stdout.
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from typing import Any, Dict, List, Optional
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


def _first_output_root_id(nodes: Any) -> Optional[int]:
    if not isinstance(nodes, list):
        return None
    for n in nodes:
        if not isinstance(n, dict):
            continue
        if str(n.get("kind", "")).lower() == "output":
            try:
                return int(n["id"])
            except (TypeError, ValueError, KeyError):
                continue
    for n in nodes:
        if isinstance(n, dict) and n.get("id") is not None:
            try:
                return int(n["id"])
            except (TypeError, ValueError, KeyError):
                continue
    return None


async def _run(base: str) -> int:
    http_b = _http_base(base)
    folders_url = urljoin(http_b + "/", "xyz/gallery/folders?include_counts=true")
    ws_url = _ws_url_from_http(http_b)

    async with aiohttp.ClientSession() as sess:
        async with sess.get(folders_url) as r:
            text = await r.text()
            assert r.status == 200, f"GET folders: {r.status} {text[:300]}"
            nodes: List[Dict[str, Any]] = json.loads(text)
        root_id = _first_output_root_id(nodes)
        assert root_id is not None, f"no root folder id in {nodes!r:.400}"

        name = f"xyz_t43_ws_probe_{uuid.uuid4().hex[:10]}"
        mkdir_url = urljoin(http_b + "/", f"xyz/gallery/folders/{root_id}/mkdir")

        changed_root: Optional[int] = None

        async with sess.ws_connect(ws_url, timeout=25) as ws:
            recv_task = asyncio.create_task(_wait_folder_changed(ws, 20.0))
            async with sess.post(
                mkdir_url,
                json={"name": name},
                headers={"Content-Type": "application/json"},
            ) as mr:
                mbody = await mr.text()
                assert mr.status == 201, f"POST mkdir: {mr.status} {mbody[:400]}"

            changed_root = await recv_task

        assert changed_root == root_id, (
            f"expected folder.changed root_id={root_id}, got {changed_root!r}"
        )

    print(f"OK: folder.changed root_id={changed_root} (probe dir: {name})")
    print("Cleanup (optional): delete the empty folder via gallery UI or OS explorer under output.")
    return 0


async def _wait_folder_changed(ws: aiohttp.ClientWebSocketResponse, timeout: float) -> Optional[int]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            msg = await asyncio.wait_for(
                ws.receive(),
                timeout=max(0.25, min(1.0, deadline - loop.time())),
            )
        except asyncio.TimeoutError:
            continue
        if msg.type == aiohttp.WSMsgType.CLOSE or msg.type == aiohttp.WSMsgType.CLOSING:
            break
        if msg.type != aiohttp.WSMsgType.TEXT:
            continue
        try:
            env = json.loads(msg.data)
        except json.JSONDecodeError:
            continue
        if not isinstance(env, dict):
            continue
        if env.get("type") != "folder.changed":
            continue
        data = env.get("data") or {}
        if isinstance(data, dict) and "root_id" in data:
            try:
                return int(data["root_id"])
            except (TypeError, ValueError):
                return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base",
        default="http://127.0.0.1:8188",
        help="ComfyUI root (scheme + host + port)",
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
