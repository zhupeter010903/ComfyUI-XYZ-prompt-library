#!/usr/bin/env python3
"""D2 (T36) — HTTP probe for ``/preferences`` + ``/admin/tags`` against a running ComfyUI.

Does **not** start the server. Expects gallery routes + WriteQueue already up.

Run (example):
    python test/manual/t36_gallery_settings_http_probe.py --base http://127.0.0.1:8188

Success (exit 0): prints JSON snippets and ``OK``.

Failure: non-zero exit + stderr message (connection refused, 4xx/5xx, or assertion).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--base",
        default="http://127.0.0.1:8188",
        help="ComfyUI HTTP root (default: %(default)s)",
    )
    args = p.parse_args()
    base = str(args.base).rstrip("/")
    pref = f"{base}/xyz/gallery/preferences"
    tags = f"{base}/xyz/gallery/admin/tags?q=&limit=5"

    def get(url: str) -> tuple[int, bytes]:
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return int(resp.status), resp.read()

    def patch(url: str, body: dict) -> tuple[int, bytes]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="PATCH",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return int(resp.status), resp.read()

    try:
        st, raw = get(pref)
    except urllib.error.URLError as exc:
        print(f"FAIL: GET {pref} -> {exc}", file=sys.stderr)
        return 2
    if st != 200:
        print(f"FAIL: GET {pref} HTTP {st}", file=sys.stderr)
        return 1
    j = json.loads(raw.decode("utf-8"))
    for k in (
        "download_variant",
        "download_prompt_each_time",
        "download_basename_prefix",
        "developer_mode",
        "theme",
        "filter_visibility",
    ):
        if k not in j:
            print(f"FAIL: preferences missing key {k!r}", file=sys.stderr)
            return 1
    print("GET /preferences:", json.dumps(j, indent=2)[:800])

    st2, raw2 = patch(pref, {"theme": j.get("theme", "dark")})
    if st2 != 200:
        print(f"FAIL: PATCH {pref} HTTP {st2} body={raw2[:500]!r}", file=sys.stderr)
        return 1
    print("PATCH /preferences (no-op theme):", raw2.decode("utf-8")[:400])

    try:
        st3, raw3 = get(tags)
    except urllib.error.URLError as exc:
        print(f"FAIL: GET {tags} -> {exc}", file=sys.stderr)
        return 2
    if st3 != 200:
        print(f"FAIL: GET {tags} HTTP {st3}", file=sys.stderr)
        return 1
    jtags = json.loads(raw3.decode("utf-8"))
    if not isinstance(jtags, dict):
        print("FAIL: admin/tags expected JSON object", file=sys.stderr)
        return 1
    rows = jtags.get("tags")
    if not isinstance(rows, list):
        print("FAIL: admin/tags.tags must be a list", file=sys.stderr)
        return 1
    if "total" not in jtags:
        print("FAIL: admin/tags missing total", file=sys.stderr)
        return 1
    print("GET /admin/tags (first rows):", json.dumps(rows[:3], indent=2), "total=", jtags.get("total"))
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
