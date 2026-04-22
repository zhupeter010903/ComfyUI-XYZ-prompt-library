// views/DetailView.js — T14 scope: 2-pane detail page with zoom + pan
// (left) and read-only metadata + copy + download + nav (right).
//
// Contract per TASKS T14 / SPEC FR-16..19:
//   * Left pane: original image served by backend-injected `raw_url`
//     (SPEC §4 #39 — NEVER hand-crafted). Zoom controls: Fit / 1:1 /
//     + / − plus pointer-drag pan; wheel-zoom is not in scope for T14.
//   * Previous / Next buttons call GET /image/{id}/neighbors with the
//     current FilterSpec + SortSpec so the traversal stays inside the
//     same result set (SPEC FR-16 wording "within the current
//     folder + filter + sort set"). Filter/sort come from the shared
//     store (stores/filters.js) — the same source MainView uses, which
//     is itself URL-mirrored per FR-4, so a direct #/image/:id link
//     still gives consistent neighbors.
//   * Wrap at ends is done FRONTEND-SIDE per TASKS T14: when
//     neighbors.prev_id === null we fetch GET /images with the sort
//     direction reversed + limit=1 to obtain the "last" element; when
//     neighbors.next_id === null we fetch GET /images with limit=1 to
//     obtain the "first" element. The extra round-trip only fires on
//     boundary clicks, so it's strictly cheaper than pre-fetching.
//   * Right pane: read-only metadata per FR-17 + copy-to-clipboard
//     buttons for positive / negative prompt / seed (FR-17 explicit).
//   * Bottom actions (FR-19):
//       - Download image → <a href="/raw/{id}/download"> (browser
//         handles the attachment disposition; routes.py emits both
//         filename= and filename*= per §4 #43).
//       - Download workflow → <a href="/image/{id}/workflow.json">
//         disabled (pointer-events: none + aria-disabled) when the
//         record says has_workflow=false (SPEC §4 #23 DB authority).
//       - Back → returns to #/ (hash router). MainView restores scroll
//         position from sessionStorage (T14 contract: onOpenImage
//         saves, onMounted restores).
//       - Delete → stub button, lands in T19/T25.
//
// T22: Autocomplete tag edit + favorite PATCH + resync + WS (connection store).
//   * Delete workflow / Move — still T25 / T24
import {
  defineComponent, ref, computed, watch,
  onMounted, onBeforeUnmount, nextTick,
} from 'vue';
import * as api from '../api.js';
import { apiQueryObject, filterState } from '../stores/filters.js';
import { BASE_URL } from '../api.js';
import { Autocomplete } from '../components/Autocomplete.js';
import { subscribeGalleryEvent, subscribeReconcile, EV } from '../stores/connection.js';

const MIN_SCALE = 0.05;
const MAX_SCALE = 20;
const ZOOM_STEP = 1.25;

export const DetailView = defineComponent({
  name: 'DetailView',
  components: { Autocomplete },
  props: { id: { type: Number, required: true } },
  setup(props) {
    const loading = ref(true);
    const error = ref(null);
    const record = ref(null);

    const prevId = ref(null);
    const nextId = ref(null);
    const neighborsLoading = ref(false);

    // Zoom / pan state — scale ≥ MIN_SCALE, translation in CSS px.
    // We do NOT persist across images: each image load re-runs fit()
    // so a huge 4K image doesn't bleed its last zoom onto a tiny one.
    const scale = ref(1);
    const tx = ref(0);
    const ty = ref(0);
    const imgNatural = ref({ w: 0, h: 0 });

    const canvasRef = ref(null);
    const canvasSize = ref({ w: 0, h: 0 });

    const tagDraft = ref(/** @type {string[]} */([]));
    const tagInput = ref('');
    const gallerySaving = ref(false);
    const favSaving = ref(false);
    const resyncing = ref(false);
    let unsubEvent = null;
    let unsubRecon = null;

    const copiedKey = ref(null);
    let copyTimer = null;

    function syncTagDraft() {
      const g = record.value && record.value.gallery;
      if (!g || !Array.isArray(g.tags)) {
        tagDraft.value = [];
      } else {
        tagDraft.value = g.tags.slice();
      }
      tagInput.value = '';
    }

    async function fetchRecord(id) {
      loading.value = true;
      error.value = null;
      record.value = null;
      try {
        record.value = await api.get(`/image/${id}`);
        syncTagDraft();
      } catch (exc) {
        error.value = exc;
      } finally {
        loading.value = false;
      }
    }

    function onTagInput(v) { tagInput.value = v; }
    function commitNewTag() {
      const s = String(tagInput.value || '').split(',').map((x) => x.trim())
        .filter(Boolean);
      if (!s.length) return;
      const set = new Set(tagDraft.value);
      const out = tagDraft.value.slice();
      for (const t of s) {
        if (!set.has(t)) {
          out.push(t);
          set.add(t);
        }
      }
      tagDraft.value = out;
      tagInput.value = '';
    }
    function removeTag(idx) {
      if (idx < 0 || idx >= tagDraft.value.length) return;
      tagDraft.value = tagDraft.value.filter((_, i) => i !== idx);
    }

    async function applyTags() {
      if (gallerySaving.value) return;
      const id = props.id;
      gallerySaving.value = true;
      const prev = record.value;
      try {
        const out = await api.patch(`/image/${id}`, { tags: tagDraft.value.slice() });
        record.value = out;
        syncTagDraft();
      } catch (e) {
        if (prev) { record.value = prev; syncTagDraft(); }
      } finally {
        gallerySaving.value = false;
      }
    }

    async function toggleFavorite() {
      if (favSaving.value || !record.value) return;
      const g = record.value.gallery || {};
      const next = !g.favorite;
      favSaving.value = true;
      const prev = record.value;
      const optimistic = { ...record.value, gallery: { ...g, favorite: next, sync_status: 'pending' } };
      record.value = optimistic;
      try {
        record.value = await api.patch(`/image/${props.id}`, { favorite: next });
        syncTagDraft();
      } catch (e) {
        record.value = prev;
        syncTagDraft();
      } finally {
        favSaving.value = false;
      }
    }

    async function doResync() {
      if (resyncing.value || !record.value) return;
      resyncing.value = true;
      try {
        const out = await api.post(`/image/${props.id}/resync`, {});
        record.value = out;
        syncTagDraft();
      } catch (e) {
        /* error stays in record; user can retry */
      } finally {
        resyncing.value = false;
      }
    }

    async function fetchNeighbors(id) {
      neighborsLoading.value = true;
      prevId.value = null;
      nextId.value = null;
      try {
        const q = apiQueryObject();
        const nb = await api.get(`/image/${id}/neighbors`, { query: q });
        prevId.value = (typeof nb.prev_id === 'number') ? nb.prev_id : null;
        nextId.value = (typeof nb.next_id === 'number') ? nb.next_id : null;
      } catch (exc) {
        // Non-fatal: leave prev/next null, user can still navigate
        // manually. We don't surface this error — the main load state
        // is the authoritative one.
        prevId.value = null;
        nextId.value = null;
      } finally {
        neighborsLoading.value = false;
      }
    }

    async function wrapTarget(mode) {
      // mode='first' → return the item that sort puts at the head
      // (i.e. what we'd wrap to when "next" is clicked at the tail).
      // mode='last'  → reverse the sort direction to grab the tail.
      const baseQ = apiQueryObject();
      const q = { ...baseQ, limit: 1 };
      if (mode === 'last') {
        const cur = filterState.sort.dir || 'desc';
        q.dir = cur === 'desc' ? 'asc' : 'desc';
      }
      try {
        const page = await api.get('/images', { query: q });
        const items = Array.isArray(page.items) ? page.items : [];
        return (items[0] && typeof items[0].id === 'number') ? items[0].id : null;
      } catch {
        return null;
      }
    }

    async function gotoPrev() {
      if (neighborsLoading.value) return;
      let target = prevId.value;
      if (target == null) {
        // Wrap: at head → jump to tail of current filter+sort set.
        target = await wrapTarget('last');
      }
      if (target != null) {
        window.location.hash = `#/image/${target}`;
      }
    }

    async function gotoNext() {
      if (neighborsLoading.value) return;
      let target = nextId.value;
      if (target == null) {
        target = await wrapTarget('first');
      }
      if (target != null) {
        window.location.hash = `#/image/${target}`;
      }
    }

    function fit() {
      const iw = imgNatural.value.w;
      const ih = imgNatural.value.h;
      const cw = canvasSize.value.w;
      const ch = canvasSize.value.h;
      if (iw > 0 && ih > 0 && cw > 0 && ch > 0) {
        const s = Math.min(cw / iw, ch / ih);
        scale.value = Math.max(MIN_SCALE, Math.min(MAX_SCALE, s || 1));
      } else {
        scale.value = 1;
      }
      tx.value = 0;
      ty.value = 0;
    }
    function actualSize() {
      scale.value = 1;
      tx.value = 0;
      ty.value = 0;
    }
    function zoomIn() {
      scale.value = Math.min(MAX_SCALE, scale.value * ZOOM_STEP);
    }
    function zoomOut() {
      scale.value = Math.max(MIN_SCALE, scale.value / ZOOM_STEP);
    }

    function onImgLoad(ev) {
      const img = ev.target;
      imgNatural.value = {
        w: img.naturalWidth || 0,
        h: img.naturalHeight || 0,
      };
      fit();
    }

    // Pointer-based pan; we set setPointerCapture so drag-out-of-
    // canvas still tracks until pointerup, and we use pointer events
    // (not mousedown) so touch/stylus also work on Chromium ≥ 110.
    let dragging = false;
    let startX = 0, startY = 0, startTx = 0, startTy = 0;
    function onPointerDown(e) {
      if (e.button !== 0) return;
      dragging = true;
      startX = e.clientX;
      startY = e.clientY;
      startTx = tx.value;
      startTy = ty.value;
      try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* ignore */ }
      e.preventDefault();
    }
    function onPointerMove(e) {
      if (!dragging) return;
      tx.value = startTx + (e.clientX - startX);
      ty.value = startTy + (e.clientY - startY);
    }
    function onPointerUp(e) {
      if (!dragging) return;
      dragging = false;
      try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* ignore */ }
    }

    async function copy(key, text) {
      const payload = text == null ? '' : String(text);
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(payload);
        } else {
          const ta = document.createElement('textarea');
          ta.value = payload;
          ta.style.position = 'fixed';
          ta.style.left = '-9999px';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand && document.execCommand('copy');
          document.body.removeChild(ta);
        }
        copiedKey.value = key;
        if (copyTimer) clearTimeout(copyTimer);
        copyTimer = setTimeout(() => { copiedKey.value = null; }, 1200);
      } catch {
        /* silent — the textarea fallback covers the common case; we
           don't want to spam the user if the browser blocks both. */
      }
    }

    // Canvas resize observer — keeps fit() honest when the user
    // resizes the window while staying on the detail page.
    let resizeObs = null;
    function _measureCanvas() {
      if (!canvasRef.value) return;
      canvasSize.value = {
        w: canvasRef.value.clientWidth,
        h: canvasRef.value.clientHeight,
      };
    }

    onMounted(() => {
      fetchRecord(props.id);
      fetchNeighbors(props.id);
      nextTick(() => {
        _measureCanvas();
        if (typeof ResizeObserver !== 'undefined' && canvasRef.value) {
          resizeObs = new ResizeObserver(() => _measureCanvas());
          resizeObs.observe(canvasRef.value);
        }
      });
      unsubRecon = subscribeReconcile(() => {
        fetchRecord(props.id);
        fetchNeighbors(props.id);
      });
      unsubEvent = subscribeGalleryEvent((env) => {
        const t = env && env.type;
        const d = (env && env.data) || {};
        if (d.id != null && Number(d.id) !== Number(props.id)) return;
        if (t === EV.DELETED) {
          error.value = { code: 'not_found', message: 'Image was removed' };
          record.value = null;
          return;
        }
        if (t === EV.UPSERTED) {
          fetchRecord(props.id);
          return;
        }
        if (t === EV.UPDATED) {
          if (!record.value) return;
          const g = { ...record.value.gallery || {} };
          if (d.version != null) g.version = d.version;
          if (d.favorite !== undefined) g.favorite = d.favorite;
          if (Array.isArray(d.tags)) g.tags = d.tags.slice();
          record.value = { ...record.value, gallery: g };
          syncTagDraft();
          return;
        }
        if (t === EV.SYNC) {
          if (!record.value) return;
          const g = { ...record.value.gallery || {} };
          if (d.sync_status != null) g.sync_status = d.sync_status;
          if (d.version != null) g.version = d.version;
          record.value = { ...record.value, gallery: g };
        }
      });
    });

    onBeforeUnmount(() => {
      if (unsubEvent) { unsubEvent(); unsubEvent = null; }
      if (unsubRecon) { unsubRecon(); unsubRecon = null; }
      if (resizeObs) { resizeObs.disconnect(); resizeObs = null; }
      if (copyTimer) { clearTimeout(copyTimer); copyTimer = null; }
    });

    watch(() => props.id, (newId) => {
      fetchRecord(newId);
      fetchNeighbors(newId);
      // Reset zoom between images so the next image starts fit-to-
      // canvas rather than inheriting the previous image's zoom.
      scale.value = 1;
      tx.value = 0;
      ty.value = 0;
    });

    const meta = computed(() => (record.value && record.value.metadata) || {});
    const gallery = computed(() => (record.value && record.value.gallery) || {});
    const size = computed(() => (record.value && record.value.size) || {});
    const folder = computed(() => (record.value && record.value.folder) || {});

    const hasWorkflow = computed(() => !!meta.value.has_workflow);

    const syncStatusBadge = computed(() => {
      const s = gallery.value.sync_status;
      if (s === 'pending') return 'pending';
      if (s === 'failed') return 'failed';
      return null;
    });
    const rawDownloadUrl = computed(() =>
      record.value ? `${BASE_URL}/raw/${record.value.id}/download` : '#');
    const workflowUrl = computed(() =>
      record.value ? `${BASE_URL}/image/${record.value.id}/workflow.json` : '#');
    const scalePct = computed(() => Math.round(scale.value * 100));

    const imgStyle = computed(() => ({
      transform:
        `translate(-50%, -50%) translate(${tx.value}px, ${ty.value}px) scale(${scale.value})`,
      transformOrigin: 'center center',
      cursor: dragging ? 'grabbing' : 'grab',
    }));

    function onWorkflowClick(e) {
      // Defence-in-depth: aria-disabled + pointer-events:none already
      // block activation, but older browsers may still follow <a
      // href="#">, so guard at the event layer too.
      if (!hasWorkflow.value) {
        e.preventDefault();
        e.stopPropagation();
      }
    }

    return {
      loading, error, record, meta, gallery, size, folder,
      prevId, nextId, neighborsLoading,
      scale, tx, ty, scalePct,
      canvasRef, imgStyle, copiedKey,
      hasWorkflow, rawDownloadUrl, workflowUrl,
      syncStatusBadge,
      tagDraft, tagInput, onTagInput, commitNewTag, removeTag, applyTags,
      gallerySaving, toggleFavorite, doResync, favSaving, resyncing,
      onImgLoad,
      onPointerDown, onPointerMove, onPointerUp,
      fit, actualSize, zoomIn, zoomOut,
      gotoPrev, gotoNext, copy,
      onWorkflowClick,
    };
  },
  template: `
    <section class="dv">
      <header class="dv-head">
        <a href="#/" class="dv-back">&larr; Back</a>
        <h2 class="dv-title">
          <span v-if="record" class="dv-title-row">
            <span v-if="syncStatusBadge"
                  class="tc-sync"
                  :class="'tc-sync-'+syncStatusBadge"
                  :title="syncStatusBadge==='pending' ? 'Metadata sync: pending' : 'Metadata sync: failed'"
                  aria-label="metadata sync" />
            #{{ record.id }} &mdash; {{ record.filename }}
          </span>
          <span v-else-if="loading" class="muted">Loading…</span>
          <span v-else-if="error" class="error">
            {{ error.code || 'error' }}: {{ error.message }}
          </span>
        </h2>
        <nav class="dv-nav">
          <button type="button"
                  class="dv-nav-btn"
                  @click="gotoPrev"
                  :disabled="neighborsLoading || !record"
                  title="Previous (wraps)">&larr; Previous</button>
          <button type="button"
                  class="dv-nav-btn"
                  @click="gotoNext"
                  :disabled="neighborsLoading || !record"
                  title="Next (wraps)">Next &rarr;</button>
        </nav>
      </header>

      <div v-if="error && !loading" class="error dv-error">
        <strong>{{ error.code || 'error' }}</strong>: {{ error.message }}
      </div>

      <div v-else class="dv-body">
        <div class="dv-left">
          <div class="dv-canvas"
               ref="canvasRef"
               @pointerdown="onPointerDown"
               @pointermove="onPointerMove"
               @pointerup="onPointerUp"
               @pointercancel="onPointerUp">
            <img v-if="record && record.raw_url"
                 class="dv-img"
                 :src="record.raw_url"
                 :style="imgStyle"
                 draggable="false"
                 @load="onImgLoad"
                 alt="" />
            <div v-else-if="loading" class="muted dv-canvas-hint">Loading image…</div>
          </div>
          <div class="dv-zoom">
            <button type="button" @click="fit" title="Fit to screen">Fit</button>
            <button type="button" @click="actualSize" title="1:1 (actual size)">1:1</button>
            <button type="button" @click="zoomOut" title="Zoom out">−</button>
            <button type="button" @click="zoomIn" title="Zoom in">+</button>
            <span class="dv-zoom-pct muted">{{ scalePct }}%</span>
          </div>
        </div>

        <aside class="dv-right">
          <h3 class="dv-sec">Metadata</h3>
          <dl class="dv-meta">
            <template v-if="record">
              <dt>Size</dt>
              <dd>
                <template v-if="size.width && size.height">
                  {{ size.width }} &times; {{ size.height }}
                </template>
                <span v-else class="muted">—</span>
                <span v-if="size.bytes" class="muted dv-bytes">
                  ({{ size.bytes }} bytes)
                </span>
              </dd>

              <dt>Created</dt>
              <dd>{{ record.created_at || '—' }}</dd>

              <dt>Folder</dt>
              <dd>
                <code>{{ folder.display_name || '—' }}</code>
                <span v-if="folder.kind" class="muted"> ({{ folder.kind }})</span>
              </dd>

              <dt>Model</dt>
              <dd><code v-if="meta.model">{{ meta.model }}</code><span v-else class="muted">—</span></dd>

              <dt>
                Seed
                <button type="button" class="dv-copy"
                        :disabled="meta.seed == null"
                        @click="copy('seed', meta.seed)">
                  {{ copiedKey === 'seed' ? 'Copied!' : 'Copy' }}
                </button>
              </dt>
              <dd><code v-if="meta.seed != null">{{ meta.seed }}</code><span v-else class="muted">—</span></dd>

              <dt>CFG</dt>
              <dd><code v-if="meta.cfg != null">{{ meta.cfg }}</code><span v-else class="muted">—</span></dd>

              <dt>Sampler</dt>
              <dd><code v-if="meta.sampler">{{ meta.sampler }}</code><span v-else class="muted">—</span></dd>

              <dt>Scheduler</dt>
              <dd><code v-if="meta.scheduler">{{ meta.scheduler }}</code><span v-else class="muted">—</span></dd>

              <dt>
                Positive prompt
                <button type="button" class="dv-copy"
                        :disabled="!meta.positive_prompt"
                        @click="copy('positive', meta.positive_prompt)">
                  {{ copiedKey === 'positive' ? 'Copied!' : 'Copy' }}
                </button>
              </dt>
              <dd>
                <pre v-if="meta.positive_prompt" class="dv-prompt">{{ meta.positive_prompt }}</pre>
                <span v-else class="muted">—</span>
              </dd>

              <dt>
                Negative prompt
                <button type="button" class="dv-copy"
                        :disabled="!meta.negative_prompt"
                        @click="copy('negative', meta.negative_prompt)">
                  {{ copiedKey === 'negative' ? 'Copied!' : 'Copy' }}
                </button>
              </dt>
              <dd>
                <pre v-if="meta.negative_prompt" class="dv-prompt">{{ meta.negative_prompt }}</pre>
                <span v-else class="muted">—</span>
              </dd>

              <dt>Gallery</dt>
              <dd>
                <div class="dv-favrow">
                  <span class="muted">Favorite:</span>
                  <button type="button"
                          class="dv-fav"
                          :class="{ active: gallery.favorite }"
                          :aria-pressed="gallery.favorite ? 'true' : 'false'"
                          :disabled="favSaving"
                          :title="gallery.favorite ? 'Unfavorite' : 'Favorite'"
                          @click="toggleFavorite">★</button>
                </div>
                <p v-if="syncStatusBadge==='failed' && record" class="dv-resync">
                  <button type="button" class="dv-resync-btn" :disabled="resyncing" @click="doResync">
                    {{ resyncing ? 'Retrying…' : 'Retry metadata sync' }}
                  </button>
                </p>
                <p class="muted">Tags (T21 / T22)</p>
                <ul class="dv-tags" v-if="tagDraft && tagDraft.length">
                  <li v-for="(t, i) in tagDraft" :key="i" class="dv-tag">
                    <code>{{ t }}</code>
                    <button type="button" class="dv-tag-x" @click="removeTag(i)" :aria-label="'remove '+t">×</button>
                  </li>
                </ul>
                <p v-else class="dv-tags-empty muted">No tags in draft (add below)</p>
                <Autocomplete class="dv-tagac"
                              fetch-kind="tags"
                              placeholder="Type a tag, pick from list, Enter"
                              :model-value="tagInput"
                              @update:model-value="onTagInput"
                              @commit="commitNewTag" />
                <p class="dv-applyp">
                  <button type="button" class="dv-apply" :disabled="gallerySaving" @click="applyTags">
                    {{ gallerySaving ? 'Saving…' : 'Apply tags' }}
                  </button>
                </p>
              </dd>
            </template>
            <template v-else-if="loading">
              <dt class="muted">Loading…</dt><dd>&nbsp;</dd>
            </template>
          </dl>

          <div class="dv-actions">
            <a class="dv-btn"
               :href="rawDownloadUrl"
               :aria-disabled="!record"
               :class="{ 'dv-btn-disabled': !record }"
               download>Download image</a>
            <a class="dv-btn"
               :href="workflowUrl"
               :aria-disabled="!hasWorkflow"
               :class="{ 'dv-btn-disabled': !hasWorkflow }"
               :tabindex="hasWorkflow ? 0 : -1"
               @click="onWorkflowClick"
               download>Download workflow</a>
            <button type="button"
                    class="dv-btn dv-btn-danger"
                    disabled
                    title="Lands in T19 / T25">Delete</button>
            <a class="dv-btn" href="#/">Back</a>
          </div>
        </aside>
      </div>
    </section>
  `,
});

export default DetailView;
