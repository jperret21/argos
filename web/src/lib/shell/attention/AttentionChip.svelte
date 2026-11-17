<!--
  The status-bar attention chip (BRAND §13; functional-spaces §4.10 "Status bar"): the most
  urgent open item's level by mark AND word, the count of items needing the observer, and
  that item's headline ("HFD 18.3 px · 1.5× baseline"). A button: it opens the list
  (AttentionList in a Popover anchored here). With nothing open but items in this run, a
  quiet glyph keeps the list one click away; with no item at all, nothing is drawn.
  Critical: a --danger edge, never a red fill (the brightest thing in the room, BRAND 4.3);
  no blinking. `compact` folds the headline (1 280 px with a run chip, or wherever the status bar measures an overflow; the tooltip keeps it).
-->
<script lang="ts">
  import Icon from '../../components/Icon.svelte';
  import { tooltip } from '../../components/tooltip';
  import { LEVEL_WORD, type ChipView } from './model';
  import AttentionMark from './AttentionMark.svelte';

  interface Props {
    chip: ChipView;
    expanded?: boolean;
    /** id of the list's popover (aria-controls). */
    controls?: string;
    compact?: boolean;
    /** The headline's room (px) when the status bar measured too little for all of it: it ends in an ellipsis. */
    textMax?: number | null;
    onclick?: () => void;
    /** The button, for the popover's anchor. */
    element?: HTMLButtonElement | null;
  }
  let { chip, expanded = false, controls, compact = false, textMax = null, onclick, element = $bindable(null) }: Props = $props();
</script>

{#if !chip.hidden}
  <button
    bind:this={element}
    type="button"
    class="chip {chip.level ? `l-${chip.level}` : 'quiet'}"
    aria-haspopup="dialog"
    aria-expanded={expanded}
    aria-controls={controls}
    aria-label={chip.label}
    use:tooltip={{ text: chip.label, placement: 'top' }}
    {onclick}
  >
    {#if chip.level}
      <AttentionMark level={chip.level} size={10} />
      <span class="word">{LEVEL_WORD[chip.level]}</span>
      <span class="count num">{chip.count}</span>
      {#if !compact}<span class="text num" style:max-width={textMax ? `${textMax}px` : undefined}>{chip.text}</span>{/if}
    {:else}
      <Icon name="attention" size="s" />
    {/if}
  </button>
{/if}

<style>
  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
    max-width: 360px;
    height: 22px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg);
    color: var(--fg);
    font-family: var(--font-ui);
    font-size: var(--text-xs);
    flex: none;
    cursor: pointer;
  }
  .chip:hover {
    background: var(--hover-bg);
  }
  .chip:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .chip[aria-expanded='true'] {
    background: var(--toggled-bg);
  }
  .l-critical {
    border-color: var(--danger);
    border-width: 2px;
    padding: 0 calc(var(--space-2) - 1px);
  }
  .l-attention {
    border-color: var(--border);
  }
  .quiet {
    width: 26px;
    justify-content: center;
    padding: 0;
    border-color: transparent;
    background: transparent;
    color: var(--fg-muted);
  }
  .word {
    font-weight: var(--weight-semibold);
  }
  .l-attention .word {
    font-weight: var(--weight-medium);
  }
  .count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-round);
    font-size: var(--text-2xs);
  }
  .text {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--fg);
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
</style>
