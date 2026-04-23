# T23 — live ComfyUI probe: POST /xyz/gallery/bulk/resolve_selection + /bulk/favorite
# (smoke) + all_except resolve (no mutation on all_except path).
# Requires: ComfyUI running with this plugin; gallery with ≥1 indexed image.
#
# Run (example):
#   python test/manual/t23_comfyui_bulk_probe.py --base http://127.0.0.1:8188
#
# Success: exit 0, prints short JSON lines.
# Failure: non-zero exit, assert or HTTP error.
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Dict
from urllib.parse import urljoin

import aiohttp


def _http_base(s: str) -> str:
    s = s.rstrip("/")
    if not s.startswith("http://") and not s.startswith("https://"):
        s = "http://" + s
    return s


async def _run(base: str) -> int:
    http_b = _http_base(base)
    g = urljoin(http_b + "/", "xyz/gallery")
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{g}/images?limit=2&sort=time&dir=desc") as r:
            t = await r.text()
            assert r.status == 200, f"GET /images: {r.status} {t[:300]}"
            page: Dict[str, Any] = json.loads(t)
        items = page.get("items") or []
        assert items, "need at least one image in the gallery DB"
        iid = int(items[0]["id"])
        sel_ex: dict = {"mode": "explicit", "ids": [iid]}
        async with sess.post(
            f"{g}/bulk/resolve_selection",
            json={"selection": sel_ex, "limit": 10},
        ) as r:
            t = await r.text()
            assert r.status == 200, f"resolve explicit: {r.status} {t[:400]}"
            res = json.loads(t)
        assert res.get("count") == 1, res
        assert isinstance(res.get("ids"), list) and res["ids"][0] == iid, res

        sel_all: dict = {
            "mode": "all_except",
            "filters": {
                "name": "",
                "positive_tokens": [],
                "tag_tokens": [],
                "favorite": "all",
                "model": "",
                "date_after": "",
                "date_before": "",
                "folder_id": None,
                "recursive": False,
            },
            "excluded_ids": [],
        }
        async with sess.post(
            f"{g}/bulk/resolve_selection",
            json={"selection": sel_all, "limit": 0},
        ) as r:
            t = await r.text()
            assert r.status == 200, f"resolve all_except: {r.status} {t[:400]}"
            res2 = json.loads(t)
        assert "count" in res2 and int(res2["count"]) >= 1, res2

        body_fav = {"selection": sel_ex, "value": True}
        async with sess.post(f"{g}/bulk/favorite", json=body_fav) as r:
            t = await r.text()
            assert r.status == 200, f"bulk favorite: {r.status} {t[:400]}"
            out = json.loads(t)
        assert out.get("affected") == 1 and "bulk_id" in out, out
        body_un = {"selection": sel_ex, "value": False}
        async with sess.post(f"{g}/bulk/favorite", json=body_un) as r:
            t = await r.text()
            assert r.status == 200, f"bulk unfavorite: {r.status} {t[:400]}"
            out2 = json.loads(t)
        assert out2.get("affected") == 1, out2

    print("OK: bulk resolve + favorite round-trip for id", iid)
    print("     all_except count =", int(res2["count"]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base",
        default="http://127.0.0.1:8188",
        help="ComfyUI HTTP root (default 127.0.0.1:8188)",
    )
    args = ap.parse_args()
    try:
        return asyncio.run(_run(args.base))
    except AssertionError as e:
        print("ASSERT:", e, file=sys.stderr)
        return 1
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
