"""XYZ Image Gallery — path sandbox (T05).

Per ``PROJECT_SPEC C-5`` and ``NFR-19``: every path that crosses the trust
boundary from the client must be ``Path.resolve()``-d and verified to live
inside one of the registered roots before any file IO. This module owns
the *check*; ``folders.py`` owns the registry that supplies the roots.

Out of scope (deferred):
  * Any IO / readability checks  — `folders.add_root` does that.
  * Wiring into HTTP error envelopes — T10's job.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Union

__all__ = [
    "SandboxError",
    "assert_inside_root",
    "is_derivative_path_excluded",
    "prune_derivative_walk_dirnames",
    "XYZ_GALLERY_ATOMIC_DIRNAME",
]

# T29 / V1.1-F11 — keep in sync with indexer walk pruning.
# ``.xyz_gallery_atomic`` — same-volume staging for ``metadata.write_xyz_chunks``;
# must not be walked or indexed as user content (see ``metadata`` module).
XYZ_GALLERY_ATOMIC_DIRNAME = ".xyz_gallery_atomic"
# Case-folded directory segments under a root that are not user library paths.
_DERIVATIVE_EXCLUDED_SEGMENTS_ICASE: frozenset = frozenset(
    str(x).casefold() for x in ("_thumbs", XYZ_GALLERY_ATOMIC_DIRNAME)
)

_PathLike = Union[str, Path]


class SandboxError(Exception):
    """Raised when a candidate path resolves outside every registered root.

    Custom type (not ``ValueError``) per TASKS.md T05 — downstream tasks
    (T10 routes, T17 metadata write, T24/T25 bulk move/delete) match on
    this class to translate to HTTP 400.
    """


def assert_inside_root(path: _PathLike, roots: Iterable[_PathLike]) -> Path:
    """Resolve ``path`` and assert it lives inside (or equals) some root.

    Both sides go through ``Path.resolve(strict=False)`` so ``..`` segments,
    symlinks, and Windows drive-letter casing are normalised before the
    containment check. Returns the resolved absolute Path on success.
    """
    resolved = Path(path).resolve(strict=False)
    for root in roots:
        root_resolved = Path(root).resolve(strict=False)
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            continue
        return resolved
    raise SandboxError(
        f"path {str(resolved)!r} is not inside any registered root"
    )


def is_derivative_path_excluded(abs_path: str, root_path: str) -> bool:
    """True when ``abs_path`` is under a barred derivative directory (T29).

    Matches any path component (directory segment) equal to ``_thumbs`` or
    :data:`XYZ_GALLERY_ATOMIC_DIRNAME` under ``root_path``. Folder-only paths
    such as ``…/output/_thumbs`` (single relative segment) are included.
    """
    try:
        root_r = Path(str(root_path)).resolve(strict=False)
        abs_r = Path(str(abs_path)).resolve(strict=False)
        rel = abs_r.relative_to(root_r)
    except (ValueError, OSError):
        return False
    parts = rel.parts
    if not parts:
        return False
    to_scan = parts[:-1] if len(parts) > 1 else parts
    for seg in to_scan:
        if str(seg).casefold() in _DERIVATIVE_EXCLUDED_SEGMENTS_ICASE:
            return True
    return False


def prune_derivative_walk_dirnames(dirnames: List[str]) -> None:
    """Drop derivative dir names (case-insensitive) from ``os.walk`` descent (T29)."""
    dirnames[:] = [
        d for d in dirnames
        if str(d).casefold() not in _DERIVATIVE_EXCLUDED_SEGMENTS_ICASE
    ]
