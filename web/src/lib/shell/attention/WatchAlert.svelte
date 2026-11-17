<!--
  Watch's attention row (owner D3; PROPOSAL §2.3 "the pulse fix"; functional-spaces §4.7):
  the most urgent open item replaces Watch's first row, read from 2 m: its level by a 44 px
  mark AND the word, the item's headline (the value and the factor only) fitted to the
  room so it never ellipsises at 1 440 or 1 280 px, the rule, when and which frame; and,
  at its right end, the run's PULSE (the last-frame age and n / N): the one signal that
  tells a frozen run from a healthy one must not disappear when an alert shows.
  A Critical item is a 4 px --danger outline with bold words, never a red fill (the
  brightest thing in the room, BRAND 4.3). Acknowledge is shared by every client.
-->
<script lang="ts">
  import type { AttentionItem } from '../../api/attention';
  import { clockUtc } from '../../format/time';
  import type { AgeView } from '../watch';
  import { LEVEL_WORD } from './model';
  import AttentionMark from './AttentionMark.svelte';

  interface Props {
    item: AttentionItem;
    age: AgeView;
    /** "160 / 195". */
    frames: string;
    /** The run's state word when it is not RUNNING ("PAUSED", "STOPPING"): a paused run
     * with an open item never looks like a stalled one from 2 m. */
    state?: string | null;
    /** Open items besides this one ("+1 more"). */
    more?: number;
    busy?: boolean;
    onack?: (id: string) => Promise<unknown> | void;
  }
  let { item, age, frames, state = null, more = 0, busy = false, onack }: Props = $props();

  const meta = $derived(
    [item.ruleLabel, item.since !== null ? `${clockUtc(item.since, false)} UTC` : null, item.frame !== null ? `frame ${item.frame}` : null, item.active ? null : 'cleared']
      .filter(Boolean)
      .join(' · '),
  );
  // Mono digits are 0.6 em wide: the headline's width in em, for the fit (container units).
  const em = $derived(Math.max(8, item.short.length * 0.6));
</script>

<section class="alert l-{item.level}" role="alert" aria-label="{LEVEL_WORD[item.level]}: {item.short}">
  <span class="mark"><AttentionMark level={item.level} size={44} /></span>
  <span class="words">
    <span class="top"><span class="lvl">{LEVEL_WORD[item.level].toUpperCase()}</span><span class="meta">{meta}</span></span>
    <span class="fit"><span class="short num" style:--em={em}>{item.short}</span></span>
  </span>
  <!-- The pulse at the size it has without an alert's row: the age and n / N, 48 px mono. -->
  <span class="pulse" class:late={age.late}>
    <span class="age num">{age.value}<span class="sep"> · </span><span class="n">{frames}</span></span>
    <span class="note">last frame{state ? ` · ${state}` : ''}{more > 0 ? ` · +${more} more` : ''}</span>
  </span>
  {#if onack}
    <button type="button" class="ack" aria-busy={busy} disabled={busy} onclick={() => void Promise.resolve(onack?.(item.id)).catch(() => undefined)}>Acknowledge</button>
  {/if}
</section>

<style>
  .alert {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto auto;
    align-items: center;
    column-gap: var(--space-6);
    height: 100%;
    padding: 0 var(--space-6);
    box-shadow: inset 0 0 0 2px var(--warning);
  }
  .l-critical {
    box-shadow: inset 0 0 0 4px var(--danger);
  }
  .l-info {
    box-shadow: inset 0 0 0 2px var(--border);
  }
  .mark {
    display: inline-flex;
  }
  .words {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .top {
    display: flex;
    align-items: baseline;
    gap: var(--space-4);
    min-width: 0;
    white-space: nowrap;
  }
  .lvl {
    flex: none;
    font-family: var(--font-ui);
    font-size: var(--watch-s);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.04em;
    line-height: 1.1;
  }
  .l-attention .lvl {
    font-weight: var(--weight-medium);
  }
  /* The rule line may shorten (the level word and the headline never do). */
  .meta {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-muted);
    font-size: calc(var(--watch-s) * 0.8);
  }
  .fit {
    display: block;
    container-type: inline-size;
    min-width: 0;
  }
  /* 48 px when the room allows, fitted to the column below that (26 px floor; past it the
     headline wraps rather than hide a number). */
  .short {
    display: block;
    font-size: max(26px, min(calc(var(--watch-m) * 1.2), calc(100cqi / var(--em))));
    font-weight: var(--weight-medium);
    line-height: 1.1;
    overflow-wrap: anywhere;
  }
  .pulse {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    padding-left: var(--space-5);
    border-left: var(--border-w) solid var(--border-soft);
    white-space: nowrap;
  }
  .age {
    font-size: calc(var(--watch-m) * 1.2);
    font-weight: var(--weight-medium);
    line-height: 1.05;
  }
  .sep {
    color: var(--text-muted);
  }
  .note {
    color: var(--text-muted);
    font-size: 22px;
  }
  .late .age {
    color: var(--text-muted);
  }
  .ack {
    height: 64px;
    padding: 0 var(--space-6);
    border: 2px solid var(--fg-muted);
    border-radius: var(--radius-m);
    background: var(--surface);
    color: var(--fg);
    font-family: var(--font-ui);
    font-size: 24px;
    font-weight: var(--weight-medium);
    cursor: pointer;
  }
  .ack:hover {
    background: var(--hover-bg);
  }
  .ack:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }
  .ack[aria-busy='true'] {
    color: var(--text-muted);
    cursor: progress;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  /* 1 280 px (the Watch container, so the gallery's frames behave as the window). */
  @container watch (max-width: 1380px) {
    .alert {
      column-gap: var(--space-5);
      padding: 0 var(--space-5);
    }
    .ack {
      height: 56px;
      padding: 0 var(--space-5);
      font-size: 22px;
    }
  }
</style>
