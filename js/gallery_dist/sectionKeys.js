// sectionKeys.js — T45 line-view section keys (PROJECT_SPEC §12.2).
// Pure helpers; no Vue / no network. Kept separate for unit tests (Node).

/**
 * Size bin boundaries in bytes, strictly ascending, first 0, last sentinel.
 * Adjacent bins [edges[i], edges[i+1]) cover all non‑negative sizes with no
 * gaps or overlaps. Example: a 900 KiB file falls in the bin whose label spans
 * 512 KiB → 1 MiB (see ``sizeSectionLabel``).
 */
export const SIZE_BIN_EDGES_BYTES = Object.freeze([
  0,
  10 * 1024,
  100 * 1024,
  512 * 1024,
  1024 * 1024,
  4 * 1024 * 1024,
  16 * 1024 * 1024,
  64 * 1024 * 1024,
  Number.MAX_SAFE_INTEGER,
]);

function _fmtSizeShort(bytes) {
  const x = Math.max(0, Number(bytes) || 0);
  if (x < 1024) return `${x} B`;
  if (x < 1024 * 1024) return `${(x / 1024).toFixed(x < 10 * 1024 ? 1 : 0)} KiB`;
  if (x < 1024 * 1024 * 1024) return `${(x / (1024 * 1024)).toFixed(x < 10 * 1024 * 1024 ? 1 : 0)} MiB`;
  return `${(x / (1024 * 1024 * 1024)).toFixed(1)} GiB`;
}

/** Bin index i covers [edges[i], edges[i+1]) (0-sized files use i=0). */
export function sizeBinIndex(bytes) {
  const b = Math.max(0, Number(bytes) || 0);
  const edges = SIZE_BIN_EDGES_BYTES;
  for (let i = edges.length - 2; i >= 0; i -= 1) {
    if (b >= edges[i]) return i;
  }
  return 0;
}

export function sizeSectionLabel(bytes) {
  const i = sizeBinIndex(bytes);
  const lo = SIZE_BIN_EDGES_BYTES[i];
  const hi = SIZE_BIN_EDGES_BYTES[i + 1];
  if (hi === Number.MAX_SAFE_INTEGER) return `${_fmtSizeShort(lo)} +`;
  return `${_fmtSizeShort(lo)} – ${_fmtSizeShort(hi)}`;
}

export function sizeSectionSortKey(bytes) {
  return String(sizeBinIndex(bytes)).padStart(4, '0');
}

export function localDayFromCreatedAt(iso) {
  if (!iso) return 'Unknown';
  const d = new Date(String(iso));
  if (Number.isNaN(d.getTime())) return 'Unknown';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function nameSectionKey(filename) {
  const base = String(filename || '').trim();
  if (!base) return '#';
  const c0 = base[0];
  const cp = c0.codePointAt(0);
  if (cp >= 0x41 && cp <= 0x5a) return c0;
  if (cp >= 0x61 && cp <= 0x7a) return String.fromCharCode(cp - 0x20);
  return '#';
}

/**
 * Root id + relative parent dir under that root (API fields).
 * ``folder.id`` is the registered root row id; ``relative_dir`` is the parent
 * path under the root (POSIX, no leading slash).
 */
export function folderSectionPathParts(item) {
  const f = item && item.folder;
  const rootId = (f && (typeof f.id === 'number' || typeof f.id === 'string'))
    ? String(f.id)
    : '';
  let rd = f && f.relative_dir != null ? String(f.relative_dir) : '';
  rd = rd.replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+$/, '');
  return { rootId, relativeDir: rd };
}

/** Stable partition key: same root + same parent path → same section. */
export function folderSectionKey(item) {
  const { rootId, relativeDir } = folderSectionPathParts(item);
  return `${rootId}::${relativeDir}`;
}

/** Root label segment: ``display_name``, else ``kind``, else empty. */
export function folderRootDisplaySegment(item) {
  const f = item && item.folder;
  const dn = (f && f.display_name != null) ? String(f.display_name).trim() : '';
  if (dn) return dn;
  const k = (f && f.kind != null) ? String(f.kind).trim() : '';
  return k;
}

/**
 * Line-view section title, e.g. ``output``, ``output/cache_base``, ``input/3d``,
 * ``Downloads`` (root display + optional ``/`` + ``relative_dir``).
 */
export function folderSectionLabelFromItem(item) {
  const { relativeDir } = folderSectionPathParts(item);
  const root = folderRootDisplaySegment(item) || '(root)';
  if (!relativeDir) return root;
  return `${root}/${relativeDir}`;
}

/**
 * Stable section key + human label for one item (sort column only).
 */
export function sectionMetaForItem(item, sortKey) {
  if (sortKey === 'time') {
    const day = localDayFromCreatedAt(item && item.created_at);
    return { key: `t:${day}`, label: day };
  }
  if (sortKey === 'name') {
    const k = nameSectionKey(item && item.filename);
    return { key: `n:${k}`, label: k };
  }
  if (sortKey === 'size') {
    const bytes = item && item.size && item.size.bytes != null ? item.size.bytes : 0;
    const sk = sizeSectionSortKey(bytes);
    return { key: `s:${sk}`, label: sizeSectionLabel(bytes) };
  }
  if (sortKey === 'folder') {
    const k = folderSectionKey(item);
    return { key: `f:${k}`, label: folderSectionLabelFromItem(item) };
  }
  const day = localDayFromCreatedAt(item && item.created_at);
  return { key: `t:${day}`, label: day };
}

/**
 * Partition already-sorted ``items`` into contiguous runs (same section key).
 * Order of sections = first occurrence in list (matches ``list_images`` order).
 */
export function partitionItemsIntoSections(items, sortKey) {
  const arr = Array.isArray(items) ? items : [];
  const out = [];
  let curKey = null;
  let curLabel = null;
  let bucket = [];
  for (let i = 0; i < arr.length; i += 1) {
    const it = arr[i];
    const { key, label } = sectionMetaForItem(it, sortKey);
    if (key !== curKey) {
      if (bucket.length) out.push({ key: curKey, label: curLabel, items: bucket });
      curKey = key;
      curLabel = label;
      bucket = [it];
    } else {
      bucket.push(it);
    }
  }
  if (bucket.length) out.push({ key: curKey, label: curLabel, items: bucket });
  return out;
}

/**
 * Line view sections. For **folder** sort, merge all items that share the same
 * section key (legacy interleaved pages, or duplicate runs) into one header.
 * Section order follows **first occurrence** in ``items`` (same as
 * ``list_images`` order after folder sort — avoids re-ordering sections when
 * appending pages). Other sort keys: contiguous runs only.
 */
export function partitionItemsForLineView(items, sortKey, sortDir) {
  void sortDir;
  const sk = sortKey || 'time';
  const arr = Array.isArray(items) ? items : [];
  if (sk !== 'folder') {
    return partitionItemsIntoSections(arr, sk);
  }
  const buckets = new Map();
  const order = [];
  for (let i = 0; i < arr.length; i += 1) {
    const it = arr[i];
    const meta = sectionMetaForItem(it, sk);
    const { key, label } = meta;
    if (!buckets.has(key)) {
      buckets.set(key, { key, label, items: [] });
      order.push(key);
    }
    buckets.get(key).items.push(it);
  }
  return order.map((k) => buckets.get(k));
}
