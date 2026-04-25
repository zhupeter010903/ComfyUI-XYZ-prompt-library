# T31 integration (requires running ComfyUI): ``GET /xyz/gallery/images`` and
# ``GET /xyz/gallery/images/count`` with ``metadata_presence`` /
# ``prompt_match_mode`` / ``prompt`` query params; assert HTTP status and
# JSON envelope (not semantic row counts — DB-dependent).
#
# Prerequisites:
#   - ComfyUI with plugin loaded, default ``http://127.0.0.1:8188``
#
# Run:
#   python E:/.../ComfyUI-XYZNodes/test/manual/t31_comfyui_images_filter_probe.py
#
# Success (example):
#   OK: all probe requests returned expected status / JSON shape.
#
# Failure (example):
#   FAIL: GET ... expected 200 got 404 ...
#   HTTP error (is ComfyUI running?): ...
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _request_json(url: str) -> tuple[int, object]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = int(resp.status)
            body = json.loads(resp.read().decode("utf-8"))
        return status, body
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"_raw": raw}
        return int(e.code), body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8188")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    probes: list[tuple[str, int, str]] = [
        (
            f"{base}/xyz/gallery/images?limit=5&sort=time&dir=desc"
            "&metadata_presence=all",
            200,
            "list",
        ),
        (
            f"{base}/xyz/gallery/images/count?metadata_presence=yes",
            200,
            "count_yes",
        ),
        (
            f"{base}/xyz/gallery/images?metadata_presence=no&limit=5",
            200,
            "list_no",
        ),
        (
            f"{base}/xyz/gallery/images?prompt_match_mode=string&prompt=test"
            "&limit=5",
            200,
            "list_string",
        ),
        (
            f"{base}/xyz/gallery/images?metadata_presence=invalid_enum",
            400,
            "bad_meta",
        ),
        (
            f"{base}/xyz/gallery/images/count?prompt_match_mode=bad",
            400,
            "bad_pmm",
        ),
    ]

    try:
        for url, want, tag in probes:
            status, body = _request_json(url)
            if status != want:
                print(
                    f"FAIL [{tag}]: expected HTTP {want} got {status} url={url!r}",
                    file=sys.stderr,
                )
                return 1
            if want == 200:
                if tag.startswith("count"):
                    if not isinstance(body, dict) or "total" not in body:
                        print(f"FAIL [{tag}]: bad count JSON {body!r}", file=sys.stderr)
                        return 1
                else:
                    if not isinstance(body, dict) or "items" not in body:
                        print(f"FAIL [{tag}]: bad list JSON keys", file=sys.stderr)
                        return 1
            else:
                err = body.get("error") if isinstance(body, dict) else None
                if not isinstance(err, dict) or err.get("code") != "invalid_query":
                    print(
                        f"FAIL [{tag}]: expected invalid_query envelope, got {body!r}",
                        file=sys.stderr,
                    )
                    return 1
    except urllib.error.URLError as e:
        print(f"HTTP error (is ComfyUI running?): {e}", file=sys.stderr)
        return 2

    print("OK: all probe requests returned expected status / JSON shape.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
