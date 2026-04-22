"""XYZ Image Gallery — repository (T04 write side + T09 read side).

Scope:
  * **Write side (T04)**: ``WriteQueue`` priority queue + single-writer
    daemon thread; every op is wrapped in its *own*
    ``BEGIN / op.apply(conn) / COMMIT`` transaction (**not** the
    drain-64 / SAVEPOINT batch model that an earlier revision of
    ARCHITECTURE §4.6 described — explicitly superseded by T04's
    UPDATED spec to guarantee that a failing op never partially-commits
    alongside its neighbours).  ``enqueue_write(priority, op) -> Future``
    is the sole public write API.
  * **Op classes**: ``UpsertImageOp`` (T07), ``EnsureFolderOp`` (T05),
    ``InsertThumbCacheOp`` (T08), placeholders ``UpdateImagePathOp``
    (T24) / ``DeleteImageOp`` (T19/T25).
  * **Read side (T09)**: ``get_image`` / ``list_images`` (cursor-paged,
    filtered) / ``folder_tree`` / ``neighbors``.  All read APIs open a
    short-lived ``db.connect_read`` connection (WAL → multi-reader);
    they never touch the WriteQueue.

Out of scope (deferred):
  * Selection resolution                           — T23
  * ``UpdateImageOp`` / real ``DeleteImageOp``     — T19 / T24 / T25
  * ``tag`` / ``image_tag`` / FTS5 schema + queries — T15 / T28
"""

from __future__ import annotations

import base64
import itertools
import json
import logging
import queue
import sqlite3
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

from . import db as _db

logger = logging.getLogger("xyz.gallery.repo")

__all__ = [
    "HIGH",
    "MID",
    "LOW",
    "WriteQueue",
    "UpsertImageOp",
    "UpdateImagePathOp",
    "DeleteImageOp",
    "EnsureFolderOp",
    "InsertThumbCacheOp",
    # T09 read-side DTOs + API
    "FilterSpec",
    "SortSpec",
    "ImageRecord",
    "FolderNode",
    "ListPage",
    "Neighbors",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "TOTAL_ESTIMATE_CAP",
    "get_image",
    "list_images",
    "folder_tree",
    "neighbors",
]


HIGH: int = 0
MID: int = 1
LOW: int = 2

_VALID_PRIORITIES = frozenset((HIGH, MID, LOW))

# Starvation guard: after this many consecutive LOW ops, if any HIGH/MID is
# waiting, defer the current LOW. In the one-op-per-tx model PriorityQueue
# already preempts on every get(); this is a belt-and-suspenders check
# mandated by TASKS.md T04.
_LOW_YIELD_THRESHOLD: int = 200

# Writer-crash restart backoff: keep it well under the 200 ms stop budget
# (TASKS.md T04 test #4) so a single crash can't blow the join deadline.
_CRASH_RESTART_SLEEP_SEC: float = 0.02

_PathLike = Union[str, Path]


# -- Placeholder op factories ----------------------------------------------
#
# T04 intentionally ships these as empty shells: the WriteQueue contract is
# "anything with a .apply(conn) method can be enqueued". Concrete fields and
# SQL are added by the owning downstream task. Do NOT widen these here.

class UpsertImageOp:
    """Upsert one ``image`` row (T07 cold-scan / delta-scan / index_one).

    Fields mirror the ``image`` columns populated at index time (SPEC §6.1).
    ``content_hash`` is intentionally left NULL — SPEC marks it as
    "computed lazily" and T07 does not compute it (AI_RULES R1.2 / R4.3).

    ``favorite`` / ``tags_csv`` come from the PNG's ``xyz_gallery.*`` mirror
    chunks (if present).  On conflict we ``COALESCE`` these two columns so
    that re-indexing a PNG that no longer carries the mirror does NOT wipe
    a value the DB already holds (DB is the source of truth — C-1).

    Folder-chain maintenance also lives here: before the image row itself,
    ``apply()`` walks ``root → ... → immediate dir`` and ``INSERT OR IGNORE``s
    each level into ``folder`` (``parent_id`` chained).  The per-op
    transaction guarantees image + sub-folder rows land atomically.
    Reusing the shared op-per-transaction envelope keeps the invariant
    from PROJECT_STATE §4 #15 intact (no writes outside the queue).
    """

    def __init__(self, *,
                 path: str,
                 folder_id: int,
                 root_path: str,
                 root_kind: str,
                 relative_path: str,
                 filename: str,
                 filename_lc: str,
                 ext: str,
                 width: Optional[int],
                 height: Optional[int],
                 file_size: int,
                 mtime_ns: int,
                 created_at: int,
                 positive_prompt: Optional[str],
                 negative_prompt: Optional[str],
                 model: Optional[str],
                 seed: Optional[int],
                 cfg: Optional[float],
                 sampler: Optional[str],
                 scheduler: Optional[str],
                 workflow_present: int,
                 favorite: Optional[int],
                 tags_csv: Optional[str],
                 indexed_at: int):
        self.path = path
        self.folder_id = folder_id
        self.root_path = root_path
        self.root_kind = root_kind
        self.relative_path = relative_path
        self.filename = filename
        self.filename_lc = filename_lc
        self.ext = ext
        self.width = width
        self.height = height
        self.file_size = int(file_size)
        self.mtime_ns = int(mtime_ns)
        self.created_at = int(created_at)
        self.positive_prompt = positive_prompt
        self.negative_prompt = negative_prompt
        self.model = model
        self.seed = seed
        self.cfg = cfg
        self.sampler = sampler
        self.scheduler = scheduler
        self.workflow_present = int(workflow_present)
        self.favorite = favorite
        self.tags_csv = tags_csv
        self.indexed_at = int(indexed_at)

    def apply(self, conn: sqlite3.Connection) -> None:
        self._ensure_folder_chain(conn)
        conn.execute(_UPSERT_IMAGE_SQL, {
            "path": self.path,
            "folder_id": self.folder_id,
            "relative_path": self.relative_path,
            "filename": self.filename,
            "filename_lc": self.filename_lc,
            "ext": self.ext,
            "width": self.width,
            "height": self.height,
            "file_size": self.file_size,
            "mtime_ns": self.mtime_ns,
            "created_at": self.created_at,
            "positive_prompt": self.positive_prompt,
            "negative_prompt": self.negative_prompt,
            "model": self.model,
            "seed": self.seed,
            "cfg": self.cfg,
            "sampler": self.sampler,
            "scheduler": self.scheduler,
            "workflow_present": self.workflow_present,
            "favorite": self.favorite,
            "tags_csv": self.tags_csv,
            "indexed_at": self.indexed_at,
        })

    def _ensure_folder_chain(self, conn: sqlite3.Connection) -> None:
        # relative_path is the POSIX path relative to root_path, including
        # the filename.  The folder chain is everything *above* the file.
        rel_dir = self.relative_path.rsplit("/", 1)[0] if "/" in self.relative_path else ""
        if not rel_dir:
            return
        parent_id: int = self.folder_id
        parent_path: str = self.root_path
        for part in rel_dir.split("/"):
            if not part:
                continue
            sub_path = parent_path + "/" + part if not parent_path.endswith("/") else parent_path + part
            conn.execute(
                "INSERT OR IGNORE INTO folder"
                "(path, kind, parent_id, display_name, removable) "
                "VALUES (?, ?, ?, ?, ?)",
                (sub_path, self.root_kind, parent_id, part, 0),
            )
            row = conn.execute(
                "SELECT id FROM folder WHERE path = ?", (sub_path,)
            ).fetchone()
            if row is None:
                # Extremely unlikely — INSERT OR IGNORE above is inside the
                # same tx, so the row must be visible to this SELECT.
                # Bail out rather than silently stranding the image.
                raise RuntimeError(
                    f"folder row for {sub_path!r} vanished mid-transaction"
                )
            parent_id = int(row[0])
            parent_path = sub_path


# Stored at module level so the (somewhat long) SQL is built once per
# process rather than on every op.  ``COALESCE`` on ``favorite`` /
# ``tags_csv`` protects DB-authoritative values across re-indexing runs
# that happen to re-read a PNG whose xyz_gallery mirror chunks were not
# (or are no longer) written.
_UPSERT_IMAGE_SQL = """
INSERT INTO image (
    path, folder_id, relative_path, filename, filename_lc, ext,
    width, height, file_size, mtime_ns, created_at,
    positive_prompt, negative_prompt, model, seed, cfg, sampler, scheduler,
    workflow_present, favorite, tags_csv, indexed_at
) VALUES (
    :path, :folder_id, :relative_path, :filename, :filename_lc, :ext,
    :width, :height, :file_size, :mtime_ns, :created_at,
    :positive_prompt, :negative_prompt, :model, :seed, :cfg, :sampler, :scheduler,
    :workflow_present, :favorite, :tags_csv, :indexed_at
)
ON CONFLICT(path) DO UPDATE SET
    folder_id        = excluded.folder_id,
    relative_path    = excluded.relative_path,
    filename         = excluded.filename,
    filename_lc      = excluded.filename_lc,
    ext              = excluded.ext,
    width            = excluded.width,
    height           = excluded.height,
    file_size        = excluded.file_size,
    mtime_ns         = excluded.mtime_ns,
    created_at       = excluded.created_at,
    positive_prompt  = excluded.positive_prompt,
    negative_prompt  = excluded.negative_prompt,
    model            = excluded.model,
    seed             = excluded.seed,
    cfg              = excluded.cfg,
    sampler          = excluded.sampler,
    scheduler        = excluded.scheduler,
    workflow_present = excluded.workflow_present,
    favorite         = COALESCE(excluded.favorite, image.favorite),
    tags_csv         = COALESCE(excluded.tags_csv, image.tags_csv),
    indexed_at       = excluded.indexed_at
"""


class UpdateImagePathOp:
    """Placeholder for T24's bulk-move path update."""

    def apply(self, conn: sqlite3.Connection) -> None:
        return None


class DeleteImageOp:
    """Placeholder for T19 / T25's single and bulk delete paths."""

    def apply(self, conn: sqlite3.Connection) -> None:
        return None


# T05: real (non-placeholder) op for registering a root folder. Lives here
# so that folders.py never touches a write connection directly — preserves
# the WriteQueue invariant (PROJECT_STATE §4 #15 / AI_RULES R5.5). Defined
# alongside the placeholder ops rather than inside folders.py to keep all
# op classes discoverable from a single module (ARCHITECTURE §2.1).
class EnsureFolderOp:
    """Idempotently INSERT a row into ``folder``.

    INSERT OR IGNORE makes the op safe to enqueue on every startup; the
    UNIQUE(path) index on ``folder`` decides idempotency. ``parent_id``
    defaults to NULL (= registered root); discovered sub-folders are not
    in T05's scope (T07 owns that wiring).
    """

    def __init__(self, *, path: str, kind: str, removable: int,
                 display_name: str, parent_id: Optional[int] = None):
        self.path = path
        self.kind = kind
        self.removable = int(removable)
        self.display_name = display_name
        self.parent_id = parent_id

    def apply(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO folder"
            "(path, kind, parent_id, display_name, removable) "
            "VALUES (?, ?, ?, ?, ?)",
            (self.path, self.kind, self.parent_id,
             self.display_name, self.removable),
        )


# T08: real op for the thumbnail_cache bookkeeping row written after a
# .webp has already been materialised on disk ("先物理后入队", §4.5).
# INSERT OR REPLACE keeps the row fresh if the same hash_key is written
# twice (e.g. a regeneration after a transient disk error) — hash_key is
# derived from (path, mtime_ns) so collisions on a stable file are a
# no-op rewrite, and mtime_ns changes produce a brand-new PK entirely.
class InsertThumbCacheOp:
    """Record a freshly-generated WebP thumbnail in ``thumbnail_cache``."""

    def __init__(self, *, hash_key: str, image_id: int,
                 size_bytes: int, created_at: int, last_accessed: int):
        self.hash_key = hash_key
        self.image_id = int(image_id)
        self.size_bytes = int(size_bytes)
        self.created_at = int(created_at)
        self.last_accessed = int(last_accessed)

    def apply(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO thumbnail_cache"
            "(hash_key, image_id, size_bytes, created_at, last_accessed) "
            "VALUES (?, ?, ?, ?, ?)",
            (self.hash_key, self.image_id, self.size_bytes,
             self.created_at, self.last_accessed),
        )


# -- Read side (T09) -------------------------------------------------------
#
# All read APIs are synchronous, open a short-lived ``db.connect_read``
# connection per call, and never touch the WriteQueue (ARCHITECTURE §4.2:
# reads go directly through WAL-backed read connections so writer
# pressure cannot block them). Callers in the future HTTP layer (T10)
# are expected to wrap each call in ``loop.run_in_executor`` per C-2.

_PathArg = Union[str, Path]

DEFAULT_PAGE_SIZE: int = 200      # SPEC §7.3 default limit
MAX_PAGE_SIZE: int = 500          # clamp: keep per-request work bounded
# Bounded COUNT budget. Under this threshold the total is exact; at or
# above it we report ``approximate=True`` without computing further.
# The count query is ``SELECT COUNT(*) FROM (SELECT id ... LIMIT :cap)``
# so its runtime is bounded by the LIMIT, not by the full row count —
# this satisfies SPEC §7.3 / §8.4's 25 ms budget deterministically
# without resorting to ``set_progress_handler`` timer tricks
# (PROJECT_STATE §7 #5 explicitly left the choice to T09).
TOTAL_ESTIMATE_CAP: int = 5000


_VALID_SORT_KEYS: frozenset = frozenset({"name", "time", "size", "folder"})
_VALID_SORT_DIRS: frozenset = frozenset({"asc", "desc"})
_VALID_FAVORITE_STATES: frozenset = frozenset({"all", "yes", "no"})


@dataclass(frozen=True)
class SortSpec:
    """Sort envelope — SPEC §6.2.

    ``key`` maps to an ``image`` column per T09's SQL helpers:
      * ``name``   → ``filename_lc``  (hits ``idx_image_filename_lc``)
      * ``time``   → ``created_at``   (hits ``idx_image_created_at``)
      * ``size``   → ``file_size``    (hits ``idx_image_file_size``)
      * ``folder`` → ``path``         (POSIX lex, uses ``UNIQUE(path)``
                                       auto-index; folders group
                                       naturally by directory prefix)
    """
    key: str = "time"
    dir: str = "desc"

    def __post_init__(self) -> None:
        if self.key not in _VALID_SORT_KEYS:
            raise ValueError(f"unknown sort key: {self.key!r}")
        if self.dir not in _VALID_SORT_DIRS:
            raise ValueError(f"unknown sort dir: {self.dir!r}")


@dataclass(frozen=True)
class FilterSpec:
    """Query filter — SPEC §6.2 + FR-3 series.

    ``tags_and`` and ``prompts_and`` must be **already normalised** by
    the caller (PROJECT_STATE §7 #10). T15 + T21 own user-input → token
    normalisation; T09 treats the tuples as opaque lowercase literals.

    ``date_after`` / ``date_before`` are Unix epoch seconds
    (half-open: ``after <= created_at < before``) to match the on-disk
    ``image.created_at`` column (int seconds).  T10 will convert the
    ISO-8601 wire format to epoch before constructing a ``FilterSpec``.
    """
    name: Optional[str] = None
    favorite: str = "all"         # 'all' | 'yes' | 'no'
    model: Optional[str] = None
    date_after: Optional[int] = None
    date_before: Optional[int] = None
    folder_id: Optional[int] = None
    recursive: bool = False
    tags_and: Tuple[str, ...] = field(default_factory=tuple)
    prompts_and: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.favorite not in _VALID_FAVORITE_STATES:
            raise ValueError(f"invalid favorite state: {self.favorite!r}")


@dataclass(frozen=True)
class ImageRecord:
    """Flat image DTO.

    T10 serialises this to the nested JSON shape of SPEC §6.2
    (``folder{...}``, ``size{...}``, ``metadata{...}``, ``gallery{...}``)
    and injects ``thumb_url`` / ``raw_url``.  ``mtime_ns`` is exposed
    because the T10 thumb URL cache-buster ``?v=<mtime_ns>`` depends on
    it (§4 #32 / T08).  ``sync_status`` / ``version`` (T16) are
    intentionally absent — adding them now would shape the DTO against
    a schema version that does not yet exist (AI_RULES R1.2).
    """
    id: int
    path: str
    folder_id: int
    folder_kind: str
    folder_display_name: Optional[str]
    relative_path: str
    relative_dir: str
    filename: str
    ext: str
    width: Optional[int]
    height: Optional[int]
    file_size: Optional[int]
    mtime_ns: Optional[int]
    created_at: Optional[int]
    positive_prompt: Optional[str]
    negative_prompt: Optional[str]
    model: Optional[str]
    seed: Optional[int]
    cfg: Optional[float]
    sampler: Optional[str]
    scheduler: Optional[str]
    has_workflow: bool
    favorite: bool
    tags: Tuple[str, ...]


@dataclass(frozen=True)
class FolderNode:
    """Folder-tree DTO — SPEC §6.2.

    ``image_count_self`` / ``image_count_recursive`` are populated only
    when ``folder_tree(include_counts=True)``; otherwise both are None.
    """
    id: int
    path: str
    kind: str
    display_name: Optional[str]
    parent_id: Optional[int]
    removable: bool
    children: Tuple["FolderNode", ...]
    image_count_self: Optional[int]
    image_count_recursive: Optional[int]


@dataclass(frozen=True)
class ListPage:
    items: Tuple[ImageRecord, ...]
    next_cursor: Optional[str]
    total: int
    total_approximate: bool


@dataclass(frozen=True)
class Neighbors:
    prev_id: Optional[int]
    next_id: Optional[int]


# ---- SQL-building helpers (T09 internal) ---------------------------------

# SELECT list shared by get_image / list_images / neighbors.  The LEFT
# JOIN to ``folder`` is safe because ``image.folder_id`` is constrained
# to a registered root (PROJECT_STATE §4 #27); the LEFT is defensive
# against transient rows during migration.
_IMAGE_SELECT = (
    "SELECT image.id, image.path, image.folder_id, "
    "image.relative_path, image.filename, image.filename_lc, image.ext, "
    "image.width, image.height, image.file_size, image.mtime_ns, "
    "image.created_at, image.positive_prompt, image.negative_prompt, "
    "image.model, image.seed, image.cfg, image.sampler, image.scheduler, "
    "image.workflow_present, image.favorite, image.tags_csv, "
    "folder.kind AS folder_kind, folder.display_name AS folder_display_name "
    "FROM image LEFT JOIN folder ON folder.id = image.folder_id"
)


# Maps public sort key → (SQL expression, Python type coercer for cursor
# round-trip). The expression must be indexed (or cheap) so that
# ``ORDER BY <expr>`` scales — see module docstring / R7.1.
def _sort_column(key: str) -> str:
    # Use a local conditional rather than a dict so the SQL literal is
    # never built from user input — keeps any future grep-for-injection
    # audit trivial.
    if key == "name":
        return "image.filename_lc"
    if key == "time":
        return "image.created_at"
    if key == "size":
        return "image.file_size"
    if key == "folder":
        return "image.path"
    raise ValueError(f"unknown sort key: {key!r}")


def _cursor_null_sentinel(key: str) -> Any:
    # ``file_size`` / ``created_at`` can be NULL (rare, but possible on
    # header-broken files). ``ORDER BY col`` in SQLite places NULLs
    # first in ASC and last in DESC; for cursor stability we normalise
    # NULLs to a deterministic sentinel on both sides of the comparison.
    if key in ("name", "folder"):
        return ""
    return 0


def _encode_cursor(sort_val: Any, last_id: int) -> str:
    raw = json.dumps({"v": sort_val, "id": int(last_id)},
                     separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(token: str) -> Tuple[Any, int]:
    # Re-pad to a multiple of 4 for urlsafe_b64decode; the strip/pad
    # dance keeps the wire token free of ``=`` which some HTTP clients
    # mangle in URLs.
    pad = "=" * (-len(token) % 4)
    raw = base64.urlsafe_b64decode((token + pad).encode("ascii"))
    obj = json.loads(raw.decode("utf-8"))
    return obj["v"], int(obj["id"])


def _folder_row(
    conn: sqlite3.Connection, folder_id: int
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT id, path, parent_id FROM folder WHERE id = ?",
        (folder_id,),
    ).fetchone()


def _folder_root_and_prefix(
    conn: sqlite3.Connection, folder_id: int
) -> Optional[Tuple[int, str]]:
    """Return ``(root_id, relative_prefix_with_trailing_slash_or_empty)``.

    Climbs ``folder.parent_id`` until a root (``parent_id IS NULL``) is
    reached, then computes the selected folder's POSIX path relative to
    that root.  Result is ``("" if the folder IS the root else "sub/")``.
    Returns ``None`` if the folder id is unknown.

    The prefix is designed to be dropped straight into a
    ``relative_path LIKE :prefix || '%'`` clause — which, together with
    ``folder_id = :root_id``, uses the composite index
    ``idx_image_folder_rel (folder_id, relative_path)``.  See
    PROJECT_STATE §4 #27: images always carry the *root*'s folder_id,
    so recursive filtering is a prefix match on ``relative_path``
    (hinted §7 #4 CTE-over-``folder_id IN`` is wrong for this schema
    and would return empty for any sub-folder selection).
    """
    row = _folder_row(conn, folder_id)
    if row is None:
        return None
    sub_path = str(row["path"])
    sub_id = int(row["id"])
    if row["parent_id"] is None:
        return sub_id, ""

    # Climb to the root. Depth is bounded by directory nesting (< ~10
    # in practice); each step is a point-query hit on folder.id PK.
    cur = row
    while cur["parent_id"] is not None:
        parent = _folder_row(conn, int(cur["parent_id"]))
        if parent is None:
            # Broken chain — defensive; should never happen given T07's
            # _ensure_folder_chain invariant. Returning NOMATCH makes
            # the caller's WHERE clause select 0 rows cleanly.
            return sub_id, "\x00NOMATCH\x00"
        cur = parent
    root_id = int(cur["id"])
    root_path = str(cur["path"]).rstrip("/")

    if sub_path == root_path or sub_path == root_path + "/":
        return root_id, ""
    if not sub_path.startswith(root_path + "/"):
        return root_id, "\x00NOMATCH\x00"
    rel = sub_path[len(root_path) + 1:].rstrip("/")
    return root_id, rel + "/"


def _build_filter(
    conn: sqlite3.Connection, flt: FilterSpec
) -> Tuple[str, List[Any]]:
    """Return ``(where_sql_without_leading_WHERE, params)``.

    When ``flt`` selects a folder that cannot be resolved the WHERE
    clause short-circuits to ``1=0`` — this keeps the rest of the
    pipeline (sorting / cursor) uniform.
    """
    where: List[str] = []
    params: List[Any] = []

    if flt.folder_id is not None:
        resolved = _folder_root_and_prefix(conn, int(flt.folder_id))
        if resolved is None:
            return "1=0", []
        root_id, prefix = resolved
        where.append("image.folder_id = ?")
        params.append(root_id)
        if prefix:
            where.append("image.relative_path LIKE ?")
            params.append(prefix + "%")
            if not flt.recursive:
                # Exclude descendants: no extra '/' after the prefix.
                # ``NOT LIKE prefix || '%/%'`` does this cheaply.
                where.append("image.relative_path NOT LIKE ?")
                params.append(prefix + "%/%")
        else:
            # Root selection: recursive=True → all images under root;
            # recursive=False → flat files only (relative_path has no '/').
            if not flt.recursive:
                where.append("image.relative_path NOT LIKE ?")
                params.append("%/%")

    if flt.name:
        needle = flt.name.strip().lower()
        if needle:
            # SPEC §8.4: < 3 chars prefer prefix LIKE (index-friendly);
            # ≥ 3 chars would ideally hit FTS5 but that is T28 — retreat
            # to substring LIKE (full scan on filename_lc only, < 100 B
            # per row, acceptable for MVP).
            if len(needle) < 3:
                where.append("image.filename_lc LIKE ?")
                params.append(needle + "%")
            else:
                # TODO T28: replace with image_fts MATCH ':needle*'.
                where.append("image.filename_lc LIKE ?")
                params.append("%" + needle + "%")

    if flt.favorite == "yes":
        where.append("image.favorite = 1")
    elif flt.favorite == "no":
        where.append("(image.favorite = 0 OR image.favorite IS NULL)")
    # 'all' → no predicate

    if flt.model is not None:
        where.append("image.model = ?")
        params.append(flt.model)

    if flt.date_after is not None:
        where.append("image.created_at >= ?")
        params.append(int(flt.date_after))
    if flt.date_before is not None:
        where.append("image.created_at < ?")
        params.append(int(flt.date_before))

    # TODO T15/T28: migrate to ``EXISTS (SELECT 1 FROM image_tag ...)``
    # with rarest-first ordering. Current impl is an MVP retreat because
    # schema v2 has no ``image_tag`` table (that ships in T15).  The
    # comma-bracketed LIKE enforces token boundaries so the tag ``cat``
    # does not match ``category`` — the indexer stores tags_csv already
    # lower-cased (PROJECT_STATE §4 #24) so caller-side lowercasing is
    # the whole normalisation contract at this stage.
    for tag in flt.tags_and:
        tok = str(tag).strip().lower()
        if not tok:
            continue
        where.append(
            "(',' || IFNULL(image.tags_csv, '') || ',') LIKE ?"
        )
        params.append("%," + tok + ",%")

    # TODO T28: FTS5 prompt token search.
    for token in flt.prompts_and:
        tok = str(token).strip()
        if not tok:
            continue
        where.append("IFNULL(image.positive_prompt, '') LIKE ?")
        params.append("%" + tok + "%")

    if not where:
        return "1=1", params
    return " AND ".join(where), params


def _row_to_image_record(row: sqlite3.Row) -> ImageRecord:
    rel_path = str(row["relative_path"])
    rel_dir = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
    tags_csv = row["tags_csv"]
    tags: Tuple[str, ...] = tuple(
        t for t in (tags_csv.split(",") if tags_csv else []) if t
    )
    return ImageRecord(
        id=int(row["id"]),
        path=str(row["path"]),
        folder_id=int(row["folder_id"]) if row["folder_id"] is not None else 0,
        folder_kind=str(row["folder_kind"]) if row["folder_kind"] is not None else "",
        folder_display_name=row["folder_display_name"],
        relative_path=rel_path,
        relative_dir=rel_dir,
        filename=str(row["filename"]),
        ext=str(row["ext"]) if row["ext"] is not None else "",
        width=row["width"],
        height=row["height"],
        file_size=row["file_size"],
        mtime_ns=row["mtime_ns"],
        created_at=row["created_at"],
        positive_prompt=row["positive_prompt"],
        negative_prompt=row["negative_prompt"],
        model=row["model"],
        seed=row["seed"],
        cfg=row["cfg"],
        sampler=row["sampler"],
        scheduler=row["scheduler"],
        has_workflow=bool(row["workflow_present"]),
        favorite=bool(row["favorite"]) if row["favorite"] is not None else False,
        tags=tags,
    )


# ---- Public read APIs ----------------------------------------------------

def get_image(image_id: int, *, db_path: _PathArg) -> Optional[ImageRecord]:
    """Return the ``ImageRecord`` for ``image_id`` or None if absent."""
    conn = _db.connect_read(db_path)
    try:
        row = conn.execute(
            _IMAGE_SELECT + " WHERE image.id = ?", (int(image_id),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_image_record(row)


def list_images(
    *,
    db_path: _PathArg,
    filter: Optional[FilterSpec] = None,
    sort: Optional[SortSpec] = None,
    cursor: Optional[str] = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> ListPage:
    """Cursor-paged image listing.

    The cursor contract is ``(sort_val, id)``: to fetch the next page,
    pass the ``next_cursor`` verbatim.  Middle-of-iteration writes are
    safe — newly-inserted rows whose ``(sort_val, id)`` compare greater
    than the current cursor show up on a future page; rows deleted
    below the cursor are simply skipped (cf. TASKS T09 tests #2/#3).
    """
    flt = filter or FilterSpec()
    srt = sort or SortSpec()
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))

    conn = _db.connect_read(db_path)
    try:
        where_sql, where_params = _build_filter(conn, flt)
        sort_col = _sort_column(srt.key)
        ascending = (srt.dir == "asc")
        order_sql = (
            f" ORDER BY {sort_col} {'ASC' if ascending else 'DESC'}, "
            f"image.id {'ASC' if ascending else 'DESC'}"
        )

        cursor_params: List[Any] = []
        cursor_clause = ""
        if cursor:
            try:
                last_val, last_id = _decode_cursor(cursor)
            except Exception as exc:
                raise ValueError(f"invalid cursor: {exc!r}") from exc
            # COALESCE on sort_col mirrors the NULL-sentinel applied at
            # cursor-emit time; keeps (sort_val, id) monotone across rows
            # where the sort column is NULL (file_size / created_at).
            null_default = _cursor_null_sentinel(srt.key)
            op = ">" if ascending else "<"
            cursor_clause = (
                f" AND (COALESCE({sort_col}, ?) {op} ? "
                f"OR (COALESCE({sort_col}, ?) = ? AND image.id {op} ?))"
            )
            cursor_params = [
                null_default, last_val,
                null_default, last_val, int(last_id),
            ]

        sql = (
            _IMAGE_SELECT
            + " WHERE " + where_sql
            + cursor_clause
            + order_sql
            + " LIMIT ?"
        )
        params = list(where_params) + list(cursor_params) + [limit + 1]
        rows = conn.execute(sql, params).fetchall()

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = tuple(_row_to_image_record(r) for r in page_rows)

        next_cursor: Optional[str] = None
        if has_more and page_rows:
            last_row = page_rows[-1]
            raw_val = last_row[_sort_col_key(srt.key)]
            if raw_val is None:
                raw_val = _cursor_null_sentinel(srt.key)
            next_cursor = _encode_cursor(raw_val, int(last_row["id"]))

        # Bounded count — see TOTAL_ESTIMATE_CAP docstring.
        count_sql = (
            "SELECT COUNT(*) FROM ("
            "SELECT image.id FROM image "
            "LEFT JOIN folder ON folder.id = image.folder_id "
            f"WHERE {where_sql} LIMIT ?)"
        )
        count_params = list(where_params) + [TOTAL_ESTIMATE_CAP + 1]
        (total_raw,) = conn.execute(count_sql, count_params).fetchone()
        total_int = int(total_raw)
        approximate = total_int > TOTAL_ESTIMATE_CAP
        if approximate:
            total_int = TOTAL_ESTIMATE_CAP
    finally:
        conn.close()

    return ListPage(items=items, next_cursor=next_cursor,
                    total=total_int, total_approximate=approximate)


def _sort_col_key(key: str) -> str:
    # Row-dict key name to read the cursor value back from the result.
    return {
        "name":   "filename_lc",
        "time":   "created_at",
        "size":   "file_size",
        "folder": "path",
    }[key]


def neighbors(
    image_id: int,
    *,
    db_path: _PathArg,
    filter: Optional[FilterSpec] = None,
    sort: Optional[SortSpec] = None,
) -> Neighbors:
    """Return the prev/next id within the given filter+sort ordering.

    SPEC / FR-16 / T14: returns ``None`` for either side if the current
    image is at the boundary of the result set. Wrap-around is the
    front-end's job (SPEC FR-16).  If ``image_id`` does not satisfy the
    filter (or does not exist), both sides are ``None`` — this is the
    same semantic the front-end already handles for first/last cards.
    """
    flt = filter or FilterSpec()
    srt = sort or SortSpec()

    conn = _db.connect_read(db_path)
    try:
        # Pull the anchor row's sort value. ``filename_lc`` is not in
        # ``_IMAGE_SELECT`` (it's only used for sorting), so fetch sort
        # column directly.
        sort_col = _sort_column(srt.key)
        anchor = conn.execute(
            f"SELECT {sort_col} AS sv, image.id FROM image WHERE image.id = ?",
            (int(image_id),),
        ).fetchone()
        if anchor is None:
            return Neighbors(prev_id=None, next_id=None)
        anchor_val = anchor["sv"]
        if anchor_val is None:
            anchor_val = _cursor_null_sentinel(srt.key)

        # Confirm the anchor matches the filter; if not, return None/None.
        where_sql, where_params = _build_filter(conn, flt)
        in_set = conn.execute(
            f"SELECT 1 FROM image LEFT JOIN folder ON folder.id = image.folder_id "
            f"WHERE {where_sql} AND image.id = ? LIMIT 1",
            list(where_params) + [int(image_id)],
        ).fetchone()
        if in_set is None:
            return Neighbors(prev_id=None, next_id=None)

        ascending = (srt.dir == "asc")
        null_default = _cursor_null_sentinel(srt.key)

        def _one_side(forward: bool) -> Optional[int]:
            # forward = direction the *user* means "next":
            #   asc + forward → strictly greater (sort_val, id)
            #   desc + forward → strictly lesser
            go_gt = ascending if forward else not ascending
            op = ">" if go_gt else "<"
            order_dir = "ASC" if go_gt else "DESC"
            sql = (
                "SELECT image.id FROM image LEFT JOIN folder "
                "ON folder.id = image.folder_id "
                f"WHERE {where_sql} "
                f"AND (COALESCE({sort_col}, ?) {op} ? "
                f"OR (COALESCE({sort_col}, ?) = ? AND image.id {op} ?)) "
                f"ORDER BY COALESCE({sort_col}, ?) {order_dir}, image.id {order_dir} "
                "LIMIT 1"
            )
            params = list(where_params) + [
                null_default, anchor_val,
                null_default, anchor_val, int(image_id),
                null_default,
            ]
            row = conn.execute(sql, params).fetchone()
            return int(row["id"]) if row is not None else None

        next_id = _one_side(forward=True)
        prev_id = _one_side(forward=False)
    finally:
        conn.close()
    return Neighbors(prev_id=prev_id, next_id=next_id)


def folder_tree(
    *, db_path: _PathArg, include_counts: bool = False,
) -> Tuple[FolderNode, ...]:
    """Return the forest of folders, rooted at rows with ``parent_id IS NULL``.

    ``include_counts`` issues one bounded count query per folder node.
    For a typical library (≲ a few hundred folders) the O(F) cost is
    negligible; if it ever becomes hot, T26's janitor can maintain a
    denormalised ``folder.image_count`` column (explicitly out of scope
    for T09 — AI_RULES R1.2).
    """
    conn = _db.connect_read(db_path)
    try:
        rows = conn.execute(
            "SELECT id, path, kind, parent_id, display_name, removable "
            "FROM folder ORDER BY path ASC"
        ).fetchall()

        children_of: dict = {}
        roots: List[sqlite3.Row] = []
        rows_by_id: dict = {}
        for r in rows:
            rows_by_id[int(r["id"])] = r
            if r["parent_id"] is None:
                roots.append(r)
            else:
                children_of.setdefault(int(r["parent_id"]), []).append(r)

        # Resolve each folder's (root_id, rel_prefix) once, then reuse
        # for count queries below.  Walking the tree top-down gives us
        # the prefix by extension instead of re-climbing per node.
        def _build(
            node_row: sqlite3.Row, root_id: int, rel_prefix: str,
        ) -> FolderNode:
            fid = int(node_row["id"])
            self_count: Optional[int] = None
            recursive_count: Optional[int] = None
            if include_counts:
                self_count = _count_in_folder(
                    conn, root_id, rel_prefix, recursive=False
                )
                recursive_count = _count_in_folder(
                    conn, root_id, rel_prefix, recursive=True
                )

            kids = children_of.get(fid, [])
            kid_nodes: List[FolderNode] = []
            for kid_row in kids:
                # Child path relative to root = child.path - root.path - "/"
                root_path = str(rows_by_id[root_id]["path"]).rstrip("/")
                kid_path = str(kid_row["path"])
                if kid_path.startswith(root_path + "/"):
                    new_prefix = kid_path[len(root_path) + 1:] + "/"
                else:
                    # Defensive; T07 invariant keeps this from firing.
                    new_prefix = "\x00NOMATCH\x00"
                kid_nodes.append(_build(kid_row, root_id, new_prefix))

            return FolderNode(
                id=fid,
                path=str(node_row["path"]),
                kind=str(node_row["kind"]),
                display_name=node_row["display_name"],
                parent_id=node_row["parent_id"],
                removable=bool(node_row["removable"]),
                children=tuple(kid_nodes),
                image_count_self=self_count,
                image_count_recursive=recursive_count,
            )

        forest = tuple(_build(r, int(r["id"]), "") for r in roots)
    finally:
        conn.close()
    return forest


def _count_in_folder(
    conn: sqlite3.Connection,
    root_id: int,
    rel_prefix: str,
    *,
    recursive: bool,
) -> int:
    # Uses idx_image_folder_rel (folder_id, relative_path); the LIKE
    # patterns are prefix-anchored so SQLite can range-scan the index.
    if not rel_prefix:
        if recursive:
            sql = "SELECT COUNT(*) FROM image WHERE folder_id = ?"
            params: List[Any] = [root_id]
        else:
            sql = (
                "SELECT COUNT(*) FROM image "
                "WHERE folder_id = ? AND relative_path NOT LIKE ?"
            )
            params = [root_id, "%/%"]
    else:
        if recursive:
            sql = (
                "SELECT COUNT(*) FROM image "
                "WHERE folder_id = ? AND relative_path LIKE ?"
            )
            params = [root_id, rel_prefix + "%"]
        else:
            sql = (
                "SELECT COUNT(*) FROM image "
                "WHERE folder_id = ? AND relative_path LIKE ? "
                "AND relative_path NOT LIKE ?"
            )
            params = [root_id, rel_prefix + "%", rel_prefix + "%/%"]
    (n,) = conn.execute(sql, params).fetchone()
    return int(n)


# -- Internals -------------------------------------------------------------

class _StopSentinel:
    """Marker op used by stop() to wake the blocking get()."""

    def apply(self, conn: sqlite3.Connection) -> None:  # pragma: no cover
        return None


_STOP_SENTINEL: _StopSentinel = _StopSentinel()


# -- WriteQueue ------------------------------------------------------------

class WriteQueue:
    """Single-writer priority queue (ARCHITECTURE §4.6 + TASKS T04 UPDATED).

    One op → one transaction. A failing op only rolls back itself; its
    neighbours are committed in their own independent transactions, so
    there is no partial-commit / partial-rollback grey zone.
    """

    def __init__(self, db_path: _PathLike):
        self._db_path: Path = Path(db_path)
        # Queue entries: ``(priority, seq, op, future_or_none)``.
        # ``seq`` is monotonic → stable FIFO within the same priority class.
        self._pq: "queue.PriorityQueue[tuple[int, int, Any, Optional[Future]]]" = (
            queue.PriorityQueue()
        )
        self._seq_counter = itertools.count()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._thread_lock = threading.Lock()

    # ---- public API ------------------------------------------------------

    def enqueue_write(self, priority: int, op: Any) -> "Future":
        if priority not in _VALID_PRIORITIES:
            raise ValueError(f"unknown priority: {priority!r}")
        if not hasattr(op, "apply"):
            raise TypeError("op must implement .apply(conn)")
        fut: "Future" = Future()
        seq = next(self._seq_counter)
        self._pq.put((priority, seq, op, fut))
        return fut

    def start(self) -> None:
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._supervised_loop,
                name="xyz-gallery-writer",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 0.2) -> bool:
        """Signal the writer to exit; return True iff it joined in time."""
        with self._thread_lock:
            t = self._thread
            if t is None:
                return True
            self._stop_event.set()
            # Ensure a blocked get() wakes up even on an empty queue.
            # seq=-1 keeps the sentinel distinct from any real entry
            # (real seqs come from itertools.count() starting at 0).
            self._pq.put((HIGH, -1, _STOP_SENTINEL, None))
        t.join(timeout=timeout)
        joined = not t.is_alive()
        if joined:
            with self._thread_lock:
                self._thread = None
        return joined

    # ---- internals -------------------------------------------------------

    def _supervised_loop(self) -> None:
        # Any exception that escapes _writer_loop is logged and the loop is
        # restarted, per TASKS.md T04 ("thread crash auto-restart + error
        # log"). Normal exit (stop signalled) returns cleanly.
        while not self._stop_event.is_set():
            try:
                self._writer_loop()
                return
            except Exception:
                logger.exception("xyz.gallery writer loop crashed; restarting")
                time.sleep(_CRASH_RESTART_SLEEP_SEC)

    def _writer_loop(self) -> None:
        conn = _db.connect_write(self._db_path)
        low_streak = 0
        try:
            while not self._stop_event.is_set():
                item = self._pq.get(block=True)
                priority, _seq, op, fut = item

                if op is _STOP_SENTINEL:
                    return

                if priority == LOW:
                    low_streak += 1
                    if (
                        low_streak >= _LOW_YIELD_THRESHOLD
                        and self._has_higher_priority_waiting()
                    ):
                        # Re-enqueue this LOW; PriorityQueue will hand us
                        # the pending HIGH/MID first on the next get().
                        self._pq.put(item)
                        low_streak = 0
                        continue
                else:
                    low_streak = 0

                self._execute_single(conn, op, fut)
        finally:
            try:
                conn.close()
            except Exception:
                logger.exception("error closing write connection")

    def _execute_single(
        self,
        conn: sqlite3.Connection,
        op: Any,
        fut: Optional["Future"],
    ) -> None:
        # db.connect_write() puts sqlite3 in autocommit (isolation_level=None),
        # so BEGIN/COMMIT are explicit. Using BEGIN IMMEDIATE acquires the
        # RESERVED lock up-front — with one writer thread this is equivalent
        # to BEGIN, but it fails fast if the file was locked externally
        # (e.g. migration script mid-flight) rather than surprising op.apply.
        tx_open = False
        try:
            conn.execute("BEGIN IMMEDIATE")
            tx_open = True
            result = op.apply(conn)
            conn.execute("COMMIT")
            tx_open = False
            if fut is not None and not fut.done():
                fut.set_result(result)
        except BaseException as exc:
            if tx_open:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    logger.exception("ROLLBACK failed after op error")
            if fut is not None and not fut.done():
                fut.set_exception(exc)
            # Writer thread survives op-level failures — only the offending
            # op's transaction is discarded. Non-Exception BaseExceptions
            # (KeyboardInterrupt / SystemExit) are re-raised to let the
            # supervisor handle shutdown semantics.
            if not isinstance(exc, Exception):
                raise

    def _has_higher_priority_waiting(self) -> bool:
        # Peek the heap under its own mutex. Advisory — another thread may
        # enqueue between this check and the next get(), but in that case
        # PriorityQueue will simply hand us the newly-added higher op next.
        with self._pq.mutex:
            for entry in self._pq.queue:
                if entry[0] < LOW:
                    return True
        return False
