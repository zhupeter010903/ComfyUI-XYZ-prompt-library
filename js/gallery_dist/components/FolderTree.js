// components/FolderTree.js — T12 read + T33 collapse, context menu, folder HTTP.
//
// Collapsed node ids persist in localStorage (``xyz_gallery.foldertree.collapsed.v2``).
// Modals match MovePicker / gallery shell (no ``window.prompt`` / ``alert``).
import {
  defineComponent, ref, computed, watch, onMounted, onBeforeUnmount, nextTick,
} from 'vue';
import * as api from '../api.js';
import { ConfirmModal } from './ConfirmModal.js';
import { FolderInputModal } from './FolderInputModal.js';
import { FolderMovePicker } from './FolderMovePicker.js';

const LS_KEY = 'xyz_gallery.foldertree.collapsed.v2';

function _readCollapsed() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return {};
    const o = JSON.parse(raw);
    return o && typeof o === 'object' ? o : {};
  } catch {
    return {};
  }
}

function _writeCollapsed(obj) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(obj));
  } catch {
    /* ignore */
  }
}

function flattenVisible(nodes, depth, collapsedMap, out) {
  for (const n of nodes || []) {
    out.push({ ...n, depth });
    const collapsed = !!collapsedMap[n.id];
    if (!collapsed && Array.isArray(n.children) && n.children.length) {
      flattenVisible(n.children, depth + 1, collapsedMap, out);
    }
  }
  return out;
}

export const FolderTree = defineComponent({
  name: 'FolderTree',
  components: { ConfirmModal, FolderInputModal, FolderMovePicker },
  props: {
    nodes: { type: Array, required: true },
    selectedId: { type: Number, default: null },
    recursive: { type: Boolean, default: false },
  },
  emits: ['select', 'update:recursive', 'folders-changed'],
  setup(props, { emit }) {
    const collapsedMap = ref(_readCollapsed());
    const menu = ref({
      open: false,
      x: 0,
      y: 0,
      adjLeft: null,
      adjTop: null,
      folderId: null,
      label: '',
    });
    const ctxMenuEl = ref(null);

    const nameModal = ref({
      open: false,
      mode: '',
      folderId: null,
      title: '',
      hint: '',
      label: '',
      initial: '',
      busy: false,
      err: '',
    });

    const moveOpen = ref(false);
    const moveSourceId = ref(null);
    const moveSourceLabel = ref('');

    const deleteOpen = ref(false);
    const deleteFolderId = ref(null);
    const deleteLabel = ref('');
    const deleteBusy = ref(false);
    const deletePreview = ref(null);
    const deletePreviewLoading = ref(false);

    const toast = ref({ text: '', kind: 'ok' });
    let toastTimer = null;

    function showToast(text, kind = 'ok') {
      if (toastTimer) clearTimeout(toastTimer);
      toast.value = { text: String(text || ''), kind };
      toastTimer = setTimeout(() => {
        toast.value = { text: '', kind: 'ok' };
        toastTimer = null;
      }, 4200);
    }

    watch(collapsedMap, (v) => {
      _writeCollapsed(v || {});
    }, { deep: true });

    const flat = computed(() => flattenVisible(props.nodes, 0, collapsedMap.value, []));

    function positionCtxMenu() {
      const el = ctxMenuEl.value;
      const m = menu.value;
      if (!el || !m.open) return;
      const r = el.getBoundingClientRect();
      let left = m.x;
      let top = m.y;
      const pad = 8;
      if (left + r.width > window.innerWidth - pad) {
        left = window.innerWidth - r.width - pad;
      }
      if (top + r.height > window.innerHeight - pad) {
        top = window.innerHeight - r.height - pad;
      }
      if (left < pad) left = pad;
      if (top < pad) top = pad;
      menu.value = { ...m, adjLeft: left, adjTop: top };
    }

    function onSelect(id) {
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

    function hasChildren(n) {
      return Array.isArray(n.children) && n.children.length > 0;
    }

    function onToggleCollapse(id, ev) {
      if (ev) ev.preventDefault();
      if (ev) ev.stopPropagation();
      const m = { ...collapsedMap.value };
      if (m[id]) delete m[id];
      else m[id] = true;
      collapsedMap.value = m;
    }

    function closeMenu() {
      menu.value = {
        open: false, x: 0, y: 0, adjLeft: null, adjTop: null, folderId: null, label: '',
      };
    }

    function onWinResize() {
      if (menu.value.open) {
        nextTick(() => positionCtxMenu());
      }
    }

    function onDocClick() {
      closeMenu();
    }
    onMounted(() => {
      window.addEventListener('click', onDocClick);
      window.addEventListener('resize', onWinResize);
    });
    onBeforeUnmount(() => {
      window.removeEventListener('click', onDocClick);
      window.removeEventListener('resize', onWinResize);
      if (toastTimer) clearTimeout(toastTimer);
    });

    function onCtxMenu(n, ev) {
      ev.preventDefault();
      menu.value = {
        open: true,
        x: ev.clientX,
        y: ev.clientY,
        adjLeft: null,
        adjTop: null,
        folderId: n.id,
        label: labelOf(n),
      };
      nextTick(() => {
        positionCtxMenu();
      });
    }

    async function notify() {
      emit('folders-changed');
    }

    function closeNameModal() {
      nameModal.value = {
        open: false, mode: '', folderId: null, title: '', hint: '', label: '',
        initial: '', busy: false, err: '',
      };
    }

    function ctxMkdir() {
      const id = menu.value.folderId;
      closeMenu();
      if (typeof id !== 'number') return;
      nameModal.value = {
        open: true,
        mode: 'mkdir',
        folderId: id,
        title: 'New subfolder',
        hint: 'Enter a name (no slashes). The folder is created under the folder you right-clicked.',
        label: 'Folder name',
        initial: '',
        busy: false,
        err: '',
      };
    }

    async function onNameConfirm(val) {
      const st = nameModal.value;
      if (!st.open || typeof st.folderId !== 'number') return;
      if (!val) {
        nameModal.value = { ...st, err: 'Name is required.' };
        return;
      }
      nameModal.value = { ...st, busy: true, err: '' };
      try {
        if (st.mode === 'mkdir') {
          await api.post(`/folders/${st.folderId}/mkdir`, { name: val });
        } else if (st.mode === 'rename') {
          await api.patch(`/folders/${st.folderId}`, { name: val });
        }
        closeNameModal();
        await notify();
      } catch (e) {
        nameModal.value = {
          ...nameModal.value,
          busy: false,
          err: (e && e.message) ? String(e.message) : String(e),
        };
      }
    }

    function ctxRename() {
      const id = menu.value.folderId;
      const lab = menu.value.label;
      closeMenu();
      if (typeof id !== 'number') return;
      nameModal.value = {
        open: true,
        mode: 'rename',
        folderId: id,
        title: 'Rename folder',
        hint: 'Changes the last path segment on disk (same as renaming files elsewhere).',
        label: 'New name',
        initial: lab,
        busy: false,
        err: '',
      };
    }

    function ctxMove() {
      const id = menu.value.folderId;
      const lab = menu.value.label;
      closeMenu();
      if (typeof id !== 'number') return;
      moveSourceId.value = id;
      moveSourceLabel.value = lab;
      moveOpen.value = true;
    }

    function closeMovePicker() {
      moveOpen.value = false;
      moveSourceId.value = null;
      moveSourceLabel.value = '';
    }

    async function onMoveDone() {
      await notify();
    }

    async function ctxDelete() {
      const id = menu.value.folderId;
      const lab = menu.value.label;
      closeMenu();
      if (typeof id !== 'number') return;
      deleteFolderId.value = id;
      deleteLabel.value = lab;
      deleteOpen.value = true;
      deletePreview.value = null;
      deletePreviewLoading.value = true;
      try {
        deletePreview.value = await api.get(`/folders/${id}/delete-preview`);
      } catch (e) {
        deletePreview.value = {
          error: (e && e.message) ? String(e.message) : String(e),
        };
      } finally {
        deletePreviewLoading.value = false;
      }
    }

    function closeDeleteModal() {
      if (deleteBusy.value) return;
      deleteOpen.value = false;
      deleteFolderId.value = null;
      deleteLabel.value = '';
      deleteBusy.value = false;
      deletePreview.value = null;
      deletePreviewLoading.value = false;
    }

    async function onDeleteConfirm() {
      const id = deleteFolderId.value;
      const p = deletePreview.value;
      if (typeof id !== 'number') return;
      if (deletePreviewLoading.value) return;
      if (!p || p.error) return;
      deleteBusy.value = true;
      try {
        const purge = p && !p.error && !p.can_empty_delete;
        await api.del(`/folders/${id}`, { query: purge ? { purge_files: true } : undefined });
        closeDeleteModal();
        await notify();
      } catch (e) {
        showToast((e && e.message) ? String(e.message) : String(e), 'err');
      } finally {
        deleteBusy.value = false;
      }
    }

    const deleteLines = computed(() => {
      if (deletePreviewLoading.value) {
        return ['Checking folder contents…'];
      }
      const p = deletePreview.value;
      if (!p) return ['…'];
      if (p.error) {
        return ['Could not load delete preview.', String(p.error)];
      }
      const n = typeof p.indexed_images === 'number' ? p.indexed_images : 0;
      const d = typeof p.disk_entry_count === 'number' ? p.disk_entry_count : 0;
      if (p.can_empty_delete) {
        return [
          `Remove empty folder “${deleteLabel.value}”?`,
          'The directory must be empty on disk and have no indexed images.',
        ];
      }
      return [
        `Delete folder “${deleteLabel.value}” and EVERYTHING inside?`,
        `Indexed images: ${n}. On-disk entries in this folder: ${d >= 0 ? d : 'unknown'}.`,
        'This deletes files on disk recursively and removes them from the gallery index. This cannot be undone.',
      ];
    });

    const deleteConfirmLabel = computed(() => {
      const p = deletePreview.value;
      if (p && !p.error && p.can_empty_delete) return 'Delete';
      return 'Delete all';
    });

    const deleteConfirmDisabled = computed(() => {
      if (deletePreviewLoading.value) return true;
      const p = deletePreview.value;
      return !!(p && p.error);
    });

    async function ctxRescan() {
      const id = menu.value.folderId;
      closeMenu();
      if (typeof id !== 'number') return;
      try {
        await api.post(`/folders/${id}/rescan`, {});
        showToast('Rescan scheduled for this branch.', 'ok');
      } catch (e) {
        showToast((e && e.message) ? String(e.message) : String(e), 'err');
      }
    }

    async function ctxOpen() {
      const id = menu.value.folderId;
      closeMenu();
      if (typeof id !== 'number') return;
      try {
        await api.post(`/folders/${id}/open`, {});
        showToast('Opened in OS file manager.', 'ok');
      } catch (e) {
        showToast((e && e.message) ? String(e.message) : String(e), 'err');
      }
    }

    const ctxStyle = computed(() => {
      const m = menu.value;
      if (!m.open) return {};
      const left = m.adjLeft != null ? m.adjLeft : m.x;
      const top = m.adjTop != null ? m.adjTop : m.y;
      return {
        position: 'fixed',
        left: `${left}px`,
        top: `${top}px`,
        zIndex: 9999,
      };
    });

    return {
      flat,
      collapsedMap,
      menu,
      ctxMenuEl,
      ctxStyle,
      onSelect,
      toggleRecursive,
      labelOf,
      countSuffix,
      hasChildren,
      onToggleCollapse,
      onCtxMenu,
      closeMenu,
      ctxMkdir,
      ctxRename,
      ctxMove,
      ctxDelete,
      ctxRescan,
      ctxOpen,
      nameModal,
      closeNameModal,
      onNameConfirm,
      moveOpen,
      moveSourceId,
      moveSourceLabel,
      closeMovePicker,
      onMoveDone,
      deleteOpen,
      deleteBusy,
      deletePreviewLoading,
      deleteLines,
      deleteConfirmLabel,
      deleteConfirmDisabled,
      closeDeleteModal,
      onDeleteConfirm,
      toast,
    };
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
      <ul class="ft-list" @click="closeMenu">
        <li>
          <a href="#"
             class="ft-node ft-all"
             :class="{ active: selectedId === null }"
             @click.prevent="onSelect(null)">
            All folders
          </a>
        </li>
        <li v-for="n in flat" :key="n.id" class="ft-row">
          <span class="ft-row-inner"
                :style="{ paddingLeft: (4 + n.depth * 14) + 'px' }">
            <button v-if="hasChildren(n)"
                    type="button"
                    class="ft-chev"
                    :aria-expanded="collapsedMap[n.id] ? 'false' : 'true'"
                    :title="collapsedMap[n.id] ? 'Expand' : 'Collapse'"
                    @click="onToggleCollapse(n.id, $event)">
              {{ collapsedMap[n.id] ? '▶' : '▼' }}
            </button>
            <span v-else class="ft-chev-spacer"></span>
            <a href="#"
               class="ft-node"
               :class="{ active: selectedId === n.id }"
               :title="n.path"
               @click.prevent="onSelect(n.id)"
               @contextmenu="onCtxMenu(n, $event)">
              <span class="ft-kind" v-if="n.kind">[{{ n.kind }}]</span>
              {{ labelOf(n) }}<span class="ft-count muted">{{ countSuffix(n) }}</span>
            </a>
          </span>
        </li>
      </ul>
      <teleport to="body">
        <div v-if="menu.open"
             ref="ctxMenuEl"
             class="ft-ctx"
             :style="ctxStyle"
             @click.stop>
          <button type="button" class="ft-ctx-item" @click="ctxMkdir">New subfolder…</button>
          <button type="button" class="ft-ctx-item" @click="ctxRename">Rename…</button>
          <button type="button" class="ft-ctx-item" @click="ctxMove">Move…</button>
          <button type="button" class="ft-ctx-item" @click="ctxDelete">Delete…</button>
          <button type="button" class="ft-ctx-item" @click="ctxRescan">Rescan tree</button>
          <button type="button" class="ft-ctx-item" @click="ctxOpen">Open in OS</button>
        </div>
      </teleport>
      <teleport to="body">
        <FolderInputModal
          v-if="nameModal.open"
          :key="(nameModal.folderId || '') + '-' + nameModal.mode"
          :title="nameModal.title"
          :hint="nameModal.hint"
          :label="nameModal.label"
          :initial-value="nameModal.initial"
          :busy="nameModal.busy"
          :error="nameModal.err"
          confirm-label="Save"
          @cancel="closeNameModal"
          @confirm="onNameConfirm"
        />
        <FolderMovePicker
          v-if="moveOpen && moveSourceId != null"
          :source-folder-id="moveSourceId"
          :source-label="moveSourceLabel"
          @close="closeMovePicker"
          @done="onMoveDone"
        />
        <ConfirmModal
          v-if="deleteOpen"
          title="Delete folder"
          :lines="deleteLines"
          :confirm-label="deleteConfirmLabel"
          cancel-label="Cancel"
          :danger="true"
          :busy="deleteBusy"
          :confirm-disabled="deleteConfirmDisabled"
          @cancel="closeDeleteModal"
          @confirm="onDeleteConfirm"
        />
        <div v-if="toast.text" class="ft-toast" :class="'ft-toast--' + toast.kind">
          {{ toast.text }}
        </div>
      </teleport>
    </div>
  `,
});

export default FolderTree;
