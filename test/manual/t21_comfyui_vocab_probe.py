#!/usr/bin/env python3
"""Semi-automatic T21 probe — ``/vocab/*`` + filtered ``/images`` on live ComfyUI.

Uses stdlib only (no ``import gallery`` — avoids SQLite lock with ComfyUI).

Usage::

  python test/manual/t21_comfyui_vocab_probe.py [base_url]

Default base_url: http://127.0.0.1:8188

Requires: ComfyUI running with ComfyUI-XYZNodes; gallery DB populated (T15
vocab tables non-empty for meaningful autocomplete).

Exit code 0 on success; non-zero on HTTP errors or assertion failures.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def _get_json(url: str) -> tuple[int, object]:
    """GET JSON; returns ``(status, body)`` for 2xx/4xx/5xx (body parsed when JSON)."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return int(resp.status), json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            body = {"_raw": raw}
        return int(e.code), body


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8188"
    root = base.rstrip("/")
    pfx = f"{root}/xyz/gallery"

    def get(path_qs: str) -> tuple[int, object]:
        url = f"{pfx}{path_qs}"
        try:
            return _get_json(url)
        except urllib.error.URLError as e:
            print("URLError", url, e.reason)
            raise SystemExit(2)

    st, tags = get("/vocab/tags?prefix=&limit=5")
    if st != 200:
        print("FAIL vocab/tags status", st)
        raise SystemExit(3)
    if not isinstance(tags, list):
        print("FAIL vocab/tags not a list", type(tags))
        raise SystemExit(3)
    for row in tags[:3]:
        if not isinstance(row, dict) or "name" not in row or "usage_count" not in row:
            print("FAIL vocab/tags row shape", row)
            raise SystemExit(3)
    print("OK /vocab/tags rows:", len(tags), "sample:", tags[0] if tags else None)

    st2, prompts = get("/vocab/prompts?prefix=a&limit=5")
    if st2 != 200 or not isinstance(prompts, list):
        print("FAIL vocab/prompts", st2, prompts)
        raise SystemExit(4)
    print("OK /vocab/prompts rows:", len(prompts))

    st3, models = get("/vocab/models")
    if st3 != 200 or not isinstance(models, list):
        print("FAIL vocab/models", st3, models)
        raise SystemExit(5)
    if models and not isinstance(models[0], dict):
        print("FAIL vocab/models row must be object with model/label/usage_count", models[0])
        raise SystemExit(5)
    print("OK /vocab/models count:", len(models), "sample:", models[0] if models else None)

    st4, bad = get("/vocab/tags?limit=notanumber")
    if st4 != 400:
        print("FAIL expected 400 invalid limit, got", st4, bad)
        raise SystemExit(6)
    err = bad.get("error") if isinstance(bad, dict) else None
    if not isinstance(err, dict) or err.get("code") != "invalid_query":
        print("FAIL expected error.code invalid_query, got", bad)
        raise SystemExit(6)
    print("OK invalid limit -> 400 invalid_query")

    st5, imgs = get("/images?limit=3&sort=time&dir=desc")
    if st5 != 200 or "items" not in imgs:
        print("FAIL /images baseline", st5)
        raise SystemExit(7)
    print("OK /images baseline items:", len(imgs.get("items", [])))

    print("\nT21 comfy vocab probe: ALL OK")


if __name__ == "__main__":
    main()
