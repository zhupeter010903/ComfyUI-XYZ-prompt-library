#!/usr/bin/env python3
"""T24 integration — HTTP bulk move + single move (requires running ComfyUI).

**Not run by CI** (needs PromptServer + gallery routes + WriteQueue).

Usage (example):
    python test/manual/t24_bulk_move_http.py --base http://127.0.0.1:8188

Exit code 0 on success; non-zero on first failed assertion or HTTP error.

``GET /images`` sort: use ``sort=time|name|size|folder`` and optional ``dir=asc|desc``
(see ``repo.SortSpec``), not ``created_at_desc``.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


def _req(
    method: str,
    url: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = 120.0,
) -> tuple[int, Any]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            code = int(resp.status)
            if not raw:
                return code, None
            try:
                return code, json.loads(raw)
            except json.JSONDecodeError:
                return code, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"_raw": raw}
        print(f"HTTP {e.code} {url}: {payload}", file=sys.stderr)
        raise SystemExit(2) from e


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--base",
        default="http://127.0.0.1:8188",
        help="ComfyUI PromptServer base URL (no trailing slash)",
    )
    args = p.parse_args()
    base = str(args.base).rstrip("/")
    g = f"{base}/xyz/gallery"

    code, folders = _req("GET", f"{g}/folders?include_counts=false")
    assert code == 200 and isinstance(folders, list) and folders, "need /folders"
    root_id = int(folders[0]["id"])

    code, page = _req(
        "GET",
        f"{g}/images?limit=5&folder_id={root_id}&recursive=true&sort=time&dir=desc",
    )
    assert code == 200 and isinstance(page, dict), page
    items = page.get("items") or []
    assert isinstance(items, list) and items, "need at least one indexed image"
    img_id = int(items[0]["id"])

    sel = {"mode": "explicit", "ids": [img_id]}
    code, pre = _req(
        "POST",
        f"{g}/bulk/move/preflight",
        {"selection": sel, "target_folder_id": root_id},
    )
    assert code == 200 and pre.get("plan_id"), pre
    plan_id = str(pre["plan_id"])
    mappings = pre.get("mappings") or []
    assert isinstance(mappings, list), mappings

    if not mappings:
        print("preflight returned no moves (image already at target); smoke OK")
        return

    code, ex = _req(
        "POST",
        f"{g}/bulk/move/execute",
        {"plan_id": plan_id, "rename_overrides": {}},
    )
    assert code == 200 and isinstance(ex, dict), ex
    assert "moved" in ex, ex
    print("OK bulk preflight+execute:", json.dumps(ex, indent=2)[:800])

    code, page2 = _req(
        "GET",
        f"{g}/images?limit=5&folder_id={root_id}&recursive=true&sort=time&dir=desc",
    )
    assert code == 200, page2


if __name__ == "__main__":
    main()
