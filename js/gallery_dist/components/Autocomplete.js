// components/Autocomplete.js — T21 debounced vocab autocomplete (FR-3b/c).
import {
  defineComponent, ref, watch, onBeforeUnmount, onMounted, nextTick,
} from 'vue';
import * as api from '../api.js';
import { vocabCacheGet, vocabCacheSet } from '../stores/vocab.js';

function currentPrefix(full) {
  const s = String(full ?? '');
  const last = s.lastIndexOf(',');
  const seg = last < 0 ? s : s.slice(last + 1);
  return seg.trim();
}

/** Replace the segment after the last comma with ``completion``. */
export function applyCompletion(full, completion) {
  const s = String(full ?? '');
  const idx = s.lastIndexOf(',');
  if (idx < 0) return String(completion).trim();
  const head = s.slice(0, idx + 1);
  return `${head} ${String(completion).trim()}`.replace(/ ,/g, ',');
}

export const Autocomplete = defineComponent({
  name: 'Autocomplete',
  props: {
    modelValue: { type: String, default: '' },
    fetchKind: { type: String, required: true }, // 'tags' | 'prompts'
    placeholder: { type: String, default: '' },
    debounceMs: { type: Number, default: 150 },
  },
  emits: ['update:modelValue', 'commit'],
  setup(props, { emit }) {
    const inputRef = ref(null);
    const listRef = ref(null);
    const dropdownStyle = ref({});
    const open = ref(false);
    const items = ref([]);
    const active = ref(-1);
    const loading = ref(false);
    let timer = null;
    let seq = 0;

    function updateDropdownPos() {
      const el = inputRef.value;
      if (!el || !open.value) return;
      const r = el.getBoundingClientRect();
      const gap = 2;
      const room = window.innerHeight - r.bottom - gap - 8;
      const maxH = Math.max(72, Math.min(220, room));
      dropdownStyle.value = {
        position: 'fixed',
        top: `${r.bottom + gap}px`,
        left: `${r.left}px`,
        width: `${r.width}px`,
        maxHeight: `${maxH}px`,
        zIndex: '10050',
      };
    }

    function scrollActiveIntoView() {
      const ul = listRef.value;
      if (!ul || active.value < 0) return;
      const lis = ul.querySelectorAll('li[role="option"]');
      const li = lis[active.value];
      if (!li) return;
      // Manual clamp: ``scrollIntoView({behavior:'smooth'})`` stacks poorly
      // when the arrow key is held — list scroll would not follow the highlight.
      const liTop = li.offsetTop;
      const liH = li.offsetHeight;
      const viewTop = ul.scrollTop;
      const viewH = ul.clientHeight;
      if (liTop < viewTop) ul.scrollTop = liTop;
      else if (liTop + liH > viewTop + viewH) ul.scrollTop = liTop + liH - viewH;
    }

    function hoverRow(i) {
      active.value = i;
    }

    function onWinReposition() {
      if (open.value) updateDropdownPos();
    }

    function clearTimer() {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    }

    async function runFetch() {
      const prefix = currentPrefix(props.modelValue);
      const cached = vocabCacheGet(props.fetchKind, prefix);
      if (cached) {
        items.value = cached;
        active.value = items.value.length ? 0 : -1;
        return;
      }
      const my = ++seq;
      loading.value = true;
      try {
        const path = props.fetchKind === 'tags' ? '/vocab/tags' : '/vocab/prompts';
        const rows = await api.get(path, { query: { prefix, limit: 20 } });
        if (my !== seq) return;
        const list = Array.isArray(rows) ? rows : [];
        items.value = list;
        vocabCacheSet(props.fetchKind, prefix, list);
        active.value = list.length ? 0 : -1;
      } catch {
        if (my !== seq) return;
        items.value = [];
        active.value = -1;
      } finally {
        if (my === seq) loading.value = false;
      }
    }

    function scheduleFetch() {
      clearTimer();
      timer = setTimeout(() => {
        timer = null;
        runFetch();
      }, props.debounceMs);
    }

    watch(
      () => props.modelValue,
      () => {
        open.value = true;
        scheduleFetch();
        nextTick(() => {
          updateDropdownPos();
        });
      },
    );

    watch(
      () => [open.value, items.value.length, loading.value],
      () => {
        if (open.value && (items.value.length || loading.value)) {
          nextTick(() => {
            updateDropdownPos();
          });
        }
      },
    );

    watch(active, () => {
      nextTick(scrollActiveIntoView);
    });

    onMounted(() => {
      window.addEventListener('scroll', onWinReposition, true);
      window.addEventListener('resize', onWinReposition);
    });

    onBeforeUnmount(() => {
      window.removeEventListener('scroll', onWinReposition, true);
      window.removeEventListener('resize', onWinReposition);
      clearTimer();
      seq += 1;
    });

    function onInput(e) {
      emit('update:modelValue', e.target.value);
    }

    function onFocus() {
      open.value = true;
      scheduleFetch();
      nextTick(() => updateDropdownPos());
    }

    function onBlur() {
      clearTimer();
      setTimeout(() => {
        open.value = false;
        active.value = -1;
        emit('commit');
      }, 120);
    }

    function choose(row) {
      if (!row || !row.name) return;
      const next = applyCompletion(props.modelValue, row.name);
      emit('update:modelValue', next);
      open.value = false;
      items.value = [];
      active.value = -1;
      emit('commit');
    }

    function onKeydown(e) {
      if (!open.value || !items.value.length) {
        if (e.key === 'Enter') emit('commit');
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        active.value = (active.value + 1) % items.value.length;
        nextTick(() => scrollActiveIntoView());
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        active.value = (active.value - 1 + items.value.length) % items.value.length;
        nextTick(() => scrollActiveIntoView());
      } else if (e.key === 'Enter' || e.key === 'Tab') {
        if (active.value >= 0 && active.value < items.value.length) {
          e.preventDefault();
          choose(items.value[active.value]);
        }
      } else if (e.key === 'Escape') {
        open.value = false;
      }
    }

    return {
      inputRef,
      listRef,
      dropdownStyle,
      open,
      items,
      active,
      loading,
      onInput,
      onFocus,
      onBlur,
      onKeydown,
      choose,
      hoverRow,
    };
  },
  template: `
    <div class="ac-wrap" @keydown="onKeydown">
      <input ref="inputRef"
             type="text"
             class="ac-input"
             :value="modelValue"
             :placeholder="placeholder"
             autocomplete="off"
             @input="onInput"
             @focus="onFocus"
             @blur="onBlur" />
      <Teleport to="body">
        <ul v-show="open && (items.length || loading)"
            ref="listRef"
            class="ac-list ac-list--floating"
            :style="dropdownStyle"
            role="listbox"
            aria-label="Suggestions">
          <li v-if="loading" class="ac-item ac-muted">Loading…</li>
          <li v-for="(row, i) in items"
              :key="row.name + ':' + row.usage_count"
              :class="['ac-item', { 'ac-active': i === active }]"
              role="option"
              :aria-selected="i === active"
              @mouseenter="hoverRow(i)"
              @mousedown.prevent="choose(row)">
            <span class="ac-line">
              <span class="ac-name">{{ row.name }}</span><span class="ac-usage"> ({{ row.usage_count }})</span>
            </span>
          </li>
        </ul>
      </Teleport>
    </div>
  `,
});
