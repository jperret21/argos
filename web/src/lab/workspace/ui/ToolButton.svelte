<!--
  Ghost toolbar button for the lab's PROPOSED glyphs (lab-watch, ...): the
  same metrics and states as lib IconButton's ghost variant, but drawn with
  LabIcon. Once the glyphs are in the inventory, IconButton replaces it.
-->
<script lang="ts">
  import { ariaShortcut } from '../../../lib/app/shortcuts';
  import { tooltip } from '../../../lib/components/tooltip';
  import LabIcon from './LabIcon.svelte';

  interface Props {
    icon: string;
    label: string;
    shortcut?: string;
    pressed?: boolean;
    badge?: number | null;
    onclick: (e: MouseEvent) => void;
  }

  let { icon, label, shortcut, pressed, badge = null, onclick }: Props = $props();
</script>

<button
  type="button"
  class="tool"
  aria-label={label}
  aria-pressed={pressed}
  aria-keyshortcuts={shortcut ? ariaShortcut(shortcut) : undefined}
  {onclick}
  use:tooltip={{ text: label, shortcut, placement: 'bottom' }}
>
  <LabIcon name={icon} size={20} />
  {#if badge}<span class="badge num">{badge}</span>{/if}
</button>

<style>
  .tool {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--control-h-m);
    height: var(--control-h-m);
    padding: 0;
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg-muted);
    cursor: pointer;
    transition:
      background-color var(--duration-fast) var(--ease-standard),
      color var(--duration-fast) var(--ease-standard);
  }
  .tool:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .tool:active {
    background: var(--pressed-bg);
  }
  .tool[aria-pressed='true'] {
    background: var(--toggled-bg);
    color: var(--fg);
  }
  .badge {
    position: absolute;
    top: 2px;
    right: 1px;
    min-width: 14px;
    height: 14px;
    padding: 0 3px;
    border-radius: var(--radius-round);
    background: var(--warning);
    color: var(--on-accent);
    font-size: 9px;
    font-weight: var(--weight-medium);
    line-height: 14px;
    text-align: center;
  }
</style>
