"""T42 offline validation — user-facing copy / placeholders (TASKS T42, SPEC §12.1/§12.5).

Scope:
  * ``MainView.js`` template + ``promptFilterPlaceholder`` strings: no debounce ms,
    no task ids in placeholders, no API path hints or spec section refs in UI copy.
  * ``SettingsView.js`` tag-admin search placeholder: no ``substring`` dev phrasing.

Run:
    pytest ComfyUI-XYZNodes/test/t42_test.py -q
    # from plugin root:
    pytest test/t42_test.py -q

Expected: all tests passed.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_MAIN = _PLUGIN_ROOT / "js" / "gallery_dist" / "views" / "MainView.js"
_SETTINGS = _PLUGIN_ROOT / "js" / "gallery_dist" / "views" / "SettingsView.js"


def _main_template_only() -> str:
    t = _MAIN.read_text(encoding="utf-8")
    start = t.index("template: `") + len("template: `")
    end = t.rindex("\n  `,\n});")
    return t[start:end]


def _main_script_only() -> str:
    t = _MAIN.read_text(encoding="utf-8")
    start = t.index("template: `")
    return t[:start]


def test_mainview_template_has_user_name_placeholder() -> None:
    tpl = _main_template_only()
    assert "Type part of a filename (not case-sensitive)" in tpl
    assert "name filter:" in tpl  # FR-3a label unchanged
    assert "debounced" not in tpl
    assert "250 ms" not in tpl
    assert "T21" not in tpl
    assert "/vocab/words" not in tpl and "/vocab/prompts" not in tpl
    assert "§" not in tpl


def test_mainview_template_tag_placeholder() -> None:
    tpl = _main_template_only()
    assert "Tags, comma-separated; suggestions as you type" in tpl


def test_mainview_prompt_placeholder_computed_user_copy() -> None:
    script = _main_script_only()
    i = script.index("const promptFilterPlaceholder")
    j = script.index("const promptFetchKind", i)
    block = script[i:j]
    assert "All typed fragments must appear" in block
    assert "Words or short phrases, comma- or space-separated" in block
    assert "Comma-separated prompt phrases; all must match" in block
    for bad in ("/vocab/words", "/vocab/prompts", "§8.8", "debounced", "250 ms", "T21"):
        assert bad not in block, f"dev-facing fragment in placeholder block: {bad!r}"


def test_mainview_fr3a_debounce_still_in_logic() -> None:
    """FR-3a 250 ms debounce remains in script (not in placeholder)."""
    body = _MAIN.read_text(encoding="utf-8")
    assert "250" in body and "setTimeout" in body


def test_settingsview_tag_search_placeholder() -> None:
    s = _SETTINGS.read_text(encoding="utf-8")
    assert "Search tag names…" in s
    assert "Search tags (substring)" not in s


def test_no_writequeue_in_gallery_dist_sources() -> None:
    """TASKS T42 rg hint: WriteQueue must not appear in shipped gallery JS."""
    root = _PLUGIN_ROOT / "js" / "gallery_dist"
    for path in sorted(root.rglob("*.js")):
        txt = path.read_text(encoding="utf-8")
        assert "WriteQueue" not in txt, f"WriteQueue in {path.relative_to(_PLUGIN_ROOT)}"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
