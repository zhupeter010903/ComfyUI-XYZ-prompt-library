"""T38 offline validation — design tokens, color-scheme, scrollbars (TASKS T38).

Scope:
  * ``index.html`` global style contains ``color-scheme`` + ``--xyz-*`` bridge
    tokens, Firefox ``scrollbar-color`` on Main/Detail/Settings scroll surfaces,
    and Detail tag-line inputs styled with ``var(--bg)`` / ``var(--fg)``.

Run:
    python test/t38_test.py
    # or: pytest test/t38_test.py -q

Expected: last line ``T38 ALL TESTS PASSED``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _index_html() -> str:
    p = _PLUGIN_ROOT / "js" / "gallery_dist" / "index.html"
    assert p.is_file(), f"missing {p}"
    return p.read_text(encoding="utf-8")


def test_t38_tokens_and_color_scheme() -> None:
    html = _index_html()
    assert "--xyz-bg:" in html and "var(--bg)" in html
    assert "--xyz-on-accent:" in html
    assert re.search(r"html\s*\{[^}]*color-scheme:\s*dark", html, re.DOTALL)
    assert re.search(
        r"html\[data-xyz-gallery-theme=\"light\"\][^{]*\{[^}]*color-scheme:\s*light",
        html,
        re.DOTALL,
    )
    assert "scrollbar-color: var(--border) var(--panel)" in html
    assert ".dv-right::-webkit-scrollbar" in html
    assert ".gs-win-main::-webkit-scrollbar" in html
    assert "#app input[type=\"checkbox\"]" in html
    assert "accent-color: var(--accent)" in html
    assert ".dv-tagac input" in html and "background: var(--bg)" in html
    assert "color: var(--xyz-on-accent)" in html
    # T39: FolderTree 行选中与 Main 区 Autocomplete/模型列表同一强调（0.22 + 左边条），替代旧「满幅 accent 填充」
    assert re.search(
        r"\.ft-node\.active\s*\{[^}]*0\.22",
        html,
        re.DOTALL,
    )
    assert "border-left-color: var(--accent" in html


def main() -> int:
    test_t38_tokens_and_color_scheme()
    print("T38 ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
