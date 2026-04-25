// components/FolderInputModal.js — gallery-native text prompt (same shell as MovePicker).
import { defineComponent, ref, watch } from 'vue';

export const FolderInputModal = defineComponent({
  name: 'FolderInputModal',
  props: {
    title: { type: String, required: true },
    hint: { type: String, default: '' },
    label: { type: String, default: 'Name' },
    initialValue: { type: String, default: '' },
    confirmLabel: { type: String, default: 'Save' },
    busy: { type: Boolean, default: false },
    error: { type: String, default: '' },
  },
  emits: ['cancel', 'confirm'],
  setup(props, { emit }) {
    const text = ref('');

    watch(
      () => props.initialValue,
      (v) => {
        text.value = typeof v === 'string' ? v : '';
      },
      { immediate: true },
    );

    function onCancel() {
      if (!props.busy) emit('cancel');
    }
    function onConfirm() {
      if (!props.busy) emit('confirm', String(text.value || '').trim());
    }
    return { text, onCancel, onConfirm };
  },
  template: `
    <div class="mp-overlay ft-mp-overlay" @click.self="onCancel">
      <div class="mp-panel" role="dialog" :aria-busy="busy ? 'true' : 'false'">
        <header class="mp-head">
          <h2 class="mp-title">{{ title }}</h2>
          <button type="button" class="mp-x" :disabled="busy" @click="onCancel">×</button>
        </header>
        <div class="mp-body">
          <p v-if="hint" class="muted mp-hint">{{ hint }}</p>
          <label class="mp-field">
            <span>{{ label }}</span>
            <input type="text" class="mp-in" v-model="text" :disabled="busy"
                   autocomplete="off" @keydown.enter.prevent="onConfirm" />
          </label>
          <div class="mp-actions">
            <button type="button" class="mp-btn" :disabled="busy" @click="onCancel">Cancel</button>
            <button type="button" class="mp-btn primary" :disabled="busy" @click="onConfirm">{{ confirmLabel }}</button>
          </div>
          <div v-if="error" class="error mp-err">{{ error }}</div>
        </div>
      </div>
    </div>
  `,
});

export default FolderInputModal;
