"""T13 offline validation — VirtualGrid + ThumbCard + toolbar + pagination.

Scope (TASKS.md T13):
  * ``components/VirtualGrid.js`` and ``components/ThumbCard.js`` land
    on disk and are served by the existing T10 static handler.
  * ``stores/filters.js`` grew a cards-per-row persistence layer
    (``layoutState`` + ``setCardsPerRow``) clamped to [2, 12] (FR-9a).
  * ``views/MainView.js`` now wires a toolbar (cards-per-row slider +
    sort dropdown), uses ``VirtualGrid`` instead of the T12 filename
    preview list, drives cursor-based pagination from ``next_cursor``,
    navigates to ``#/image/:id`` on left-click, and opens a placeholder
    right-click context menu.
  * ``index.html`` carries the T13 CSS (``.mv-toolbar``, ``.vg``,
    ``.tc``, ``.mv-ctx``) alongside the T12 surface (regression).
  * No Python source was edited; this file only re-verifies the T10
    static handler keeps serving the new files.

Run:
    python test/t13_test.py
Expected tail: ``T13 ALL TESTS PASSED``.

Offline-only by design: Vue runtime behaviour (scroll window, rAF
throttle, IntersectionObserver load-more, native ``<img loading=lazy>``
viewport decode) is covered by D3 manual QA because those paths need a
real browser. What we *can* assert statically is the contract surface
each file promises — imports, emits, attribute presence, localStorage
keys, etc.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402


class _FakeServer:
    def __init__(self) -> None:
        self.routes = web.RouteTableDef()


def _build_app():
    from gallery import routes as _routes

    fake = _FakeServer()
    _routes._registered = False
    _routes.register(fake)

    app = web.Application()
    app.add_routes(fake.routes)
    return app


# ---------------------------------------------------------------- disk ---

def _assert_files_exist() -> None:
    root = _PLUGIN_ROOT / "js" / "gallery_dist"
    expected = [
        "index.html",
        "app.js",
        "api.js",
        "stores/filters.js",
        "components/FolderTree.js",
        "components/ThumbCard.js",
        "components/VirtualGrid.js",
        "views/MainView.js",
    ]
    for rel in expected:
        p = root / rel
        assert p.is_file(), f"missing SPA asset: {p}"
    print("T13 disk layout (8 files) OK")


def _assert_filters_js_layout_contract() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "stores" / "filters.js").read_text(encoding="utf-8")
    must = [
        "export const layoutState",
        "export function setCardsPerRow",
        "xyz_gallery.cards_per_row.v1",
        "CARDS_PER_ROW_MIN",
        "CARDS_PER_ROW_MAX",
        "CARDS_PER_ROW_DEFAULT",
    ]
    for needle in must:
        assert needle in body, f"filters.js (T13) missing: {needle!r}"
    # Range matches FR-9a: 2..12, default 6.
    assert re.search(r"CARDS_PER_ROW_MIN\s*=\s*2", body), body[:800]
    assert re.search(r"CARDS_PER_ROW_MAX\s*=\s*12", body), body[:800]
    assert re.search(r"CARDS_PER_ROW_DEFAULT\s*=\s*6", body), body[:800]
    # Clamp path: Math.max/min applied on write.
    assert "Math.max" in body and "Math.min" in body
    # _internals is extended for the test harness — this also verifies
    # T12's export shape survived our edit.
    assert "CARDS_PER_ROW_KEY" in body
    print("T13 stores/filters.js cards-per-row contract OK")


def _assert_thumb_card_contract() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "components" / "ThumbCard.js").read_text(encoding="utf-8")
    assert "export const ThumbCard" in body
    # Native lazy-decoded img per SPEC §8.6.
    assert 'loading="lazy"' in body, body[:400]
    assert 'decoding="async"' in body, body[:400]
    # Uses backend-provided thumb_url verbatim (SPEC §4 #39).
    assert ":src=\"item.thumb_url\"" in body or ":src='item.thumb_url'" in body
    # Emits: open (click), toggle-favorite, context (right-click).
    assert "'open'" in body
    assert "'toggle-favorite'" in body
    assert "'context'" in body
    # Right-click preventDefault + emit context (FR-14 affordance).
    assert "e.preventDefault()" in body
    assert "@contextmenu" in body
    # Filename tooltip (FR-11 truncation).
    assert ":title=\"item.filename" in body
    # Favorite toggle stops propagation so it doesn't also open detail.
    assert "stopPropagation" in body
    print("T13 components/ThumbCard.js contract OK")


def _assert_virtual_grid_contract() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "components" / "VirtualGrid.js").read_text(encoding="utf-8")
    assert "export const VirtualGrid" in body
    # Imports ThumbCard (same directory, relative path).
    assert "./ThumbCard.js" in body
    # Virtual-scroll primitives per SPEC §8.6.
    assert "IntersectionObserver" in body, body[:600]
    assert "requestAnimationFrame" in body, body[:600]
    # Scroll container + ±2 viewport buffer (literal heuristic).
    assert "@scroll" in body
    assert re.search(r"2\s*\*\s*vh", body), "missing ±2 viewport buffer math"
    # Props and emits wiring.
    for prop in ("items", "cardsPerRow", "totalEstimate", "hasMore",
                 "loading", "loadingMore"):
        assert prop in body, f"VirtualGrid prop missing: {prop}"
    for emit in ("'load-more'", "'open'", "'toggle-favorite'", "'context'"):
        assert emit in body, f"VirtualGrid emit missing: {emit}"
    # Disconnects observers on unmount to prevent leaks.
    assert "onBeforeUnmount" in body
    assert "disconnect()" in body
    # Uses the grid template via gridTemplateColumns so cards-per-row
    # reflows the CSS grid without DOM structural change.
    assert "gridTemplateColumns" in body
    # Sentinel element for IntersectionObserver-driven pagination.
    assert "ref=\"sentinel\"" in body
    # Scroll-position fallback for load-more (regression guard for the
    # fix landed during T14 QA: IntersectionObserver misses a
    # non-intersecting → non-intersecting jump when the user drags the
    # scrollbar past the sentinel in one gesture, or when T14's
    # sessionStorage restore lands scrollTop past the loaded tail, or
    # when DevTools docking drops the initial IO callback). Must keep
    # BOTH paths.
    assert "maybeLoadMore" in body, \
        "VirtualGrid must keep the scroll-position load-more fallback"
    # Fallback must be armed from the rAF scroll handler and from the
    # items watcher (new-page chain after the first far jump).
    assert re.search(r"requestAnimationFrame\([\s\S]*?maybeLoadMore\(\)", body), \
        "maybeLoadMore must be called from the rAF scroll handler"
    assert re.search(r"nextTick\(\(\)\s*=>\s*maybeLoadMore\(\)\)", body), \
        "maybeLoadMore must be called after items change via nextTick"
    print("T13 components/VirtualGrid.js contract OK")


def _assert_main_view_contract() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "views" / "MainView.js").read_text(encoding="utf-8")
    # Imports: VirtualGrid + layoutState/setCardsPerRow from the store.
    assert "../components/VirtualGrid.js" in body
    assert "layoutState" in body and "setCardsPerRow" in body
    # Toolbar markup.
    assert "mv-toolbar" in body
    assert 'type="range"' in body
    assert 'min="2"' in body and 'max="12"' in body
    # Sort dropdown (FR-9b): key:dir pairs.
    assert "SORT_OPTIONS" in body
    for pair in ("time:desc", "time:asc", "name:asc", "size:desc",
                 "folder:asc"):
        assert pair in body, f"sort option missing: {pair}"
    # Grid wire-up.
    assert "<VirtualGrid" in body
    assert ":cards-per-row=\"layoutState.cardsPerRow\"" in body
    assert "@load-more=\"loadMore\"" in body
    assert "@open=\"onOpenImage\"" in body
    assert "@toggle-favorite=\"onToggleFavorite\"" in body
    assert "@context=\"onContext\"" in body
    # Cursor-based pagination: next_cursor -> cursor param.
    assert "next_cursor" in body
    assert "cursor: nextCursor.value" in body
    # Left-click navigation hits hash router.
    assert "#/image/" in body
    # Right-click context menu placeholder (FR-14 stub; real Move/Delete
    # land in T24 / T25 → disabled=true today).
    assert "mv-ctx" in body
    assert "disabled" in body
    # Filter watcher must reset pagination (resetAndFetch called).
    assert "resetAndFetch" in body
    # T12 surface (regression — filter labels still present).
    for label in (
        "name filter:", "positive prompt filter:", "tag filter:",
        "favorite filter:", "model filter:", "date filter:",
    ):
        assert label in body, f"MainView lost T12 label: {label!r}"
    print("T13 views/MainView.js contract OK")


def _assert_index_html_css() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "index.html").read_text(encoding="utf-8")
    for sel in (".mv-toolbar", ".mv-cpr", ".mv-sort",
                ".vg ", ".vg-spacer", ".vg-window", ".vg-sentinel",
                ".tc ", ".tc-thumb", ".tc-fav", ".tc-name",
                ".mv-ctx"):
        assert sel in body, f"index.html missing CSS: {sel!r}"
    # T12 surface still present (regression).
    assert ".mv-sidebar" in body
    assert ".ft-node" in body
    # T11 SPA shell intact.
    assert 'type="importmap"' in body
    assert "/xyz/gallery/static/app.js" in body
    print("T13 index.html CSS surface OK")


# ---------------------------------------------------------------- HTTP ---

async def _assert_served(client: TestClient, rel: str, sniff: str) -> None:
    r = await client.get(f"/xyz/gallery/static/{rel}")
    assert r.status == 200, f"{rel} → {r.status}"
    body = await r.text()
    assert sniff in body, f"{rel} body missing: {sniff!r}"


async def _assert_all_served(client: TestClient) -> None:
    await _assert_served(client, "components/ThumbCard.js",
                         "export const ThumbCard")
    await _assert_served(client, "components/VirtualGrid.js",
                         "export const VirtualGrid")
    # T12 assets still reachable (regression).
    await _assert_served(client, "stores/filters.js",
                         "export const filterState")
    await _assert_served(client, "views/MainView.js",
                         "export const MainView")
    print("T13 static handler serves new components + T12 regression OK")


async def _assert_traversal_still_blocked(client: TestClient) -> None:
    r = await client.get("/xyz/gallery/static/components/%2e%2e/%2e%2e/routes.py")
    assert r.status in (400, 404), r.status
    print("T13 nested-dir traversal guard OK")


async def _run_all() -> None:
    app = _build_app()
    async with TestServer(app) as srv:
        async with TestClient(srv) as client:
            await _assert_all_served(client)
            await _assert_traversal_still_blocked(client)


def main() -> None:
    _assert_files_exist()
    _assert_filters_js_layout_contract()
    _assert_thumb_card_contract()
    _assert_virtual_grid_contract()
    _assert_main_view_contract()
    _assert_index_html_css()
    asyncio.run(_run_all())
    print("T13 ALL TESTS PASSED")


if __name__ == "__main__":
    main()
