// stores/vocab.js — T21 prefix → autocomplete result LRU (FR-3b/c).

const MAX_KEYS = 64;
/** @type {Map<string, { results: Array<{name: string, usage_count: number}> }>} */
const cache = new Map();

/**
 * @param {'tags'|'prompts'} kind
 * @param {string} prefix
 * @returns {Array<{name: string, usage_count: number}>|null}
 */
export function vocabCacheGet(kind, prefix) {
  const key = `${kind}|${prefix}`;
  const hit = cache.get(key);
  if (!hit) return null;
  cache.delete(key);
  cache.set(key, hit);
  return hit.results;
}

/**
 * @param {'tags'|'prompts'} kind
 * @param {string} prefix
 * @param {Array<{name: string, usage_count: number}>} results
 */
export function vocabCacheSet(kind, prefix, results) {
  const key = `${kind}|${prefix}`;
  if (cache.has(key)) cache.delete(key);
  cache.set(key, { results });
  while (cache.size > MAX_KEYS) {
    const first = cache.keys().next().value;
    cache.delete(first);
  }
}

/** Clear all prefix caches (e.g. after bulk tag edit or new tags in DB). */
export function vocabCacheClear() {
  cache.clear();
}

export const _internals = { MAX_KEYS };
