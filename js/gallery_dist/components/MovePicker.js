// components/MovePicker.js — T24 two-phase bulk move UI (preflight + execute).
import {
  defineComponent, ref, reactive, computed, watch, onMounted, onBeforeUnmount,
} from 'vue';
import * as api from '../api.js';
import { buildWireSelection } from '../stores/selection.js';

function fmtBytes(n) {
  const x = Number(n) || 0;
  if (x < 1024) return `${x} B`;
  if (x < 1024 * 1024) return `${(x / 1024).toFixed(1)} KiB`;
  if (x < 1024 * 1024 * 1024) return `${(x / (1024 * 1024)).toFixed(1)} MiB`;
  return `${(x / (1024 * 1024 * 1024)).toFixed(2)} GiB`;
}

function flattenFolders(nodes, depth, out) {
  for (const n of nodes || []) {
    if (!n || typeof n.id !== 'number') continue;
    out.push({
      id: n.id,
      depth,
      label: n.display_name || n.path || `folder-${n.id}`,
    });
    if (Array.isArray(n.children) && n.children.length) {
      flattenFolders(n.children, depth + 1, out);
    }
  }
  return out;
}

export const MovePicker = defineComponent({
  name: 'MovePicker',
  props: {
    forcedSelection: { type: Object, default: null },
    /** When set (e.g. bulk bar), shown as “Moving N image(s)”. */
    selectionCountHint: { type: Number, default: null },
  },
  emits: ['close', 'done'],
  setup(props, { emit }) {
    const foldersFlat = ref([]);
    const foldersLoading = ref(true);
    const targetId = ref('');
    const plan = ref(null);
    const planId = ref('');
    const overrides = reactive({});
    const busy = ref(false);
    const err = ref('');
    const moveBytes = ref(0);
    let targetDebounce = null;

    async function loadFolders() {
      foldersLoading.value = true;
      try {
        const resp = await api.get('/folders', { query: { include_counts: 'false' } });
        const arr = Array.isArray(resp) ? resp : [];
        foldersFlat.value = flattenFolders(arr, 0, []);
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

    function selectionPayload() {
      if (props.forcedSelection && typeof props.forcedSelection === 'object') {
        return props.forcedSelection;
      }
      return buildWireSelection();
    }

    function resetPlan() {
      plan.value = null;
      planId.value = '';
      for (const k of Object.keys(overrides)) {
        delete overrides[k];
      }
    }

    watch(
      () => props.forcedSelection,
      () => {
        resetPlan();
      },
    );

    watch(targetId, () => {
      if (targetDebounce) clearTimeout(targetDebounce);
      targetDebounce = setTimeout(() => {
        targetDebounce = null;
        const tid = Number(targetId.value);
        if (Number.isFinite(tid) && tid >= 1) {
          void onPreflight();
        } else {
          resetPlan();
        }
      }, 380);
    });

    function padLabel(n) {
      return '\u00A0'.repeat(n.depth * 2) + n.label;
    }

    async function onPreflight() {
      err.value = '';
      resetPlan();
      const sel = selectionPayload();
      if (!sel) {
        err.value = 'No images selected.';
        return;
      }
      const tid = Number(targetId.value);
      if (!Number.isFinite(tid) || tid < 1) {
        err.value = 'Pick a target folder.';
        return;
      }
      busy.value = true;
      try {
        const out = await api.post('/bulk/move/preflight', {
          selection: sel,
          target_folder_id: tid,
        });
        plan.value = Array.isArray(out.mappings) ? out.mappings : [];
        planId.value = out.plan_id || '';
        moveBytes.value = typeof out.total_bytes === 'number' ? out.total_bytes : 0;
        for (const row of plan.value) {
          if (row && row.conflict === 'renamed' && row.dst) {
            const base = String(row.dst).split(/[/\\]/).pop() || '';
            overrides[String(row.id)] = base;
          }
        }
      } catch (e) {
        err.value = (e && e.message) ? String(e.message) : String(e);
      } finally {
        busy.value = false;
      }
    }

    async function onExecute() {
      err.value = '';
      busy.value = true;
      try {
        const body = { plan_id: planId.value };
        const ro = {};
        for (const row of plan.value || []) {
          const id = String(row.id);
          if (Object.prototype.hasOwnProperty.call(overrides, id)) {
            const v = overrides[id];
            if (typeof v === 'string' && v.trim()) {
              ro[id] = v.trim();
            }
          }
        }
        if (Object.keys(ro).length) {
          body.rename_overrides = ro;
        }
        await api.post('/bulk/move/execute', body);
        emit('done');
        emit('close');
      } catch (e) {
        err.value = (e && e.message) ? String(e.message) : String(e);
      } finally {
        busy.value = false;
      }
    }

    function onCancel() {
      emit('close');
    }

    async function onRunClick() {
      err.value = '';
      if (busy.value) {
        err.value = 'Preview still loading — wait a moment.';
        return;
      }
      const tid = Number(targetId.value);
      if (!Number.isFinite(tid) || tid < 1) {
        err.value = 'Pick a target folder.';
        return;
      }
      if (!planId.value) {
        await onPreflight();
        if (!planId.value || err.value) return;
      }
      await onExecute();
    }

    onBeforeUnmount(() => {
      if (targetDebounce) clearTimeout(targetDebounce);
    });

    return {
      foldersFlat,
      foldersLoading,
      targetId,
      plan,
      planId,
      overrides,
      busy,
      err,
      padLabel,
      onPreflight,
      onExecute,
      onRunClick,
      moveBytes,
      fmtBytes,
      onCancel,
      selectionCountHint: computed(() => props.selectionCountHint),
    };
  },
  template: `
    <div class="mp-overlay" @click.self="onCancel">
      <div class="mp-panel" role="dialog" aria-label="Move images">
        <header class="mp-head">
          <h2 class="mp-title">Move to folder</h2>
          <button type="button" class="mp-x" :disabled="busy" @click="onCancel">×</button>
        </header>
        <div class="mp-body">
          <p v-if="selectionCountHint != null && selectionCountHint >= 1" class="muted mp-hint">
            Moving <strong>{{ selectionCountHint }}</strong> image(s).
          </p>
          <p class="muted mp-hint">Choose a target folder — a preview appears automatically. Adjust renamed filenames if needed, then Run.</p>
          <label class="mp-field">
            <span>Target folder</span>
            <select v-model="targetId" :disabled="busy || foldersLoading">
              <option value="">— select —</option>
              <option v-for="n in foldersFlat" :key="n.id" :value="String(n.id)">
                {{ padLabel(n) }}
              </option>
            </select>
          </label>
          <div class="mp-actions">
            <button type="button" class="mp-btn" :disabled="busy || foldersLoading" @click="onPreflight">Refresh preview</button>
            <button type="button" class="mp-btn primary" :disabled="busy || foldersLoading || !targetId" @click="onRunClick">Run</button>
          </div>
          <div v-if="foldersLoading" class="muted">Loading folders…</div>
          <div v-if="err" class="error mp-err">{{ err }}</div>
          <div v-if="plan && plan.length" class="mp-table-wrap">
            <table class="mp-table">
              <thead>
                <tr><th>id</th><th>destination</th><th>filename override</th></tr>
              </thead>
              <tbody>
                <tr v-for="row in plan" :key="row.id">
                  <td class="mp-td-id">{{ row.id }}</td>
                  <td class="mp-td-dst"><code>{{ row.dst }}</code></td>
                  <td>
                    <input v-if="row.conflict === 'renamed' || overrides[String(row.id)] !== undefined"
                           class="mp-in"
                           type="text"
                           v-model="overrides[String(row.id)]"
                           :placeholder="(row.dst && row.dst.split('/').pop()) || ''" />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `,
});

export default MovePicker;
