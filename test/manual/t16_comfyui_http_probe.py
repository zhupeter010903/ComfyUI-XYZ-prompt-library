#!/usr/bin/env python3
"""Semi-automatic T16 probe (run while ComfyUI serves the XYZ Gallery routes).

Checks that GET /xyz/gallery/image/{id} JSON includes gallery.sync_status and
gallery.version after MIGRATIONS[4].

Usage:
  python test/manual/t16_comfyui_http_probe.py [base_url] [image_id]

Defaults: base_url=http://127.0.0.1:8188  image_id=1

Requires: Python stdlib only (urllib). Does not import gallery package.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8188"
    iid = sys.argv[2] if len(sys.argv) > 2 else "1"
    url = base.rstrip("/") + "/xyz/gallery/image/" + iid
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print("HTTPError:", e.code, e.reason, e.read().decode("utf-8", errors="replace"))
        raise SystemExit(1)
    except urllib.error.URLError as e:
        print("URLError:", e.reason)
        print("Hint: start ComfyUI with XYZNodes loaded; adjust base URL if needed.")
        raise SystemExit(1)

    data = json.loads(body)
    g = data.get("gallery")
    if not isinstance(g, dict):
        print("FAIL: missing gallery object:", data)
        raise SystemExit(2)
    if "sync_status" not in g or "version" not in g:
        print("FAIL: gallery missing sync_status/version:", g)
        raise SystemExit(2)
    print("OK gallery.sync_status =", repr(g["sync_status"]))
    print("OK gallery.version =", repr(g["version"]))


if __name__ == "__main__":
    main()
