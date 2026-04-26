"""T39 offline validation — FolderTree 图式（内联 SVG、缩进/层级线、行样式）。

Scope (TASKS.md T39, PROJECT_SPEC §12.1):
  * components/FolderTree.js 含 folder + chevron 的 <svg>（1.5 stroke, 与 T40 将抽取的 24 网格对齐）
  * 层级 .ft-guide、选中态在 index.html 用与 .ac-item 相近的 0.22 背景 + 左描边
  * ``stores/filters`` 未变（T39 不触及）

Run:
    python test/t39_test.py
    # or: pytest test/t39_test.py -q

Expected: last line ``T39 ALL TESTS PASSED``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _ft_js() -> str:
    p = _PLUGIN_ROOT / "js" / "gallery_dist" / "components" / "FolderTree.js"
    assert p.is_file(), f"missing {p}"
    return p.read_text(encoding="utf-8")


def _index_html() -> str:
    p = _PLUGIN_ROOT / "js" / "gallery_dist" / "index.html"
    assert p.is_file(), f"missing {p}"
    return p.read_text(encoding="utf-8")


def test_t39_folder_tree_ico_svg() -> None:
    js = _ft_js()
    assert "export const FolderTree" in js
    # 每个节点可辨：folder 轮廓 + 展开/折叠（chevron 路径，非纯 ▶/▼ 字符）
    assert '<svg' in js and "stroke-width=\"1.5\"" in js, "T39 inline SVG 契约"
    assert "ft-guide" in js, "T39 缩进/层级线节点"
    assert "M9.75 5.5" in js and "M5.5 9.75" in js, "T39 期望 chevron path (right and down)"
    # 与 filters 的 emit/选择 不变
    assert "selectedId === id ? null : id" in js
    assert "'folders-changed'" in js


def test_t39_index_folder_row_styles() -> None:
    html = _index_html()
    assert ".ft-node.active" in html
    assert re.search(
        r"\.ft-node\.active\s*\{[^}]*0\.22",
        html,
        re.DOTALL,
    )
    assert "border-left-color: var(--accent" in html
    assert ".ft-guide::before" in html
    assert "rgba(74, 158, 255, 0.22)" in html
    # 与主过滤区 .ac-item:hover 同档 0.08
    assert "rgba(74, 158, 255, 0.08)" in html
    assert ".ft-node:hover" in html


def main() -> int:
    test_t39_folder_tree_ico_svg()
    test_t39_index_folder_row_styles()
    print("T39 ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
