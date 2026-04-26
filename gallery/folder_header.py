"""Gallery folder line-header string (matches ``sectionKeys.folderSectionLabelFromItem``).

Used as the SQLite ``xyz_folder_line_header`` UDF so ``list_images`` / cursors
sort by the same label the UI shows, not by ``image.path``.
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = ["folder_line_header_value_sql"]


def _folder_line_header_value(
    relative_path: Optional[str],
    display_name: Optional[str],
    kind: Optional[str],
) -> str:
    rp = "" if relative_path is None else str(relative_path)
    if "/" in rp:
        rd = rp.rsplit("/", 1)[0]
    else:
        rd = ""
    rd = rd.replace("\\", "/")
    rd = rd.lstrip("/").rstrip("/")

    dn = ("" if display_name is None else str(display_name)).strip()
    if dn:
        root = dn
    else:
        k = ("" if kind is None else str(kind)).strip()
        root = k
    if not root:
        root = "(root)"
    if not rd:
        return root
    return f"{root}/{rd}"


def folder_line_header_value_sql(
    relative_path: Any,
    display_name: Any,
    kind: Any,
) -> str:
    """SQLite UDF (3 args); coerces NULL / blobs to str/empty."""
    return _folder_line_header_value(
        None if relative_path is None else str(relative_path),
        None if display_name is None else str(display_name),
        None if kind is None else str(kind),
    )
