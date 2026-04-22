#!/usr/bin/env python3
"""T19 D3 — consolidated automated acceptance probe (ComfyUI must be running).

Runs the former D3 checklist items that can be scripted over HTTP (+ optional
WebSocket) against a live PromptServer. Does **not** import ``gallery`` (no
SQLite lock with ComfyUI).

HTTP checks (stdlib ``urllib`` only):

  1. GET/PATCH/GET — favorite + ``gallery.version`` monotonic
  2. PATCH tags — response + GET list tags contain markers
  3. Invalid PATCH bodies — ``400`` + ``error.code == invalid_body``
  4. DELETE stub — ``501`` + ``not_implemented``
  5. POST ``/resync`` — ``version`` unchanged vs pre-resync, ``sync_status`` pending
  6. Read-path coexistence — ``GET /images``, ``GET /thumb/{id}`` return 200
  7. Optional non-PNG row — if found in listing, PATCH favorite and re-GET (sync may go failed)
  8. GET unknown image id — ``404`` + ``not_found`` (path sandbox 403 remains manual)

WebSocket checks (requires ``aiohttp`` — use the same interpreter / venv as ComfyUI):

  9. After PATCH, receive ``image.updated`` with matching ``id`` / ``version``
  10. Within a timeout, receive ``image.sync_status_changed`` for same id

Usage::

  python test/manual/t19_d3_automated_probe.py [base_url] [image_id] [--no-ws]

Defaults: ``http://127.0.0.1:8188`` and ``image_id=1``.

Exit code ``0`` = all executed checks passed; non-zero = first failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def _req(
    method: str,
    url: str,
    *,
    body: Any = None,
    timeout: float = 60.0,
) -> Tuple[int, Any]:
    """Return ``(status, parsed_json)``. On HTTP error, returns error status and body JSON if any."""
    payload = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            st = int(resp.status)
            if not raw.strip():
                return st, {}
            return st, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            parsed = {"_raw": raw}
        return int(e.code), parsed


def _get(url: str, *, timeout: float = 60.0) -> Tuple[int, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return int(resp.status), json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return int(e.code), json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return int(e.code), {"_raw": raw}


def _fail(step: str, detail: str) -> None:
    print(f"FAIL [{step}] {detail}")
    raise SystemExit(1)


def _ok(step: str, detail: str = "") -> None:
    print(f"OK   [{step}]{(' ' + detail) if detail else ''}")


def _gallery(doc: Any) -> Dict[str, Any]:
    g = doc.get("gallery")
    if not isinstance(g, dict):
        _fail("shape", "missing gallery object: " + repr(doc)[:200])
    return g


def run_http_suite(base: str, image_id: int) -> Dict[str, Any]:
    """Run HTTP-only checks; returns last ``GET /image/{id}`` document for WS phase."""
    root = base.rstrip("/")
    img_url = f"{root}/xyz/gallery/image/{image_id}"

    # --- D3.1 PATCH favorite + GET consistency ---
    st0, before = _get(img_url)
    if st0 != 200:
        _fail("D3.1 GET", f"status {st0} {before}")
    g0 = _gallery(before)
    ver0 = g0.get("version")
    fav0 = bool(g0.get("favorite"))
    if ver0 is None:
        _fail("D3.1 GET", "missing gallery.version")

    toggle = not fav0
    stp, patched = _req("PATCH", img_url, body={"favorite": toggle})
    if stp != 200:
        _fail("D3.1 PATCH", f"status {stp} {patched}")
    g1 = _gallery(patched)
    if g1.get("favorite") is not toggle:
        _fail("D3.1 PATCH body", f"favorite expected {toggle!r} got {g1.get('favorite')!r}")
    if g1.get("version") != ver0 + 1:
        _fail("D3.1 version", f"expected {ver0 + 1} got {g1.get('version')}")

    stg, after = _get(img_url)
    if stg != 200:
        _fail("D3.1 GET-after", f"status {stg} {after}")
    g2 = _gallery(after)
    if g2.get("favorite") is not toggle or g2.get("version") != ver0 + 1:
        _fail("D3.1 GET-after", f"mismatch {g2!r}")
    _ok("D3.1", f"favorite={toggle} version {ver0} -> {g2.get('version')}")

    # --- D3.2 PATCH tags ---
    tag_a, tag_b = "t19d3_cat", "t19d3_dog"
    stt, tagged = _req("PATCH", img_url, body={"tags": [tag_a, tag_b]})
    if stt != 200:
        _fail("D3.2 PATCH tags", f"status {stt} {tagged}")
    g3 = _gallery(tagged)
    ver_tags = g3.get("version")
    tags = g3.get("tags") or []
    if not isinstance(tags, list):
        _fail("D3.2 tags shape", str(tags))
    flat = ",".join(str(t).lower() for t in tags)
    if tag_a.lower() not in flat or tag_b.lower() not in flat:
        _fail("D3.2 tags", f"expected markers in tags, got {tags!r}")
    if ver_tags != ver0 + 2:
        _fail("D3.2 version", f"expected {ver0 + 2} got {ver_tags}")

    stg2, after_tags = _get(img_url)
    if stg2 != 200:
        _fail("D3.2 GET-after", str(after_tags))
    g4 = _gallery(after_tags)
    tags2 = g4.get("tags") or []
    flat2 = ",".join(str(t).lower() for t in tags2)
    if tag_a.lower() not in flat2 or tag_b.lower() not in flat2:
        _fail("D3.2 GET-after tags", str(tags2))
    _ok("D3.2", f"tags + version -> {g4.get('version')}")

    # --- D3.3 invalid body ---
    st_e, empty = _req("PATCH", img_url, body={})
    if st_e != 400 or empty.get("error", {}).get("code") != "invalid_body":
        _fail("D3.3 empty PATCH", f"status {st_e} {empty}")
    _ok("D3.3a", "empty {} -> 400 invalid_body")

    st_u, unk = _req("PATCH", img_url, body={"not_a_field": 1})
    if st_u != 400 or unk.get("error", {}).get("code") != "invalid_body":
        _fail("D3.3 unknown field", f"status {st_u} {unk}")
    _ok("D3.3b", "unknown field -> 400 invalid_body")

    # --- D3.4 DELETE stub ---
    st_d, del_body = _req("DELETE", img_url, body=None)
    if st_d != 501 or del_body.get("error", {}).get("code") != "not_implemented":
        _fail("D3.4 DELETE", f"status {st_d} {del_body}")
    _ok("D3.4", "DELETE -> 501 not_implemented")

    # --- D3.5 resync: version unchanged ---
    st_b5, snap = _get(img_url)
    if st_b5 != 200:
        _fail("D3.5 pre-resync GET", str(snap))
    v_before_resync = _gallery(snap).get("version")
    rs_url = f"{root}/xyz/gallery/image/{image_id}/resync"
    st_r, rs_doc = _req("POST", rs_url, body=None)
    if st_r != 200:
        _fail("D3.5 POST resync", f"status {st_r} {rs_doc}")
    g_rs = _gallery(rs_doc)
    if g_rs.get("version") != v_before_resync:
        _fail(
            "D3.5 resync version",
            f"expected unchanged {v_before_resync} got {g_rs.get('version')}",
        )
    if g_rs.get("sync_status") != "pending":
        _fail("D3.5 resync status", f"expected pending got {g_rs.get('sync_status')!r}")
    _ok("D3.5", f"resync version={v_before_resync} sync=pending")

    # --- D3.6 read-path coexistence ---
    st_li, li = _get(f"{root}/xyz/gallery/images?limit=3")
    if st_li != 200 or not isinstance(li.get("items"), list):
        _fail("D3.6 /images", f"status {st_li} {repr(li)[:300]}")
    th_url = f"{root}/xyz/gallery/thumb/{image_id}"
    try:
        with urllib.request.urlopen(th_url, timeout=120) as resp:
            raw = resp.read(16)
            st_th = int(resp.status)
    except urllib.error.HTTPError as e:
        _fail("D3.6 /thumb", f"HTTP {e.code} {e.read()[:200]!r}")
    if st_th != 200 or len(raw) < 1:
        _fail("D3.6 /thumb", f"status {st_th} bytes={len(raw)}")
    _ok("D3.6", "/images + /thumb OK")

    # --- D3.7 optional non-PNG ---
    st_li2, li2 = _get(f"{root}/xyz/gallery/images?limit=200")
    items = li2.get("items") if isinstance(li2, dict) else []
    non_png: Optional[Dict[str, Any]] = None
    if isinstance(items, list):
        for it in items:
            ext = (it or {}).get("ext")
            if isinstance(ext, str) and ext.lower() not in ("png", ""):
                non_png = it
                break
    if non_png is None:
        print("SKIP [D3.7] no non-png in first 200 /images rows")
    else:
        oid = int(non_png["id"])
        ou = f"{root}/xyz/gallery/image/{oid}"
        st_o, ob = _get(ou)
        if st_o != 200:
            print("SKIP [D3.7] GET non-png id failed", oid)
        else:
            vo = _gallery(ob).get("version")
            st_po, _ = _req("PATCH", ou, body={"favorite": True})
            if st_po != 200:
                _fail("D3.7 PATCH non-png", f"id={oid} status {st_po}")
            time.sleep(2.0)
            st_oa, oa = _get(ou)
            if st_oa != 200:
                _fail("D3.7 GET after", str(oa))
            st_final = _gallery(oa).get("sync_status")
            v_final = _gallery(oa).get("version")
            if v_final != vo + 1:
                _fail("D3.7 version", f"id={oid} expected {vo + 1} got {v_final}")
            _ok("D3.7", f"non-png id={oid} ext={non_png.get('ext')!r} sync={st_final!r}")

    print("SKIP [D3.10] WriteQueue not_ready — needs custom harness (no automation here).")

    # --- D3.8a GET unknown id (error envelope; true path sandbox needs hand-SQL) ---
    st_nf, nf = _get(f"{root}/xyz/gallery/image/999999999")
    if st_nf != 404 or nf.get("error", {}).get("code") != "not_found":
        _fail("D3.8a GET 404", f"expected 404 not_found got {st_nf} {nf}")
    _ok("D3.8a", "GET missing id -> 404 not_found")

    return after_tags


async def run_ws_suite(base: str, image_id: int, *, ws_timeout: float = 25.0) -> None:
    try:
        import aiohttp
    except ImportError:
        print("SKIP [D3.9-10] aiohttp not installed; use ComfyUI's Python or: pip install aiohttp")
        return

    from urllib.parse import urlparse

    p = urlparse(base)
    scheme = "wss" if p.scheme == "https" else "ws"
    ws_url = f"{scheme}://{p.netloc}/xyz/gallery/ws"
    root = base.rstrip("/")
    img_url = f"{root}/xyz/gallery/image/{image_id}"

    st0, before = _get(img_url)
    if st0 != 200:
        _fail("D3.9 WS-prep GET", f"{st0} {before}")
    g0 = _gallery(before)
    next_fav = not bool(g0.get("favorite"))

    events: List[Dict[str, Any]] = []

    async def _reader(ws: Any) -> None:
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        events.append(json.loads(msg.data))
                    except json.JSONDecodeError:
                        pass
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break
        except asyncio.CancelledError:
            raise

    async def _run() -> None:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url, timeout=30) as ws:
                read_task = asyncio.create_task(_reader(ws))
                await asyncio.sleep(0.25)
                async with session.patch(
                    img_url,
                    json={"favorite": next_fav},
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    body = await resp.json()
                    if resp.status != 200:
                        read_task.cancel()
                        try:
                            await read_task
                        except asyncio.CancelledError:
                            pass
                        _fail("D3.9 WS PATCH", f"{resp.status} {body}")
                    g = _gallery(body)
                    exp_ver = int(g["version"])

                deadline = time.monotonic() + ws_timeout
                seen_update = False
                seen_sync = False
                while time.monotonic() < deadline:
                    await asyncio.sleep(0.12)
                    for ev in events:
                        if ev.get("type") == "image.updated":
                            d = ev.get("data") or {}
                            if int(d.get("id", -1)) == image_id and int(d.get("version", -2)) == exp_ver:
                                seen_update = True
                        if ev.get("type") == "image.sync_status_changed":
                            d = ev.get("data") or {}
                            if int(d.get("id", -1)) == image_id:
                                st = str(d.get("sync_status", ""))
                                if st in ("ok", "failed", "pending"):
                                    seen_sync = True
                    if seen_update and seen_sync:
                        break

                read_task.cancel()
                try:
                    await read_task
                except asyncio.CancelledError:
                    pass

                if not seen_update:
                    _fail("D3.9 WS", f"no image.updated for id={image_id} ver={exp_ver}; tail={events[-5:]}")
                _ok("D3.9", "WS image.updated id+version match")

                if not seen_sync:
                    _fail(
                        "D3.10 WS",
                        f"no image.sync_status_changed within {ws_timeout}s; tail={events[-8:]}",
                    )
                _ok("D3.10", "WS image.sync_status_changed received")

    await _run()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base", nargs="?", default="http://127.0.0.1:8188")
    ap.add_argument("image_id", nargs="?", type=int, default=1)
    ap.add_argument("--no-ws", action="store_true", help="skip WebSocket checks")
    ap.add_argument(
        "--ws-timeout",
        type=float,
        default=25.0,
        metavar="SEC",
        help="max seconds to wait for WS sync_status_changed (default: 25)",
    )
    args = ap.parse_args()

    try:
        run_http_suite(args.base, int(args.image_id))
    except urllib.error.URLError as e:
        print("URLError:", e.reason)
        print("Hint: start ComfyUI with ComfyUI-XYZNodes; check base URL.")
        raise SystemExit(2) from e

    if not args.no_ws:
        try:
            asyncio.run(
                run_ws_suite(
                    args.base,
                    int(args.image_id),
                    ws_timeout=float(args.ws_timeout),
                )
            )
        except urllib.error.URLError:
            raise
    else:
        print("SKIP [D3.9-10] --no-ws")

    print("---")
    print("T19 D3 automated probe: ALL EXECUTED CHECKS PASSED")


if __name__ == "__main__":
    main()
