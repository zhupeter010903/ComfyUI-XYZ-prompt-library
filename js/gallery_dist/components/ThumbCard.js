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
// * Right-click opens a placeholder context menu (FR-14 `Move…` /
//   `Delete…`); the actual actions land in T24 / T25.
import { defineComponent, computed } from 'vue';

export const ThumbCard = defineComponent({
  name: 'ThumbCard',
  props: {
    item: { type: Object, required: true },
  },
  emits: ['open', 'toggle-favorite', 'context'],
  setup(props, { emit }) {
    const isFav = computed(
      () => !!(props.item && props.item.gallery && props.item.gallery.favorite),
    );

    function onClick() {
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

    return { isFav, onClick, onContextMenu, onFavClick };
  },
  template: `
    <div class="tc" @click="onClick" @contextmenu="onContextMenu">
      <div class="tc-thumb">
        <img v-if="item.thumb_url"
             :src="item.thumb_url"
             :alt="item.filename || ''"
             loading="lazy"
             decoding="async" />
        <div v-else class="tc-thumb-empty" aria-hidden="true"></div>
        <button type="button"
                class="tc-fav"
                :class="{ active: isFav }"
                :aria-pressed="isFav ? 'true' : 'false'"
                :title="isFav ? 'Unfavorite' : 'Favorite'"
                @click="onFavClick">★</button>
      </div>
      <div class="tc-name" :title="item.filename || ''">{{ item.filename }}</div>
    </div>
  `,
});

export default ThumbCard;
