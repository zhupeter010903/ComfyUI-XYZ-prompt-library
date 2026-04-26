"""T40 offline validation — IconButton + 非裸「Back」链（TASKS T40, SPEC §12.5）。

Run:
    python test/t40_test.py
    # or: pytest test/t40_test.py -q

Expected: last line ``T40 ALL TESTS PASSED``.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    p = _PLUGIN_ROOT / "js" / "gallery_dist" / rel
    assert p.is_file(), f"missing {p}"
    return p.read_text(encoding="utf-8")


def test_t40_icon_button_module() -> None:
    body = _read("components/IconButton.js")
    assert "export const IconButton" in body
    assert "stroke-width=\"1.5\"" in body
    assert "M15.75 19.5L8.25 12l7.5-7.5" in body
    assert "chevronRight" in body
    assert "class=\"ib\"" in body
    assert "var(--" not in body and "color:" not in body, "T40 色值走 index.html token，本组件不内联"


def test_t40_index_ib_tokens() -> None:
    html = _read("index.html")
    assert ".ib {" in html
    assert "var(--panel)" in html and "var(--border)" in html
    assert ".ib-ico" in html
    assert ".ib-sr-only" in html


def test_t40_replaced_nav_surfaces() -> None:
    dv = _read("views/DetailView.js")
    assert "IconButton" in dv
    assert 'import { IconButton }' in dv
    assert 'href="#/"' in dv, "T14 hash Back 合同"
    assert "&larr; Back" not in dv
    assert "&larr; Previous" not in dv
    assert "components/IconButton.js" in dv

    gs = _read("views/SettingsView.js")
    assert "IconButton" in gs
    assert "&larr; Back" not in gs
    assert ":href=\"backHref\"" in gs
    assert "<IconButton" in gs, "Settings toolbar Back 为 IconButton"

    app = _read("app.js")
    assert "from './components/IconButton.js'" in app
    assert "&larr; Home" not in app
    assert "NotFoundView" in app and "IconButton" in app


def main() -> int:
    test_t40_icon_button_module()
    test_t40_index_ib_tokens()
    test_t40_replaced_nav_surfaces()
    print("T40 ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
