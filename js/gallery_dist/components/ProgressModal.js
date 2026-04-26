// T44 — 单一 Progress 模态；消费 stores/galleryProgress
import { defineComponent, computed } from 'vue';
import {
  progressJob,
  progressModalOpen,
} from '../stores/galleryProgress.js';

function kindLabel(k) {
  if (!k) return '';
  const s = { move: 'Move', delete: 'Delete', favorite: 'Favorite', tags: 'Tags',
    index: 'Index', tag_delete: 'Tag delete', tag_rename: 'Tag rename' };
  return s[k] || k;
}

export const ProgressModal = defineComponent({
  name: 'ProgressModal',
  template: `
    <teleport to="body" v-if="open">
      <div class="pm-root" role="presentation">
        <div class="pm-backdrop" role="presentation" />
        <div
          class="pm-panel"
          role="dialog"
          aria-modal="true"
          :aria-label="aria"
        >
          <div class="pm-h">{{ title }}</div>
          <p class="pm-line pm-top" :title="topTextRaw">{{ topLine }}</p>
          <div class="pm-bar-outer" aria-hidden="true">
            <div
              class="pm-bar-in"
              :class="{ 'pm-bar-indet': !hasPercent }"
              :style="barInnerStyle"
            />
          </div>
          <p class="pm-line pm-detail" role="status">{{ detailLine }}</p>
          <p class="pm-line pm-meta" aria-live="polite">{{ countsText }}</p>
        </div>
      </div>
    </teleport>
  `,
  setup() {
    const NB = '\u00A0';
    const j = progressJob;
    const open = progressModalOpen;
    const title = computed(() => {
      const d = j.value;
      if (!d) return 'Processing…';
      if (d.kind) return `${kindLabel(d.kind)} in progress…`;
      return 'Processing…';
    });
    const hasPercent = computed(() => {
      if (!j.value) return false;
      return Math.max(0, Number(j.value.total) || 0) > 0;
    });
    const barPct = computed(() => {
      const d = j.value;
      if (!d) return '0%';
      const t = Math.max(0, Number(d.total) || 0);
      if (t <= 0) return '100%';
      const done = Math.max(0, Math.min(t, Number(d.done) || 0));
      return `${Math.min(100, Math.round(100 * done / t))}%`;
    });
    const barInnerStyle = computed(() => {
      if (hasPercent.value) {
        return { width: barPct.value };
      }
      return {};
    });
    const topTextRaw = computed(() => {
      const d = j.value;
      if (!d) return '';
      const a = d.phase != null && String(d.phase) !== '' ? String(d.phase) : '';
      const b = d.message != null && String(d.message) !== '' ? String(d.message) : '';
      return a || b || '';
    });
    const topLine = computed(() => {
      const s = topTextRaw.value.trim();
      return s || NB;
    });
    const detailLine = computed(() => {
      if (hasPercent.value) {
        return NB;
      }
      if (j.value && j.value.message) {
        return String(j.value.message);
      }
      if (j.value && j.value.kind === 'index') {
        return 'Index working… (length unknown — see counts)';
      }
      return 'Working…';
    });
    const countsText = computed(() => {
      const d = j.value;
      if (!d) return NB;
      const t = d.total;
      if (t != null && t > 0) {
        return `Done: ${d.done} / ${t}`;
      }
      if (d.done != null) {
        return `Progress: ${d.done}`;
      }
      return NB;
    });
    const aria = computed(() => (title.value || 'Progress'));
    return {
      open, title, hasPercent, barInnerStyle, topLine, topTextRaw, detailLine, countsText, aria,
    };
  },
});
