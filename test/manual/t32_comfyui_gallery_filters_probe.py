# T32 integration (requires running ComfyUI): static assets + ``GET /images``
# with the same query shape the SPA ``apiQueryObject()`` emits after T32
# (non-default ``metadata_presence`` / ``prompt_match_mode`` + repeated ``prompt``).
#
# Prerequisites:
#   - ComfyUI with ComfyUI-XYZNodes loaded, default ``http://127.0.0.1:8188``
#
# Run:
#   python E:/.../ComfyUI-XYZNodes/test/manual/t32_comfyui_gallery_filters_probe.py
#
# Success (example):
#   OK: T32 gallery filter probe (7 checks).
#
# Failure (example):
#   FAIL: ... expected 200 got ...
#   HTTP error (is ComfyUI running?): ...
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _get(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as e:
        return int(e.code), e.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8188")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    checks: list[tuple[str, int, str]] = [
        (f"{base}/xyz/gallery/static/stores/filters.js", 200, "static_filters"),
        (f"{base}/xyz/gallery/static/views/MainView.js", 200, "static_mainview"),
        (f"{base}/xyz/gallery/static/components/Autocomplete.js", 200, "static_ac"),
        (
            f"{base}/xyz/gallery/images?limit=3&sort=time&dir=desc"
            "&metadata_presence=yes&prompt_match_mode=word&prompt=cat&prompt=sitting",
            200,
            "images_word_multi_prompt",
        ),
        (
            f"{base}/xyz/gallery/images/count?metadata_presence=no&prompt_match_mode=prompt",
            200,
            "count_no_meta",
        ),
        (
            f"{base}/xyz/gallery/images?prompt_match_mode=string&prompt=foo_bar&limit=3",
            200,
            "images_string_underscore",
        ),
        (
            f"{base}/xyz/gallery/vocab/words?prefix=a&limit=5",
            200,
            "vocab_words",
        ),
    ]

    for url, want_status, tag in checks:
        status, raw = _get(url)
        if status != want_status:
            print(f"FAIL: [{tag}] {url!r} expected {want_status} got {status}", file=sys.stderr)
            try:
                print(raw.decode("utf-8", errors="replace")[:800], file=sys.stderr)
            except Exception:
                pass
            return 1
        if tag.startswith("static_"):
            if tag == "static_filters":
                if b"metadata_presence" not in raw or b"prompt_match_mode" not in raw:
                    print(f"FAIL: [{tag}] body missing T32 wire markers", file=sys.stderr)
                    return 1
            elif tag == "static_mainview":
                if b"promptFetchKind" not in raw:
                    print(f"FAIL: [{tag}] body missing promptFetchKind", file=sys.stderr)
                    return 1
            elif tag == "static_ac":
                if b"suggestionsOff" not in raw:
                    print(f"FAIL: [{tag}] Autocomplete missing suggestionsOff prop", file=sys.stderr)
                    return 1
        elif tag == "vocab_words":
            try:
                arr = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                print(f"FAIL: [{tag}] invalid JSON", file=sys.stderr)
                return 1
            if not isinstance(arr, list):
                print(f"FAIL: [{tag}] expected list", file=sys.stderr)
                return 1
        else:
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                print(f"FAIL: [{tag}] invalid JSON", file=sys.stderr)
                return 1
            if tag != "count_no_meta" and "items" not in body:
                print(f"FAIL: [{tag}] list JSON missing items", file=sys.stderr)
                return 1
            if tag == "count_no_meta":
                if "total" not in body:
                    print(f"FAIL: [{tag}] count JSON missing total", file=sys.stderr)
                    return 1

    print("OK: T32 gallery filter probe (%d checks)." % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
