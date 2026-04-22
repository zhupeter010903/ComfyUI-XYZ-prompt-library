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
//   * openWS() is a *stub* — the real /xyz/gallery/ws route lands in
//     T18 (AI_RULES R1.2 — no cross-task implementation).

const BASE = '/xyz/gallery';

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
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }
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

// Stubbed — the real WebSocket route (/xyz/gallery/ws) and message
// handling belong to T18. Returning a shaped object lets later views
// (T22+) wire their handlers today without needing a second rollout.
export function openWS(handlers = {}) {
  return {
    isStub: true,
    handlers,
    send() { /* no-op */ },
    close() { /* no-op */ },
  };
}

export const BASE_URL = BASE;

export default {
  get, post, patch, delete: del, openWS, ApiError, BASE_URL,
};
