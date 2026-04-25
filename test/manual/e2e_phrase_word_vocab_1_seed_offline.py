# E2E seed (ComfyUI **stopped**): drop one synthetic PNG under a registered
# output root and ``index_one`` it into ``gallery.sqlite`` so fresh phrase +
# word markers (with trailing ``.`` in the PNG text) land in
# ``prompt_token`` / ``word_token`` **without** storing the trailing dots.
#
# Prerequisites:
#   * ComfyUI not running (single writer on ``gallery.sqlite``).
#   * ``--output-root`` equals a ``folder`` row with ``parent_id IS NULL``
#     (typically the Comfy ``output`` directory already registered by T05).
#
# Run:
#   python test/manual/e2e_phrase_word_vocab_1_seed_offline.py ^
#     --gallery-data E:/.../ComfyUI-XYZNodes/gallery_data ^
#     --output-root E:/.../ComfyUI/output
#
# Success: prints JSON manifest path + ``OK script1``.
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _find_output_root(conn, want: Path) -> tuple[int, str, str]:
    want_r = want.resolve()
    for rid, path, kind in conn.execute(
        "SELECT id, path, kind FROM folder WHERE parent_id IS NULL",
    ):
        try:
            if Path(str(path)).resolve() == want_r:
                return int(rid), str(Path(str(path)).resolve()), str(kind)
        except OSError:
            continue
    raise SystemExit(
        f"No registered folder row matches --output-root {want_r} "
        "(seed default roots via Comfy once, or adjust path).",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--gallery-data",
        type=Path,
        required=True,
        help="Directory containing gallery.sqlite",
    )
    ap.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Absolute path to the registered gallery root (e.g. Comfy output/)",
    )
    args = ap.parse_args()
    gd = args.gallery_data.resolve()
    db_path = gd / "gallery.sqlite"
    if not db_path.is_file():
        print(f"ERROR: missing {db_path}", file=sys.stderr)
        return 2
    out_root = args.output_root.resolve()
    if not out_root.is_dir():
        print(f"ERROR: not a directory: {out_root}", file=sys.stderr)
        return 2

    from gallery import db, indexer, repo

    conn = db.connect_write(db_path)
    try:
        db.migrate(conn)
        conn.commit()
    finally:
        conn.close()

    r = db.connect_read(db_path)
    try:
        root_id, root_path, root_kind = _find_output_root(r, out_root)
    finally:
        r.close()

    uniq = uuid.uuid4().hex[:10]
    # No underscores: word lexemes replace "_" with space before split, so
    # "foo_bar" becomes two tokens, not one row in word_token.
    phrase = f"xyzgalphrase{uniq}"
    word = f"xyzgalword{uniq}"
    sub = out_root / "_xyz_gallery_e2e_probe"
    sub.mkdir(parents=True, exist_ok=True)
    png = sub / f"e2e_vocab_{uniq}.png"
    posix_png = png.resolve().as_posix()

    info = PngInfo()
    pos_line = f"{phrase}., {word}., sand."
    info.add_text(
        "parameters",
        f"{pos_line}\nNegative prompt: none\n"
        "Steps: 1, Sampler: Euler, CFG scale: 7, Seed: 1, Model: e2e_model",
    )
    Image.new("RGB", (4, 4), "white").save(png, pnginfo=info)

    wq = repo.WriteQueue(db_path)
    wq.start()
    try:
        root = {"id": root_id, "path": root_path, "kind": root_kind}
        iid = indexer.index_one(
            posix_png,
            root=root,
            db_path=db_path,
            write_queue=wq,
        )
        if iid is None:
            print(
                "ERROR: index_one returned None (already indexed same mtime/size? "
                "delete the png and retry).",
                file=sys.stderr,
            )
            return 3

        r2 = db.connect_read(db_path)
        try:
            p_ok = r2.execute(
                "SELECT 1 FROM prompt_token WHERE token = ? COLLATE NOCASE",
                (phrase.lower(),),
            ).fetchone()
            p_bad = r2.execute(
                "SELECT 1 FROM prompt_token WHERE token = ? COLLATE NOCASE",
                (phrase.lower() + ".",),
            ).fetchone()
            w_ok = r2.execute(
                "SELECT 1 FROM word_token WHERE token = ? COLLATE NOCASE",
                (word.lower(),),
            ).fetchone()
            w_bad = r2.execute(
                "SELECT 1 FROM word_token WHERE token = ? COLLATE NOCASE",
                (word.lower() + ".",),
            ).fetchone()
        finally:
            r2.close()

        if not p_ok or p_bad:
            print(f"ERROR: phrase token check p_ok={p_ok!r} p_bad={p_bad!r}", file=sys.stderr)
            return 4
        if not w_ok or w_bad:
            print(f"ERROR: word token check w_ok={w_ok!r} w_bad={w_bad!r}", file=sys.stderr)
            return 5

        manifest = {
            "uniq": uniq,
            "phrase_token": phrase.lower(),
            "word_token": word.lower(),
            "png_posix": posix_png,
            "image_id": int(iid),
        }
        man_path = sub / f"e2e_vocab_{uniq}.manifest.json"
        man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(man_path.resolve())
        print(json.dumps(manifest, indent=2))
    finally:
        wq.stop()

    print("OK script1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
