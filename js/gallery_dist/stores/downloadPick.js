// Modal state for per-download PNG variant choice (when ``download_prompt_each_time``).
import { ref } from 'vue';

export const pickModalOpen = ref(false);
export const pickModalTitle = ref('Download');

let _resolver = null;

/**
 * Opens the picker and resolves with ``'full'|'no_workflow'|'clean'`` or ``null`` if cancelled.
 * @param {{ title?: string }} [opts]
 */
export function requestDownloadPick(opts = {}) {
  pickModalTitle.value = (opts.title && String(opts.title))
    || 'Choose PNG metadata for this download';
  pickModalOpen.value = true;
  return new Promise((resolve) => {
    _resolver = resolve;
  });
}

export function submitDownloadPick(variant) {
  pickModalOpen.value = false;
  if (_resolver) {
    _resolver(variant);
    _resolver = null;
  }
}

export function cancelDownloadPick() {
  pickModalOpen.value = false;
  if (_resolver) {
    _resolver(null);
    _resolver = null;
  }
}
