"""T14 offline validation — DetailView + zoom + neighbors + Back scroll.

Scope (TASKS.md T14):
  * ``js/gallery_dist/views/DetailView.js`` lands on disk and is served
    by the existing T10 static handler.
  * ``js/gallery_dist/app.js`` imports the real ``DetailView`` (no more
    T11 JSON-dump stub) and routes ``#/image/:id`` to it.
  * ``js/gallery_dist/views/MainView.js`` saves scroll position into
    ``sessionStorage`` inside ``onOpenImage`` and schedules restoration
    on the first post-mount fetch (T14 Back-button contract).
  * ``index.html`` carries the T14 CSS (``.dv``, ``.dv-canvas``,
    ``.dv-zoom``, ``.dv-meta``, ``.dv-actions``) alongside T11–T13
    surfaces (regression).

Run:
    python test/t14_test.py
Expected tail: ``T14 ALL TESTS PASSED``.

Offline-only by design — Vue runtime (pointer drag, nextTick timing,
real clipboard, native <a download> semantics) needs a real browser
and is covered by the D3 manual QA checklist. What we *can* assert
statically is the contract surface of each file (imports, emits,
backend URLs, disabled-state wiring, sessionStorage key).
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
        "views/DetailView.js",  # NEW in T14
    ]
    for rel in expected:
        p = root / rel
        assert p.is_file(), f"missing SPA asset: {p}"
    print("T14 disk layout (9 files) OK")


def _assert_detail_view_contract() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "views" / "DetailView.js"
            ).read_text(encoding="utf-8")

    assert "export const DetailView" in body, "missing named export"
    # Imports: shared filter store + api client (for neighbors / list /
    # detail). The store import is the single source of truth for
    # filter+sort context (SPEC FR-16 "within the current folder +
    # filter + sort set").
    assert "from '../api.js'" in body
    assert "apiQueryObject" in body and "filterState" in body
    assert "from '../stores/filters.js'" in body

    # Fetches the 3 endpoints T14 needs.
    assert "/image/${id}/neighbors" in body or "/image/${newId}/neighbors" in body \
        or re.search(r"/image/\$\{[^}]+\}/neighbors", body), \
        "DetailView must hit /image/{id}/neighbors"
    assert re.search(r"api\.get\(`?/image/\$\{[^}]+\}`", body), \
        "DetailView must fetch /image/{id}"
    # Wrap path uses /images with limit=1 (frontend wrap per TASKS).
    assert "'/images'" in body
    assert re.search(r"limit:\s*1", body), "wrap query must use limit=1"

    # Zoom / pan controls (FR-16).
    for fn in ("fit", "actualSize", "zoomIn", "zoomOut"):
        assert fn in body, f"DetailView missing zoom fn: {fn}"
    assert "ZOOM_STEP" in body
    assert "MIN_SCALE" in body and "MAX_SCALE" in body
    assert "onPointerDown" in body and "onPointerMove" in body and "onPointerUp" in body
    assert "setPointerCapture" in body, "pan needs setPointerCapture for drag-out-of-canvas"

    # Neighbors wrap buttons exposed & call neighbors; wrap logic uses
    # reversed sort direction for the "last" target.
    assert "gotoPrev" in body and "gotoNext" in body
    assert "wrapTarget" in body
    assert "'last'" in body and "'first'" in body

    # Copy-to-clipboard for seed / positive / negative (FR-17).
    assert "navigator.clipboard" in body
    assert "'seed'" in body and "'positive'" in body and "'negative'" in body

    # Download actions (FR-19): image / workflow / delete stub / back.
    # Backend-injected URLs (SPEC §4 #39): record.raw_url is consumed
    # by the <img>, the /raw/{id}/download URL is composed from id (not
    # hand-crafted at any earlier layer).
    assert ":src=\"record.raw_url\"" in body or ":src='record.raw_url'" in body, \
        "must use backend-injected raw_url verbatim"
    assert "/raw/${record.value.id}/download" in body \
        or re.search(r"/raw/\$\{[^}]+\}/download", body)
    assert "/image/${record.value.id}/workflow.json" in body \
        or re.search(r"/image/\$\{[^}]+\}/workflow\.json", body)

    # Download workflow is disabled when has_workflow=false (§4 #23).
    assert "hasWorkflow" in body
    assert re.search(r"'dv-btn-disabled':\s*!hasWorkflow", body)

    # Delete is a stub (TASKS T14).
    assert re.search(r"dv-btn-danger[^>]*disabled", body, re.S) \
        or ("dv-btn-danger" in body and "disabled" in body), \
        "Delete button must be a disabled stub in T14"

    # Back link points at #/ (hash router).
    assert 'href="#/"' in body

    # Guards against a bad "#/" fallback firing on disabled workflow.
    assert "onWorkflowClick" in body
    assert "preventDefault" in body

    print("T14 views/DetailView.js contract OK")


def _assert_main_view_back_contract() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "views" / "MainView.js"
            ).read_text(encoding="utf-8")

    # T14 Back-scroll: sessionStorage key + save on open + restore on
    # mount via a watcher on images.length.
    assert "MAIN_SCROLL_KEY" in body
    assert "xyz_gallery.main_scroll.v1" in body
    assert "sessionStorage" in body
    assert "pendingScrollRestore" in body
    assert "_readPendingRestore" in body

    # onOpenImage must capture scrollTop BEFORE setting location.hash.
    # We enforce the ordering textually (the storage write appears
    # above the hash assignment inside the same function body).
    m_open = re.search(
        r"function onOpenImage\(id\)\s*\{(.*?)\}\s*\n\s*//",
        body, re.S,
    )
    assert m_open, "could not locate onOpenImage body"
    inner = m_open.group(1)
    pos_set = inner.find("sessionStorage.setItem")
    pos_hash = inner.find("window.location.hash")
    assert pos_set != -1 and pos_hash != -1 and pos_set < pos_hash, \
        "onOpenImage must setItem BEFORE setting location.hash"

    # Restore watcher uses nextTick + querySelector('.vg') so it cooperates
    # with VirtualGrid's own scroll-reset watcher (post-DOM-update write).
    assert "_tryRestoreScroll" in body
    assert "nextTick" in body
    assert "document.querySelector('.vg')" in body

    # lastOpenedId still exposed for future T22 focus affordances.
    assert "lastOpenedId" in body

    # T13 regression: VirtualGrid wiring still present.
    assert "<VirtualGrid" in body
    assert "@load-more=\"loadMore\"" in body

    # T14 Back-scroll depends on VirtualGrid's scroll-position load-more
    # fallback (maybeLoadMore): when sessionStorage restores scrollTop
    # to a value past the initial page's loaded tail, the
    # IntersectionObserver sees no non-intersecting → intersecting
    # transition, so paging stalls and the user lands on empty slots.
    # The fallback in VirtualGrid makes the Back contract actually work
    # end-to-end. We assert it here too so this test fails loudly if
    # T13's VirtualGrid ever regresses.
    vg_body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "components" /
               "VirtualGrid.js").read_text(encoding="utf-8")
    assert "maybeLoadMore" in vg_body, \
        "VirtualGrid.maybeLoadMore missing — T14 Back-scroll will stall"
    print("T14 views/MainView.js Back-scroll contract OK")


def _assert_app_js_wired() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "app.js"
            ).read_text(encoding="utf-8")

    # Real DetailView import + registration.
    assert "from './views/DetailView.js'" in body
    assert re.search(r"import\s*\{[^}]*DetailView[^}]*\}", body)
    assert re.search(r"components:\s*\{[^}]*\bDetailView\b", body), \
        "App.components must register DetailView"

    # The old JSON-dump stub (the one that rendered
    # `<pre>{{ JSON.stringify(record, null, 2) }}</pre>`) must be gone.
    assert "JSON.stringify(record" not in body, \
        "T11 stub DetailView must be removed"
    # The <img class="thumb-preview"> stub was also part of the old
    # inline DetailView — scrubbed now that the real component owns
    # the detail page.
    assert 'class="thumb-preview"' not in body

    # Routing shape preserved.
    assert "parseHash" in body
    assert "route.name === 'detail'" in body
    print("T14 app.js wiring OK")


def _assert_index_html_css() -> None:
    body = (_PLUGIN_ROOT / "js" / "gallery_dist" / "index.html"
            ).read_text(encoding="utf-8")

    # T14 CSS surface.
    for sel in (
        ".dv ", ".dv-head", ".dv-title", ".dv-nav", ".dv-nav-btn",
        ".dv-body", ".dv-left", ".dv-canvas", ".dv-img",
        ".dv-zoom", ".dv-zoom-pct",
        ".dv-right", ".dv-sec", ".dv-meta", ".dv-prompt",
        ".dv-copy", ".dv-actions", ".dv-btn",
        ".dv-btn-disabled", ".dv-btn-danger",
    ):
        assert sel in body, f"index.html missing CSS: {sel!r}"

    # Regression: T11–T13 surfaces still present.
    assert 'type="importmap"' in body                 # T11
    assert "/xyz/gallery/static/app.js" in body       # T11
    assert ".mv-sidebar" in body                      # T12
    assert ".ft-node" in body                         # T12
    assert ".vg " in body                             # T13
    assert ".tc " in body                             # T13
    assert ".mv-ctx" in body                          # T13
    print("T14 index.html CSS surface + T11–T13 regression OK")


# ---------------------------------------------------------------- HTTP ---

async def _assert_served(client: TestClient, rel: str, sniff: str) -> None:
    r = await client.get(f"/xyz/gallery/static/{rel}")
    assert r.status == 200, f"{rel} → {r.status}"
    body = await r.text()
    assert sniff in body, f"{rel} body missing: {sniff!r}"


async def _assert_all_served(client: TestClient) -> None:
    await _assert_served(client, "views/DetailView.js",
                         "export const DetailView")
    # T13 assets still reachable (regression).
    await _assert_served(client, "components/VirtualGrid.js",
                         "export const VirtualGrid")
    await _assert_served(client, "components/ThumbCard.js",
                         "export const ThumbCard")
    # T12 assets still reachable (regression).
    await _assert_served(client, "views/MainView.js",
                         "export const MainView")
    await _assert_served(client, "stores/filters.js",
                         "export const filterState")
    print("T14 static handler serves DetailView + T12–T13 regression OK")


async def _assert_traversal_still_blocked(client: TestClient) -> None:
    r = await client.get("/xyz/gallery/static/views/%2e%2e/%2e%2e/routes.py")
    assert r.status in (400, 404), r.status
    print("T14 nested-dir traversal guard OK")


async def _run_all() -> None:
    app = _build_app()
    async with TestServer(app) as srv:
        async with TestClient(srv) as client:
            await _assert_all_served(client)
            await _assert_traversal_still_blocked(client)


def main() -> None:
    _assert_files_exist()
    _assert_detail_view_contract()
    _assert_main_view_back_contract()
    _assert_app_js_wired()
    _assert_index_html_css()
    asyncio.run(_run_all())
    print("T14 ALL TESTS PASSED")


if __name__ == "__main__":
    main()
