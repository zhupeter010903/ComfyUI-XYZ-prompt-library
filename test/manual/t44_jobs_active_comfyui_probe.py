# integration (requires running ComfyUI with XYZ gallery routes)
# Usage:  python t44_jobs_active_comfyui_probe.py [--base http://127.0.0.1:8188]
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
        help="ComfyUI base URL (no trailing slash)",
    )
    a = p.parse_args()
    url = f"{a.base.rstrip('/')}/xyz/gallery/jobs/active"
    req = urllib.request.Request(  # noqa: S310
        url, headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            body = resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        print("FAIL: cannot reach", url, e, file=sys.stderr)
        return 2
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        print("FAIL: not JSON:", e, body[:200], file=sys.stderr)
        return 3
    if not isinstance(data, dict) or "jobs" not in data:
        print("FAIL: envelope {jobs:[...]}", data, file=sys.stderr)
        return 4
    if not isinstance(data["jobs"], list):
        print("FAIL: jobs is not a list", file=sys.stderr)
        return 5
    print("OK", data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
