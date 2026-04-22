"""XYZ Image Gallery — SQLite schema, PRAGMAs, and forward-only migrations (T03).

Scope (per TASKS.md T03):
  * Opinionated PRAGMA setup (WAL / NORMAL / MEMORY / 256 MiB mmap / 5 s busy_timeout)
    applied uniformly to both read and write connections.
  * Version-gated forward-only migration framework keyed on ``PRAGMA user_version``.
  * ``MIGRATIONS[1]`` creates the ``folder`` + ``image`` tables and all indexes
    listed in ``PROJECT_SPEC §6.1``.

Out of scope (intentionally deferred, per AI_RULES R1.2 / R6.3 / R6.4):
  * ``tag`` / ``image_tag`` / ``prompt_token`` / ``image_prompt_token`` / ``image_fts``
    + FTS5 tokenizer declaration              — T15 / T28
  * ``metadata_sync_*`` columns + ``version`` — T16 / MIGRATIONS[4]
  * WriteQueue / repo read APIs / ops         — T04 / T09
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Dict, Union

__all__ = [
    "connect_read",
    "connect_write",
    "migrate",
    "MIGRATIONS",
    "SCHEMA_VERSION",
]


# -- PRAGMA -----------------------------------------------------------------

_MMAP_BYTES = 256 * 1024 * 1024
_BUSY_TIMEOUT_MS = 5000


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    # Order matters: WAL must be set before heavy reads/writes touch the file.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute(f"PRAGMA mmap_size = {_MMAP_BYTES}")
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")


# -- Connection factories ---------------------------------------------------

_PathLike = Union[str, Path]


def connect_read(path: _PathLike) -> sqlite3.Connection:
    """Open a short-lived read connection. WAL allows many of these concurrently."""
    conn = sqlite3.connect(str(path))
    _apply_pragmas(conn)
    conn.row_factory = sqlite3.Row
    return conn


def connect_write(path: _PathLike) -> sqlite3.Connection:
    """Open an exclusive writer-side connection.

    ``isolation_level=None`` puts sqlite3 in autocommit mode so the future
    single-writer loop (T04) can own ``BEGIN`` / ``COMMIT`` boundaries
    explicitly (one op per transaction, per ARCHITECTURE §4.6).
    """
    conn = sqlite3.connect(str(path), isolation_level=None)
    _apply_pragmas(conn)
    return conn


# -- Schema v1 --------------------------------------------------------------

# NOTE: every DDL uses IF NOT EXISTS so that forcing ``PRAGMA user_version=0``
# and restarting re-runs the migration idempotently (TASKS.md T03 test #3).
_V1_DDL = """
CREATE TABLE IF NOT EXISTS folder (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    path          TEXT UNIQUE NOT NULL,
    kind          TEXT NOT NULL,
    parent_id     INTEGER REFERENCES folder(id),
    display_name  TEXT,
    removable     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS image (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    path              TEXT UNIQUE NOT NULL,
    folder_id         INTEGER REFERENCES folder(id),
    relative_path     TEXT NOT NULL,
    filename          TEXT NOT NULL,
    filename_lc       TEXT NOT NULL,
    ext               TEXT NOT NULL,
    width             INTEGER,
    height            INTEGER,
    file_size         INTEGER,
    mtime_ns          INTEGER,
    created_at        INTEGER,
    content_hash      TEXT,
    positive_prompt   TEXT,
    negative_prompt   TEXT,
    model             TEXT,
    seed              INTEGER,
    cfg               REAL,
    sampler           TEXT,
    scheduler         TEXT,
    workflow_present  INTEGER,
    favorite          INTEGER,
    tags_csv          TEXT,
    indexed_at        INTEGER
);

CREATE INDEX IF NOT EXISTS idx_image_folder_rel    ON image(folder_id, relative_path);
CREATE INDEX IF NOT EXISTS idx_image_filename_lc   ON image(filename_lc);
CREATE INDEX IF NOT EXISTS idx_image_model         ON image(model);
CREATE INDEX IF NOT EXISTS idx_image_favorite      ON image(favorite);
CREATE INDEX IF NOT EXISTS idx_image_created_at    ON image(created_at);
CREATE INDEX IF NOT EXISTS idx_image_file_size     ON image(file_size);
CREATE INDEX IF NOT EXISTS idx_image_mtime_ns      ON image(mtime_ns);
"""


def _migrate_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(_V1_DDL)


# -- Schema v2 (T08) --------------------------------------------------------

# ``thumbnail_cache`` is the authoritative LRU index for the on-disk .webp
# shards under ``gallery_data/thumbs/`` (SPEC §6.1, §8.3). The ``.webp``
# files are treated as a materialisation of the rows here; a daily janitor
# (T26) reconciles drift. ON DELETE CASCADE on ``image_id`` means deleting
# an image row automatically prunes its thumb-cache bookkeeping, but the
# physical .webp still needs the janitor (§8.3 "two-way reconciliation").
_V2_DDL = """
CREATE TABLE IF NOT EXISTS thumbnail_cache (
    hash_key       TEXT PRIMARY KEY,
    image_id       INTEGER NOT NULL REFERENCES image(id) ON DELETE CASCADE,
    size_bytes     INTEGER NOT NULL,
    created_at     INTEGER NOT NULL,
    last_accessed  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_thumb_last_accessed ON thumbnail_cache(last_accessed);
CREATE INDEX IF NOT EXISTS idx_thumb_image_id      ON thumbnail_cache(image_id);
"""


def _migrate_v2(conn: sqlite3.Connection) -> None:
    conn.executescript(_V2_DDL)


# -- Migration framework ----------------------------------------------------

# Forward-only ledger. Future tasks append entries here (T15 → 3,
# T16 → 4, T28 → 5); an FTS5-tokenizer-signature check at that point should
# gate a full reindex — intentionally not wired yet (see module docstring).
MIGRATIONS: Dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _migrate_v1,
    2: _migrate_v2,
}

SCHEMA_VERSION: int = max(MIGRATIONS)


def migrate(conn: sqlite3.Connection) -> None:
    """Bring ``conn`` up to ``SCHEMA_VERSION`` by forward-executing MIGRATIONS.

    * Reads ``PRAGMA user_version`` as the current level.
    * Runs every registered step with ``version > current`` in ascending order.
    * Bumps ``user_version`` after each step (persisted on commit).
    * Raises on a DB that is *newer* than this build knows about, to avoid
      silently downgrading or stepping on unknown schema (C-4).
    """
    (current,) = conn.execute("PRAGMA user_version").fetchone()
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"gallery.sqlite user_version={current} is newer than "
            f"this build (max known = {SCHEMA_VERSION}); refusing to downgrade."
        )
    for version in sorted(MIGRATIONS):
        if version <= current:
            continue
        MIGRATIONS[version](conn)
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()
