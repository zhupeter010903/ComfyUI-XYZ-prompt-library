// components/FolderTree.js — T12 scope: read-only tree of FolderNode,
// single-select with re-click-to-deselect, top-level "Recursive" toggle.
//
// Tree is rendered as a flat, indented list (no expand/collapse yet —
// deliberately minimal until FR-7 "Manage custom folders" modal lands,
// which is a later task). This keeps the DOM small enough on typical
// trees (tens of nodes) and avoids recursive-component plumbing.
//
// Counts (image_count_self / image_count_recursive) are only shown
// when present on the node — the parent decides via
// GET /folders?include_counts=true.
import { defineComponent, computed } from 'vue';

function flatten(nodes, depth, out) {
  for (const n of nodes || []) {
    out.push({ ...n, depth });
    if (Array.isArray(n.children) && n.children.length) {
      flatten(n.children, depth + 1, out);
    }
  }
  return out;
}

export const FolderTree = defineComponent({
  name: 'FolderTree',
  props: {
    nodes: { type: Array, required: true },
    selectedId: { type: Number, default: null },
    recursive: { type: Boolean, default: false },
  },
  emits: ['select', 'update:recursive'],
  setup(props, { emit }) {
    const flat = computed(() => flatten(props.nodes, 0, []));

    function onSelect(id) {
      // Re-click on the already-selected node deselects (test #1:
      // "选择 / 取消选择目录 → 网格内容改变").
      emit('select', props.selectedId === id ? null : id);
    }
    function toggleRecursive() {
      emit('update:recursive', !props.recursive);
    }
    function labelOf(n) {
      return n.display_name || n.path || `folder-${n.id}`;
    }
    function countSuffix(n) {
      const self = n.image_count_self;
      const rec = n.image_count_recursive;
      if (self === undefined && rec === undefined) return '';
      if (rec !== undefined && rec !== self) return ` (${self ?? 0}/${rec})`;
      return ` (${self ?? 0})`;
    }

    return { flat, onSelect, toggleRecursive, labelOf, countSuffix };
  },
  template: `
    <div class="ft">
      <div class="ft-toolbar">
        <button type="button"
                class="ft-recursive"
                :aria-pressed="recursive ? 'true' : 'false'"
                @click="toggleRecursive">
          Recursive: {{ recursive ? 'on' : 'off' }}
        </button>
      </div>
      <ul class="ft-list">
        <li>
          <a href="#"
             class="ft-node ft-all"
             :class="{ active: selectedId === null }"
             @click.prevent="onSelect(null)">
            All folders
          </a>
        </li>
        <li v-for="n in flat" :key="n.id" class="ft-row">
          <a href="#"
             class="ft-node"
             :class="{ active: selectedId === n.id }"
             :style="{ paddingLeft: (10 + n.depth * 14) + 'px' }"
             :title="n.path"
             @click.prevent="onSelect(n.id)">
            <span class="ft-kind" v-if="n.kind">[{{ n.kind }}]</span>
            {{ labelOf(n) }}<span class="ft-count muted">{{ countSuffix(n) }}</span>
          </a>
        </li>
      </ul>
    </div>
  `,
});

export default FolderTree;
