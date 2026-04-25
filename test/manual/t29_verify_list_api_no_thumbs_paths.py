# T29 integration (requires running ComfyUI): sample ``GET /xyz/gallery/images``
# and assert no returned ``path`` contains a ``/_thumbs/`` directory segment.
#
# Prerequisites:
#   - ComfyUI listening on ``--base`` (default http://127.0.0.1:8188)
#   - Gallery routes mounted (plugin loaded)
#
# Run from any CWD:
#   python E:/.../ComfyUI-XYZNodes/test/manual/t29_verify_list_api_no_thumbs_paths.py
#
# Success:
#   OK: checked N items, no /_thumbs/ paths in sample.
#
# Failure:
#   FAIL: path contains _thumbs segment: '...'
#   HTTP error (is ComfyUI running?): ...
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def _path_has_thumbs_segment(path: str) -> bool:
    if not path:
        return False
    norm = path.replace("\\", "/").strip().lower()
    return "/_thumbs/" in norm or norm.endswith("/_thumbs")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8188")
    ap.add_argument("--pages", type=int, default=3)
    args = ap.parse_args()
    base = args.base.rstrip("/")
    url = f"{base}/xyz/gallery/images?limit=200&sort=time&dir=desc"
    checked = 0
    cursor = None
    try:
        for _ in range(max(1, args.pages)):
            q = url + (
                f"&cursor={urllib.parse.quote(cursor, safe='')}" if cursor else ""
            )
            req = urllib.request.Request(q, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            items = body.get("items") or []
            for it in items:
                checked += 1
                p = it.get("path")
                if isinstance(p, str) and _path_has_thumbs_segment(p):
                    print(
                        f"FAIL: path contains _thumbs segment: {p!r}",
                        file=sys.stderr,
                    )
                    return 1
            cursor = body.get("next_cursor")
            if not cursor:
                break
    except urllib.error.URLError as e:
        print(f"HTTP error (is ComfyUI running?): {e}", file=sys.stderr)
        return 2

    print(f"OK: checked {checked} list item(s), no /_thumbs/ paths in sample.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
