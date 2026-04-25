"""T12 offline validation — MainView + FolderTree + filters store.

Scope (TASKS.md T12):
  * New static assets are on disk AND served by the existing T10
    ``/xyz/gallery/static/{tail:.*}`` handler (regression-safe — T12
    added *zero* Python changes, but we re-verify the static handler
    still works after we placed files into new subdirs).
  * Each new file carries its public contract surface:
      - stores/filters.js   → DEFAULT_FILTER, DEFAULT_SORT, filterState,
                              panelCollapsed, setPanelCollapsed,
                              apiQueryObject, resetFilter,
                              STORAGE_KEY (via _internals).
      - components/FolderTree.js → export FolderTree.
      - views/MainView.js   → export MainView; imports FolderTree +
                              filters store + ../api.js.
  * app.js now imports MainView and registers it on the home route;
    the old inline HomeView is gone.
  * index.html no longer caps .content at max-width 1200px.

Run:
    python test/t12_test.py
Expected tail: ``T12 ALL TESTS PASSED``.

No DB / WriteQueue / PIL / browser is needed — we only exercise
aiohttp's in-process test server on the T10 static handler and do
string-level contract checks. The actual Vue runtime behaviour
(reactive URL / localStorage sync, click → emit('select')) is covered
in D3 (manual) because it requires a real browser.
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
        "stores/gallerySettings.js",
        "components/FolderTree.js",
        "views/MainView.js",
        "views/SettingsView.js",
    ]
    for rel in expected:
        p = root / rel
        assert p.is_file(), f"missing SPA asset: {p}"
    print(f"T12 disk layout ({len(expected)} files) OK")


def _assert_filters_js_contract() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "stores" / "filters.js").read_text(encoding="utf-8")
    must = [
        "export const DEFAULT_FILTER",
        "export const DEFAULT_SORT",
        "export const filterState",
        "export const panelCollapsed",
        "export function setPanelCollapsed",
        "export function apiQueryObject",
        "export function resetFilter",
        # URL + localStorage wire-up signatures.
        "URLSearchParams",
        "history.replaceState",
        "localStorage",
        # Store key is namespaced.
        "xyz_gallery.filters.v1",
        "xyz_gallery.filter_panel_collapsed.v1",
        # /images query compatibility with routes._parse_filter.
        "q.favorite = f.favorite",
        "q.folder_id",
        "q.recursive",
        "q.tag",
        "q.prompt",
        "q.sort",
        "q.dir",
    ]
    for needle in must:
        assert needle in body, f"filters.js missing: {needle!r}"
    # Defaults match SPEC §6.2: favorite='all', recursive=false,
    # sort time desc.
    assert "favorite: 'all'" in body, body[:400]
    assert "recursive: false" in body, body[:400]
    assert "key: 'time'" in body, body[:400]
    assert "dir: 'desc'" in body, body[:400]
    print("T12 stores/filters.js contract OK")


def _assert_folder_tree_contract() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "components" / "FolderTree.js").read_text(encoding="utf-8")
    assert "export const FolderTree" in body, body[:300]
    # Props + emits per FR-7 first item.
    assert "selectedId" in body
    assert "recursive" in body
    assert "'select'" in body and "'update:recursive'" in body
    # Re-click deselect rule (test #1: 选择 / 取消选择).
    assert "selectedId === id ? null : id" in body
    # Renders an "All folders" entry (deselect shortcut).
    assert "All folders" in body
    # Recursive toggle button text.
    assert "Recursive:" in body
    print("T12 components/FolderTree.js contract OK")


def _assert_main_view_contract() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "views" / "MainView.js").read_text(encoding="utf-8")
    assert "export const MainView" in body
    # Imports: Vue, api, FolderTree, filters store.
    assert re.search(r"from ['\"]vue['\"]", body), body[:500]
    assert "../api.js" in body
    assert "../components/FolderTree.js" in body
    assert "../stores/filters.js" in body
    assert "../stores/gallerySettings.js" in body
    # Wires the FR labels verbatim per SPEC §2.2.1.
    for label in (
        "name filter:",
        "positive prompt filter:",
        "tag filter:",
        "favorite filter:",
        "model filter:",
        "date filter:",
    ):
        assert label in body, f"MainView missing label: {label!r}"
    # Favorite dropdown options (FR-3d).
    for opt in ('value="all"', 'value="yes"', 'value="no"'):
        assert opt in body, f"favorite dropdown missing: {opt}"
    # Name filter debounce 250 ms (FR-3a).
    assert "250" in body and "setTimeout" in body
    # Calls /folders?include_counts=true and /images + /images/count.
    assert "'/folders'" in body and "include_counts" in body
    assert "'/images'" in body
    assert "'/images/count'" in body
    # Re-fetch on filter change (test #1).
    assert "watch(" in body
    assert "apiQueryObject" in body
    print("T12 views/MainView.js contract OK")


def _assert_app_js_swapped() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "app.js").read_text(encoding="utf-8")
    # Home route now mounts MainView, not an inline HomeView.
    assert "./views/MainView.js" in body, body[:400]
    assert "MainView" in body
    assert "HomeView" not in body, "HomeView must be gone after T12 swap"
    # Detail + Settings + NotFound are still wired (regression).
    assert "DetailView" in body
    assert "SettingsView" in body
    assert "NotFoundView" in body
    assert "parseHash" in body
    print("T12 app.js home route → MainView OK")


def _assert_index_html_css() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "index.html").read_text(encoding="utf-8")
    # T12 dropped the 1200px cap so the sidebar + main grid can breathe.
    assert "max-width: 1200px" not in body, \
        "index.html still caps .content at 1200px"
    # MainView CSS surface present.
    assert ".mv " in body or ".mv{" in body, body[:1000]
    assert ".mv-sidebar" in body
    assert ".mv-filters-body" in body
    assert ".ft-node" in body
    # Importmap + module script still intact (T11 regression).
    assert 'type="importmap"' in body
    assert "/xyz/gallery/static/app.js" in body
    print("T12 index.html CSS + T11 regression OK")


# ---------------------------------------------------------------- HTTP ---

async def _assert_served(client: TestClient, rel: str, sniff: str) -> None:
    r = await client.get(f"/xyz/gallery/static/{rel}")
    assert r.status == 200, f"{rel} → {r.status}"
    body = await r.text()
    assert sniff in body, f"{rel} body missing: {sniff!r}"


async def _assert_all_served(client: TestClient) -> None:
    await _assert_served(client, "stores/filters.js",
                         "export const filterState")
    await _assert_served(client, "components/FolderTree.js",
                         "export const FolderTree")
    await _assert_served(client, "views/MainView.js",
                         "export const MainView")
    print("T12 static handler serves nested dirs (stores/, components/, views/) OK")


async def _assert_traversal_still_blocked(client: TestClient) -> None:
    # Regression: nested dirs must not create a bypass. %2e%2e from a
    # nested path must still trip the T10 guard.
    r = await client.get("/xyz/gallery/static/views/%2e%2e/%2e%2e/routes.py")
    assert r.status in (400, 404), r.status
    print("T12 nested-dir traversal guard OK")


async def _run_all() -> None:
    app = _build_app()
    async with TestServer(app) as srv:
        async with TestClient(srv) as client:
            await _assert_all_served(client)
            await _assert_traversal_still_blocked(client)


def main() -> None:
    _assert_files_exist()
    _assert_filters_js_contract()
    _assert_folder_tree_contract()
    _assert_main_view_contract()
    _assert_app_js_swapped()
    _assert_index_html_css()
    asyncio.run(_run_all())
    print("T12 ALL TESTS PASSED")


if __name__ == "__main__":
    main()
