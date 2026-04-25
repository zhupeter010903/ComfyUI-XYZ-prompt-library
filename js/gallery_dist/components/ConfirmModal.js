// components/ConfirmModal.js — T25 shared confirm for destructive actions.
import { defineComponent } from 'vue';

export const ConfirmModal = defineComponent({
  name: 'ConfirmModal',
  props: {
    title: { type: String, default: 'Confirm' },
    lines: { type: Array, default: () => [] },
    confirmLabel: { type: String, default: 'Confirm' },
    cancelLabel: { type: String, default: 'Cancel' },
    danger: { type: Boolean, default: false },
    busy: { type: Boolean, default: false },
    /** When true, confirm is disabled but cancel stays enabled (unless ``busy``). */
    confirmDisabled: { type: Boolean, default: false },
  },
  emits: ['confirm', 'cancel'],
  setup(props, { emit }) {
    function onConfirm() {
      if (!props.busy && !props.confirmDisabled) emit('confirm');
    }
    function onCancel() {
      if (!props.busy) emit('cancel');
    }
    return { onConfirm, onCancel };
  },
  template: `
    <div class="cm-overlay" @click.self="onCancel">
      <div class="cm-panel" role="alertdialog" :aria-busy="busy ? 'true' : 'false'">
        <header class="cm-head">
          <h2 class="cm-title">{{ title }}</h2>
          <button type="button" class="cm-x" :disabled="busy" @click="onCancel">×</button>
        </header>
        <div class="cm-body">
          <p v-for="(line, i) in lines" :key="i" class="cm-line">{{ line }}</p>
        </div>
        <footer class="cm-foot">
          <button type="button" class="cm-btn" :disabled="busy" @click="onCancel">{{ cancelLabel }}</button>
          <button type="button" class="cm-btn" :class="{ 'cm-btn-danger': danger }" :disabled="busy || confirmDisabled" @click="onConfirm">{{ confirmLabel }}</button>
        </footer>
      </div>
    </div>
  `,
});

export default ConfirmModal;
