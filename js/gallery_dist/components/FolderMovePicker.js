// components/FolderMovePicker.js — move folder under a new parent (T33).
import { defineComponent, ref, watch, onMounted } from 'vue';
import * as api from '../api.js';

function findNode(nodes, id) {
  for (const n of nodes || []) {
    if (!n || typeof n.id !== 'number') continue;
    if (n.id === id) return n;
    const c = findNode(n.children, id);
    if (c) return c;
  }
  return null;
}

function collectDescendantIds(node, out) {
  if (!node) return;
  for (const c of node.children || []) {
    if (!c || typeof c.id !== 'number') continue;
    out.add(c.id);
    collectDescendantIds(c, out);
  }
}

function flattenFolders(nodes, depth, out, excluded) {
  for (const n of nodes || []) {
    if (!n || typeof n.id !== 'number') continue;
    if (excluded.has(n.id)) {
      continue;
    }
    out.push({
      id: n.id,
      depth,
      label: n.display_name || n.path || `folder-${n.id}`,
    });
    if (Array.isArray(n.children) && n.children.length) {
      flattenFolders(n.children, depth + 1, out, excluded);
    }
  }
  return out;
}

function padLabel(n) {
  return '\u00A0'.repeat(n.depth * 2) + n.label;
}

function folderSegmentLc(node) {
  if (!node) return '';
  if (node.display_name && String(node.display_name).trim()) {
    return String(node.display_name).trim().toLowerCase();
  }
  const p = node.path || '';
  const parts = String(p).split(/[/\\]/).filter(Boolean);
  return parts.length ? parts[parts.length - 1].toLowerCase() : '';
}

function targetHasChildNamed(tree, targetId, dirNameLc) {
  if (!dirNameLc) return false;
  const tgt = findNode(tree, targetId);
  if (!tgt || !Array.isArray(tgt.children)) return false;
  for (const c of tgt.children) {
    if (folderSegmentLc(c) === dirNameLc) return true;
  }
  return false;
}

export const FolderMovePicker = defineComponent({
  name: 'FolderMovePicker',
  props: {
    sourceFolderId: { type: Number, required: true },
    sourceLabel: { type: String, default: '' },
  },
  emits: ['close', 'done'],
  setup(props, { emit }) {
    const foldersFlat = ref([]);
    const foldersLoading = ref(true);
    const targetId = ref('');
    const busy = ref(false);
    const err = ref('');
    const treeSnap = ref([]);
    const nameConflictOpen = ref(false);
    const conflictName = ref('');

    const excludedIds = new Set();
    function rebuildExcluded() {
      excludedIds.clear();
      excludedIds.add(props.sourceFolderId);
      const src = findNode(treeSnap.value, props.sourceFolderId);
      collectDescendantIds(src, excludedIds);
    }

    async function loadFolders() {
      foldersLoading.value = true;
      err.value = '';
      try {
        const resp = await api.get('/folders', { query: { include_counts: 'false' } });
        treeSnap.value = Array.isArray(resp) ? resp : [];
        rebuildExcluded();
        const flat = [];
        flattenFolders(treeSnap.value, 0, flat, excludedIds);
        foldersFlat.value = flat;
      } catch (e) {
        err.value = (e && e.message) ? String(e.message) : String(e);
        foldersFlat.value = [];
      } finally {
        foldersLoading.value = false;
      }
    }

    onMounted(() => {
      loadFolders();
    });

    watch(
      () => props.sourceFolderId,
      () => {
        targetId.value = '';
        nameConflictOpen.value = false;
        loadFolders();
      },
    );

    function onCancel() {
      emit('close');
    }

    function closeNameConflict() {
      nameConflictOpen.value = false;
      conflictName.value = '';
    }

    function sourceDirNameLc() {
      const trimmed = (props.sourceLabel || '').trim();
      if (trimmed) return trimmed.toLowerCase();
      const node = findNode(treeSnap.value, props.sourceFolderId);
      return folderSegmentLc(node);
    }

    function sourceDirDisplayName() {
      const trimmed = (props.sourceLabel || '').trim();
      if (trimmed) return trimmed;
      const node = findNode(treeSnap.value, props.sourceFolderId);
      if (node && node.display_name) return String(node.display_name);
      const node2 = findNode(treeSnap.value, props.sourceFolderId);
      const p = (node2 && node2.path) || '';
      const parts = String(p).split(/[/\\]/).filter(Boolean);
      return parts.length ? parts[parts.length - 1] : String(props.sourceFolderId);
    }

    async function onMoveClick() {
      err.value = '';
      const tid = Number(targetId.value);
      if (!Number.isFinite(tid) || tid < 1) {
        err.value = 'Pick a target parent folder.';
        return;
      }
      if (tid === props.sourceFolderId) {
        err.value = 'Pick a different folder.';
        return;
      }
      const nmLc = sourceDirNameLc();
      if (nmLc && targetHasChildNamed(treeSnap.value, tid, nmLc)) {
        conflictName.value = sourceDirDisplayName();
        nameConflictOpen.value = true;
        return;
      }
      await doMove();
    }

    async function doMove() {
      err.value = '';
      const tid = Number(targetId.value);
      busy.value = true;
      try {
        await api.post(`/folders/${props.sourceFolderId}/move`, { parent_id: tid });
        nameConflictOpen.value = false;
        conflictName.value = '';
        emit('done');
        emit('close');
      } catch (e) {
        err.value = (e && e.message) ? String(e.message) : String(e);
      } finally {
        busy.value = false;
      }
    }

    return {
      foldersFlat,
      foldersLoading,
      targetId,
      busy,
      err,
      padLabel,
      onCancel,
      onMoveClick,
      nameConflictOpen,
      conflictName,
      closeNameConflict,
    };
  },
  template: `
    <div class="mp-overlay ft-mp-overlay" @click.self="onCancel">
      <div class="mp-panel" role="dialog" aria-label="Move folder">
        <header class="mp-head">
          <h2 class="mp-title">Move folder</h2>
          <button type="button" class="mp-x" :disabled="busy" @click="onCancel">×</button>
        </header>
        <div class="mp-body mp-body--rel">
          <p class="muted mp-hint">Choose the folder that should become the new parent, then Move.</p>
          <label class="mp-field">
            <span>Target parent folder</span>
            <select v-model="targetId" :disabled="busy || foldersLoading">
              <option value="">— select —</option>
              <option v-for="n in foldersFlat" :key="n.id" :value="String(n.id)">
                {{ padLabel(n) }}
              </option>
            </select>
          </label>
          <div class="mp-actions">
            <button type="button" class="mp-btn" :disabled="busy" @click="onCancel">Cancel</button>
            <button type="button" class="mp-btn primary" :disabled="busy || !targetId" @click="onMoveClick">Move</button>
          </div>
          <div v-if="foldersLoading" class="muted">Loading folders…</div>
          <div v-if="err" class="error mp-err">{{ err }}</div>

          <div v-if="nameConflictOpen" class="mp-inline-overlay" @click.self="closeNameConflict">
            <div class="mp-inline-card" role="alertdialog" aria-label="Folder name conflict">
              <h3 class="mp-inline-title">Same name in target</h3>
              <p class="mp-inline-text">
                The target folder already contains a subfolder named
                <strong>“{{ conflictName }}”</strong>.
              </p>
              <p class="muted mp-inline-sub">Pick another parent, or rename the folder you are moving, then try again.</p>
              <div class="mp-actions mp-inline-actions">
                <button type="button" class="mp-btn primary" @click="closeNameConflict">OK</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
});

export default FolderMovePicker;
