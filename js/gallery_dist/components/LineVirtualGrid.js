// LineVirtualGrid.js — T45 line view: section headers + virtualized card rows.
// Same ``items`` / cursor / load-more contract as VirtualGrid (ARCHITECTURE §7.6).
import {
  defineComponent, ref, computed, watch,
  onMounted, onBeforeUnmount, nextTick,
} from 'vue';
import { ThumbCard } from './ThumbCard.js';
import { isCardSelectedInBulk } from '../stores/selection.js';
import { partitionItemsForLineView } from '../sectionKeys.js';

const NAME_LABEL_PX = 28;
const HEADER_ROW_PX = 28;

function _prefixTops(rows) {
  const p = [0];
  let t = 0;
  for (let i = 0; i < rows.length; i += 1) {
    t += rows[i].h;
    p.push(t);
  }
  return p;
}

function _findWindow(prefix, scrollTop, viewport, overscanPx) {
  const top = Math.max(0, scrollTop - overscanPx);
  const bot = scrollTop + viewport + overscanPx;
  if (!prefix.length || prefix.length === 1) return { start: 0, end: 0 };
  let lo = 0;
  let hi = prefix.length - 2;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (prefix[mid + 1] <= top) lo = mid + 1;
    else hi = mid;
  }
  const start = lo;
  let end = start;
  const last = prefix.length - 1;
  while (end < last && prefix[end + 1] < bot) end += 1;
  return { start, end: Math.max(start, end) };
}

export const LineVirtualGrid = defineComponent({
  name: 'LineVirtualGrid',
  components: { ThumbCard },
  props: {
    items: { type: Array, required: true },
    listGen: { type: Number, default: 0 },
    cardsPerRow: { type: Number, default: 6 },
    totalEstimate: { type: Number, default: 0 },
    hasMore: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    loadingMore: { type: Boolean, default: false },
    bulkMode: { type: Boolean, default: false },
    sortKey: { type: String, default: 'time' },
    sortDir: { type: String, default: 'desc' },
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

    const sections = computed(
      () => partitionItemsForLineView(
        props.items || [],
        props.sortKey || 'time',
        props.sortDir || 'desc',
      ),
    );

    const layoutRows = computed(() => {
      const cpr = Math.max(1, props.cardsPerRow || 1);
      const rh = rowHeight.value || 1;
      const rows = [];
      const secs = sections.value || [];
      for (let s = 0; s < secs.length; s += 1) {
        const sec = secs[s];
        rows.push({
          type: 'H',
          h: HEADER_ROW_PX,
          label: sec.label,
          _rid: `h-${s}-${sec.key}`,
        });
        const its = sec.items || [];
        for (let i = 0; i < its.length; i += cpr) {
          rows.push({
            type: 'R',
            h: rh,
            cells: its.slice(i, i + cpr),
            _rid: `r-${s}-${i}`,
          });
        }
      }
      return rows;
    });

    const prefixTops = computed(() => _prefixTops(layoutRows.value));

    const loadedHeight = computed(() => {
      const p = prefixTops.value;
      return p.length ? p[p.length - 1] : 0;
    });

    const totalHeight = computed(() => {
      const n = Math.max((props.items || []).length, props.totalEstimate || 0);
      const cpr = Math.max(1, props.cardsPerRow || 1);
      const rh = rowHeight.value || 1;
      const estCardRows = Math.ceil(n / cpr);
      const estHeaders = Math.min(estCardRows + 2, Math.ceil(estCardRows / 4) + 8);
      const est = estCardRows * rh + estHeaders * HEADER_ROW_PX;
      return Math.max(loadedHeight.value, est, viewportHeight.value || 0);
    });

    const offsetY = computed(() => {
      const p = prefixTops.value;
      const win = _findWindow(p, scrollTop.value, viewportHeight.value || 0, (viewportHeight.value || 0) * 2);
      return p[win.start] || 0;
    });

    const visibleLayoutRows = computed(() => {
      const rows = layoutRows.value;
      const p = prefixTops.value;
      if (!rows.length) return [];
      const win = _findWindow(p, scrollTop.value, viewportHeight.value || 0, (viewportHeight.value || 0) * 2);
      return rows.slice(win.start, win.end + 1).map((r, j) => ({ ...r, _vidx: win.start + j }));
    });

    function maybeLoadMore() {
      if (!props.hasMore || props.loadingMore || props.loading) return;
      if (!scroller.value) return;
      const lh = loadedHeight.value;
      if (lh <= 0) return;
      const viewBottom = scrollTop.value + viewportHeight.value;
      if (viewBottom + 200 >= lh) emit('load-more');
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
      if (sentinel.value && scroller.value && typeof IntersectionObserver !== 'undefined') {
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
      () => { nextTick(() => maybeLoadMore()); },
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
      visibleLayoutRows,
      onScroll, onOpen, onFav, onCtx, onToggleBulk,
      isCardSelectedInBulk,
    };
  },
  template: `
    <div class="lvl lv-scroller" ref="scroller" @scroll="onScroll">
      <div class="lvl-spacer" :style="{ height: totalHeight + 'px' }">
        <div class="lvl-window" :style="{ transform: 'translateY(' + offsetY + 'px)' }">
          <div class="lvl-win-slot"
               v-for="row in visibleLayoutRows"
               :key="row._rid + '-' + row._vidx">
            <div v-if="row.type==='H'" class="lvl-sec-head">{{ row.label }}</div>
            <div v-else
                 class="lvl-card-row"
                 :style="{
                   height: row.h + 'px',
                   gridTemplateColumns: 'repeat(' + cardsPerRow + ', 1fr)',
                 }">
              <ThumbCard v-for="it in row.cells"
                         :key="it.id"
                         :item="it"
                         :bulk-mode="bulkMode"
                         :bulk-selected="isCardSelectedInBulk(it.id)"
                         @open="onOpen"
                         @toggle-favorite="onFav"
                         @context="onCtx"
                         @toggle-bulk="onToggleBulk" />
            </div>
          </div>
        </div>
        <div ref="sentinel"
             class="lvl-sentinel"
             :style="{ top: loadedHeight + 'px' }"
             aria-hidden="true"></div>
      </div>
      <div v-if="loading && !items.length" class="lvl-hint loading">Loading…</div>
      <div v-if="loadingMore" class="lvl-hint muted">Loading more…</div>
      <div v-if="!loading && !items.length" class="lvl-hint muted">
        No images match the current filter.
      </div>
    </div>
  `,
});

export default LineVirtualGrid;
