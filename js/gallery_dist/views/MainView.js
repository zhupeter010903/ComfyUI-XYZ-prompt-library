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
import { executeImageDownload } from '../stores/downloadHelper.js';
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
import {
  LS_SIDEBAR_W,
  LS_FILTERS_H,
  DEFAULT_SIDEBAR_WIDTH_PX,
  DEFAULT_FILTERS_PANE_HEIGHT_PX,
  vocabAutocompleteMatch,
  filterVisibility,
  developerMode,
} from '../stores/gallerySettings.js';

const PAGE_SIZE = 120;

function readLayoutNum(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    const n = Number(v);
    if (Number.isFinite(n) && n > 0) return n;
  } catch { /* ignore */ }
  return fallback;
}

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
    let vocabClearTimer = null;
    function scheduleVocabCacheClearTags() {
      if (vocabClearTimer) clearTimeout(vocabClearTimer);
      vocabClearTimer = setTimeout(() => {
        vocabClearTimer = null;
        vocabCacheClear();
      }, 160);
    }

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
    const movePickerSelectionHint = computed(() => {
      const s = movePickerSel.value;
      if (s && s.mode === 'explicit' && Array.isArray(s.ids)) {
        return s.ids.length;
      }
      return null;
    });
    // Only increments on full first-page list replace (reset / filter) — not on favorite/WS
    // patches — so VirtualGrid can scroll to top *only* then, never on in-place item edits.
    const gridListGen = ref(0);
    const folderTreeScrollEl = ref(null);
    const sidebarStackEl = ref(null);

    const sidebarWidthPx = ref(readLayoutNum(LS_SIDEBAR_W, DEFAULT_SIDEBAR_WIDTH_PX));
    const filtersPaneHeightPx = ref(readLayoutNum(LS_FILTERS_H, DEFAULT_FILTERS_PANE_HEIGHT_PX));

    let fsUpsertRefreshTimer = null;
    function scheduleGridRefreshAfterFsUpsert() {
      if (fsUpsertRefreshTimer) clearTimeout(fsUpsertRefreshTimer);
      fsUpsertRefreshTimer = setTimeout(() => {
        fsUpsertRefreshTimer = null;
        resetAndFetch();
      }, 420);
    }

    function persistLayoutDims() {
      try {
        localStorage.setItem(LS_SIDEBAR_W, String(Math.round(sidebarWidthPx.value)));
        localStorage.setItem(LS_FILTERS_H, String(Math.round(filtersPaneHeightPx.value)));
      } catch { /* ignore */ }
    }

    const mvGridStyle = computed(() => ({
      display: 'grid',
      gridTemplateColumns: `${Math.round(sidebarWidthPx.value)}px 8px 1fr`,
      alignItems: 'stretch',
      columnGap: '0',
    }));

    const filtersPaneStyle = computed(() => {
      if (panelCollapsed.filters) {
        return {
          flex: '0 0 auto',
          height: 'auto',
          minHeight: 0,
          overflow: 'visible',
        };
      }
      return {
        flex: '0 0 auto',
        height: `${Math.round(filtersPaneHeightPx.value)}px`,
        minHeight: '120px',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      };
    });

    function clampFiltersPaneHeight() {
      if (panelCollapsed.filters) return;
      const aside = sidebarStackEl.value;
      if (!aside) return;
      const h = aside.clientHeight;
      const reserved = 200;
      const maxH = Math.max(140, h - reserved);
      const minH = 120;
      if (filtersPaneHeightPx.value > maxH) filtersPaneHeightPx.value = maxH;
      if (filtersPaneHeightPx.value < minH) filtersPaneHeightPx.value = minH;
    }

    let splitVActive = false;
    let splitVStartX = 0;
    let splitVStartW = 0;
    function onSplitVDown(ev) {
      splitVActive = true;
      splitVStartX = ev.clientX;
      splitVStartW = sidebarWidthPx.value;
      window.addEventListener('mousemove', onSplitVMove, true);
      window.addEventListener('mouseup', onSplitVUp, true);
      document.body.classList.add('mv-dragging-col');
    }
    function onSplitVMove(ev) {
      if (!splitVActive) return;
      const dx = ev.clientX - splitVStartX;
      let nw = splitVStartW + dx;
      nw = Math.max(200, Math.min(560, nw));
      sidebarWidthPx.value = nw;
    }
    function onSplitVUp() {
      if (!splitVActive) return;
      splitVActive = false;
      window.removeEventListener('mousemove', onSplitVMove, true);
      window.removeEventListener('mouseup', onSplitVUp, true);
      document.body.classList.remove('mv-dragging-col');
      persistLayoutDims();
    }

    let splitHActive = false;
    let splitHStartY = 0;
    let splitHStartH = 0;
    function onSplitHDown(ev) {
      if (panelCollapsed.filters) return;
      splitHActive = true;
      splitHStartY = ev.clientY;
      splitHStartH = filtersPaneHeightPx.value;
      window.addEventListener('mousemove', onSplitHMove, true);
      window.addEventListener('mouseup', onSplitHUp, true);
      document.body.classList.add('mv-dragging-row');
    }
    function onSplitHMove(ev) {
      if (!splitHActive) return;
      const dy = ev.clientY - splitHStartY;
      let nh = splitHStartH + dy;
      nh = Math.max(120, nh);
      const aside = sidebarStackEl.value;
      if (aside) {
        const cap = aside.clientHeight - 200;
        nh = Math.min(nh, Math.max(140, cap));
      }
      filtersPaneHeightPx.value = nh;
    }
    function onSplitHUp() {
      if (!splitHActive) return;
      splitHActive = false;
      window.removeEventListener('mousemove', onSplitHMove, true);
      window.removeEventListener('mouseup', onSplitHUp, true);
      document.body.classList.remove('mv-dragging-row');
      clampFiltersPaneHeight();
      persistLayoutDims();
    }

    let sidebarResizeObs = null;

    async function fetchFolders(opts = {}) {
      const silent = !!opts.silent;
      let prevScroll = null;
      if (silent && folderTreeScrollEl.value) {
        prevScroll = folderTreeScrollEl.value.scrollTop;
      }
      if (!silent) {
        foldersLoading.value = true;
      }
      foldersError.value = null;
      try {
        const resp = await api.get('/folders', { query: { include_counts: 'true' } });
        folders.value = Array.isArray(resp) ? resp : [];
      } catch (e) {
        if (!silent) {
          foldersError.value = e;
        }
      } finally {
        if (!silent) {
          foldersLoading.value = false;
        }
        if (prevScroll != null) {
          await nextTick();
          requestAnimationFrame(() => {
            const el = folderTreeScrollEl.value;
            if (el) el.scrollTop = prevScroll;
          });
        }
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

    watch(
      () => panelCollapsed.filters,
      () => {
        nextTick(() => { clampFiltersPaneHeight(); });
      },
    );

    function onFoldersExternalRefresh() {
      void fetchFolders({ silent: true });
      resetAndFetch();
    }

    onMounted(() => {
      fetchFolders();
      fetchVocabModels();
      resetAndFetch();
      window.addEventListener('click', closeContextMenu);
      window.addEventListener('scroll', closeContextMenu, true);
      window.addEventListener('xyz-gallery-folders-refresh', onFoldersExternalRefresh);

      nextTick(() => {
        clampFiltersPaneHeight();
        const el = sidebarStackEl.value;
        if (el && typeof ResizeObserver !== 'undefined') {
          sidebarResizeObs = new ResizeObserver(() => {
            clampFiltersPaneHeight();
          });
          sidebarResizeObs.observe(el);
        }
      });

      unsubRecon = subscribeReconcile(() => { resetAndFetch(); });
      unsubEvent = subscribeGalleryEvent((env) => {
        const t = env && env.type;
        const d = (env && env.data) || {};
        if (t === EV.DRIFT) {
          void fetchFolders({ silent: true });
          resetAndFetch();
          return;
        }
        if (t === EV.FOLDER_CHANGED) {
          void fetchFolders({ silent: true });
          resetAndFetch();
          return;
        }
        if (t === EV.BULK_DONE) {
          void fetchFolders({ silent: true });
          resetAndFetch();
          return;
        }
        if (t === EV.UPSERTED) {
          void fetchFolders({ silent: true });
          const iid = typeof d.id === 'number' ? d.id : Number(d.id);
          if (!Number.isFinite(iid)) return;
          const idx = images.value.findIndex((x) => x && x.id === iid);
          if (idx >= 0) {
            void mergeRowFromIndexUpsert(iid);
          } else {
            /* New id or row not on current page (OS add/rename): merge cannot insert. */
            scheduleGridRefreshAfterFsUpsert();
          }
          return;
        }
        if (t === EV.DELETED) {
          void fetchFolders({ silent: true });
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
          if (Array.isArray(d.tags)) scheduleVocabCacheClearTags();
          if (d.moved_to) {
            void fetchFolders({ silent: true });
            resetAndFetch();
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
      if (fsUpsertRefreshTimer) {
        clearTimeout(fsUpsertRefreshTimer);
        fsUpsertRefreshTimer = null;
      }
      if (splitVActive) onSplitVUp();
      if (splitHActive) onSplitHUp();
      if (sidebarResizeObs) {
        try {
          sidebarResizeObs.disconnect();
        } catch { /* ignore */ }
        sidebarResizeObs = null;
      }
      if (pendingAborter) pendingAborter.abort();
      if (nameTimer) clearTimeout(nameTimer);
      if (vocabClearTimer) {
        clearTimeout(vocabClearTimer);
        vocabClearTimer = null;
      }
      if (unsubEvent) { unsubEvent(); unsubEvent = null; }
      if (unsubRecon) { unsubRecon(); unsubRecon = null; }
      window.removeEventListener('click', closeContextMenu);
      window.removeEventListener('scroll', closeContextMenu, true);
      window.removeEventListener('xyz-gallery-folders-refresh', onFoldersExternalRefresh);
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

    watch(
      () => filterState.filter.prompt_match_mode,
      (_nv, ov) => {
        if (ov === undefined) return;
        promptInput.value = '';
        filterState.filter.positive_tokens = [];
      },
    );

    const hasDateAfter = computed(() => !!filterState.filter.date_after);
    const hasDateBefore = computed(() => !!filterState.filter.date_before);

    /** T32 — §11 F04: string = no fetch; word = ``/vocab/words``; prompt = ``/vocab/prompts``. */
    const promptFilterPlaceholder = computed(() => {
      const m = filterState.filter.prompt_match_mode;
      if (m === 'string') {
        return 'Match string: fragments → substring AND (_→ space, case-insensitive)';
      }
      if (m === 'word') {
        return 'Match word: comma/space-separated; autocomplete /vocab/words';
      }
      return 'Match phrase: comma segments → §8.8 tokens; autocomplete /vocab/prompts';
    });
    const promptFetchKind = computed(() => (
      filterState.filter.prompt_match_mode === 'word' ? 'words' : 'prompts'
    ));

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

    const ctxDownloadBusy = ref(false);
    async function onCtxDownload() {
      const id = contextMenu.value.id;
      closeContextMenu();
      if (typeof id !== 'number') return;
      ctxDownloadBusy.value = true;
      try {
        await executeImageDownload(id);
      } catch {
        /* ignore — user may cancel or network blip */
      } finally {
        ctxDownloadBusy.value = false;
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
      hasDateAfter, hasDateBefore, promptFilterPlaceholder, promptFetchKind,
      vocabAutocompleteMatch,
      contextMenu, movePickerOpen, movePickerSel, movePickerSelectionHint,
      deleteCtxOpen, deleteCtxBusy, deleteCtxErr, deleteCtxLines,
      onCtxDelete, closeDeleteCtx, onDeleteCtxConfirmed,
      SORT_OPTIONS, sortValue,
      lastOpenedId,
      onNameInput, commitPromptTokens, commitTagTokens, setPromptInput, setTagInput,
      onToggleDateBound, onSelectFolder, onToggleRecursive,
      toggleCollapse, onResetClick,
      onCardsPerRowInput,
      onOpenImage, onToggleFavorite, onContext,
      closeContextMenu, onCtxOpenDetail, onCtxMove, onCtxDownload, ctxDownloadBusy,
      closeMovePicker,
      loadMore, bulkMode, onToggleBulk, gridListGen, folderTreeScrollEl,
      sidebarStackEl, mvGridStyle, filtersPaneStyle, onSplitVDown, onSplitHDown,
      fetchFolders, resetAndFetch,
      filterVisibility,
      developerMode,
    };
  },
  template: `
    <div class="mv" :style="mvGridStyle">
      <aside class="mv-sidebar" ref="sidebarStackEl">
        <div class="mv-filters-pane" :style="filtersPaneStyle">
          <section class="mv-filters mv-filters--stack">
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
            <div v-show="!panelCollapsed.filters" class="mv-filters-scroll">
              <div class="mv-filters-body">
                <label v-show="filterVisibility.name" class="mv-field">
                  <span>name filter:</span>
                  <input type="text"
                         :value="nameInput"
                         @input="onNameInput"
                         placeholder="substring (debounced 250 ms)" />
                </label>
                <label v-show="filterVisibility.metadata_presence" class="mv-field">
                  <span>Comfy metadata (indexed PNG):</span>
                  <select v-model="filter.metadata_presence">
                    <option value="all">any</option>
                    <option value="yes">has metadata</option>
                    <option value="no">no metadata</option>
                  </select>
                </label>
                <label v-show="filterVisibility.prompt_mode" class="mv-field">
                  <span>prompt match mode:</span>
                  <select v-model="filter.prompt_match_mode">
                    <option value="prompt">Match phrase</option>
                    <option value="word">Match word</option>
                    <option value="string">Match string</option>
                  </select>
                </label>
                <label v-show="filterVisibility.prompt_tokens" class="mv-field">
                  <span>positive prompt filter:</span>
                  <Autocomplete :fetch-kind="promptFetchKind"
                                :vocab-match-mode="vocabAutocompleteMatch"
                                :placeholder="promptFilterPlaceholder"
                                :suggestions-off="filter.prompt_match_mode === 'string'"
                                :model-value="promptInput"
                                @update:model-value="setPromptInput"
                                @commit="commitPromptTokens" />
                </label>
                <label v-show="filterVisibility.tags" class="mv-field">
                  <span>tag filter:</span>
                  <Autocomplete fetch-kind="tags"
                                :vocab-match-mode="vocabAutocompleteMatch"
                                placeholder="comma-separated tags (T21 autocomplete)"
                                :model-value="tagInput"
                                @update:model-value="setTagInput"
                                @commit="commitTagTokens" />
                </label>
                <label v-show="filterVisibility.favorite" class="mv-field">
                  <span>favorite filter:</span>
                  <select v-model="filter.favorite">
                    <option value="all">all</option>
                    <option value="yes">favorite</option>
                    <option value="no">not favorite</option>
                  </select>
                </label>
                <label v-show="filterVisibility.model" class="mv-field">
                  <span>model filter:</span>
                  <ModelFilterPick v-model="filter.model"
                                   :options="knownModels"
                                   :disabled="panelCollapsed.filters" />
                </label>
                <fieldset v-show="filterVisibility.dates" class="mv-field mv-date">
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
            </div>
          </section>
        </div>
        <div v-show="!panelCollapsed.filters"
             class="mv-splitter-h"
             role="separator"
             aria-orientation="horizontal"
             title="Drag to resize filter vs folder area"
             @mousedown.prevent="onSplitHDown"></div>
        <section class="mv-folders">
          <h3>Folders</h3>
          <div v-if="foldersLoading && !folders.length" class="muted">Loading folders…</div>
          <div v-else-if="foldersError && !folders.length" class="error">
            <strong>{{ foldersError.code || 'error' }}</strong>: {{ foldersError.message }}
          </div>
          <div v-else class="mv-folders-scroll" ref="folderTreeScrollEl">
            <FolderTree :nodes="folders"
                        :selected-id="filter.folder_id"
                        :recursive="filter.recursive"
                        @select="onSelectFolder"
                        @update:recursive="onToggleRecursive"
                        @folders-changed="() => fetchFolders({ silent: true })" />
          </div>
        </section>
      </aside>
      <div class="mv-splitter-v"
           role="separator"
           aria-orientation="vertical"
           title="Drag to resize sidebar"
           @mousedown.prevent="onSplitVDown"></div>
      <section class="mv-main">
        <header class="mv-main-head">
          <span class="mv-count">
            <strong>{{ totalCount }}</strong>
            image<span v-if="totalCount !== 1">s</span>
            <span v-if="approximate" class="muted"> (approximate)</span>
          </span>
          <span v-show="developerMode" class="muted mv-sep">·</span>
          <span v-show="developerMode" class="muted">
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
          <button type="button" :disabled="ctxDownloadBusy" @click="onCtxDownload">
            {{ ctxDownloadBusy ? 'Downloading…' : 'Download image' }}
          </button>
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
                    :selection-count-hint="movePickerSelectionHint != null ? movePickerSelectionHint : undefined"
                    @close="closeMovePicker"
                    @done="resetAndFetch" />
      </section>
    </div>
  `,
});

export default MainView;
