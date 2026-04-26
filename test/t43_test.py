"""T43 offline validation — WS / list refresh policy (TASKS T43, SPEC §12.3 / NFR-20).

* Static: ``MainView.js`` contains the T43 decision table and ``folder.changed`` gating.
* Logic: Python port of ``rootIdContainingFolderId`` (must mirror JS for the same fixtures).

Run::

    pytest ComfyUI-XYZNodes/test/t43_test.py -q
    pytest test/t43_test.py -q

Expected: all tests passed.
"""
from __future__ import annotations

import re
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_MAIN = _PLUGIN_ROOT / "js" / "gallery_dist" / "views" / "MainView.js"


def root_id_containing_folder_id(nodes: object, folder_id: int) -> int | None:
    """Mirror of ``rootIdContainingFolderId`` in ``MainView.js`` (T43)."""
    if not isinstance(folder_id, int) or not isinstance(nodes, list):
        return None

    def contains(n: object, fid: int) -> bool:
        if not isinstance(n, dict):
            return False
        if n.get("id") == fid:
            return True
        ch = n.get("children")
        if not isinstance(ch, list):
            return False
        for c in ch:
            if contains(c, fid):
                return True
        return False

    for root in nodes:
        if not isinstance(root, dict):
            continue
        if contains(root, folder_id):
            rid = root.get("id")
            return int(rid) if isinstance(rid, int) else None
    return None


def test_root_id_containing_folder_id_nested() -> None:
    tree = [
        {
            "id": 1,
            "children": [
                {"id": 10, "children": [{"id": 100, "children": []}]},
            ],
        },
        {"id": 2, "children": [{"id": 20, "children": []}]},
    ]
    assert root_id_containing_folder_id(tree, 100) == 1
    assert root_id_containing_folder_id(tree, 20) == 2
    assert root_id_containing_folder_id(tree, 1) == 1


def test_root_id_containing_folder_id_missing() -> None:
    assert root_id_containing_folder_id([], 5) is None
    assert root_id_containing_folder_id([{"id": 1, "children": []}], 99) is None


def test_mainview_has_t43_policy_table() -> None:
    body = _MAIN.read_text(encoding="utf-8")
    assert "T43 / SPEC §12.3 / NFR-20" in body
    assert "subscribeGalleryEvent` list vs tree policy" in body
    assert "folder.changed" in body and "index.drift_detected" in body


def test_mainview_folder_changed_gating() -> None:
    body = _MAIN.read_text(encoding="utf-8")
    assert "rootIdContainingFolderId" in body
    assert "EV.FOLDER_CHANGED" in body
    assert "selRoot !== rid" in body or "selRoot != null && selRoot !== rid" in body
    m = re.search(r"if \(fid == null\)\s*\{[^}]*return;\s*\}", body)
    assert m, "expected `if (fid == null) { return; }` after folder.changed fetchFolders"


def test_fs_upsert_debounce_unchanged_ms() -> None:
    body = _MAIN.read_text(encoding="utf-8")
    assert "420" in body and "scheduleGridRefreshAfterFsUpsert" in body
