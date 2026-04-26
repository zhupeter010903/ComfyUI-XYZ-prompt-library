// stores/connection.js — T22 WebSocket + focus reconciliation (SPEC §7.9).
import * as api from '../api.js';

const EV = {
  UPDATED: 'image.updated',
  UPSERTED: 'image.upserted',
  DELETED: 'image.deleted',
  SYNC: 'image.sync_status_changed',
  INDEX_PROGRESS: 'index.progress',
  DRIFT: 'index.drift_detected',
  FOLDER_CHANGED: 'folder.changed',
  BULK: 'bulk.progress',
  BULK_DONE: 'bulk.completed',
  PONG: 'pong',
};

let lastAppliedTs = 0;
let ws = null;
let reconnectTimer = null;
let reconnectMs = 1000;
const RECONNECT_CAP_MS = 30000;
let eventSubs = new Set();
let reconcileSubs = new Set();
let onOpenSubs = new Set();
let focusBound = false;

function noteEnvelopeTs(env) {
  if (!env || typeof env.ts !== 'number' || env.type === EV.PONG) return;
  if (env.ts > lastAppliedTs) lastAppliedTs = env.ts;
}

export function getLastAppliedEventTs() {
  return lastAppliedTs;
}

export function subscribeGalleryEvent(fn) {
  eventSubs.add(fn);
  return () => { eventSubs.delete(fn); };
}

export function subscribeReconcile(fn) {
  reconcileSubs.add(fn);
  return () => { reconcileSubs.delete(fn); };
}

export function onWebSocketOpen(fn) {
  onOpenSubs.add(fn);
  if (typeof window !== 'undefined' && ws && ws.readyState === WebSocket.OPEN) {
    try { fn(); } catch (e) { console.error('[gallery ws open]', e); }
  }
  return () => { onOpenSubs.delete(fn); };
}

function _emitOnOpen() {
  for (const fn of onOpenSubs) {
    try {
      fn();
    } catch (e) {
      console.error('[gallery ws onOpen]', e);
    }
  }
}

function emitToSubs(set, a1, a2) {
  for (const fn of set) {
    try {
      fn(a1, a2);
    } catch (e) {
      console.error('[gallery ws]', e);
    }
  }
}

export async function runFocusReconcile() {
  let st;
  try {
    st = await api.get('/index/status');
  } catch {
    return;
  }
  const ser = (st && typeof st.last_event_ts === 'number')
    ? st.last_event_ts
    : Number((st && st.last_event_ts) || 0) || 0;
  if (ser > lastAppliedTs) {
    emitToSubs(reconcileSubs, 'focus', ser);
    lastAppliedTs = ser;
  } else {
    lastAppliedTs = Math.max(lastAppliedTs, ser);
  }
}

function clearReconnectTimer() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

function scheduleConnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    openSocket();
  }, reconnectMs);
  reconnectMs = Math.min(RECONNECT_CAP_MS, reconnectMs * 2);
}

function openSocket() {
  if (typeof WebSocket === 'undefined' || !api.buildGalleryWebSocketUrl()) {
    return;
  }
  clearReconnectTimer();
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  const url = api.buildGalleryWebSocketUrl();
  let socket;
  try {
    socket = new WebSocket(url);
  } catch {
    scheduleConnect();
    return;
  }
  ws = socket;
  socket.addEventListener('open', () => {
    reconnectMs = 1000;
    runFocusReconcile();
    _emitOnOpen();
  });
  socket.addEventListener('message', (ev) => {
    let env;
    try {
      env = JSON.parse(ev.data);
    } catch {
      return;
    }
    noteEnvelopeTs(env);
    if (env && env.type && env.type !== EV.PONG) {
      emitToSubs(eventSubs, env);
    }
  });
  socket.addEventListener('close', () => {
    ws = null;
    scheduleConnect();
  });
  socket.addEventListener('error', () => {
    try { socket.close(); } catch { /* ignore */ }
  });
}

export function startGalleryConnection() {
  if (typeof window === 'undefined') return;
  if (!focusBound) {
    focusBound = true;
    window.addEventListener('focus', runFocusReconcile);
  }
  openSocket();
}

export function stopGalleryConnectionForTest() {
  if (typeof window === 'undefined') return;
  window.removeEventListener('focus', runFocusReconcile);
  focusBound = false;
  clearReconnectTimer();
  if (ws) {
    try { ws.close(); } catch { /* ignore */ }
    ws = null;
  }
  eventSubs = new Set();
  reconcileSubs = new Set();
  onOpenSubs = new Set();
  lastAppliedTs = 0;
}

export { EV };
