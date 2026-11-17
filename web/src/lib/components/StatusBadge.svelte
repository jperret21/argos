<!--
  State badge / chip: a state, a value or an alert in one compact element,
  always double-coded (a shape or a word, never colour alone: BRAND 4.2,
  Night Red dots sit below 3:1, the word carries the state).

  Extended in wave 2 with the Chip variants of the controls lab
  (src/lab/controls/components/Chip.svelte; web/lab/PROPOSAL.md 3.3 and 6):

  tone     idle (hollow ring) · ok · busy · error · active (brass, the one
           thing that must stand out) · stale (dashed edge, muted words: not
           current) · none (no mark)
  variant  badge (card headers, default) · hud (over the image: opaque,
           mono, --elev-hud) · bar (status bar: no box) · alert (attention)
  level    critical (filled --danger disc) · attention (an upright mark, a
           bar over a dot, in --warning) · info (hollow ring). The SHAPE
           differs per level, so Night Red (luminance only) still separates
           them, and the word is always there. Never a triangle: the
           triangle is the check star (BRAND 2.6).
  value    a mono value after the label ("Exp", "2.0 s")
  count    a number in a pill; countTone="critical" fills it
  keys     a key cap ("W")

  `plain` (wave 1) is the quiet variant for dense rows: no outline, natural
  height. `live={false}` drops role="status" for chips in lists (a live
  region per row would be read on every change).
-->
<script lang="ts">
  import type { Tone } from '../app/status';
  import Icon from './Icon.svelte';

  export type BadgeTone = Tone | 'stale' | 'none';
  export type BadgeLevel = 'critical' | 'attention' | 'info';

  interface Props {
    tone?: BadgeTone;
    label: string;
    /** Quieter variant for dense rows (no outline). */
    plain?: boolean;
    variant?: 'badge' | 'hud' | 'bar' | 'alert';
    level?: BadgeLevel;
    icon?: string;
    value?: string;
    count?: number;
    countTone?: 'neutral' | 'critical';
    keys?: string;
    /** role="status" (default true). */
    live?: boolean;
  }

  let {
    tone = 'none',
    label,
    plain = false,
    variant = 'badge',
    level,
    icon,
    value,
    count,
    countTone = 'neutral',
    keys,
    live = true,
  }: Props = $props();

  const LEVEL_WORD: Record<BadgeLevel, string> = { critical: 'Critical', attention: 'Attention', info: 'Info' };
</script>

<span
  class="badge v-{variant} tone-{tone} {level ? `lvl-${level}` : ''}"
  class:plain
  role={live ? 'status' : undefined}
>
  {#if level}
    <span class="mark" aria-hidden="true"></span>
    <span class="visually-hidden">{LEVEL_WORD[level]}:</span>
  {:else if tone !== 'none' && tone !== 'stale'}
    <span class="dot" aria-hidden="true"></span>
  {/if}
  {#if icon}<span class="glyph" aria-hidden="true"><Icon name={icon} size={14} /></span>{/if}
  <span class="label">{label}</span>
  {#if value}<span class="value num">{value}</span>{/if}
  {#if keys}<kbd class="cap" aria-hidden="true">{keys}</kbd>{/if}
  {#if count !== undefined}<span class="count num" class:critical={countTone === 'critical'}>{count}</span>{/if}
</span>

<style>
  .badge {
    --dot: var(--status-idle);
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 22px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-family: var(--font-ui);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    line-height: 1;
    white-space: nowrap;
  }
  .badge.plain {
    height: auto;
    padding: 0;
    border: none;
    background: none;
  }
  /* Over the image: opaque (never translucent over data), mono, one hard shadow. */
  .v-hud {
    gap: 6px;
    height: 20px;
    padding: 0 6px;
    box-shadow: var(--elev-hud);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: 0.02em;
  }
  /* Status bar: no box, the label muted and the value --fg. */
  .v-bar {
    gap: 6px;
    height: 20px;
    padding: 0;
    border: none;
    background: none;
    font-size: var(--text-s);
    font-weight: var(--weight-regular);
  }
  .v-alert {
    height: 24px;
    padding: 0 var(--space-2) 0 6px;
  }

  .dot {
    width: 7px;
    height: 7px;
    flex: none;
    border-radius: var(--radius-round);
    background: var(--dot);
  }
  .tone-ok {
    --dot: var(--status-ok);
  }
  .tone-busy {
    --dot: var(--status-busy);
  }
  .tone-error {
    --dot: var(--status-error);
  }
  .tone-active {
    --dot: var(--accent);
  }
  /* Idle is a hollow ring: the state reads without colour. */
  .tone-idle .dot {
    background: none;
    box-shadow: inset 0 0 0 1.5px var(--status-idle);
  }
  /* Stale: not current. Dashed edge, muted words (BRAND 11.1). */
  .tone-stale {
    border-style: dashed;
    border-color: var(--border);
    color: var(--text-muted);
  }
  .tone-stale.plain,
  .tone-stale.v-bar {
    border: none;
  }

  .glyph {
    display: inline-flex;
    color: var(--fg-muted);
  }
  .value {
    color: var(--fg);
    font-weight: var(--weight-regular);
  }
  .label + .value {
    margin-left: -2px;
  }
  /* A badge reads "Exposure 2.0 s" with the value quieter; the status bar the
     other way round (the key muted, the value --fg). */
  .v-badge .label + .value,
  .v-bar .label {
    color: var(--text-muted);
  }
  .v-bar .label + .value {
    color: var(--fg);
  }

  /* Attention levels: the shape differs per level (Night Red keeps them apart). */
  .mark {
    flex: none;
    width: 10px;
    height: 10px;
  }
  .lvl-critical {
    border-color: var(--danger);
  }
  .lvl-critical .mark {
    border-radius: var(--radius-round);
    background: var(--danger);
  }
  /* An upright mark (a bar over a dot), not a triangle: the triangle is the
     check star everywhere else (BRAND 2.6). */
  .lvl-attention .mark {
    position: relative;
    width: 3px;
    height: 7px;
    margin: 0 3px 4px;
    border-radius: 1px;
    background: var(--warning);
  }
  .lvl-attention .mark::after {
    content: '';
    position: absolute;
    left: 0;
    top: 8px;
    width: 3px;
    height: 3px;
    border-radius: 1px;
    background: var(--warning);
  }
  .lvl-info .mark {
    border-radius: var(--radius-round);
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }

  .count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 16px;
    height: 16px;
    margin-right: -3px;
    padding: 0 4px;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-round);
    color: var(--fg);
    font-size: var(--text-2xs);
  }
  .count.critical {
    border-color: var(--danger);
    background: var(--danger);
    color: var(--on-danger);
    font-weight: var(--weight-medium);
  }
  .cap {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 14px;
    height: 14px;
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
  }
</style>
