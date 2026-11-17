<!--
  Key hint cap for an element that is not a Control (BRAND 7 amendment,
  design review): rail entries (F1-F5), the Help button (?), the Settings
  filter (/), the command palette affordance (Mod+K). The same neutral cap
  as Control.svelte's `.keyhint` (--fg on --surface, never brass), drawn
  while Cmd / Ctrl is held alone (app/keyhints.svelte.ts). The parent must
  be positioned: the cap sits on its lower-right corner, or inline.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { ensureKeyHints, keyHintsVisible } from '../app/keyhints.svelte';
  import { formatShortcut } from '../app/shortcuts';

  interface Props {
    /** Shortcut spec from the registry ("F1", "/", "Mod+K"). */
    keys: string;
    /** corner: on the parent's lower-right corner; inline: in the text flow; end: centred on the right edge. */
    place?: 'corner' | 'inline' | 'end';
    /** Gallery only: draw it now. */
    force?: boolean;
  }
  let { keys, place = 'corner', force = false }: Props = $props();

  onMount(() => ensureKeyHints());
</script>

{#if force || keyHintsVisible()}
  <kbd class="keyhint {place}" aria-hidden="true">{formatShortcut(keys)}</kbd>
{/if}

<style>
  .keyhint {
    z-index: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: var(--cap-h);
    height: var(--cap-h);
    padding: 0 3px;
    border: var(--border-w) solid var(--border);
    border-bottom-width: 2px;
    border-radius: var(--radius-s);
    background: var(--surface);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    line-height: 1;
    pointer-events: none;
    animation: hint-in var(--duration-fast) var(--ease-out);
  }
  .corner {
    position: absolute;
    right: -5px;
    bottom: -6px;
  }
  .end {
    position: absolute;
    top: 50%;
    right: var(--space-2);
    transform: translateY(-50%);
  }
  @keyframes hint-in {
    from {
      opacity: 0;
    }
  }
</style>
