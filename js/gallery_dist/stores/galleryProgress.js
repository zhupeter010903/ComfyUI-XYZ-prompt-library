// T44 — ProgressModal 状态 + jobs/active（FR-Prog-1/5/6，SPEC §12.4）
// T44_BULK_MODAL_MIN_ROWS = 12：位于 TASKS 所给 8–20 中值区；与 time 阈值 400ms 成对
import { ref, nextTick } from 'vue';
import * as api from '../api.js';
import { subscribeGalleryEvent, onWebSocketOpen, EV } from './connection.js';

export const T44_BULK_MODAL_MIN_ROWS = 12;
const T44_MODAL_TIME_MS = 400; // 300–500
const T44_MODAL_AUTO_MS = 600; // 0.4–0.8s

const job = ref(null);
const visible = ref(false);
const frozen = ref(false);

const _keyStartMs = new Map();
let _delayToken = 0;
let _closeTimer = null;
/** If set, ``job.completed`` for ``index``-kind jobs await this *before* closing. */
let _indexUiSync = null;

function keyOf(d) {
  if (!d) return null;
  const s = d.job_id || d.bulk_id || d.plan_id;
  if (s != null) return String(s);
  return null;
}

function isProgress(t) {
  return t === 'bulk.progress' || t === EV.INDEX_PROGRESS || t === 'job.progress';
}
function isDone(t) {
  return t === 'bulk.completed' || t === EV.BULK_DONE || t === 'job.completed';
} // BULK_DONE === "bulk.completed"

function isIndexKind(k) {
  return k === 'index' || k === 'cold_scan' || k === 'delta' || k === 'rescan';
}

/**
 * 是否满足「大列表」或「可观测索引」的立即/确定条件。
 * FR-Prog-6：行数 或 时间+小规模由下方 schedule 处理。
 */
function canShowLargeOrIndex(d) {
  if (!d) return false;
  const t = Math.max(0, Number(d.total) || 0);
  if (d.kind && isIndexKind(d.kind) && t === 0) return true;
  if (t > 0 && t >= T44_BULK_MODAL_MIN_ROWS) return true;
  return false;
}

function canShowByTime(d, startedMs) {
  if (!d) return false;
  const t = Math.max(0, Number(d.total) || 0);
  if (d.kind && isIndexKind(d.kind) && t === 0) return true;
  if (t > 0 && t < T44_BULK_MODAL_MIN_ROWS) {
    return (Date.now() - startedMs) >= T44_MODAL_TIME_MS;
  }
  return t >= T44_BULK_MODAL_MIN_ROWS;
}

function scheduleForJob(d) {
  const k = keyOf(d);
  if (k) {
    if (!_keyStartMs.has(k)) {
      _keyStartMs.set(k, Date.now());
    }
  }
  const started = k ? _keyStartMs.get(k) : Date.now();
  if (canShowLargeOrIndex(d)) {
    if (!visible.value) {
      nextTick(() => {
        visible.value = true;
        frozen.value = true;
      });
    }
    return;
  }
  // 小规模 + 等时间：400ms 后若同一 job 仍在跑，则出模态
  const token = ++_delayToken;
  setTimeout(() => {
    if (token !== _delayToken) return;
    if (k && keyOf(job.value) === k) {
      if (canShowByTime(job.value, started)) {
        if (!visible.value) {
          visible.value = true;
          frozen.value = true;
        }
      }
    }
  }, T44_MODAL_TIME_MS);
}

function merge(d) {
  if (!d) {
    return;
  }
  const o = { ...d };
  if (!o.job_id) {
    o.job_id = o.bulk_id || o.plan_id || o.job_id;
  }
  job.value = o;
}

function _finishModalState(withResume) {
  visible.value = false;
  frozen.value = false;
  job.value = null;
  _keyStartMs.clear();
  _delayToken++;
  _closeTimer = null;
  if (!withResume) {
    return;
  }
  if (typeof window !== 'undefined' && window.dispatchEvent) {
    try {
      window.dispatchEvent(new Event('xyz-gallery-resume-after-modal'));
    } catch {
      /* ignore */
    }
  }
}

function handleEvent(env) {
  if (!env) return;
  const t = env.type;
  const d = (env && env.data) || {};
  if (isProgress(t)) {
    const k = keyOf(d);
    const cur = job.value;
    if (
      visible.value
      && cur
      && k
      && k !== keyOf(cur)
      && String(d.kind || '') === 'index'
      && String(d.phase || '') === 'delta'
      && (Number(d.total) || 0) === 0
    ) {
      // Full-tree ``delta`` uses done=files walked; do not replace another
      // in-flight index job (e.g. file-watcher) on the same modal.
      if (String(cur.phase || '') !== 'delta') {
        return;
      }
    }
    merge(d);
    if (!visible.value) {
      scheduleForJob(d);
    }
  } else if (isDone(t)) {
    if (_closeTimer) {
      clearTimeout(_closeTimer);
      _closeTimer = null;
    }
    if (
      t === 'job.completed'
      && d
      && d.kind === 'index'
      && String(d.phase) === 'delta'
      && job.value
    ) {
      if (keyOf(d) !== keyOf(job.value)) {
        // Completion for a background full-tree delta, not the job shown in the modal.
        return;
      }
    }
    merge(d);
    if (t === 'job.completed' && d.kind && isIndexKind(d.kind) && _indexUiSync) {
      (async () => {
        const msg0 = d.message;
        const hasMsg = msg0 != null && String(msg0) !== '';
        job.value = {
          ...d,
          job_id: d.job_id,
          message: hasMsg ? d.message : 'Updating view…',
        };
        try {
          await _indexUiSync();
        } catch (e) {
          if (typeof console !== 'undefined' && console.error) {
            /* eslint-disable no-console */
            console.error('[xyz-gallery] index UI sync', e);
            /* eslint-enable no-console */
          }
        } finally {
          _finishModalState(false);
        }
      })();
      return;
    }
    _closeTimer = setTimeout(() => {
      _finishModalState(true);
    }, T44_MODAL_AUTO_MS);
  }
}

export function bootstrapJobsActive() {
  return (async () => {
    let r;
    try {
      r = await api.get('/jobs/active');
    } catch {
      return;
    }
    const arr = (r && r.jobs) || [];
    if (!arr.length) {
      return;
    }
    merge({ ...arr[0] });
    if (!visible.value) {
      scheduleForJob(job.value);
    }
  })();
}

export function initGalleryProgress() {
  subscribeGalleryEvent(handleEvent);
  onWebSocketOpen(bootstrapJobsActive);
}

/**
 * When `MainView` is mounted, set to an async function that refetches the folder
 * tree and main grid. Cleared on unmount so a detail-only view falls back to the
 * delayed + resume path.
 * @param {null|(() => Promise<void>)} fn
 */
export function setIndexJobUiSyncHandler(fn) {
  _indexUiSync = typeof fn === 'function' ? fn : null;
}

export { visible as progressModalOpen, job as progressJob, frozen as progressMainFrozen };
