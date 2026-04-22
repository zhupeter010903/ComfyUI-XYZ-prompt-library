"""Create PNG / edge-case files under ComfyUI ``input/`` for manual QA.

Targets (T15 D3 / D5 style checks):

* **D3 #3** — One minimal valid PNG with ``xyz_gallery.tags`` (and optional
  ``xyz_gallery.favorite``) so cold scan / indexer fills ``tag`` /
  ``image_tag`` after re-index.
* **D5** — ``input/`` edge cases: tiny valid PNG, truncated PNG bytes, empty
  file (0 bytes) with ``.png`` extension — indexer should tolerate without
  wedging WriteQueue.

Run **with ComfyUI stopped** if you want zero risk of the process holding
handles open; otherwise closing the file picker / not having the file open
is usually enough.

Usage (from plugin root ``ComfyUI-XYZNodes``)::

    python test/manual/create_d3_d5_input_fixtures.py

Override directory::

    python test/manual/create_d3_d5_input_fixtures.py --input-dir "E:\\AI\\ComfyUI-aki-v2\\ComfyUI\\input"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo


# Keys must match ``gallery/metadata.py`` (T06).
_KEY_XYZ_TAGS = "xyz_gallery.tags"
_KEY_XYZ_FAVORITE = "xyz_gallery.favorite"
_KEY_PROMPT = "prompt"


def _default_input_dir() -> Path:
    # .../ComfyUI/custom_nodes/ComfyUI-XYZNodes/test/manual/this.py
    here = Path(__file__).resolve()
    comfy_root = here.parents[4]
    return comfy_root / "input"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="ComfyUI input directory (default: <ComfyUI root>/input next to this repo)",
    )
    args = p.parse_args()
    out: Path = args.input_dir if args.input_dir is not None else _default_input_dir()
    out = out.resolve()
    if not out.is_dir():
        print(f"ERROR: not a directory: {out}", file=sys.stderr)
        print("Pass --input-dir explicitly.", file=sys.stderr)
        return 1

    prefix = "xyz_gallery_qa_"

    # --- D3 #3: valid PNG + mirror tags (comma-separated; includes weight-like fragment)
    d3_name = prefix + "d3_tags.png"
    d3_path = out / d3_name
    info = PngInfo()
    info.add_text(
        _KEY_XYZ_TAGS,
        "d3-alpha, D3-Beta, (gallery-weight:1.2), 中文标签",
    )
    info.add_text(_KEY_XYZ_FAVORITE, "1")
    # Small positive prompt so ``positive_prompt`` / ``prompt_token`` are non-empty
    mini_prompt = (
        '{"1":{"class_type":"CLIPTextEncode","inputs":{"text":"hello d3 qa"}},'
        '"2":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":"dummy.ckpt"}}}'
    )
    info.add_text(_KEY_PROMPT, mini_prompt)
    Image.new("RGB", (4, 4), color=(240, 240, 240)).save(d3_path, pnginfo=info)
    print("Wrote", d3_path)

    # --- D5: tiny valid PNG (no gallery chunks)
    tiny_name = prefix + "d5_tiny_valid.png"
    tiny_path = out / tiny_name
    Image.new("RGB", (1, 1), color=(0, 0, 0)).save(tiny_path)
    print("Wrote", tiny_path)

    # --- D5: truncated PNG (magic + garbage — PIL should fail on full decode)
    bad_name = prefix + "d5_truncated.png"
    bad_path = out / bad_name
    bad_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"_not_a_real_chunk_")
    print("Wrote", bad_path)

    # --- D5: zero-byte file pretending to be PNG
    empty_name = prefix + "d5_zero_bytes.png"
    empty_path = out / empty_name
    empty_path.write_bytes(b"")
    print("Wrote", empty_path, "(0 bytes)")

    print()
    print("Next steps:")
    print("  1. Start ComfyUI; wait for cold_scan / indexer on the input root.")
    print("  2. D3: run  python test/manual/t15_vocab_sqlite_probe.py  <path-to-gallery.sqlite>")
    print("     Expect  tag / image_tag  counts > 0 for rows linked to", d3_name)
    print("  3. D5: confirm logs show no crash; DB still has image rows for tiny PNG;")
    print("     broken / empty files may have errors in metadata but rows exist (T07).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
