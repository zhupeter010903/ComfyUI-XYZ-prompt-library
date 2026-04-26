"""T45 offline validation — line view wiring + section key logic.

* Node runner exercises ``js/gallery_dist/sectionKeys.js`` (folder/name/size/time).
* Static checks: ``LineVirtualGrid.js``, ``filters.js`` ``view_mode``, ``MainView`` toggle.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_SECTION_RUNNER = _PLUGIN_ROOT / "test" / "t45_section_keys_runner.mjs"


def test_t45_section_keys_node_runner():
    node = shutil.which("node") or shutil.which("node.exe")
    assert node, "node is required on PATH for T45 sectionKeys runner"
    r = subprocess.run(
        [node, str(_SECTION_RUNNER)],
        cwd=str(_PLUGIN_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in (r.stdout or ""), r.stdout + r.stderr


def test_t45_static_files():
    filters_body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "stores" / "filters.js").read_text(encoding="utf-8")
    assert "view_mode" in filters_body
    assert "setViewMode" in filters_body
    assert "VALID_VIEW_MODE" in filters_body

    main = (_PLUGIN_ROOT / "js" / "gallery_dist" / "views" / "MainView.js").read_text(encoding="utf-8")
    assert "LineVirtualGrid" in main
    assert "setViewMode" in main
    assert "galleryViewMode" in main
    assert "<LineVirtualGrid" in main

    line = (_PLUGIN_ROOT / "js" / "gallery_dist" / "components" / "LineVirtualGrid.js").read_text(encoding="utf-8")
    assert "export const LineVirtualGrid" in line
    assert "partitionItemsForLineView" in line

    idx = (_PLUGIN_ROOT / "js" / "gallery_dist" / "index.html").read_text(encoding="utf-8")
    assert ".lvl-sec-head" in idx
    assert ".mv-view-btn" in idx

    keys = (_PLUGIN_ROOT / "js" / "gallery_dist" / "sectionKeys.js").read_text(encoding="utf-8")
    assert "SIZE_BIN_EDGES_BYTES" in keys
    assert "partitionItemsForLineView" in keys
