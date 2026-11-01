<!--
  Icon for the workspace lab: the design system's Icon for every existing id,
  plus three PROPOSED glyphs (ids starting "lab-") that the functional study
  asks for and the inventory does not have yet. They follow BRAND 6: 24 grid,
  one 1.5 stroke, round caps and joins, keylines, lattice, fills only for
  data points; to be redrawn by the icon designers after review, then added
  to icon-inventory.json (BRAND 12) without the prefix.

  - lab-watch: a screen on a stand showing three light-curve points (the
    glance view of a run). No digits, no eye (reserved for nav-imaging).
  - lab-attention: the r = 9 ring with an upright mark (an alert that is not
    a triangle: the triangle is the check-star role).
  - lab-inspector: a sheet with a star and key / value rows (the selected
    star's details).
-->
<script lang="ts" module>
  const LAB: Record<string, string> = {
    'lab-watch':
      '<rect x="2.25" y="3.75" width="19.5" height="12" rx="2.25"/><path d="M12 15.75V20.25M8.25 20.25H15.75"/><circle cx="7.5" cy="8.25" r="1.5" fill="currentColor" stroke="none"/><circle cx="12" cy="11.25" r="1.5" fill="currentColor" stroke="none"/><circle cx="16.5" cy="8.25" r="1.5" fill="currentColor" stroke="none"/>',
    'lab-attention': '<circle cx="12" cy="12" r="9"/><path d="M12 7.5V12.75"/><path d="M12 16.5V16.51"/>',
    'lab-inspector':
      '<rect x="3.75" y="3.75" width="16.5" height="16.5" rx="2.25"/><circle cx="8.25" cy="8.25" r="1.875" fill="currentColor" stroke="none"/><path d="M12.75 8.25H17.25M6.75 12.75H17.25M6.75 17.25H13.5"/>',
  };
  export const LAB_ICON_IDS = Object.keys(LAB);
</script>

<script lang="ts">
  import Icon, { type IconSize } from '../../../lib/components/Icon.svelte';

  interface Props {
    name: string;
    size?: IconSize;
    label?: string;
  }

  let { name, size = 20, label }: Props = $props();
  const px = $derived(typeof size === 'number' ? `${size}px` : `var(--icon-${size})`);
</script>

{#if name in LAB}
  <span class="icon" style:width={px} style:height={px} role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : 'true'}>
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      {@html LAB[name]}
    </svg>
  </span>
{:else}
  <Icon {name} {size} {label} />
{/if}

<style>
  .icon {
    display: inline-flex;
    flex: none;
  }
  svg {
    width: 100%;
    height: 100%;
    display: block;
  }
</style>
