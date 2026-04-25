#!/usr/bin/env python3
"""
T37 — 运行中 ComfyUI：校验 ``GET /xyz/gallery/image/{id}`` 的
``metadata.positive_prompt`` / ``metadata.positive_prompt_normalized`` 字段。

前置：ComfyUI 已启动、ComfyUI-XYZNodes 已加载、库中至少 1 张图。

成功：退出码 0，打印含 ``positive_prompt_normalized`` 的 ``metadata`` 片段。

失败：非 200、缺字段、或 JSON 非对象 —— 非零退出 + stderr。

用法::

  python test/manual/t37_detail_json_probe.py
  python test/manual/t37_detail_json_probe.py --base http://127.0.0.1:8188 --id 42
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _get_json(url: str) -> object:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base",
        default="http://127.0.0.1:8188",
        help="ComfyUI 根（无尾斜杠）",
    )
    ap.add_argument(
        "--id",
        type=int,
        default=None,
        help="图片 id；省略则从 /xyz/gallery/images?limit=1&sort=time&dir=desc 取首条",
    )
    args = ap.parse_args()
    base = str(args.base).rstrip("/")
    api = f"{base}/xyz/gallery"
    image_id = args.id
    if image_id is None:
        page = _get_json(f"{api}/images?limit=1&sort=time&dir=desc")
        items = page.get("items") if isinstance(page, dict) else None
        if not items or not isinstance(items, list) or not items:
            print("no items in gallery — add images or pass --id", file=sys.stderr)
            return 2
        first = items[0]
        if not isinstance(first, dict) or first.get("id") is None:
            print("unexpected /images item shape", file=sys.stderr)
            return 2
        image_id = int(first["id"])

    try:
        data = _get_json(f"{api}/image/{image_id}")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} for /image/{image_id}", file=sys.stderr)
        return 3
    except OSError as e:
        print(f"request failed: {e}", file=sys.stderr)
        return 3

    if not isinstance(data, dict):
        print("response is not a JSON object", file=sys.stderr)
        return 4
    meta = data.get("metadata")
    if not isinstance(meta, dict):
        print("missing metadata object", file=sys.stderr)
        return 4
    if "positive_prompt_normalized" not in meta:
        print("metadata.positive_prompt_normalized missing (T37)", file=sys.stderr)
        return 5

    print(json.dumps(
        {
            "id": data.get("id"),
            "filename": data.get("filename"),
            "positive_prompt": meta.get("positive_prompt"),
            "positive_prompt_normalized": meta.get("positive_prompt_normalized"),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
