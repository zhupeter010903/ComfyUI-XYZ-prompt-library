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
from typing import Iterable, Union

__all__ = ["SandboxError", "assert_inside_root"]

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
