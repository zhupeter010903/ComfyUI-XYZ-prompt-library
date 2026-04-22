/**
 * T18 semi-automatic WebSocket probe (run under real ComfyUI — do not automate).
 *
 * Placement: ComfyUI-XYZNodes/test/manual/t18_comfyui_ws_probe.js
 *
 * How to load:
 *   1. Start ComfyUI so PromptServer is listening (default http://127.0.0.1:8188).
 *   2. Open any ComfyUI page in Chromium (same origin as the API).
 *   3. DevTools → Sources → Snippets → New snippet → paste this file → Run,
 *      OR paste the IIFE body directly into the Console.
 *
 * What it checks:
 *   - WS URL resolves relative to current origin → /xyz/gallery/ws
 *   - onopen fires
 *   - Text "ping" yields one JSON message with type "pong" and ts field
 */

(function t18WsProbe() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${window.location.host}/xyz/gallery/ws`;
  console.info('[T18] connecting', url);
  const ws = new WebSocket(url);
  ws.onopen = () => {
    console.info('[T18] open; sending text ping');
    ws.send('ping');
  };
  ws.onmessage = (ev) => {
    console.info('[T18] message raw:', ev.data);
    try {
      const o = JSON.parse(ev.data);
      if (o.type === 'pong' && typeof o.ts === 'number' && o.data && typeof o.data === 'object') {
        console.info('[T18] PASS pong envelope shape');
      } else {
        console.warn('[T18] unexpected JSON shape', o);
      }
    } catch (e) {
      console.warn('[T18] non-JSON message', e);
    }
    ws.close();
  };
  ws.onerror = (e) => console.error('[T18] ws error', e);
  ws.onclose = (ev) => console.info('[T18] closed', ev.code, ev.reason);
})();
