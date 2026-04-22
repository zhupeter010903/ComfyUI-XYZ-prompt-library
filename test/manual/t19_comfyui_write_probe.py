#!/usr/bin/env python3
"""Semi-automatic T19 probe — PATCH + /resync while ComfyUI is running.

Exercises ``PATCH /xyz/gallery/image/{id}`` and
``POST /xyz/gallery/image/{id}/resync`` against a live PromptServer.

Usage (from any directory, stdlib only):

  python test/manual/t19_comfyui_write_probe.py [base_url] [image_id]

Defaults: base_url=http://127.0.0.1:8188  image_id=1

Requires: ComfyUI up with ComfyUI-XYZNodes loaded; image_id must exist and
lie inside a registered gallery root (same constraints as GET /raw).

Does **not** import the gallery package (avoids ``gallery.sqlite`` lock
contention with the ComfyUI process).

For the **full D3 acceptance bundle** (invalid body, DELETE stub, /images,
/thumb, optional non-PNG, WS events), run::

  python test/manual/t19_d3_automated_probe.py [base_url] [image_id]
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def _req_json(method: str, url: str, body: object | None = None) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
        return int(resp.status), json.loads(raw) if raw.strip() else {}


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8188"
    iid = sys.argv[2] if len(sys.argv) > 2 else "1"
    root = base.rstrip("/")

    get_url = f"{root}/xyz/gallery/image/{iid}"
    try:
        with urllib.request.urlopen(get_url, timeout=30) as resp:
            before = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print("GET HTTPError:", e.code, e.read().decode("utf-8", errors="replace"))
        raise SystemExit(1)
    except urllib.error.URLError as e:
        print("GET URLError:", e.reason)
        raise SystemExit(1)

    ver0 = before.get("gallery", {}).get("version")
    fav0 = before.get("gallery", {}).get("favorite")
    print("before gallery.version =", ver0, "gallery.favorite =", fav0)

    patch_url = f"{root}/xyz/gallery/image/{iid}"
    toggle = not bool(fav0)
    try:
        st, after = _req_json("PATCH", patch_url, {"favorite": toggle})
    except urllib.error.HTTPError as e:
        print("PATCH HTTPError:", e.code, e.read().decode("utf-8", errors="replace"))
        raise SystemExit(2)
    if st != 200:
        print("PATCH unexpected status", st, after)
        raise SystemExit(2)
    ver1 = after.get("gallery", {}).get("version")
    if ver1 != ver0 + 1:
        print("FAIL: expected version increment", ver0, "->", ver0 + 1, "got", ver1)
        raise SystemExit(3)
    if after.get("gallery", {}).get("favorite") is not toggle:
        print("FAIL: favorite not toggled", after.get("gallery"))
        raise SystemExit(3)
    print("OK PATCH favorite ->", toggle, "gallery.version ->", ver1)

    resync_url = f"{root}/xyz/gallery/image/{iid}/resync"
    try:
        st2, rs = _req_json("POST", resync_url, None)
    except urllib.error.HTTPError as e:
        print("POST resync HTTPError:", e.code, e.read().decode("utf-8", errors="replace"))
        raise SystemExit(4)
    if st2 != 200:
        print("resync unexpected status", st2, rs)
        raise SystemExit(4)
    ver2 = rs.get("gallery", {}).get("version")
    if ver2 != ver1:
        print("FAIL: /resync must not bump version", ver1, ver2)
        raise SystemExit(4)
    if rs.get("gallery", {}).get("sync_status") != "pending":
        print("WARN: expected sync_status pending after resync, got", rs.get("gallery"))
    print("OK POST /resync version unchanged =", ver2, "sync_status =", rs.get("gallery", {}).get("sync_status"))

    print("T19 manual HTTP probe finished OK")


if __name__ == "__main__":
    main()
