// T40 / PROJECT_SPEC §12.5 — icon + tokenized panel button for Back / 主导航（非裸链接色）。
// SVG 1.5 stroke, 24 视口，与 FolderTree（T39）同网格。
import { defineComponent, computed, toRefs } from 'vue';

const PATHS = {
  chevronLeft: 'M15.75 19.5L8.25 12l7.5-7.5',
  chevronRight: 'M8.25 4.5L15.75 12l-7.5 7.5',
};

export const IconButton = defineComponent({
  name: 'IconButton',
  props: {
    href: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
    /** `chevronLeft` | `chevronRight` */
    icon: { type: String, default: 'chevronLeft' },
    text: { type: String, default: '' },
    /** 若真则可视文案进 `.ib-sr-only`，须配合 `text` 或 `ariaLabel` 满足可访问性 */
    textSrOnly: { type: Boolean, default: false },
    ariaLabel: { type: String, default: '' },
    title: { type: String, default: '' },
    buttonType: { type: String, default: 'button' },
  },
  setup(props) {
    const isLink = computed(() => Boolean(props.href));
    const pathD = computed(
      () => (PATHS[props.icon] ? PATHS[props.icon] : PATHS.chevronLeft),
    );
    const aria = computed(() => {
      if (props.ariaLabel) return props.ariaLabel;
      if (props.textSrOnly && props.text) return props.text;
      return undefined;
    });
    const rootBind = computed(() => {
      if (props.href) {
        return {
          href: props.disabled ? undefined : props.href,
          'aria-disabled': props.disabled ? 'true' : undefined,
        };
      }
      return {
        type: props.buttonType,
        disabled: props.disabled,
      };
    });
    function onLinkClick(e) {
      if (props.href && props.disabled) e.preventDefault();
    }
    return { ...toRefs(props), isLink, pathD, aria, rootBind, onLinkClick };
  },
  template: `
    <component
      :is="isLink ? 'a' : 'button'"
      v-bind="rootBind"
      class="ib"
      :class="[{ 'ib--disabled': disabled }]"
      :title="title"
      :aria-label="aria"
      @click="onLinkClick"
    >
      <span class="ib-ico" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="20" height="20" focusable="false" xmlns="http://www.w3.org/2000/svg">
          <path
            :d="pathD"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round" />
        </svg>
      </span>
      <span v-if="text" :class="textSrOnly ? 'ib-sr-only' : 'ib-txt'">{{ text }}</span>
    </component>
  `,
});

export default IconButton;
