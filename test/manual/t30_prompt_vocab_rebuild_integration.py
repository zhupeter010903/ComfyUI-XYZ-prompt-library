#!/usr/bin/env python3
"""T30 integration (requires ComfyUI cwd + PYTHONPATH to plugin root).

Verifies:
  * ``gallery_config.json`` ``vocab_version`` matches
    ``vocab.PROMPT_VOCAB_PIPELINE_VERSION`` after ``maybe_rebuild_prompt_vocab_from_config``
  * For the first ``image`` row (if any), ``image_prompt_token`` tokens match
    ``sorted(vocab.normalize_prompt(positive_prompt))``

Do **not** run against production ``gallery_data`` without backup.

Usage (from ComfyUI root, with ComfyUI Python):
  set PYTHONPATH=custom_nodes/ComfyUI-XYZNodes
  python custom_nodes/ComfyUI-XYZNodes/test/manual/t30_prompt_vocab_rebuild_integration.py

Or from plugin root (offline DB copy):
  python test/manual/t30_prompt_vocab_rebuild_integration.py --db path/to/gallery.sqlite --data-dir path/to/gallery_data_parent
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parents[2]
if str(_PLUGIN) not in sys.path:
    sys.path.insert(0, str(_PLUGIN))


def _run_offline(db_path: Path, data_dir: Path) -> int:
    from gallery import db, indexer, repo, vocab

    if not db_path.is_file():
        print("FAIL: db not found:", db_path, file=sys.stderr)
        return 2

    cfg = data_dir / "gallery_config.json"
    if not cfg.is_file():
        cfg.write_text(
            json.dumps(
                {
                    "roots": [],
                    "prompt_stopwords": [],
                    "vocab_version": 1,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    wq = repo.WriteQueue(db_path)
    wq.start()
    try:
        indexer.maybe_rebuild_prompt_vocab_from_config(
            db_path=db_path,
            data_dir=data_dir,
            write_queue=wq,
        )
    finally:
        wq.stop()

    ver = int(json.loads(cfg.read_text(encoding="utf-8")).get("vocab_version", 0))
    if ver != vocab.PROMPT_VOCAB_PIPELINE_VERSION:
        print("FAIL: vocab_version", ver, file=sys.stderr)
        return 1

    conn = db.connect_read(db_path)
    try:
        row = conn.execute(
            "SELECT id, positive_prompt FROM image ORDER BY id LIMIT 1",
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        print("OK (empty image table); vocab_version=", ver)
        return 0

    iid = int(row[0])
    pp = row[1]
    expect = sorted(vocab.normalize_prompt(pp or "", frozenset()))
    conn = db.connect_read(db_path)
    try:
        got = sorted(
            str(r[0])
            for r in conn.execute(
                "SELECT prompt_token.token FROM image_prompt_token ipt "
                "INNER JOIN prompt_token ON prompt_token.id = ipt.token_id "
                "WHERE ipt.image_id = ?",
                (iid,),
            ).fetchall()
        )
    finally:
        conn.close()

    if got != expect:
        print("FAIL image", iid, "got", got, "expect", expect, file=sys.stderr)
        return 1

    print("OK image", iid, "tokens", got)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--db",
        type=Path,
        default=_PLUGIN / "gallery_data" / "gallery.sqlite",
        help="path to gallery.sqlite",
    )
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=_PLUGIN / "gallery_data",
        help="directory containing gallery_config.json",
    )
    args = ap.parse_args()
    return _run_offline(args.db, args.data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
