// components/VirtualGrid.js — T13 scope: windowed grid for ImageRecord
// cards. Three independent concerns are wired here so MainView stays
// a thin fetch-shell (see MainView.js):
//
//   1. Virtual scrolling (SPEC §8.6 / NFR-5/6):
//        * Total container height is computed from the *estimated*
//          total image count (or loaded length, whichever is larger)
//          times `rowHeight`, so the browser's own scrollbar reflects
//          "true library size" without mounting 50 000 DOM nodes.
//        * On scroll we recompute which row range intersects the
//          viewport ± 2 viewport heights (SPEC §8.6 literal window)
//          and render only those cards, offset via `translateY`.
//        * Scroll events are coalesced via rAF so rapid wheel events
//          don't thrash Vue's reactive updates.
//
//   2. Pagination (TASKS T13 "按需 api.get('/images', cursor) 续翻"):
//        * A 1 px `<div>` sentinel is absolutely positioned at the
//          *loaded* tail (loadedRows * rowHeight), NOT at the
//          estimated tail. An `IntersectionObserver` rooted at the
//          scroll container with a 200 px rootMargin fires
//          `load-more` when the user scrolls near the end of what's
//          already loaded, giving the parent time to append the next
//          cursor page before the user actually sees a gap.
//
//   3. Lazy image decode (SPEC §8.6 bullet "Image decode"):
//        * `<img loading="lazy" decoding="async">` is emitted by
//          ThumbCard; VirtualGrid itself does not touch `src` so
//          native browser lazy-loading covers the "assign src only
//          when card is within 500 px" goal without a second
//          IntersectionObserver per card (which would dominate
//          allocation budget at cards-per-row=12).
//
// Deliberately NOT implemented (task boundary per AI_RULES R1.2 /
// R1.3 / R6.5):
//   * Timeline layout (FR-9c) — P2, T28+ scope.
//   * LIFO viewport-priority thumbnail prefetch (T26).
//   * Bulk-edit checkbox overlay (T23) — see ThumbCard.
//   * Focus reconciliation on window.onfocus (T22).
import {
  defineComponent, ref, computed, watch,
  onMounted, onBeforeUnmount, nextTick,
} from 'vue';
import { ThumbCard } from './ThumbCard.js';
import { isCardSelectedInBulk } from '../stores/selection.js';

const NAME_LABEL_PX = 28;

export const VirtualGrid = defineComponent({
  name: 'VirtualGrid',
  components: { ThumbCard },
  props: {
    items: { type: Array, required: true },
    /** Increments only when MainView replaces the first page (new query); not on PATCH/WS. */
    listGen: { type: Number, default: 0 },
    cardsPerRow: { type: Number, default: 6 },
    totalEstimate: { type: Number, default: 0 },
    hasMore: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    loadingMore: { type: Boolean, default: false },
    bulkMode: { type: Boolean, default: false },
  },
  emits: ['load-more', 'open', 'toggle-favorite', 'context', 'toggle-bulk'],
  setup(props, { emit }) {
    const scroller = ref(null);
    const sentinel = ref(null);
    const containerWidth = ref(0);
    const viewportHeight = ref(0);
    const scrollTop = ref(0);

    const cardWidth = computed(() => {
      const cpr = Math.max(1, props.cardsPerRow || 1);
      const w = containerWidth.value || 0;
      return w > 0 ? Math.max(40, Math.floor(w / cpr)) : 160;
    });
    const rowHeight = computed(() => cardWidth.value + NAME_LABEL_PX);

    const loadedRows = computed(
      () => Math.ceil((props.items || []).length / Math.max(1, props.cardsPerRow)),
    );
    const estimatedTotalRows = computed(() => {
      const n = Math.max((props.items || []).length, props.totalEstimate || 0);
      return Math.ceil(n / Math.max(1, props.cardsPerRow));
    });

    const totalHeight = computed(
      () => Math.max(estimatedTotalRows.value * rowHeight.value, viewportHeight.value || 0),
    );
    const loadedHeight = computed(() => loadedRows.value * rowHeight.value);

    const _window = computed(() => {
      const rh = rowHeight.value || 1;
      const vh = viewportHeight.value || 0;
      const top = scrollTop.value;
      const start = Math.max(0, Math.floor((top - 2 * vh) / rh));
      const end = Math.min(loadedRows.value, Math.ceil((top + 3 * vh) / rh));
      return { start, end: Math.max(start, end) };
    });

    const visibleItems = computed(() => {
      const { start, end } = _window.value;
      const from = start * props.cardsPerRow;
      const to = Math.min((props.items || []).length, end * props.cardsPerRow);
      return (props.items || []).slice(from, to);
    });
    const offsetY = computed(() => _window.value.start * rowHeight.value);

    // Scroll-position fallback for load-more. The IntersectionObserver
    // on the sentinel only fires on a non-intersecting → intersecting
    // *transition*; two scenarios skip that transition entirely:
    //   (a) user drags the scrollbar past the sentinel in a single gesture
    //       — viewport goes from "above sentinel" to "far below sentinel"
    //       without ever landing on it;
    //   (b) T14 Back-scroll restores sessionStorage.scrollTop to a value
    //       past the sentinel on mount (same jump pattern);
    //   (c) DevTools docking during the first mount (Chromium quirk)
    //       occasionally drops the initial IO callback.
    // Whenever scrollTop/viewportHeight change, we also check whether
    // the viewport bottom is within the same 200 px slack of the loaded
    // tail that the IO's rootMargin uses; if so, emit load-more. The IO
    // is kept for smooth continuous scrolling as belt-and-suspenders.
    function maybeLoadMore() {
      if (!props.hasMore || props.loadingMore || props.loading) return;
      if (!scroller.value) return;
      const loadedBottom = loadedRows.value * rowHeight.value;
      if (loadedBottom <= 0) return;
      const viewBottom = scrollTop.value + viewportHeight.value;
      if (viewBottom + 200 >= loadedBottom) emit('load-more');
    }

    let rafPending = false;
    function scheduleUpdate() {
      if (rafPending) return;
      rafPending = true;
      requestAnimationFrame(() => {
        rafPending = false;
        if (!scroller.value) return;
        scrollTop.value = scroller.value.scrollTop;
        viewportHeight.value = scroller.value.clientHeight;
        maybeLoadMore();
      });
    }
    function onScroll() { scheduleUpdate(); }

    let resizeObs = null;
    let intObs = null;

    function setupObservers() {
      if (resizeObs) { resizeObs.disconnect(); resizeObs = null; }
      if (scroller.value && typeof ResizeObserver !== 'undefined') {
        resizeObs = new ResizeObserver(() => {
          if (!scroller.value) return;
          containerWidth.value = scroller.value.clientWidth;
          viewportHeight.value = scroller.value.clientHeight;
          scheduleUpdate();
        });
        resizeObs.observe(scroller.value);
      }
      if (intObs) { intObs.disconnect(); intObs = null; }
      if (sentinel.value && scroller.value
          && typeof IntersectionObserver !== 'undefined') {
        intObs = new IntersectionObserver(
          (entries) => {
            for (const e of entries) {
              if (e.isIntersecting && props.hasMore && !props.loadingMore) {
                emit('load-more');
              }
            }
          },
          { root: scroller.value, rootMargin: '200px 0px 200px 0px' },
        );
        intObs.observe(sentinel.value);
      }
    }

    onMounted(() => {
      nextTick(() => {
        if (scroller.value) {
          containerWidth.value = scroller.value.clientWidth;
          viewportHeight.value = scroller.value.clientHeight;
        }
        setupObservers();
      });
    });

    onBeforeUnmount(() => {
      if (resizeObs) resizeObs.disconnect();
      if (intObs) intObs.disconnect();
    });

    // Only MainView’s `listGen` bumps on a *full first-page replace*
    // (filter/sort reset) — not on in-place favorite / WS field patches, so
    // scrollTop is never zeroed for those.
    watch(
      () => props.listGen,
      (n, p) => {
        if (n === p) return;
        if (!scroller.value) return;
        scroller.value.scrollTop = 0;
        scrollTop.value = 0;
        nextTick(() => maybeLoadMore());
      },
    );

    watch(
      () => (props.items || []).length,
      () => {
        nextTick(() => maybeLoadMore());
      },
    );

    watch(() => props.cardsPerRow, () => scheduleUpdate());

    function onOpen(id) { emit('open', id); }
    function onFav(id) { emit('toggle-favorite', id); }
    function onCtx(p) { emit('context', p); }
    function onToggleBulk(id) { emit('toggle-bulk', id); }

    return {
      scroller, sentinel,
      cardWidth, rowHeight,
      totalHeight, loadedHeight, offsetY,
      visibleItems,
      onScroll, onOpen, onFav, onCtx, onToggleBulk,
      isCardSelectedInBulk,
    };
  },
  template: `
    <div class="vg" ref="scroller" @scroll="onScroll">
      <div class="vg-spacer" :style="{ height: totalHeight + 'px' }">
        <div class="vg-window"
             :style="{
               transform: 'translateY(' + offsetY + 'px)',
               gridTemplateColumns: 'repeat(' + cardsPerRow + ', 1fr)',
               gridAutoRows: rowHeight + 'px',
             }">
          <ThumbCard v-for="it in visibleItems"
                     :key="it.id"
                     :item="it"
                     :bulk-mode="bulkMode"
                     :bulk-selected="isCardSelectedInBulk(it.id)"
                     @open="onOpen"
                     @toggle-favorite="onFav"
                     @context="onCtx"
                     @toggle-bulk="onToggleBulk" />
        </div>
        <div ref="sentinel"
             class="vg-sentinel"
             :style="{ top: loadedHeight + 'px' }"
             aria-hidden="true"></div>
      </div>
      <div v-if="loading && !visibleItems.length" class="vg-hint loading">Loading…</div>
      <div v-if="loadingMore" class="vg-hint muted">Loading more…</div>
      <div v-if="!loading && !items.length" class="vg-hint muted">
        No images match the current filter.
      </div>
    </div>
  `,
});

export default VirtualGrid;
