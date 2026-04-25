// api.js — thin REST + WS client for /xyz/gallery.
//
// T11 landing set:
//   * get / post / patch / del wrappers with JSON handling.
//   * Error envelope parsing mirrors gallery/routes.py _error():
//       { "error": { "code": <string>, "message": <string>,
//                    "details"?: <object> } }
//     Non-envelope failures still throw ApiError with a best-effort code.
//   * AbortController support via opts.signal (bubbles AbortError).
//   * Array-valued query entries encode as repeated key
//     (tag=a&tag=b) to match routes.py _parse_filter's getall('tag').
//   * openWS() — one-shot WebSocket; reconnection is stores/connection.js
//     (T22). buildGalleryWebSocketUrl() is shared.

const BASE = '/xyz/gallery';
const CID_KEY = 'xyz_gallery_client_id';

/** Stable per-tab id for T25 audit ``actor`` (HTTP + WS same browser). */
export function getGalleryClientId() {
  if (typeof sessionStorage === 'undefined') return '';
  let v = sessionStorage.getItem(CID_KEY);
  if (!v) {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      v = crypto.randomUUID();
    } else {
      v = `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
    }
    try {
      sessionStorage.setItem(CID_KEY, v);
    } catch {
      return v;
    }
  }
  return v;
}

export class ApiError extends Error {
  constructor(status, code, message, details = null) {
    super(message || `${status} ${code}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function _buildQuery(query) {
  if (!query) return '';
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) {
      for (const item of v) p.append(k, String(item));
    } else if (typeof v === 'boolean') {
      p.append(k, v ? 'true' : 'false');
    } else {
      p.append(k, String(v));
    }
  }
  const qs = p.toString();
  return qs ? '?' + qs : '';
}

async function _request(method, path, { body, query, signal } = {}) {
  const url = BASE + path + _buildQuery(query);
  const init = { method, signal };
  const headers = {};
  const cid = getGalleryClientId();
  if (cid) headers['X-XYZ-Gallery-Client-Id'] = cid;
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  init.headers = headers;
  let resp;
  try {
    resp = await fetch(url, init);
  } catch (exc) {
    if (exc && exc.name === 'AbortError') throw exc;
    throw new ApiError(0, 'network',
                       (exc && exc.message) || 'network error');
  }
  if (resp.status === 204) return null;

  const ct = resp.headers.get('content-type') || '';
  let data = null;
  if (ct.includes('application/json')) {
    try {
      data = await resp.json();
    } catch (exc) {
      throw new ApiError(resp.status, 'bad_json',
                         `invalid JSON from ${method} ${path}`);
    }
  } else {
    data = await resp.text();
  }

  if (!resp.ok) {
    if (data && typeof data === 'object' && data.error) {
      throw new ApiError(
        resp.status,
        data.error.code || 'unknown',
        data.error.message || 'request failed',
        data.error.details || null,
      );
    }
    throw new ApiError(
      resp.status,
      'unknown',
      typeof data === 'string' && data
        ? data
        : `request failed: ${method} ${path}`,
    );
  }
  return data;
}

export const get   = (path, opts) => _request('GET',    path, opts);
export const post  = (path, body, opts) => _request('POST',  path, { ...opts, body });
export const patch = (path, body, opts) => _request('PATCH', path, { ...opts, body });
export const del   = (path, opts) => _request('DELETE', path, opts);

/** Server-backed subset of ``gallery_config.json`` (T36). */
export async function fetchGalleryPreferences() {
  return get('/preferences');
}

export async function patchGalleryPreferences(body) {
  return patch('/preferences', body);
}

function _parseFilenameFromContentDisposition(cd) {
  if (!cd || typeof cd !== 'string') return null;
  const mStar = cd.match(/filename\*=UTF-8''([^;\s]+)/i);
  if (mStar) {
    try {
      return decodeURIComponent(mStar[1].trim());
    } catch {
      return mStar[1];
    }
  }
  const mQ = cd.match(/filename="([^"]+)"/i);
  if (mQ) return mQ[1];
  const mBare = cd.match(/filename=([^;\s]+)/i);
  if (mBare) return mBare[1].trim().replace(/^"(.*)"$/, '$1');
  return null;
}

const _ALLOWED_DL_VARIANT = new Set(['full', 'no_workflow', 'clean']);

let _downloadBasenamePrefix = '';
/** Default PNG export variant (mirrors ``gallery_config.download_variant``). */
let _downloadVariantDefault = 'full';

export function setDownloadVariant(v) {
  const s = (v && String(v).trim()) || 'full';
  _downloadVariantDefault = _ALLOWED_DL_VARIANT.has(s) ? s : 'full';
}

/** Optional prefix for client ``download=`` filename (T36 ``gallery_config``). */
export function setDownloadBasenamePrefix(s) {
  _downloadBasenamePrefix = typeof s === 'string' ? s : '';
}

/**
 * Trigger a browser download for ``/raw/{id}/download`` (T35).
 * Always sends ``?variant=`` using ``opts.variant`` when valid, otherwise
 * ``setDownloadVariant`` default (server would mirror config, but explicit
 * query avoids stale CDN / ambiguous caching).
 */
export async function downloadImage(imageId, opts = {}) {
  const q = {};
  const v = (opts.variant && _ALLOWED_DL_VARIANT.has(opts.variant))
    ? opts.variant
    : _downloadVariantDefault;
  q.variant = v;
  const url = BASE + `/raw/${Number(imageId)}/download` + _buildQuery(q);
  const headers = {};
  const cid = getGalleryClientId();
  if (cid) headers['X-XYZ-Gallery-Client-Id'] = cid;
  let resp;
  try {
    resp = await fetch(url, { signal: opts.signal, headers });
  } catch (exc) {
    if (exc && exc.name === 'AbortError') throw exc;
    throw new ApiError(0, 'network', (exc && exc.message) || 'network error');
  }
  if (!resp.ok) {
    let code = 'unknown';
    let message = `HTTP ${resp.status}`;
    try {
      const j = await resp.json();
      if (j && j.error) {
        code = j.error.code || code;
        message = j.error.message || message;
      }
    } catch { /* ignore */ }
    throw new ApiError(resp.status, code, message);
  }
  const blob = await resp.blob();
  const cd = resp.headers.get('Content-Disposition');
  let name = _parseFilenameFromContentDisposition(cd) || `image_${imageId}.png`;
  if (_downloadBasenamePrefix) {
    const pre = _downloadBasenamePrefix.replace(/[^\w.\-]+/g, '');
    if (pre) name = `${pre}_${name}`;
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
}

/** ws:// or wss:// URL for same-origin /xyz/gallery/ws (browser only). */
export function buildGalleryWebSocketUrl() {
  if (typeof location === 'undefined' || !location.host) return '';
  const p = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${p}://${location.host}${BASE}/ws`;
}

/**
 * Single WebSocket (no auto-reconnect). For gallery SPA use
 * startGalleryConnection() which wraps URL + backoff.
 */
export function openWS(handlers = {}) {
  if (typeof WebSocket === 'undefined' || !buildGalleryWebSocketUrl()) {
    return {
      isStub: true,
      handlers,
      send() { /* no-op */ },
      close() { /* no-op */ },
    };
  }
  const url = buildGalleryWebSocketUrl();
  const ws = new WebSocket(url);
  if (handlers.onOpen) {
    ws.addEventListener('open', () => handlers.onOpen());
  }
  ws.addEventListener('message', (ev) => {
    if (!handlers.onMessage) return;
    let o;
    try {
      o = JSON.parse(ev.data);
    } catch {
      return;
    }
    handlers.onMessage(o);
  });
  if (handlers.onClose) {
    ws.addEventListener('close', () => handlers.onClose());
  }
  if (handlers.onError) {
    ws.addEventListener('error', () => handlers.onError());
  }
  return {
    isStub: false,
    handlers,
    send(text) { try { ws.send(text); } catch { /* ignore */ } },
    close() { try { ws.close(); } catch { /* ignore */ } },
  };
}

export const BASE_URL = BASE;

export default {
  get,
  post,
  patch,
  delete: del,
  fetchGalleryPreferences,
  patchGalleryPreferences,
  downloadImage,
  setDownloadVariant,
  setDownloadBasenamePrefix,
  openWS,
  buildGalleryWebSocketUrl,
  getGalleryClientId,
  ApiError,
  BASE_URL,
};
