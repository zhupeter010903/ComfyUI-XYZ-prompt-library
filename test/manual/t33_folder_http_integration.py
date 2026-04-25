#!/usr/bin/env python3
"""T33 integration probe — HTTP folder endpoints against a running ComfyUI.

Does NOT start the server. Sends real HTTP requests.

Usage:
    python test/manual/t33_folder_http_integration.py --base-url http://127.0.0.1:8188

Success: exit code 0 and prints ``T33 integration OK``.

Failure: non-zero exit and stderr/stdout with HTTP status + body.

前置条件: ComfyUI 已启动且已加载 ComfyUI-XYZNodes（gallery routes 已注册）。
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
    base: str,
    path: str,
    *,
    body: Optional[Dict[str, Any]] = None,
) -> tuple[int, Any]:
    url = base.rstrip("/") + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            code = int(resp.status)
            raw = resp.read()
            if code == 204:
                return code, None
            ct = resp.headers.get("content-type", "")
            if "application/json" in ct:
                return code, json.loads(raw.decode("utf-8"))
            return code, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return int(e.code), json.loads(raw)
        except json.JSONDecodeError:
            return int(e.code), raw


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:8188",
        help="ComfyUI PromptServer origin (no trailing path)",
    )
    args = p.parse_args()
    base = str(args.base_url).rstrip("/")
    prefix = base + "/xyz/gallery"

    code, data = _req("GET", prefix, "/folders?include_counts=false")
    assert code == 200, (code, data)
    assert isinstance(data, list) and len(data) >= 1, data
    root = data[0]
    root_id = int(root["id"])

    code, data = _req("POST", prefix, f"/folders/{root_id}/mkdir", body={"name": "_t33_probe"})
    if code != 201:
        print("mkdir failed:", code, data, file=sys.stderr)
        return 1

    new_path = None
    if isinstance(data, dict):
        new_path = data.get("path")
    code2, tree = _req("GET", prefix, "/folders?include_counts=false")
    assert code2 == 200
    new_id = None
    for node in tree:
        stack = [node]
        while stack:
            n = stack.pop()
            if new_path and str(n.get("path", "")) == str(new_path):
                new_id = int(n["id"])
                break
            for c in n.get("children") or []:
                stack.append(c)
        if new_id is not None:
            break
    if new_id is None:
        print("could not resolve new folder id from tree", file=sys.stderr)
        return 1

    code, _ = _req("DELETE", prefix, f"/folders/{new_id}")
    if code != 204:
        print("delete empty failed:", code, _, file=sys.stderr)
        return 1

    code, data = _req("POST", prefix, f"/folders/{root_id}/rescan", body={})
    if code != 200 or not isinstance(data, dict) or data.get("scheduled") is not True:
        print("rescan failed:", code, data, file=sys.stderr)
        return 1

    print("T33 integration OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
