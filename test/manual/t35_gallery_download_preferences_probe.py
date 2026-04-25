#!/usr/bin/env python3
"""T35/T36 integration probe — HTTP preferences + PNG download variants (requires ComfyUI).

Usage (ComfyUI already listening, default port 8188):
    python test/manual/t35_gallery_download_preferences_probe.py
    python test/manual/t35_gallery_download_preferences_probe.py --base http://127.0.0.1:8188

``--image-id`` (optional): try this id first. If download returns 404, or if
omitted, the script discovers an id via ``GET /xyz/gallery/images?limit=1``.

Exit 0 on success; non-zero on first failure.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _req(method: str, base: str, path: str, data: dict | None = None) -> tuple[int, bytes]:
    url = base + path
    payload = None if data is None else json.dumps(data).encode("utf-8")
    r = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={} if payload is None else {"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as e:
        return int(e.code), e.read()


def _discover_image_id(base: str) -> int | None:
    st, body = _req("GET", base, "/xyz/gallery/images?limit=1&sort=time&dir=desc")
    if st != 200:
        return None
    try:
        j = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    items = j.get("items")
    if not isinstance(items, list) or not items:
        return None
    iid = items[0].get("id")
    return int(iid) if isinstance(iid, int) or (isinstance(iid, str) and str(iid).isdigit()) else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--base",
        default="http://127.0.0.1:8188",
        help="ComfyUI HTTP origin (no trailing slash)",
    )
    p.add_argument(
        "--image-id",
        type=int,
        default=None,
        help="Preferred image id; on 404 or if omitted, discover from /images",
    )
    args = p.parse_args()
    base = str(args.base).rstrip("/")

    st, body = _req("GET", base, "/xyz/gallery/preferences")
    if st != 200:
        print("FAIL GET /preferences", st, body[:500], file=sys.stderr)
        return 1
    j = json.loads(body.decode("utf-8"))
    if "download_variant" not in j:
        print("FAIL preferences JSON missing download_variant", j, file=sys.stderr)
        return 1
    print("OK GET /preferences", j)

    st2, _ = _req(
        "PATCH",
        base,
        "/xyz/gallery/preferences",
        {"download_variant": j.get("download_variant") or "full"},
    )
    if st2 != 200:
        print("FAIL PATCH /preferences", st2, file=sys.stderr)
        return 2
    print("OK PATCH /preferences (no-op variant)")

    candidates: list[int] = []
    if args.image_id is not None:
        candidates.append(int(args.image_id))
    discovered = _discover_image_id(base)
    if discovered is not None and discovered not in candidates:
        candidates.append(discovered)
    if not candidates:
        print("FAIL no image id (--image-id unset and /images empty)", file=sys.stderr)
        return 5

    last_err: tuple[int, bytes] | None = None
    for iid in candidates:
        st3, png = _req("GET", base, f"/xyz/gallery/raw/{iid}/download?variant=clean")
        if st3 != 200:
            last_err = (st3, png)
            if st3 == 404 and args.image_id is not None and iid == int(args.image_id):
                print(
                    f"WARN raw/{iid}/download 404 — trying next candidate",
                    file=sys.stderr,
                )
            continue
        if len(png) < 100 or png[:8] != b"\x89PNG\r\n\x1a\n":
            print("FAIL clean download not PNG bytes", len(png), file=sys.stderr)
            return 4
        print("OK GET raw/", iid, "/download?variant=clean bytes=", len(png))
        return 0

    if last_err:
        st_e, body_e = last_err
        print("FAIL GET raw download clean", st_e, body_e[:300], file=sys.stderr)
        return 3
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
