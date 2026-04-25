// components/BulkBar.js — T23 bulk actions + WS progress.
import { defineComponent, ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { Autocomplete } from './Autocomplete.js';
import { MovePicker } from './MovePicker.js';
import { ConfirmModal } from './ConfirmModal.js';
import * as api from '../api.js';
import { executeBulkImageDownloads } from '../stores/downloadHelper.js';
import { vocabCacheClear } from '../stores/vocab.js';
import { subscribeGalleryEvent } from '../stores/connection.js';
import {
  selectionState, buildWireSelection, resetSelection, setSelectAllInView,
} from '../stores/selection.js';
import { vocabAutocompleteMatch } from '../stores/gallerySettings.js';

function fmtBytes(n) {
  const x = Number(n) || 0;
  if (x < 1024) return `${x} B`;
  if (x < 1024 * 1024) return `${(x / 1024).toFixed(1)} KiB`;
  if (x < 1024 * 1024 * 1024) return `${(x / (1024 * 1024)).toFixed(1)} MiB`;
  return `${(x / (1024 * 1024 * 1024)).toFixed(2)} GiB`;
}

export const BulkBar = defineComponent({
  name: 'BulkBar',
  components: { Autocomplete, MovePicker, ConfirmModal },
  emits: ['moved'],
  setup(props, { emit }) {
    const tagAdd = ref('');
    const tagRem = ref('');
    const moveOpen = ref(false);
    const deleteConfirmOpen = ref(false);
    const deletePlanId = ref('');
    const deleteTotal = ref(0);
    const deleteBytes = ref(0);
    const busy = ref(false);
    const bulkDone = ref(0);
    const bulkTotal = ref(0);
    const errorText = ref('');
    /** Resolved row count for current wire ``Selection`` (explicit: local; all_except: server). */
    const selectionCount = ref(0);
    let unsub = null;
    let countTimer = null;

    async function refreshAllExceptCount() {
      const sel = buildWireSelection();
      if (!sel) {
        selectionCount.value = 0;
        return;
      }
      if (sel.mode !== 'all_except') {
        selectionCount.value = Array.isArray(sel.ids) ? sel.ids.length : 0;
        return;
      }
      try {
        const r = await api.post('/bulk/resolve_selection', { selection: sel, limit: 0 });
        selectionCount.value = typeof r.count === 'number' ? r.count : 0;
      } catch {
        selectionCount.value = 0;
      }
    }

    function scheduleSelectionCountRefresh() {
      const sel = buildWireSelection();
      if (!sel) {
        selectionCount.value = 0;
        return;
      }
      if (sel.mode === 'explicit') {
        selectionCount.value = Array.isArray(sel.ids) ? sel.ids.length : 0;
        return;
      }
      selectionCount.value = null;
      if (countTimer) clearTimeout(countTimer);
      countTimer = setTimeout(() => {
        countTimer = null;
        void refreshAllExceptCount();
      }, 200);
    }

    watch(
      selectionState,
      () => { scheduleSelectionCountRefresh(); },
      { deep: true },
    );

    function onProgress(env) {
      if (!env || !env.data) return;
      const d = env.data;
      if (d.done != null) bulkDone.value = d.done;
      if (d.total != null) bulkTotal.value = d.total;
    }

    onMounted(() => {
      scheduleSelectionCountRefresh();
      unsub = subscribeGalleryEvent((env) => {
        if (!env) return;
        if (env.type === 'bulk.progress') onProgress(env);
        if (env.type === 'bulk.completed') onProgress(env);
      });
    });
    onBeforeUnmount(() => {
      if (countTimer) {
        clearTimeout(countTimer);
        countTimer = null;
      }
      if (unsub) { unsub(); unsub = null; }
    });

    async function doFavorite(val) {
      const sel = buildWireSelection();
      if (!sel) {
        errorText.value = 'Select at least one image (or use “Select all in view”).';
        return;
      }
      errorText.value = '';
      busy.value = true;
      bulkDone.value = 0;
      bulkTotal.value = 0;
      try {
        const r = await api.post('/bulk/favorite', { selection: sel, value: !!val });
        if (r && Array.isArray(r.failed) && r.failed.length) {
          errorText.value = r.failed
            .map((f) => `#${f.id} (${f.code}): ${f.message}`)
            .join(' · ');
        }
      } catch (e) {
        errorText.value = (e && e.message) ? String(e.message) : String(e);
      } finally {
        busy.value = false;
      }
    }

    async function doTags() {
      const sel = buildWireSelection();
      if (!sel) {
        errorText.value = 'Select at least one image (or use “Select all in view”).';
        return;
      }
      const add = String(tagAdd.value || '')
        .split(',').map((s) => s.trim()).filter(Boolean);
      const remove = String(tagRem.value || '')
        .split(',').map((s) => s.trim()).filter(Boolean);
      if (!add.length && !remove.length) {
        errorText.value = 'Enter at least one tag in Add or Remove.';
        return;
      }
      errorText.value = '';
      busy.value = true;
      bulkDone.value = 0;
      bulkTotal.value = 0;
      try {
        const r = await api.post('/bulk/tags', { selection: sel, add, remove });
        vocabCacheClear();
        tagAdd.value = '';
        tagRem.value = '';
        if (r && Array.isArray(r.failed) && r.failed.length) {
          errorText.value = r.failed
            .map((f) => `#${f.id} (${f.code}): ${f.message}`)
            .join(' · ');
        }
      } catch (e) {
        errorText.value = (e && e.message) ? String(e.message) : String(e);
      } finally {
        busy.value = false;
      }
    }

    function onClear() {
      resetSelection();
      errorText.value = '';
      scheduleSelectionCountRefresh();
    }

    function openMove() {
      errorText.value = '';
      moveOpen.value = true;
    }
    function closeMove() {
      moveOpen.value = false;
    }
    function onMoved() {
      emit('moved');
    }

    function closeDeleteConfirm() {
      deleteConfirmOpen.value = false;
      deletePlanId.value = '';
      deleteTotal.value = 0;
      deleteBytes.value = 0;
    }

    async function openDeleteConfirm() {
      const sel = buildWireSelection();
      if (!sel) {
        errorText.value = 'Select at least one image (or use “Select all in view”).';
        return;
      }
      errorText.value = '';
      busy.value = true;
      try {
        const out = await api.post('/bulk/delete/preflight', { selection: sel });
        deletePlanId.value = out && out.plan_id ? String(out.plan_id) : '';
        deleteTotal.value = typeof out.total === 'number' ? out.total : 0;
        deleteBytes.value = typeof out.total_bytes === 'number' ? out.total_bytes : 0;
        if (!deletePlanId.value) {
          errorText.value = 'Preflight did not return plan_id.';
          return;
        }
        deleteConfirmOpen.value = true;
      } catch (e) {
        errorText.value = (e && e.message) ? String(e.message) : String(e);
      } finally {
        busy.value = false;
      }
    }

    const dlBusy = ref(false);
    async function doDownloadSelected() {
      const sel = buildWireSelection();
      if (!sel) {
        errorText.value = 'Select at least one image (or use “Select all in view”).';
        return;
      }
      errorText.value = '';
      dlBusy.value = true;
      try {
        const r = await api.post('/bulk/resolve_selection', { selection: sel, limit: 500 });
        const total = typeof r.count === 'number' ? r.count : 0;
        const ids = Array.isArray(r.ids) ? r.ids : [];
        if (!total || !ids.length) {
          errorText.value = 'Nothing to download.';
          return;
        }
        if (total > 500) {
          errorText.value = `Selection has ${total} images; downloading first 500 only.`;
        }
        await executeBulkImageDownloads(ids, { title: 'Bulk download' });
      } catch (e) {
        errorText.value = (e && e.message) ? String(e.message) : String(e);
      } finally {
        dlBusy.value = false;
      }
    }

    async function onDeleteConfirmed() {
      if (!deletePlanId.value) {
        closeDeleteConfirm();
        return;
      }
      errorText.value = '';
      busy.value = true;
      bulkDone.value = 0;
      bulkTotal.value = 0;
      try {
        await api.post('/bulk/delete/execute', { plan_id: deletePlanId.value });
        closeDeleteConfirm();
        resetSelection();
        emit('moved');
      } catch (e) {
        errorText.value = (e && e.message) ? String(e.message) : String(e);
      } finally {
        busy.value = false;
      }
    }

    const modeLabel = () => (selectionState.mode === 'all_except' ? 'all except exclusions' : 'hand-picked');

    function setTagAdd(v) { tagAdd.value = v; }
    function setTagRem(v) { tagRem.value = v; }

    function selectionCountLabel() {
      const n = selectionCount.value;
      if (n === null) return '…';
      return String(n);
    }

    const deleteConfirmLines = computed(() => [
      'Permanently delete '
        + String(deleteTotal.value)
        + ' file(s) (~'
        + fmtBytes(deleteBytes.value)
        + ' total)?',
      'This removes files from disk and rows from the gallery index.',
    ]);

    return {
      tagAdd, tagRem, moveOpen, busy, bulkDone, bulkTotal, errorText, selectionState,
      selectionCount, selectionCountLabel,
      doFavorite, doTags, onClear, setSelectAllInView, modeLabel, resetSelection,
      setTagAdd, setTagRem, openMove, closeMove, onMoved,
      deleteConfirmOpen, deletePlanId, deleteTotal, deleteBytes,
      openDeleteConfirm, onDeleteConfirmed, closeDeleteConfirm, fmtBytes,
      deleteConfirmLines,
      dlBusy, doDownloadSelected, vocabAutocompleteMatch,
    };
  },
  template: `
    <div class="bb" aria-label="Bulk edit">
      <div class="bb-row">
        <span class="bb-mode muted">Mode: <strong>{{ modeLabel() }}</strong></span>
        <span class="bb-count muted" aria-live="polite">Selected: <strong class="bb-count-num">{{ selectionCountLabel() }}</strong></span>
        <button type="button" class="bb-btn" :disabled="busy" @click="setSelectAllInView">Select all in view</button>
        <button type="button" class="bb-btn" :disabled="busy" @click="onClear">Clear</button>
      </div>
      <div class="bb-row">
        <button type="button" class="bb-btn" :disabled="busy" @click="doFavorite(true)">Favorite</button>
        <button type="button" class="bb-btn" :disabled="busy" @click="doFavorite(false)">Unfavorite</button>
        <Autocomplete fetch-kind="tags"
                      class="bb-ac"
                      :vocab-match-mode="vocabAutocompleteMatch"
                      placeholder="add tags (comma)"
                      :model-value="tagAdd"
                      :disabled="busy"
                      @update:model-value="setTagAdd" />
        <Autocomplete fetch-kind="tags"
                      class="bb-ac"
                      :vocab-match-mode="vocabAutocompleteMatch"
                      placeholder="remove tags (comma)"
                      :model-value="tagRem"
                      :disabled="busy"
                      @update:model-value="setTagRem" />
        <button type="button" class="bb-btn primary" :disabled="busy" @click="doTags">Apply tags</button>
        <button type="button" class="bb-btn" :disabled="busy" @click="openMove">Move to folder…</button>
        <button type="button" class="bb-btn" :disabled="busy || dlBusy" @click="doDownloadSelected">
          {{ dlBusy ? 'Downloading…' : 'Download selected' }}
        </button>
        <button type="button" class="bb-btn bb-btn-danger" :disabled="busy" @click="openDeleteConfirm">Delete selected…</button>
      </div>
      <div v-if="busy || bulkTotal &gt; 0" class="bb-prog">
        <div class="bb-prog-label">Progress: {{ bulkDone }} / {{ bulkTotal }}</div>
        <div class="bb-prog-bar" v-if="bulkTotal &gt; 0" aria-hidden="true">
          <div class="bb-prog-fill" :style="{ width: (100 * bulkDone / bulkTotal) + '%' }"></div>
        </div>
      </div>
      <div v-if="errorText" class="bb-err error">{{ errorText }}</div>
      <MovePicker v-if="moveOpen"
                  :forced-selection="null"
                  :selection-count-hint="selectionCount != null ? selectionCount : undefined"
                  @close="closeMove"
                  @done="onMoved" />
      <ConfirmModal
        v-if="deleteConfirmOpen"
        title="Delete images"
        :lines="deleteConfirmLines"
        confirm-label="Delete"
        cancel-label="Cancel"
        :danger="true"
        :busy="busy"
        @cancel="closeDeleteConfirm"
        @confirm="onDeleteConfirmed"
      />
    </div>
  `,
});

export default BulkBar;
