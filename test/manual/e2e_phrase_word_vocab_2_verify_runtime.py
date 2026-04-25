# E2E verify (ComfyUI **running**): after ``e2e_phrase_word_vocab_1_seed_offline.py``,
# check SQLite + HTTP vocab for seeded markers, add a **second** PNG with new
# markers while the watcher is live, then **delete** the first PNG and assert
# orphan phrase/word rows disappear (no autocomplete rows for the old prefix).
#
# Prerequisites:
#   * ComfyUI up with XYZ gallery plugin; same ``gallery.sqlite`` as script1.
#   * Default ``http://127.0.0.1:8188`` (override with ``--base``).
#
# Run (use the real path printed by script1 as ``manifest_path``, not ``<uniq>``):
#   python test/manual/e2e_phrase_word_vocab_2_verify_runtime.py ^
#     --manifest E:/AI/.../output/_xyz_gallery_e2e_probe/e2e_vocab_77dbea339c.manifest.json
# Or pick the newest probe manifest under your Comfy output folder:
#   python test/manual/e2e_phrase_word_vocab_2_verify_runtime.py ^
#     --latest-manifest E:/AI/.../ComfyUI/output
#
# Success: ``OK script2`` on stdout; non-zero exit on first failed assertion.
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _get_json(url: str) -> tuple[int, object]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return int(resp.status), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"_raw": raw}
        return int(e.code), body


def _newest_probe_manifest(output_root: Path) -> Path | None:
    probe = output_root.resolve() / "_xyz_gallery_e2e_probe"
    cands = sorted(
        probe.glob("e2e_vocab_*.manifest.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return cands[0] if cands else None


def _vocab_names(base: str, kind: str, prefix: str) -> list[str]:
    path = "words" if kind == "words" else "prompts"
    st, data = _get_json(
        f"{base}/xyz/gallery/vocab/{path}?prefix={urllib.parse.quote(prefix, safe='')}&limit=50",
    )
    if st != 200:
        raise RuntimeError(f"vocab {path} HTTP {st}: {data!r}")
    if not isinstance(data, list):
        raise RuntimeError(f"vocab {path} not a list: {data!r}")
    return [str(x.get("name", "")) for x in data]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mx = ap.add_mutually_exclusive_group(required=True)
    mx.add_argument(
        "--manifest",
        type=Path,
        help="JSON from script1 (field manifest_path in script1 stdout)",
    )
    mx.add_argument(
        "--latest-manifest",
        type=Path,
        metavar="OUTPUT_ROOT",
        help="Newest e2e_vocab_*.manifest.json under OUTPUT_ROOT/_xyz_gallery_e2e_probe",
    )
    ap.add_argument(
        "--gallery-data",
        type=Path,
        default=None,
        help="Override gallery dir (default: sibling gallery_data of manifest png)",
    )
    ap.add_argument("--base", default="http://127.0.0.1:8188")
    args = ap.parse_args()
    if args.latest_manifest is not None:
        man_path = _newest_probe_manifest(args.latest_manifest)
        if man_path is None:
            probe = args.latest_manifest.resolve() / "_xyz_gallery_e2e_probe"
            print(
                f"ERROR: no e2e_vocab_*.manifest.json under {probe} "
                "(run script1 first, or pass --manifest with the exact path).",
                file=sys.stderr,
            )
            return 2
    else:
        man_path = Path(args.manifest).expanduser().resolve()
        if not man_path.is_file():
            hint = ""
            s = str(man_path)
            if "<uniq>" in s or "<" in s and ">" in s:
                hint = (
                    " Do not copy doc placeholders like e2e_vocab_<uniq>.manifest.json; "
                    "use script1's printed manifest_path, or --latest-manifest OUTPUT_ROOT."
                )
            print(f"ERROR: manifest not found: {man_path}.{hint}", file=sys.stderr)
            return 2
    try:
        man = json.loads(man_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: cannot read manifest {man_path}: {exc}", file=sys.stderr)
        return 2
    phrase = str(man["phrase_token"])
    word = str(man["word_token"])
    png1 = Path(man["png_posix"])
    iid1 = int(man["image_id"])
    base = args.base.rstrip("/")

    if args.gallery_data is not None:
        db_path = Path(args.gallery_data).resolve() / "gallery.sqlite"
    else:
        db_path = _ROOT / "gallery_data" / "gallery.sqlite"
    if not db_path.is_file():
        print(f"ERROR: missing {db_path}", file=sys.stderr)
        return 2

    # --- A: SQLite phrase/word present (no trailing-dot rows) ---
    con = sqlite3.connect(str(db_path))
    try:
        def _has_token(table: str, tok: str) -> bool:
            r = con.execute(
                f"SELECT 1 FROM {table} WHERE token = ? COLLATE NOCASE",
                (tok,),
            ).fetchone()
            return r is not None

        assert _has_token("prompt_token", phrase), "missing phrase token"
        assert _has_token("word_token", word), "missing word token"
        assert not _has_token("prompt_token", phrase + "."), "bad dotted phrase row"
        assert not _has_token("word_token", word + "."), "bad dotted word row"
    finally:
        con.close()

    # --- B: HTTP autocomplete lists include markers ---
    pfx_p = phrase[:16]
    pfx_w = word[:16]
    names_p = _vocab_names(base, "prompts", pfx_p)
    names_w = _vocab_names(base, "words", pfx_w)
    if phrase not in names_p:
        print(f"ERROR: phrase not in /vocab/prompts for {pfx_p!r}: {names_p[:10]}", file=sys.stderr)
        return 3
    if word not in names_w:
        print(f"ERROR: word not in /vocab/words for {pfx_w!r}: {names_w[:10]}", file=sys.stderr)
        return 4

    # --- C: second PNG while Comfy running ---
    uniq2 = uuid.uuid4().hex[:10]
    # Same convention as script1: no underscores in markers (word lexemes split on _).
    phrase2 = f"xyzgalphrase{uniq2}"
    word2 = f"xyzgalword{uniq2}"
    png2 = png1.parent / f"e2e_vocab_{uniq2}.png"
    info2 = PngInfo()
    pos2 = f"{phrase2}., {word2}., stone."
    info2.add_text(
        "parameters",
        f"{pos2}\nNegative prompt: none\n"
        "Steps: 1, Sampler: Euler, CFG scale: 7, Seed: 2, Model: e2e_model",
    )
    Image.new("RGB", (4, 4), "gray").save(png2, pnginfo=info2)

    deadline = time.time() + 90.0
    while time.time() < deadline:
        con = sqlite3.connect(str(db_path))
        try:
            ok2 = con.execute(
                "SELECT 1 FROM word_token WHERE token = ? COLLATE NOCASE",
                (word2.lower(),),
            ).fetchone()
        finally:
            con.close()
        if ok2:
            break
        time.sleep(2)
    else:
        print("ERROR: watcher did not index second png within timeout", file=sys.stderr)
        return 5

    names_w2 = _vocab_names(base, "words", word2[:16])
    if word2.lower() not in names_w2:
        print(f"ERROR: new word not in autocomplete: {names_w2[:10]}", file=sys.stderr)
        return 6

    # --- D: remove first image file; wait for DB + vocab cleanup ---
    try:
        png1.unlink()
    except OSError as exc:
        print(f"ERROR: unlink {png1}: {exc}", file=sys.stderr)
        return 7

    deadline = time.time() + 90.0
    gone = ph_orphan = wd_orphan = False
    while time.time() < deadline:
        con = sqlite3.connect(str(db_path))
        try:
            gone = con.execute(
                "SELECT 1 FROM image WHERE id = ?",
                (iid1,),
            ).fetchone() is None
            ph_orphan = con.execute(
                "SELECT 1 FROM prompt_token WHERE token = ? COLLATE NOCASE",
                (phrase,),
            ).fetchone() is None
            wd_orphan = con.execute(
                "SELECT 1 FROM word_token WHERE token = ? COLLATE NOCASE",
                (word,),
            ).fetchone() is None
        finally:
            con.close()
        if gone and ph_orphan and wd_orphan:
            break
        time.sleep(2)
    else:
        print(
            "ERROR: timeout waiting delete reconcile "
            f"(image gone={gone} phrase gone={ph_orphan} word gone={wd_orphan})",
            file=sys.stderr,
        )
        return 8

    try:
        names_p_after = _vocab_names(base, "prompts", phrase[:16])
        names_w_after = _vocab_names(base, "words", word[:16])
    except RuntimeError as exc:
        print(f"ERROR: vocab after delete: {exc}", file=sys.stderr)
        return 9
    if phrase in names_p_after or word in names_w_after:
        print(
            f"ERROR: old markers still in autocomplete "
            f"prompts={names_p_after!r} words={names_w_after!r}",
            file=sys.stderr,
        )
        return 10

    # Optional: remove second png to avoid litter (best-effort)
    try:
        png2.unlink()
    except OSError:
        pass

    print("OK script2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
