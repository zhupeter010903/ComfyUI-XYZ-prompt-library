/**
 * T20 — 监听 image.upserted / image.deleted（需 T20 watcher + 写盘触发）.
 *
 * 用法（与 t18 相同：必须在与 Comfy 同源的页面打开）:
 *   1. 浏览器打开 http://127.0.0.1:8188/ 或任意 ComfyUI 页.
 *   2. DevTools → Console，整段粘贴回车；或 Snippets 保存本文件后 Run.
 *   3. 保持此页不关；在资源管理器向 Comfy output 拷入/删除一张白名单图 (png/jpg/jpeg/webp).
 *   4. 控制台应出现 [T20] image.upserted / image.deleted 及 data.id.
 *
 * 停监: 调 globalThis.__t20StopWs?.() 或刷新页面.
 */

(function t20WsImageEventsProbe() {
  if (globalThis.__t20ProbeWs) {
    try { globalThis.__t20ProbeWs.close(); } catch (e) { /* ok */ }
  }
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${window.location.host}/xyz/gallery/ws`;
  console.info('[T20] connect (keep-open)', url);
  const ws = new WebSocket(url);
  globalThis.__t20ProbeWs = ws;

  ws.onopen = () => console.info('[T20] open — add/delete an image under a registered root');
  ws.onmessage = (ev) => {
    let o;
    try {
      o = JSON.parse(ev.data);
    } catch (e) {
      console.info('[T20] non-JSON', ev.data);
      return;
    }
    const t = o.type;
    if (t === 'image.upserted' || t === 'image.deleted') {
      console.info(`[T20] ${t}`, o.data, 'ts=', o.ts);
    } else if (t === 'pong' || t === 'image.updated' || t === 'image.sync_status_changed') {
      console.debug('[T20] other', t, o.data);
    } else {
      console.info('[T20] message', t, o);
    }
  };
  ws.onerror = (e) => console.error('[T20] ws error', e);
  ws.onclose = (ev) => console.info('[T20] closed', ev.code, ev.reason);

  globalThis.__t20StopWs = () => {
    try { ws.close(); } catch (e) { /* ok */ }
    delete globalThis.__t20ProbeWs;
    console.info('[T20] stopped');
  };
})();
