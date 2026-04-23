// views/MainView.js — T12 sidebar + T13 toolbar/grid host.
//
// T12 already landed the left sidebar (Filters + FolderTree) and the
// single-shot /images + /images/count fetch. T13 replaces the simple
// filename preview list that used to sit in .mv-main with:
//
//   * a toolbar on top of the grid (cards-per-row slider for FR-9a,
//     sort dropdown for FR-9b);
//   * the VirtualGrid component — windowed DOM + IntersectionObserver
//     pagination driven by next_cursor from /images;
//   * ThumbCard instances inside the grid (loading=lazy etc. per
//     SPEC §8.6);
//   * right-click context menu: Open detail, Move… (T24), Delete… (T25);
//   * hash-router navigation to /image/:id on card left-click (FR-12 —
//     detail view is T14, but the *trigger* is T13).
//
// Deliberately out of scope (AI_RULES R1.2 / R1.3 / R6.5):
//   * Bulk selection / checkbox overlay (T23).
//   * Real favorite PATCH (T19); we keep an optimistic local flip and
//     emit intent that T19 will convert into an api.patch(/image/:id).
//   * Timeline (FR-9c).
//   * T21: Autocomplete for prompt/tag filters + /vocab/models for model list.
//   * T22: api.patch + WS (stores/connection.js) + /index/status focus
//     reconciliation.
import { defineComponent, ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue';
import * as api from '../api.js';
import { subscribeGalleryEvent, subscribeReconcile, EV } from '../stores/connection.js';
import { FolderTree } from '../components/FolderTree.js';
import { VirtualGrid } from '../components/VirtualGrid.js';
import { BulkBar } from '../components/BulkBar.js';
import { MovePicker } from '../components/MovePicker.js';
import { ConfirmModal } from '../components/ConfirmModal.js';
import { Autocomplete } from '../components/Autocomplete.js';
import { ModelFilterPick } from '../components/ModelFilterPick.js';
import {
  filterState, panelCollapsed, setPanelCollapsed,
  apiQueryObject, resetFilter,
  layoutState, setCardsPerRow,
} from '../stores/filters.js';
import { toggleCardInSelection, resetSelection } from '../stores/selection.js';
import { vocabCacheClear } from '../stores/vocab.js';

const PAGE_SIZE = 120;

function fmtBytesCtx(n) {
  const x = Number(n) || 0;
  if (x < 1024) return `${x} B`;
  if (x < 1024 * 1024) return `${(x / 1024).toFixed(1)} KiB`;
  if (x < 1024 * 1024 * 1024) return `${(x / (1024 * 1024)).toFixed(1)} MiB`;
  return `${(x / (1024 * 1024 * 1024)).toFixed(2)} GiB`;
}

// T14 Back-button contract: sessionStorage holds the scroll position
// (and the id the user opened) so DetailView → "#/" round-trips land
// the user back on the same viewport. Using sessionStorage (not
// localStorage) means the state dies with the tab, matching TASKS
// T14's "暂存" wording and avoiding cross-tab surprises.
const MAIN_SCROLL_KEY = 'xyz_gallery.main_scroll.v1';

function _readPendingRestore() {
  try {
    const raw = sessionStorage.getItem(MAIN_SCROLL_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(MAIN_SCROLL_KEY);
    const obj = JSON.parse(raw);
    if (!obj || typeof obj !== 'object') return null;
    const scrollTop = Number(obj.scrollTop);
    if (!Number.isFinite(scrollTop) || scrollTop < 0) return null;
    return { scrollTop, lastId: obj.lastId ?? null };
  } catch {
    return null;
  }
}

export const MainView = defineComponent({
  name: 'MainView',
  components: {
    FolderTree, VirtualGrid, BulkBar, MovePicker, ConfirmModal,
    Autocomplete, ModelFilterPick,
  },
  setup() {
    const folders = ref([]);
    const foldersLoading = ref(true);
    const foldersError = ref(null);

    const images = ref([]);
    const imagesLoading = ref(true);
    const loadingMore = ref(false);
    const imagesError = ref(null);
    const totalCount = ref(0);
    const approximate = ref(false);
    const nextCursor = ref(null);
    const hasMore = ref(false);

    const knownModels = ref([]);

    const promptInput = ref((filterState.filter.positive_tokens || []).join(', '));
    const tagInput = ref((filterState.filter.tag_tokens || []).join(', '));
    const nameInput = ref(filterState.filter.name || '');

    const contextMenu = ref({ open: false, x: 0, y: 0, id: null });
    const movePickerOpen = ref(false);
    const movePickerSel = ref(null);
    const deleteCtxOpen = ref(false);
    const deleteCtxId = ref(null);
    const deleteCtxBusy = ref(false);
    const deleteCtxErr = ref('');

    let nameTimer = null;
    let pendingAborter = null;
    let unsubEvent = null;
    let unsubRecon = null;
    // Monotonic token so a late-returning abort doesn't resurrect an
    // obsolete page (e.g. user changes sort while page-1 is mid-flight).
    let fetchToken = 0;
    // T14: one-shot scroll restoration target read on mount. Cleared
    // after the first non-empty fetch completes so a later refetch
    // (filter change) won't suddenly scroll back.
    let pendingScrollRestore = _readPendingRestore();
    // Highlight hint for the card we came back from (FR-19 "selection"
    // restore). T23 bulk checkbox overlay.
    const lastOpenedId = ref(pendingScrollRestore ? pendingScrollRestore.lastId : null);
    const bulkMode = ref(false);
    // Only increments on full first-page list replace (reset / filter) — not on favorite/WS
    // patches — so VirtualGrid can scroll to top *only* then, never on in-place item edits.
    const gridListGen = ref(0);

    async function fetchFolders() {
      foldersLoading.value = true;
      foldersError.value = null;
      try {
        const resp = await api.get('/folders', { query: { include_counts: 'true' } });
        folders.value = Array.isArray(resp) ? resp : [];
      } catch (e) {
        foldersError.value = e;
      } finally {
        foldersLoading.value = false;
      }
    }

    async function fetchVocabModels() {
      try {
        const arr = await api.get('/vocab/models');
        if (!Array.isArray(arr)) {
          knownModels.value = [];
          return;
        }
        knownModels.value = arr.map((row) => {
          if (row && typeof row === 'object' && row.model != null) {
            return {
              model: String(row.model),
              label: row.label != null ? String(row.label) : String(row.model),
              usage_count: Number(row.usage_count) || 0,
            };
          }
          if (typeof row === 'string') {
            return { model: row, label: row, usage_count: 0 };
          }
          return null;
        }).filter(Boolean);
      } catch {
        knownModels.value = [];
      }
    }

    async function resetAndFetch() {
      if (pendingAborter) pendingAborter.abort();
      pendingAborter = new AbortController();
      const signal = pendingAborter.signal;
      const token = ++fetchToken;

      imagesLoading.value = true;
      loadingMore.value = false;
      imagesError.value = null;
      images.value = [];
      nextCursor.value = null;
      hasMore.value = false;

      const baseQ = apiQueryObject();
      try {
        const [page, count] = await Promise.all([
          api.get('/images', { query: { ...baseQ, limit: PAGE_SIZE }, signal }),
          api.get('/images/count', { query: baseQ, signal }),
        ]);
        if (signal.aborted || token !== fetchToken) return;
        const items = Array.isArray(page.items) ? page.items : [];
        images.value = items;
        gridListGen.value += 1;
        nextCursor.value = page.next_cursor || null;
        hasMore.value = !!page.next_cursor;
        totalCount.value = typeof count.total === 'number' ? count.total : 0;
        approximate.value = !!count.approximate;
      } catch (e) {
        if (e && e.name === 'AbortError') return;
        if (token !== fetchToken) return;
        imagesError.value = e;
      } finally {
        if (token === fetchToken) imagesLoading.value = false;
      }
    }

    async function loadMore() {
      if (!hasMore.value || loadingMore.value || imagesLoading.value) return;
      if (!nextCursor.value) return;
      loadingMore.value = true;
      const token = fetchToken;
      const baseQ = apiQueryObject();
      try {
        const page = await api.get('/images', {
          query: { ...baseQ, limit: PAGE_SIZE, cursor: nextCursor.value },
        });
        if (token !== fetchToken) return;
        const items = Array.isArray(page.items) ? page.items : [];
        images.value = images.value.concat(items);
        nextCursor.value = page.next_cursor || null;
        hasMore.value = !!page.next_cursor;
      } catch (e) {
        if (token !== fetchToken) return;
        imagesError.value = e;
        hasMore.value = false;
      } finally {
        if (token === fetchToken) loadingMore.value = false;
      }
    }

    /**
     * Watcher re-indexes a file (favicon PATCH → metadata write → fs change) and
     * broadcasts `image.upserted` — a full `resetAndFetch` would clear `images` and
     * scroll to the top, so we only merge the single row.
     */
    async function mergeRowFromIndexUpsert(imageId) {
      if (typeof imageId !== 'number') return;
      const idx = images.value.findIndex((x) => x && x.id === imageId);
      if (idx < 0) {
        try {
          const c = await api.get('/images/count', { query: apiQueryObject() });
          if (c && typeof c.total === 'number') totalCount.value = c.total;
        } catch { /* ignore */ }
        return;
      }
      const row = images.value[idx];
      try {
        const rec = await api.get(`/image/${imageId}`);
        if (!rec || typeof rec !== 'object') return;
        Object.assign(row, rec);
      } catch { /* 404/500 — leave list as-is */ }
    }

    function removeImageRowById(imageId) {
      if (typeof imageId !== 'number') return;
      const i = images.value.findIndex((x) => x && x.id === imageId);
      if (i < 0) {
        void (async () => {
          try {
            const c = await api.get('/images/count', { query: apiQueryObject() });
            if (c && typeof c.total === 'number') totalCount.value = c.total;
          } catch { /* ignore */ }
        })();
        return;
      }
      images.value.splice(i, 1);
      if (totalCount.value > 0) totalCount.value -= 1;
    }

    onMounted(() => {
      fetchFolders();
      fetchVocabModels();
      resetAndFetch();
      window.addEventListener('click', closeContextMenu);
      window.addEventListener('scroll', closeContextMenu, true);

      unsubRecon = subscribeReconcile(() => { resetAndFetch(); });
      unsubEvent = subscribeGalleryEvent((env) => {
        const t = env && env.type;
        const d = (env && env.data) || {};
        if (t === EV.DRIFT) {
          resetAndFetch();
          return;
        }
        if (t === EV.UPSERTED) {
          const iid = typeof d.id === 'number' ? d.id : Number(d.id);
          if (Number.isFinite(iid)) {
            void mergeRowFromIndexUpsert(iid);
          }
          return;
        }
        if (t === EV.DELETED) {
          const iid = typeof d.id === 'number' ? d.id : Number(d.id);
          if (Number.isFinite(iid)) {
            removeImageRowById(iid);
          }
          return;
        }
        if (t === EV.INDEX_PROGRESS) {
          return;
        }
        if (t === EV.UPDATED && typeof d.id === 'number') {
          if (Array.isArray(d.tags)) vocabCacheClear();
          if (d.moved_to) {
            void mergeRowFromIndexUpsert(d.id);
            return;
          }
          const idx = images.value.findIndex((x) => x && x.id === d.id);
          if (idx < 0) return;
          const it = images.value[idx];
          if (!it.gallery) it.gallery = {};
          if (d.version != null) it.gallery.version = d.version;
          if (d.favorite !== undefined) it.gallery.favorite = !!d.favorite;
          if (Array.isArray(d.tags)) it.gallery.tags = d.tags.slice();
          return;
        }
        if (t === EV.SYNC && typeof d.id === 'number') {
          const idx = images.value.findIndex((x) => x && x.id === d.id);
          if (idx < 0) return;
          const it = images.value[idx];
          if (!it.gallery) it.gallery = {};
          if (d.sync_status != null) it.gallery.sync_status = d.sync_status;
          if (d.version != null) it.gallery.version = d.version;
        }
      });
    });

    onBeforeUnmount(() => {
      if (pendingAborter) pendingAborter.abort();
      if (nameTimer) clearTimeout(nameTimer);
      if (unsubEvent) { unsubEvent(); unsubEvent = null; }
      if (unsubRecon) { unsubRecon(); unsubRecon = null; }
      window.removeEventListener('click', closeContextMenu);
      window.removeEventListener('scroll', closeContextMenu, true);
    });

    // Any FilterSpec or SortSpec change resets pagination and refetches
    // page 1. cardsPerRow is intentionally NOT in this watcher — it's
    // a pure client-side layout knob and must not trigger a refetch.
    watch(
      () => JSON.stringify(apiQueryObject()),
      () => resetAndFetch(),
    );

    watch(bulkMode, (on) => {
      if (!on) resetSelection();
    });

    function onNameInput(e) {
      nameInput.value = e.target.value;
      if (nameTimer) clearTimeout(nameTimer);
      nameTimer = setTimeout(() => {
        filterState.filter.name = nameInput.value;
      }, 250);
    }

    function commitPromptTokens() {
      filterState.filter.positive_tokens = promptInput.value
        .split(',').map(s => s.trim()).filter(Boolean);
    }
    function commitTagTokens() {
      filterState.filter.tag_tokens = tagInput.value
        .split(',').map(s => s.trim()).filter(Boolean);
    }

    function setPromptInput(v) {
      promptInput.value = v;
    }
    function setTagInput(v) {
      tagInput.value = v;
    }

    function onToggleDateBound(which, enabled) {
      if (!enabled) {
        filterState.filter[which] = '';
      } else if (!filterState.filter[which]) {
        filterState.filter[which] = new Date().toISOString().slice(0, 10);
      }
    }

    function onSelectFolder(id) {
      filterState.filter.folder_id = id;
    }

    function onToggleBulk(id) {
      toggleCardInSelection(id);
    }
    function onToggleRecursive(v) {
      filterState.filter.recursive = !!v;
    }

    function toggleCollapse() {
      setPanelCollapsed(!panelCollapsed.filters);
    }

    function onResetClick() {
      resetFilter();
      nameInput.value = '';
      promptInput.value = '';
      tagInput.value = '';
    }

    watch(() => filterState.filter.name, (v) => {
      if (v !== nameInput.value) nameInput.value = v;
    });
    watch(() => filterState.filter.positive_tokens, (v) => {
      const s = Array.isArray(v) ? v.join(', ') : '';
      if (s !== promptInput.value) promptInput.value = s;
    });
    watch(() => filterState.filter.tag_tokens, (v) => {
      const s = Array.isArray(v) ? v.join(', ') : '';
      if (s !== tagInput.value) tagInput.value = s;
    });

    const hasDateAfter = computed(() => !!filterState.filter.date_after);
    const hasDateBefore = computed(() => !!filterState.filter.date_before);

    // Toolbar — cards-per-row slider + sort dropdown. The slider writes
    // through setCardsPerRow so the clamp/localStorage sink in the
    // store stays the single source of truth.
    function onCardsPerRowInput(e) {
      setCardsPerRow(e.target.value);
    }

    const SORT_OPTIONS = [
      { value: 'time:desc', label: 'Newest first' },
      { value: 'time:asc', label: 'Oldest first' },
      { value: 'name:asc', label: 'Name (A → Z)' },
      { value: 'name:desc', label: 'Name (Z → A)' },
      { value: 'size:desc', label: 'Size (largest first)' },
      { value: 'size:asc', label: 'Size (smallest first)' },
      { value: 'folder:asc', label: 'Folder (A → Z)' },
      { value: 'folder:desc', label: 'Folder (Z → A)' },
    ];
    const sortValue = computed({
      get: () => `${filterState.sort.key}:${filterState.sort.dir}`,
      set: (v) => {
        const [key, dir] = String(v || '').split(':');
        if (key) filterState.sort.key = key;
        if (dir) filterState.sort.dir = dir;
      },
    });

    function onOpenImage(id) {
      if (typeof id !== 'number' && !(typeof id === 'string' && id.length)) return;
      // T14: stash the grid's scrollTop + the id the user clicked so
      // Back can restore both. We query .vg directly rather than
      // passing a ref through VirtualGrid — VirtualGrid is T13-stable
      // and its scroller element is unambiguous in the DOM.
      try {
        const vg = document.querySelector('.vg');
        if (vg) {
          sessionStorage.setItem(MAIN_SCROLL_KEY, JSON.stringify({
            scrollTop: vg.scrollTop,
            lastId: id,
          }));
        }
      } catch { /* sessionStorage unavailable — navigation still works */ }
      window.location.hash = `#/image/${id}`;
    }

    // Restore scroll once the first post-mount fetch lands. We run in
    // nextTick so VirtualGrid’s listGen watcher (which resets
    // scrollTop=0 on a new first page) has already flushed.
    function _tryRestoreScroll() {
      if (!pendingScrollRestore) return;
      if (!images.value.length) return;
      const target = pendingScrollRestore.scrollTop;
      pendingScrollRestore = null;
      nextTick(() => {
        const vg = document.querySelector('.vg');
        if (vg) vg.scrollTop = target;
      });
    }
    watch(() => images.value.length, _tryRestoreScroll);

    async function onToggleFavorite(id) {
      if (typeof id !== 'number') return;
      const idx = images.value.findIndex((x) => x && x.id === id);
      if (idx < 0) return;
      const it = images.value[idx];
      const cur = !!(it.gallery && it.gallery.favorite);
      const next = !cur;
      const prevFav = cur;
      const prevSync = it.gallery && it.gallery.sync_status;
      if (!it.gallery) it.gallery = {};
      it.gallery.favorite = next;
      it.gallery.sync_status = 'pending';
      try {
        const u = await api.patch(`/image/${id}`, { favorite: next });
        if (u && u.gallery) {
          Object.assign(it.gallery, u.gallery);
        }
        // Do not set thumb_url — ?v= changes reload the <img> and cause visible flash;
        // favorite is DB-only and the raster thumb is unchanged.
      } catch (e) {
        it.gallery.favorite = prevFav;
        it.gallery.sync_status = prevSync;
      }
    }

    function onContext({ id, x, y }) {
      contextMenu.value = { open: true, x, y, id };
    }
    function closeContextMenu() {
      if (contextMenu.value.open) contextMenu.value = { open: false, x: 0, y: 0, id: null };
    }
    function onCtxOpenDetail() {
      const id = contextMenu.value.id;
      closeContextMenu();
      if (id != null) onOpenImage(id);
    }
    function onCtxMove() {
      const id = contextMenu.value.id;
      closeContextMenu();
      if (typeof id !== 'number') return;
      movePickerSel.value = { mode: 'explicit', ids: [id] };
      movePickerOpen.value = true;
    }
    function closeMovePicker() {
      movePickerOpen.value = false;
      movePickerSel.value = null;
    }

    const deleteCtxLines = computed(() => {
      const id = deleteCtxId.value;
      const err = deleteCtxErr.value;
      if (id == null) return ['Delete this image?'];
      const it = images.value.find((x) => x && x.id === id);
      const head = !it
        ? ['Permanently delete image #' + String(id) + '?']
        : (() => {
          const bytes = it.size && it.size.bytes != null ? it.size.bytes : 0;
          return [
            'Permanently delete "' + String(it.filename || '') + '" (#' + String(id) + ')?',
            'Approx. size: ' + fmtBytesCtx(bytes) + ' — removed from disk and index.',
          ];
        })();
      if (err) head.push('Error: ' + String(err));
      return head;
    });

    function onCtxDelete() {
      const id = contextMenu.value.id;
      closeContextMenu();
      if (typeof id !== 'number') return;
      deleteCtxErr.value = '';
      deleteCtxId.value = id;
      deleteCtxOpen.value = true;
    }

    function closeDeleteCtx() {
      if (!deleteCtxBusy.value) {
        deleteCtxOpen.value = false;
        deleteCtxId.value = null;
        deleteCtxErr.value = '';
      }
    }

    async function onDeleteCtxConfirmed() {
      const id = deleteCtxId.value;
      if (typeof id !== 'number') return;
      deleteCtxErr.value = '';
      deleteCtxBusy.value = true;
      try {
        await api.del(`/image/${id}`);
        removeImageRowById(id);
        deleteCtxOpen.value = false;
        deleteCtxId.value = null;
      } catch (e) {
        deleteCtxErr.value = (e && e.message) ? String(e.message) : String(e);
      } finally {
        deleteCtxBusy.value = false;
      }
    }

    return {
      folders, foldersLoading, foldersError,
      images, imagesLoading, loadingMore, imagesError,
      totalCount, approximate, hasMore, knownModels,
      filter: filterState.filter,
      sort: filterState.sort,
      panelCollapsed, layoutState,
      promptInput, tagInput, nameInput,
      hasDateAfter, hasDateBefore,
      contextMenu, movePickerOpen, movePickerSel,
      deleteCtxOpen, deleteCtxBusy, deleteCtxErr, deleteCtxLines,
      onCtxDelete, closeDeleteCtx, onDeleteCtxConfirmed,
      SORT_OPTIONS, sortValue,
      lastOpenedId,
      onNameInput, commitPromptTokens, commitTagTokens, setPromptInput, setTagInput,
      onToggleDateBound, onSelectFolder, onToggleRecursive,
      toggleCollapse, onResetClick,
      onCardsPerRowInput,
      onOpenImage, onToggleFavorite, onContext,
      closeContextMenu, onCtxOpenDetail, onCtxMove, closeMovePicker,
      loadMore, bulkMode, onToggleBulk, gridListGen,
    };
  },
  template: `
    <div class="mv">
      <aside class="mv-sidebar">
        <section class="mv-filters">
          <div class="mv-sec-head">
            <button type="button" class="mv-collapse" @click="toggleCollapse">
              <span class="mv-chevron">{{ panelCollapsed.filters ? '▶' : '▼' }}</span>
              Filters
            </button>
            <button type="button"
                    class="mv-reset"
                    :disabled="panelCollapsed.filters"
                    @click="onResetClick">Reset</button>
          </div>
          <div v-show="!panelCollapsed.filters" class="mv-filters-body">
            <label class="mv-field">
              <span>name filter:</span>
              <input type="text"
                     :value="nameInput"
                     @input="onNameInput"
                     placeholder="substring (debounced 250 ms)" />
            </label>
            <label class="mv-field">
              <span>positive prompt filter:</span>
              <Autocomplete fetch-kind="prompts"
                            placeholder="comma-separated tokens (T21 autocomplete)"
                            :model-value="promptInput"
                            @update:model-value="setPromptInput"
                            @commit="commitPromptTokens" />
            </label>
            <label class="mv-field">
              <span>tag filter:</span>
              <Autocomplete fetch-kind="tags"
                            placeholder="comma-separated tags (T21 autocomplete)"
                            :model-value="tagInput"
                            @update:model-value="setTagInput"
                            @commit="commitTagTokens" />
            </label>
            <label class="mv-field">
              <span>favorite filter:</span>
              <select v-model="filter.favorite">
                <option value="all">all</option>
                <option value="yes">favorite</option>
                <option value="no">not favorite</option>
              </select>
            </label>
            <label class="mv-field">
              <span>model filter:</span>
              <ModelFilterPick v-model="filter.model"
                               :options="knownModels"
                               :disabled="panelCollapsed.filters" />
            </label>
            <fieldset class="mv-field mv-date">
              <legend>date filter:</legend>
              <label class="mv-date-row">
                <input type="checkbox"
                       :checked="hasDateAfter"
                       @change="(e)=>onToggleDateBound('date_after', e.target.checked)" />
                after:
                <input type="date"
                       v-model="filter.date_after"
                       :disabled="!hasDateAfter" />
              </label>
              <label class="mv-date-row">
                <input type="checkbox"
                       :checked="hasDateBefore"
                       @change="(e)=>onToggleDateBound('date_before', e.target.checked)" />
                before:
                <input type="date"
                       v-model="filter.date_before"
                       :disabled="!hasDateBefore" />
              </label>
            </fieldset>
          </div>
        </section>
        <section class="mv-folders">
          <h3>Folders</h3>
          <div v-if="foldersLoading" class="muted">Loading folders…</div>
          <div v-else-if="foldersError" class="error">
            <strong>{{ foldersError.code || 'error' }}</strong>: {{ foldersError.message }}
          </div>
          <FolderTree v-else
                      :nodes="folders"
                      :selected-id="filter.folder_id"
                      :recursive="filter.recursive"
                      @select="onSelectFolder"
                      @update:recursive="onToggleRecursive" />
        </section>
      </aside>

      <section class="mv-main">
        <header class="mv-main-head">
          <span class="mv-count">
            <strong>{{ totalCount }}</strong>
            image<span v-if="totalCount !== 1">s</span>
            <span v-if="approximate" class="muted"> (approximate)</span>
          </span>
          <span class="muted mv-sep">·</span>
          <span class="muted">
            folder =
            <code v-if="filter.folder_id === null">all</code>
            <code v-else>#{{ filter.folder_id }}{{ filter.recursive ? ' (recursive)' : '' }}</code>
          </span>
        </header>

        <div class="mv-toolbar">
          <label class="mv-bulk">
            <input type="checkbox" v-model="bulkMode" />
            <span>Bulk edit</span>
          </label>
          <span class="mv-sep muted">·</span>
          <label class="mv-cpr">
            <span class="muted">Thumbs per row</span>
            <input type="range"
                   min="2" max="12" step="1"
                   :value="layoutState.cardsPerRow"
                   @input="onCardsPerRowInput" />
            <span class="mv-cpr-val">{{ layoutState.cardsPerRow }}</span>
          </label>
          <label class="mv-sort">
            <span class="muted">Sort</span>
            <select v-model="sortValue">
              <option v-for="o in SORT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </label>
        </div>
        <BulkBar v-if="bulkMode" @moved="resetAndFetch" />

        <div v-if="imagesError" class="error">
          <strong>{{ imagesError.code || 'error' }}</strong>: {{ imagesError.message }}
        </div>
        <VirtualGrid v-else
                     :items="images"
                     :list-gen="gridListGen"
                     :cards-per-row="layoutState.cardsPerRow"
                     :total-estimate="totalCount"
                     :has-more="hasMore"
                     :loading="imagesLoading"
                     :loading-more="loadingMore"
                     :bulk-mode="bulkMode"
                     @load-more="loadMore"
                     @open="onOpenImage"
                     @toggle-bulk="onToggleBulk"
                     @toggle-favorite="onToggleFavorite"
                     @context="onContext" />

        <div v-if="contextMenu.open"
             class="mv-ctx"
             :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
             @click.stop>
          <button type="button" @click="onCtxOpenDetail">Open detail</button>
          <button type="button" @click="onCtxMove">Move…</button>
          <button type="button" @click="onCtxDelete">Delete…</button>
        </div>
        <ConfirmModal
          v-if="deleteCtxOpen"
          title="Delete image"
          :lines="deleteCtxLines"
          confirm-label="Delete"
          cancel-label="Cancel"
          :danger="true"
          :busy="deleteCtxBusy"
          @cancel="closeDeleteCtx"
          @confirm="onDeleteCtxConfirmed"
        />
        <MovePicker v-if="movePickerOpen"
                    :forced-selection="movePickerSel"
                    @close="closeMovePicker"
                    @done="resetAndFetch" />
      </section>
    </div>
  `,
});

export default MainView;
