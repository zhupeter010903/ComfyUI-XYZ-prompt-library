# Offline: apply latest SQLite migrations, then rebuild ``prompt_token`` /
# ``image_prompt_token`` **and** ``word_token`` / ``image_word_token`` from
# every row's ``image.positive_prompt`` (same op as gallery startup
# ``maybe_rebuild_prompt_vocab_from_config``, but **unconditional**).
#
# Use when you need to (re)fill the word lexeme tables after schema v6 or
# changed split rules — **stop ComfyUI first** so only this process holds the
# WriteQueue.
#
# Run:
#   python test/manual/rebuild_gallery_vocab_tables.py
#   python test/manual/rebuild_gallery_vocab_tables.py --data-dir "D:/path/gallery_data"
#
# Success (example):
#   user_version=6
#   prompt_token rows: 42, word_token rows: 120
#   OK: vocab rebuild finished (prompt + word).
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=_ROOT / "gallery_data",
        help="Directory containing gallery.sqlite (and gallery_config.json for stopwords)",
    )
    args = ap.parse_args()
    data_dir = args.data_dir.resolve()
    db_path = data_dir / "gallery.sqlite"
    if not db_path.is_file():
        print(f"ERROR: missing database file: {db_path}", file=sys.stderr)
        return 2

    from gallery import db
    from gallery import repo
    from gallery.indexer import _load_prompt_stopwords

    conn = db.connect_write(db_path)
    try:
        db.migrate(conn)
        conn.commit()
    finally:
        conn.close()

    r0 = db.connect_read(db_path)
    try:
        (uv,) = r0.execute("PRAGMA user_version").fetchone()
        print(f"user_version={int(uv)}")
    finally:
        r0.close()

    wq = repo.WriteQueue(db_path)
    wq.start()
    try:
        extra = _load_prompt_stopwords(db_path)
        fut = wq.enqueue_write(
            repo.HIGH,
            repo.RebuildPromptVocabFullOp(extra_stopwords=extra),
        )
        fut.result(timeout=600)
    finally:
        wq.stop()

    r1 = db.connect_read(db_path)
    try:
        pc = int(r1.execute("SELECT COUNT(*) FROM prompt_token").fetchone()[0])
        wc = int(r1.execute("SELECT COUNT(*) FROM word_token").fetchone()[0])
        print(f"prompt_token rows: {pc}, word_token rows: {wc}")
    finally:
        r1.close()

    print("OK: vocab rebuild finished (prompt + word).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
