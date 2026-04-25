"""T32 offline validation — list filter UI wire (``metadata_presence``,
``prompt_match_mode``) + URL/localStorage store + MainView Autocomplete
disable in ``string`` mode.

No ComfyUI / DB. Static contract checks only (same family as ``t12_test``).

Run:
    pytest test/t32_test.py -q
Or:
    python test/t32_test.py

Expected: ``T32 ALL TESTS PASSED``.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402


def _filters_body() -> str:
    return (_PLUGIN_ROOT / "js" / "gallery_dist" / "stores" / "filters.js").read_text(encoding="utf-8")


def _main_body() -> str:
    return (_PLUGIN_ROOT / "js" / "gallery_dist" / "views" / "MainView.js").read_text(encoding="utf-8")


def _selection_body() -> str:
    return (_PLUGIN_ROOT / "js" / "gallery_dist" / "stores" / "selection.js").read_text(encoding="utf-8")


def test_filters_default_and_api_query_wiring() -> None:
    body = _filters_body()
    for needle in (
        "metadata_presence: 'all'",
        "prompt_match_mode: 'prompt'",
        "VALID_METADATA_PRESENCE",
        "VALID_PROMPT_MATCH_MODE",
        "q.metadata_presence = f.metadata_presence",
        "q.prompt_match_mode = f.prompt_match_mode",
        "sp.has('metadata_presence')",
        "sp.has('prompt_match_mode')",
    ):
        assert needle in body, f"filters.js missing: {needle!r}"


def test_filters_url_read_uses_t31_enum_sets() -> None:
    body = _filters_body()
    assert "VALID_METADATA_PRESENCE.has(v)" in body
    assert "VALID_PROMPT_MATCH_MODE.has(v)" in body


def test_mainview_prompt_autocomplete_string_disabled() -> None:
    body = _main_body()
    assert "filter.prompt_match_mode" in body and "positive_tokens = []" in body
    assert ":suggestions-off=\"filter.prompt_match_mode === 'string'\"" in body
    assert ":fetch-kind=\"promptFetchKind\"" in body
    assert "promptFilterPlaceholder" in body
    assert "promptFetchKind" in body
    assert "Comfy metadata (indexed PNG):" in body
    assert "prompt match mode:" in body
    assert "value=\"string\"" in body


def test_selection_filter_wire_includes_t31_fields() -> None:
    body = _selection_body()
    assert "metadata_presence: f.metadata_presence || 'all'" in body
    assert "prompt_match_mode: f.prompt_match_mode || 'prompt'" in body


class _FakeServer:
    def __init__(self) -> None:
        self.routes = web.RouteTableDef()


async def _static_still_served() -> None:
    from gallery import routes as _routes

    fake = _FakeServer()
    _routes._registered = False
    _routes.register(fake)
    app = web.Application()
    app.add_routes(fake.routes)
    async with TestServer(app) as srv:
        async with TestClient(srv) as client:
            for rel in (
                "/xyz/gallery/static/stores/filters.js",
                "/xyz/gallery/static/stores/selection.js",
                "/xyz/gallery/static/views/MainView.js",
            ):
                r = await client.get(rel)
                assert r.status == 200, (rel, r.status)
                txt = await r.text()
                assert len(txt) > 200, rel


def test_static_handler_serves_updated_assets() -> None:
    asyncio.run(_static_still_served())


def main() -> None:
    test_filters_default_and_api_query_wiring()
    test_filters_url_read_uses_t31_enum_sets()
    test_mainview_prompt_autocomplete_string_disabled()
    test_selection_filter_wire_includes_t31_fields()
    test_static_handler_serves_updated_assets()
    print("T32 ALL TESTS PASSED")


if __name__ == "__main__":
    main()
