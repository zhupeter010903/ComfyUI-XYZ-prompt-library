// components/ThumbCard.js — T13 scope: single thumbnail card rendered
// inside VirtualGrid. Stays deliberately dumb: only receives an
// ImageRecord via props and emits intent events up to the parent.
//
// * `<img loading="lazy" decoding="async">` per SPEC §8.6 so the
//   browser skips off-viewport decode work automatically (the
//   VirtualGrid bounds the DOM, `loading=lazy` bounds network/decode
//   within the DOM window).
// * `object-fit: cover` is applied in CSS (FR-11: all thumbs share the
//   same aspect ratio).
// * `thumb_url` comes verbatim from the backend DTO (§4 #39 — the URL
//   is minted server-side with `?v=<mtime_ns>` for cache-busting;
//   frontend MUST NOT concatenate `/thumb/{id}`).
// * Favorite toggle is a stub: the real PATCH call lands in T19. We
//   emit 'toggle-favorite' so the parent can patch local state today
//   and swap in api.patch() later without re-plumbing the child.
// * Right-click → parent context menu (Move… T24, Delete… T25).
// * T22: `gallery.sync_status` — pending=amber dot, failed=red dot, ok=hidden.
import { defineComponent, computed } from 'vue';

export const ThumbCard = defineComponent({
  name: 'ThumbCard',
  props: {
    item: { type: Object, required: true },
    bulkMode: { type: Boolean, default: false },
    bulkSelected: { type: Boolean, default: false },
  },
  emits: ['open', 'toggle-favorite', 'context', 'toggle-bulk'],
  setup(props, { emit }) {
    const isFav = computed(
      () => !!(props.item && props.item.gallery && props.item.gallery.favorite),
    );
    const syncBadge = computed(() => {
      const s = props.item && props.item.gallery && props.item.gallery.sync_status;
      if (s === 'pending') return 'pending';
      if (s === 'failed') return 'failed';
      return null;
    });
    const syncTitle = computed(() => {
      if (syncBadge.value === 'pending') return 'Metadata sync: pending';
      if (syncBadge.value === 'failed') return 'Metadata sync: failed';
      return '';
    });

    function onClick() {
      if (props.bulkMode) {
        emit('toggle-bulk', props.item.id);
        return;
      }
      emit('open', props.item.id);
    }
    function onContextMenu(e) {
      e.preventDefault();
      emit('context', { id: props.item.id, x: e.clientX, y: e.clientY });
    }
    function onFavClick(e) {
      e.stopPropagation();
      emit('toggle-favorite', props.item.id);
    }

    return { isFav, syncBadge, syncTitle, onClick, onContextMenu, onFavClick };
  },
  template: `
    <div class="tc" :class="{ 'tc-bulk-on': bulkMode }" @click="onClick" @contextmenu="onContextMenu">
      <div class="tc-thumb">
        <img v-if="item.thumb_url"
             class="tc-media"
             :src="item.thumb_url"
             :alt="item.filename || ''"
             loading="lazy"
             decoding="async" />
        <div v-else class="tc-thumb-empty tc-media" aria-hidden="true"></div>
        <div v-if="bulkMode" class="tc-bulk" aria-hidden="true">
          <input
            type="checkbox"
            class="tc-bulk-cb"
            :checked="bulkSelected"
            tabindex="-1"
            @click.stop
          />
        </div>
        <div v-if="syncBadge" class="tc-sync" :class="'tc-sync-'+syncBadge" :title="syncTitle" aria-label="metadata sync" />
        <button type="button"
                class="tc-fav"
                :class="{ active: isFav }"
                :aria-pressed="isFav ? 'true' : 'false'"
                :title="isFav ? 'Unfavorite' : 'Favorite'"
                @click="onFavClick">
          <span class="tc-fav-icon" aria-hidden="true">{{ isFav ? '♥' : '♡' }}</span>
        </button>
      </div>
      <div class="tc-name" :title="item.filename || ''">{{ item.filename }}</div>
    </div>
  `,
});

export default ThumbCard;
