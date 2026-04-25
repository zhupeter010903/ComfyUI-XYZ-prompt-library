// Secondary modal: choose PNG download variant before fetch (prefs ``download_prompt_each_time``).
import { defineComponent } from 'vue';
import {
  pickModalOpen,
  pickModalTitle,
  submitDownloadPick,
  cancelDownloadPick,
} from '../stores/downloadPick.js';

export const DownloadPickModal = defineComponent({
  name: 'DownloadPickModal',
  setup() {
    function pick(v) {
      submitDownloadPick(v);
    }
    function cancel() {
      cancelDownloadPick();
    }
    return { pickModalOpen, pickModalTitle, pick, cancel };
  },
  template: `
    <div v-if="pickModalOpen" class="cm-overlay dp-pick-overlay" @click.self="cancel">
      <div class="cm-panel dp-pick-panel" role="dialog" aria-modal="true">
        <header class="cm-head">
          <h2 class="cm-title">{{ pickModalTitle }}</h2>
          <button type="button" class="cm-x" @click="cancel">×</button>
        </header>
        <div class="cm-body">
          <p class="muted cm-line">How much ComfyUI metadata should the PNG include?</p>
          <div class="dp-choice-grid">
            <button type="button" class="cm-btn dp-choice" @click="pick('full')">Full metadata</button>
            <button type="button" class="cm-btn dp-choice" @click="pick('no_workflow')">No workflow</button>
            <button type="button" class="cm-btn dp-choice" @click="pick('clean')">No Comfy metadata</button>
          </div>
        </div>
        <footer class="cm-foot">
          <button type="button" class="cm-btn" @click="cancel">Cancel</button>
        </footer>
      </div>
    </div>
  `,
});

export default DownloadPickModal;
