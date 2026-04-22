// components/ModelFilterPick.js — T21 model picker (name vs usage styling; not <select>).
import {
  defineComponent, ref, computed, watch, onMounted, onBeforeUnmount, nextTick,
} from 'vue';

export const ModelFilterPick = defineComponent({
  name: 'ModelFilterPick',
  props: {
    modelValue: { type: String, default: '' },
    options: { type: Array, default: () => [] },
    disabled: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    const triggerRef = ref(null);
    const listRef = ref(null);
    const open = ref(false);
    const dropdownStyle = ref({});
    /** 0 = "all", 1..n = ``options[i - 1]``. */
    const active = ref(0);

    const rows = computed(() => {
      const arr = Array.isArray(props.options) ? props.options : [];
      return arr.filter((r) => r && r.model != null);
    });

    function selectionIndex() {
      const mv = String(props.modelValue || '');
      if (!mv) return 0;
      const list = rows.value;
      for (let i = 0; i < list.length; i += 1) {
        if (String(list[i].model) === mv) return i + 1;
      }
      return 0;
    }

    const display = computed(() => {
      const mv = String(props.modelValue || '');
      if (!mv) {
        return { mode: 'all', name: 'all', usage: null };
      }
      const list = rows.value;
      for (let i = 0; i < list.length; i += 1) {
        if (String(list[i].model) === mv) {
          const name = list[i].label != null ? String(list[i].label) : String(list[i].model);
          const usage = Number(list[i].usage_count);
          return {
            mode: 'pick',
            name,
            usage: Number.isFinite(usage) ? usage : 0,
          };
        }
      }
      return { mode: 'unknown', name: mv, usage: null };
    });

    function updateDropdownPos() {
      const el = triggerRef.value;
      if (!el || !open.value) return;
      const r = el.getBoundingClientRect();
      const gap = 2;
      const room = window.innerHeight - r.bottom - gap - 8;
      const maxH = Math.max(120, Math.min(280, room));
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
      if (!ul) return;
      const lis = ul.querySelectorAll('li[role="option"]');
      const li = lis[active.value];
      if (!li) return;
      const liTop = li.offsetTop;
      const liH = li.offsetHeight;
      const viewTop = ul.scrollTop;
      const viewH = ul.clientHeight;
      if (liTop < viewTop) ul.scrollTop = liTop;
      else if (liTop + liH > viewTop + viewH) ul.scrollTop = liTop + liH - viewH;
    }

    function onWinReposition() {
      if (open.value) updateDropdownPos();
    }

    function close() {
      open.value = false;
    }

    function onDocPointerDown(ev) {
      if (!open.value) return;
      const t = ev.target;
      const tr = triggerRef.value;
      const ul = listRef.value;
      if (tr && tr.contains(t)) return;
      if (ul && ul.contains(t)) return;
      close();
    }

    function toggleOpen() {
      if (props.disabled) return;
      open.value = !open.value;
      if (open.value) {
        active.value = selectionIndex();
        nextTick(() => {
          updateDropdownPos();
          scrollActiveIntoView();
        });
      }
    }

    function chooseIndex(idx) {
      if (props.disabled) return;
      if (idx === 0) {
        emit('update:modelValue', '');
      } else {
        const row = rows.value[idx - 1];
        if (!row) return;
        emit('update:modelValue', String(row.model));
      }
      close();
    }

    function onTriggerKeydown(e) {
      if (props.disabled) return;
      const n = rows.value.length;
      const maxIdx = n;

      if (!open.value) {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          open.value = true;
          active.value = selectionIndex();
          nextTick(() => {
            updateDropdownPos();
            scrollActiveIntoView();
          });
        }
        return;
      }

      if (e.key === 'Escape') {
        e.preventDefault();
        close();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        active.value = Math.min(active.value + 1, maxIdx);
        nextTick(scrollActiveIntoView);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        active.value = Math.max(active.value - 1, 0);
        nextTick(scrollActiveIntoView);
        return;
      }
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        chooseIndex(active.value);
      }
    }

    function hoverRow(idx) {
      active.value = idx;
    }

    watch(
      () => [open.value, rows.value.length],
      () => {
        if (open.value) {
          nextTick(() => updateDropdownPos());
        }
      },
    );

    onMounted(() => {
      document.addEventListener('mousedown', onDocPointerDown, true);
      window.addEventListener('scroll', onWinReposition, true);
      window.addEventListener('resize', onWinReposition);
    });

    onBeforeUnmount(() => {
      document.removeEventListener('mousedown', onDocPointerDown, true);
      window.removeEventListener('scroll', onWinReposition, true);
      window.removeEventListener('resize', onWinReposition);
    });

    return {
      triggerRef,
      listRef,
      open,
      active,
      rows,
      display,
      dropdownStyle,
      toggleOpen,
      chooseIndex,
      onTriggerKeydown,
      hoverRow,
      scrollActiveIntoView,
    };
  },
  template: `
    <div class="mv-model-pick">
      <button
        type="button"
        ref="triggerRef"
        class="mv-model-trigger"
        :disabled="disabled"
        :aria-expanded="open ? 'true' : 'false'"
        aria-haspopup="listbox"
        @click="toggleOpen"
        @keydown="onTriggerKeydown">
        <template v-if="display.mode === 'all'">
          <span class="mv-model-trigger-all">all</span>
        </template>
        <template v-else-if="display.mode === 'pick'">
          <span class="mv-model-trigger-line">
            <span class="mv-model-name">{{ display.name }}</span>
            <span class="mv-model-usage">{{ display.usage }}</span>
          </span>
        </template>
        <template v-else>
          <span class="mv-model-trigger-line mv-model-trigger-unknown">
            <span class="mv-model-name">{{ display.name }}</span>
          </span>
        </template>
      </button>
      <Teleport to="body">
        <ul
          v-show="open"
          ref="listRef"
          class="mv-model-list mv-model-list--floating"
          :style="dropdownStyle"
          role="listbox"
          aria-label="Model filter">
          <li
            role="option"
            :class="['mv-model-item', { 'mv-model-item--active': active === 0 }]"
            :aria-selected="active === 0"
            @mouseenter="hoverRow(0)"
            @mousedown.prevent="chooseIndex(0)">
            <span class="mv-model-row">
              <span class="mv-model-name mv-model-name--all">all</span>
            </span>
          </li>
          <li
            v-for="(row, i) in rows"
            :key="row.model"
            role="option"
            :class="['mv-model-item', { 'mv-model-item--active': active === i + 1 }]"
            :aria-selected="active === i + 1"
            @mouseenter="hoverRow(i + 1)"
            @mousedown.prevent="chooseIndex(i + 1)">
            <span class="mv-model-row">
              <span class="mv-model-name">{{ row.label != null ? row.label : row.model }}</span>
              <span class="mv-model-usage">{{ row.usage_count }}</span>
            </span>
          </li>
        </ul>
      </Teleport>
    </div>
  `,
});
