"""T11 offline validation — SPA shell + static asset serving.

Scope (TASKS.md T11):
  * ``GET /xyz/gallery`` now serves the real ``index.html`` (not the
    T02 placeholder). The T10 two-branch fallback in
    ``routes._serve_spa`` is exercised from the positive side.
  * ``GET /xyz/gallery/static/app.js`` / ``api.js`` / ``index.html``
    return the built assets.
  * 404 / 400 traversal semantics (re-verified from T10 boundary) still
    hold after a real ``gallery_dist/`` dir exists on disk.
  * The shipped HTML / JS carry the contract pieces T11 promises:
      - ``index.html`` has an importmap + ``app.js`` module script tag.
      - ``api.js`` exports ``ApiError`` / ``get`` / ``openWS`` / etc.
      - ``app.js`` imports from ``'vue'`` and ``'./api.js'`` (importmap
        + relative), mounts ``#app``, and wires hash routing.

Run:
    python test/t11_test.py
Expected tail: ``T11 ALL TESTS PASSED``.

No DB / WriteQueue / PIL is needed — only aiohttp's in-process test
server + the real ``gallery/routes.py`` static handlers. That makes the
test cheap and independent of any runtime state in
``ComfyUI-XYZNodes/gallery_data/``.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put plugin root on sys.path so ``import gallery`` resolves without
# needing to run from inside ComfyUI (same pattern as t06–t10).
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402


class _FakeServer:
    """Stand-in for PromptServer.instance — exposes .routes only."""

    def __init__(self) -> None:
        self.routes = web.RouteTableDef()


def _build_app():
    """Mount gallery routes on a fresh aiohttp app.

    We reset ``routes._registered`` because the module may already have
    been imported with ``_registered=True`` in another test run within
    the same Python process.
    """
    from gallery import routes as _routes

    fake = _FakeServer()
    _routes._registered = False
    _routes.register(fake)

    app = web.Application()
    app.add_routes(fake.routes)
    return app


async def _assert_spa_served(client: TestClient) -> None:
    r = await client.get("/xyz/gallery")
    assert r.status == 200, r.status
    ct = r.headers.get("Content-Type", "")
    assert "text/html" in ct, ct
    body = await r.text()
    # Real index.html, not the T02 placeholder.
    assert "Hello Gallery" not in body, body[:200]
    # Importmap + module script tag (C-9: zero build step).
    assert 'type="importmap"' in body, "importmap missing"
    assert "/xyz/gallery/static/app.js" in body, "app.js script missing"
    assert '<div id="app"></div>' in body, "mount point missing"
    # Importmap must at least declare 'vue' (Vue 3 ESM per SPEC §10 Q1).
    assert '"vue"' in body, "vue import not declared"
    print("T11 SPA shell served (real index.html) OK")


async def _assert_static_app_js(client: TestClient) -> None:
    r = await client.get("/xyz/gallery/static/app.js")
    assert r.status == 200, r.status
    body = await r.text()
    # Must be an ES module importing from 'vue' + local ./api.js, per
    # T11 contract (importmap for 'vue', relative for 'api.js').
    assert "from 'vue'" in body or 'from "vue"' in body, body[:300]
    assert "./api.js" in body, "app.js must import ./api.js"
    # Must actually mount the Vue app somewhere on '#app'.
    assert "mount('#app')" in body or 'mount("#app")' in body, body[:300]
    # Hash routing evidence — '#/image/:id' pattern lives in app.js.
    assert "hashchange" in body, "hash router missing"
    assert "/settings" in body and "SettingsView" in body, "settings route missing"
    print("T11 /static/app.js served OK")


async def _assert_static_api_js(client: TestClient) -> None:
    r = await client.get("/xyz/gallery/static/api.js")
    assert r.status == 200, r.status
    body = await r.text()
    # Public surface contract.
    assert "export class ApiError" in body, body[:300]
    assert "export const get" in body, "api.get missing"
    assert "export const post" in body, "api.post missing"
    assert "export const patch" in body, "api.patch missing"
    assert "export const del" in body, "api.del missing"
    assert "export function openWS" in body, "openWS stub missing"
    # Error-envelope awareness: parses data.error.code / data.error.message
    # per gallery/routes.py _error().
    assert "data.error" in body, "error envelope parsing missing"
    assert "/xyz/gallery" in body, "BASE URL missing"
    assert "downloadImage" in body, "T35 downloadImage missing"
    assert "fetchGalleryPreferences" in body, "preferences GET helper missing"
    print("T11 /static/api.js served OK")


async def _assert_static_index_html(client: TestClient) -> None:
    # Also reachable directly via /static — belt-and-braces for browsers
    # that resolve '<base href>' or explicit links.
    r = await client.get("/xyz/gallery/static/index.html")
    assert r.status == 200, r.status
    body = await r.text()
    assert '<div id="app"></div>' in body
    print("T11 /static/index.html served OK")


async def _assert_404_on_missing_static(client: TestClient) -> None:
    r = await client.get("/xyz/gallery/static/does_not_exist_xyz.js")
    assert r.status == 404, r.status
    # Error envelope preserved from T10.
    body = await r.json()
    assert "error" in body and body["error"]["code"] == "not_found", body
    print("T11 missing static file → 404 envelope OK")


async def _assert_traversal_rejected(client: TestClient) -> None:
    # Re-verify T10 §4 #44 guard still holds once gallery_dist/ exists
    # on disk (regression: naive join + serve would leak).
    r = await client.get("/xyz/gallery/static/%2e%2e%2froutes.py")
    # Either 400 (resolve() escapes spa_root) or 404 (stays inside but
    # file missing). Anything < 500 and != 200 is safe.
    assert r.status in (400, 404), r.status
    print("T11 /static traversal guard (T10 regression) OK")


async def _assert_api_envelope_shape(client: TestClient) -> None:
    # End-to-end: hit a 400 route (invalid sort) and confirm the shape
    # api.js parses against (``data.error.code`` + ``data.error.message``).
    # This doubles as "api.get('/folders') returns JSON" coverage on the
    # sad path — the happy path is covered under t10 with a real DB.
    r = await client.get("/xyz/gallery/images?sort=bogus")
    assert r.status == 400, r.status
    body = await r.json()
    assert "error" in body, body
    assert "code" in body["error"], body
    assert "message" in body["error"], body
    print("T11 error envelope shape (api.js parser contract) OK")


async def _run_all() -> None:
    app = _build_app()
    async with TestServer(app) as srv:
        async with TestClient(srv) as client:
            await _assert_spa_served(client)
            await _assert_static_app_js(client)
            await _assert_static_api_js(client)
            await _assert_static_index_html(client)
            await _assert_404_on_missing_static(client)
            await _assert_traversal_rejected(client)
            await _assert_api_envelope_shape(client)


def main() -> None:
    # Sanity: the four new files must actually exist on disk first; if
    # someone ran this test against a stale tree the error message
    # should name the missing file rather than leaking an aiohttp 404.
    for name in ("index.html", "app.js", "api.js"):
        p = _PLUGIN_ROOT / "js" / "gallery_dist" / name
        assert p.is_file(), f"missing SPA asset: {p}"
    asyncio.run(_run_all())
    print("T11 ALL TESTS PASSED")


if __name__ == "__main__":
    main()
