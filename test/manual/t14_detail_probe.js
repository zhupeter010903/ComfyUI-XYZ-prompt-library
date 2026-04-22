/**
 * T14 semi-automated browser probe (Debugged)
 */
(async function t14Probe() {
  const RESULTS = [];
  function ok(name)          { RESULTS.push({ name, pass: true,  detail: null }); }
  function bad(name, detail){ RESULTS.push({ name, pass: false, detail: String(detail) }); }
  function skip(name, detail){ RESULTS.push({ name, pass: 'skip', detail: String(detail) }); }

  const hash = window.location.hash || '';
  const onMain   = hash === '' || hash === '#/' || hash === '#';
  const onDetail = /^#\/image\/\d+$/.test(hash);

  if (onMain) {
    const scrollerQ = document.querySelector('.vg');
    if (!scrollerQ) {
      console.warn('[T14-B] MainView detected but .vg scroller missing; is the grid still booting?');
      return;
    }
    console.log('%c[T14-B] Running MainView Back-scroll probe', 'font-weight:bold');

    const totalSpacer = scrollerQ.querySelector('.vg-spacer');
    const totalH = totalSpacer ? parseInt(totalSpacer.style.height, 10) : 0;
    if (!totalSpacer || !(totalH > 0)) {
      bad('vg-spacer visible', `spacer=${!!totalSpacer} totalH=${totalH}`);
      return _dump();
    }
    ok('vg-spacer visible');

    const startTop = scrollerQ.scrollTop;
    const farTop = Math.floor(totalH * 0.7);
    const probeUrlPrefix = '/xyz/gallery/images';
    const origFetch = window.fetch.bind(window);
    let seenCursorLoad = 0;

    window.fetch = function(input, init) {
      try {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (url.includes(probeUrlPrefix) && url.includes('cursor=')) seenCursorLoad += 1;
      } catch (e) { /* ignore */ }
      return origFetch(input, init);
    };

    scrollerQ.scrollTop = farTop;
    await _sleep(3000);
    window.fetch = origFetch;

    if (seenCursorLoad > 0) ok(`load-more fired on far-jump (${seenCursorLoad} cursor request${seenCursorLoad>1?'s':''})`);
    else bad('load-more fired on far-jump', 'no /images?cursor=... request in 3 s');
    
    scrollerQ.scrollTop = startTop;
    return _dump();
  }

  if (!onDetail) {
    console.warn(`[T14-B] current hash is '${hash}'. Open a DetailView (#/image/<id>) and re-run.`);
    return;
  }

  console.log('%c[T14-B] Running DetailView probe', 'font-weight:bold');
  const origHash = hash;
  const origId = Number(hash.replace(/^#\/image\//, ''));

  // --- (1) DOM layout ---
  const root = document.querySelector('.dv');
  if (!root) { bad('.dv root present', 'DetailView did not mount'); return _dump(); }
  ok('.dv root present');

  const canvas = root.querySelector('.dv-canvas');
  const img    = root.querySelector('.dv-img');
  const zoom   = root.querySelector('.dv-zoom');
  const meta   = root.querySelector('.dv-meta');
  const acts   = root.querySelector('.dv-actions');
  const prev   = root.querySelector('[data-dv-prev], .dv-nav-btn[data-role="prev"], .dv-nav-btn:nth-of-type(1)');
  const next   = root.querySelector('[data-dv-next], .dv-nav-btn[data-role="next"], .dv-nav-btn:nth-of-type(2)');

  const elements = [
    ['.dv-canvas', canvas], ['.dv-img', img], ['.dv-zoom', zoom],
    ['.dv-meta', meta],     ['.dv-actions', acts],
    ['prev button', prev],  ['next button', next],
  ];
  for (const [lbl, el] of elements) {
    if (el) ok(`${lbl} present`); else bad(`${lbl} present`, 'missing');
  }

  // --- (2) Image src (FIXED: removed rawSrc!) ---
  const rawSrc = img && img.getAttribute('src');
  if (rawSrc && rawSrc.startsWith('/xyz/gallery/raw/')) {
    ok('image src uses /xyz/gallery/raw/<id>');
  } else {
    bad('image src uses /xyz/gallery/raw/<id>', `src=${rawSrc || 'null'}`);
  }

  // --- (3) Zoom ---
  const zoomIn  = zoom && zoom.querySelector('[data-role="zoom-in"], button[title*="Zoom in" i], button:nth-of-type(3)');
  const zoomFit = zoom && zoom.querySelector('[data-role="fit"], button[title*="Fit" i], button:nth-of-type(1)');
  if (img && zoomIn) {
    const t0 = img.style.transform || '';
    zoomIn.click();
    await _sleep(150); // Increased sleep for reactivity
    const t1 = img.style.transform || '';
    if (t0 !== t1) ok('Zoom-in changes img.style.transform');
    else bad('Zoom-in changes img.style.transform', `before='${t0}' after='${t1}'`);
    if (zoomFit) { zoomFit.click(); await _sleep(80); ok('Fit button clickable'); }
  } else {
    skip('Zoom controls', 'could not locate zoom-in / img node');
  }

  // --- (4) Download ---
  const dlImg = acts && acts.querySelector('a[href*="/raw/"][href*="/download"]');
  if (dlImg && dlImg.hasAttribute('download')) ok('Download image <a download> href=/raw/<id>/download');
  else bad('Download image <a download>', `href=${dlImg ? dlImg.getAttribute('href') : 'not found'}`);

  // --- (8) Copy-to-clipboard ---
  const copyBtn = meta && meta.querySelector('.dv-copy');
  if (copyBtn) {
    const origText = (copyBtn.textContent || '').trim();
    let spyCalled = false;
    let spyPayload = null;
    const origWT = navigator.clipboard ? navigator.clipboard.writeText : null;
    
    if (origWT) {
      try {
        navigator.clipboard.writeText = function(s) { 
          spyCalled = true; 
          spyPayload = s; 
          return Promise.resolve(); 
        };
      } catch (e) { /* property might be read-only */ }
    }

    copyBtn.click();
    await _sleep(300);
    const newText = (copyBtn.textContent || '').trim();
    const flipped = /copied/i.test(newText) && newText !== origText;

    if (spyCalled && spyPayload) {
      ok(`Copy button invoked writeText (${spyPayload.length} chars)`);
    } else if (flipped) {
      ok(`Copy button UI flipped to "${newText}"`);
    } else {
      bad('Copy button runs copy()', 'No UI change or spy call');
    }

    if (origWT) {
      try { navigator.clipboard.writeText = origWT; } catch (e) {}
    }
  }

  // --- (10) Final Wrap Navigation ---
  if (prev) {
    const before = window.location.hash;
    prev.click();
    await _sleep(500);
    const after = window.location.hash;
    if (after !== before) ok(`Prev navigates (${before} -> ${after})`);
    else bad('Prev navigates', 'Hash did not change');
    window.location.hash = origHash;
    await _sleep(250);
  }

  return _dump();

  function _dump() {
    const passN = RESULTS.filter(r => r.pass === true).length;
    const failN = RESULTS.filter(r => r.pass === false).length;
    const skipN = RESULTS.filter(r => r.pass === 'skip').length;
    console.log('\nT14-B PROBE\n============');
    RESULTS.forEach(r => {
      if (r.pass === true) console.log(`%c[PASS]%c ${r.name}`, 'color:#2a7', 'color:inherit');
      else if (r.pass === false) console.log(`%c[FAIL]%c ${r.name} <- ${r.detail}`, 'color:#d33;font-weight:bold', 'color:inherit');
      else console.log(`%c[SKIP]%c ${r.name} (${r.detail})`, 'color:#888', 'color:inherit');
    });
    return { pass: passN, fail: failN, skip: skipN };
  }

  function _sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
})();