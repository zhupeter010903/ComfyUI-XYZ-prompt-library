// Central download flow: optional modal vs saved ``download_variant`` (T36 prefs).
import * as api from '../api.js';
import { downloadPromptEachTime } from './gallerySettings.js';
import { requestDownloadPick } from './downloadPick.js';

/**
 * When ``download_prompt_each_time`` is off: ``undefined``.
 * When on: chosen variant, or ``null`` if user cancelled the modal.
 * @param {{ title?: string }} [opts]
 */
export async function pickDownloadVariantOptional(opts = {}) {
  if (!downloadPromptEachTime.value) return undefined;
  return requestDownloadPick(opts);
}

export async function executeImageDownload(imageId) {
  const v = await pickDownloadVariantOptional({ title: 'Download image' });
  if (downloadPromptEachTime.value && v == null) return;
  await api.downloadImage(imageId, v ? { variant: v } : {});
}

/**
 * @param {number[]} ids
 * @param {{ title?: string, gapMs?: number }} [opts]
 */
export async function executeBulkImageDownloads(ids, opts = {}) {
  if (!ids.length) return;
  const title = opts.title || 'Bulk download';
  const gapMs = typeof opts.gapMs === 'number' ? opts.gapMs : 40;
  const v = await pickDownloadVariantOptional({ title });
  if (downloadPromptEachTime.value && v == null) return;
  for (let i = 0; i < ids.length; i += 1) {
    await api.downloadImage(ids[i], v ? { variant: v } : {});
    if (i < ids.length - 1) {
      await new Promise((res) => { setTimeout(res, gapMs); });
    }
  }
}
