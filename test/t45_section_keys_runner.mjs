/**
 * T45 — Node assertions for sectionKeys.js (no ComfyUI).
 * Run: node test/t45_section_keys_runner.mjs
 * Cwd: ComfyUI-XYZNodes/
 */
import {
  partitionItemsIntoSections,
  partitionItemsForLineView,
  folderSectionKey,
  folderSectionLabelFromItem,
  nameSectionKey,
  sizeBinIndex,
  SIZE_BIN_EDGES_BYTES,
  localDayFromCreatedAt,
} from '../js/gallery_dist/sectionKeys.js';

function assert(cond, msg) {
  if (!cond) {
    console.error('FAIL:', msg);
    process.exit(1);
  }
}

// --- folder: root display + relative_dir (line view headers) ---
const imgOutRoot = {
  id: 101,
  filename: 'a.png',
  folder: { id: 1, kind: 'output', display_name: 'output', relative_dir: '' },
  created_at: '2020-01-01T00:00:00Z',
};
const imgOutSub = {
  id: 102,
  filename: 'b.png',
  folder: { id: 1, kind: 'output', display_name: 'output', relative_dir: 'cache_base' },
  created_at: '2020-01-02T00:00:00Z',
};
assert(folderSectionKey(imgOutRoot) === '1::', 'root key');
assert(folderSectionLabelFromItem(imgOutRoot) === 'output', 'root label');
assert(folderSectionLabelFromItem(imgOutSub) === 'output/cache_base', 'nested label');

const imgIn3d = {
  id: 103,
  filename: 'c.png',
  folder: { id: 2, kind: 'input', display_name: 'input', relative_dir: '3d' },
  created_at: '2020-01-03T00:00:00Z',
};
assert(folderSectionLabelFromItem(imgIn3d) === 'input/3d', 'input/3d');

const imgDl = {
  id: 104,
  filename: 'd.png',
  folder: { id: 5, kind: 'custom', display_name: 'Downloads', relative_dir: '' },
  created_at: '2020-01-04T00:00:00Z',
};
assert(folderSectionLabelFromItem(imgDl) === 'Downloads', 'custom root');

// --- folder: non-recursive sections, different parent paths under same root ---
const imgAbc = {
  id: 1,
  filename: 'c.png',
  folder: { id: 10, display_name: 'output', kind: 'output', relative_dir: 'a/b' },
  created_at: '2020-01-01T00:00:00Z',
};
const imgAd = {
  id: 2,
  filename: 'd.png',
  folder: { id: 10, display_name: 'output', kind: 'output', relative_dir: 'a' },
  created_at: '2020-01-02T00:00:00Z',
};
assert(folderSectionKey(imgAbc) === '10::a/b', 'key under root');
assert(folderSectionKey(imgAd) === '10::a', 'sibling path key');
const parts = partitionItemsIntoSections([imgAbc, imgAd], 'folder');
assert(parts.length === 2, 'two distinct folder sections');
assert(parts[0].label === 'output/a/b', 'first header');
assert(parts[1].label === 'output/a', 'second header');

// --- name bucket ---
assert(nameSectionKey('Cat.png') === 'C', 'ASCII upper first');
assert(nameSectionKey('9.png') === '#', 'digit → #');

// --- size bins: edges strictly ascending, full coverage ---
for (let i = 1; i < SIZE_BIN_EDGES_BYTES.length; i += 1) {
  assert(SIZE_BIN_EDGES_BYTES[i] > SIZE_BIN_EDGES_BYTES[i - 1], `edges ascending at ${i}`);
}
assert(sizeBinIndex(0) === 0, 'zero bytes');
assert(sizeBinIndex(9 * 1024) === 0, 'below first non-zero edge');
assert(sizeBinIndex(10 * 1024) === 1, 'on 10KiB boundary');

// --- time day ---
assert(localDayFromCreatedAt('2024-06-15T12:34:56Z').startsWith('2024-06-'), 'local day');

// --- line view folder: merge same header across interleaved API order ---
const inRootA = {
  id: 201,
  filename: 'a.png',
  folder: { id: 2, display_name: 'input', kind: 'input', relative_dir: '' },
  created_at: '2020-01-01T00:00:00Z',
};
const inSub = {
  id: 202,
  filename: 'b.png',
  folder: { id: 2, display_name: 'input', kind: 'input', relative_dir: '3d/cache_base - 副本' },
  created_at: '2020-01-02T00:00:00Z',
};
const inRootB = {
  id: 203,
  filename: 'c.png',
  folder: { id: 2, display_name: 'input', kind: 'input', relative_dir: '' },
  created_at: '2020-01-03T00:00:00Z',
};
const merged = partitionItemsForLineView([inRootA, inSub, inRootB], 'folder', 'asc');
assert(merged.length === 2, 'merged folder sections');
const inputSec = merged.find((s) => s.label === 'input');
const subSec = merged.find((s) => s.items.some((x) => x.id === 202));
assert(inputSec && inputSec.items.length === 2, 'both root files under one input header');
assert(inputSec.items[0].id === 201 && inputSec.items[1].id === 203, 'stable global order in section');
assert(subSec && subSec.items.length === 1 && subSec.items[0].id === 202, 'subfolder section');
const contig = partitionItemsIntoSections([inRootA, inSub, inRootB], 'folder');
assert(contig.length === 3, 'contiguous partition would repeat input');

console.log('T45 sectionKeys runner: OK');
