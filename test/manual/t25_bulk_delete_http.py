#!/usr/bin/env python3
"""T25 integration — HTTP bulk delete preflight (+ optional execute) + DELETE image.

**Not run by CI** (requires running ComfyUI with gallery routes).

Default (safe): only ``POST /bulk/delete/preflight`` for one indexed image — no
files are removed.

Destructive path: pass ``--execute`` to call ``POST /bulk/delete/execute`` (bulk)
and/or ``--delete-one`` to ``DELETE /xyz/gallery/image/{id}`` (single).

Usage:
    python test/manual/t25_bulk_delete_http.py --base http://127.0.0.1:8188
    python test/manual/t25_bulk_delete_http.py --base http://127.0.0.1:8188 --execute
    python test/manual/t25_bulk_delete_http.py --base http://127.0.0.1:8188 --delete-one 42

Exit code 0 on success; 2 on HTTP error; 1 on assertion failure.

``GET /images`` sort keys: ``time|name|size|folder`` (``repo.SortSpec``).
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


def _req(
    method: str,
    url: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = 120.0,
    headers: Optional[Dict[str, str]] = None,
) -> tuple[int, Any]:
    data = None
    hdrs: Dict[str, str] = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=data, headers=hdrs, method=method)
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
    p.add_argument(
        "--execute",
        action="store_true",
        help="Run bulk delete execute after preflight (removes selected files!)",
    )
    p.add_argument(
        "--delete-one",
        type=int,
        default=0,
        metavar="ID",
        help="If >0, DELETE /image/{id} after bulk checks (still destructive)",
    )
    args = p.parse_args()
    base = str(args.base).rstrip("/")
    g = f"{base}/xyz/gallery"
    cid = str(uuid.uuid4())
    extra = {"X-XYZ-Gallery-Client-Id": cid}

    code, page = _req(
        "GET",
        f"{g}/images?limit=3&recursive=true&sort=time&dir=desc",
        headers=extra,
    )
    assert code == 200 and isinstance(page, dict), page
    items = page.get("items") or []
    assert isinstance(items, list) and items, "need at least one indexed image"
    img_id = int(items[0]["id"])

    sel = {"mode": "explicit", "ids": [img_id]}
    code, pre = _req(
        "POST",
        f"{g}/bulk/delete/preflight",
        {"selection": sel},
        headers=extra,
    )
    assert code == 200 and isinstance(pre, dict), pre
    assert pre.get("plan_id"), pre
    assert int(pre.get("total", 0)) >= 1, pre
    assert int(pre.get("total_bytes", -1)) >= 0, pre
    print("preflight OK:", json.dumps(pre, indent=2)[:500])

    if args.execute:
        code, ex = _req(
            "POST",
            f"{g}/bulk/delete/execute",
            {"plan_id": str(pre["plan_id"])},
            headers=extra,
        )
        assert code == 200 and isinstance(ex, dict), ex
        print("execute OK:", ex)

    if int(args.delete_one) > 0:
        one = int(args.delete_one)
        code, out = _req(
            "DELETE",
            f"{g}/image/{one}",
            headers=extra,
        )
        assert code == 200 and isinstance(out, dict), out
        print("DELETE single OK:", out)

    print("t25_bulk_delete_http: assertions passed")


if __name__ == "__main__":
    main()
