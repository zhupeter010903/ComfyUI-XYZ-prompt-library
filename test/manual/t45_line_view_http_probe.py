#!/usr/bin/env python3
"""
T45 — HTTP integration probe (requires running ComfyUI with XYZ Gallery).

Verifies static assets for line view exist and MainView wires LineVirtualGrid.

Run (from ComfyUI-XYZNodes):
  python test/manual/t45_line_view_http_probe.py [--base http://127.0.0.1:8188]

Exit 0 on success; non-zero with stderr on failure.
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8188", help="ComfyUI HTTP origin")
    args = p.parse_args()
    base = str(args.base).rstrip("/")

    checks = [
        (f"{base}/xyz/gallery/static/components/LineVirtualGrid.js", "LineVirtualGrid"),
        (f"{base}/xyz/gallery/static/sectionKeys.js", "sectionKeys"),
        (f"{base}/xyz/gallery/static/views/MainView.js", "MainView"),
        (f"{base}/xyz/gallery/static/stores/filters.js", "filters"),
    ]
    for url, label in checks:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read().decode("utf-8", errors="replace")
                code = r.status
        except urllib.error.HTTPError as e:
            print(f"FAIL {label}: HTTP {e.code} {url}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"FAIL {label}: {e!r} {url}", file=sys.stderr)
            return 1
        if code != 200:
            print(f"FAIL {label}: status {code} {url}", file=sys.stderr)
            return 1
        if label == "LineVirtualGrid" and "export const LineVirtualGrid" not in body:
            print("FAIL: LineVirtualGrid.js missing export", file=sys.stderr)
            return 1
        if label == "MainView" and "<LineVirtualGrid" not in body:
            print("FAIL: MainView.js missing LineVirtualGrid template", file=sys.stderr)
            return 1
        if label == "filters" and "view_mode" not in body:
            print("FAIL: filters.js missing view_mode", file=sys.stderr)
            return 1
        print(f"OK  {label} ({code})")

    print("t45_line_view_http_probe: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
