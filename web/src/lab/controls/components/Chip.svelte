<!--
  Chip (proposal extending lib StatusBadge): a state, a value or an alert
  in one compact element, always double-coded (shape or word, never colour
  alone, BRAND 4.2).

  tone     idle (hollow ring) · ok · busy · error · active (brass) · stale
           (dashed edge: not current) · none
  variant  badge (card headers) · hud (over the image, mono) · bar (status
           bar, no box) · alert (attention levels)
  level    critical (filled danger disc) · attention (an upright mark:
           a bar over a dot, the stroke of the lab-attention glyph) ·
           info (hollow ring): the shape differs by level, so Night Red
           (luminance only) still separates them. Never a triangle: the
           triangle is the check-star role (BRAND 2.6, lab synthesis).
  count    a number in a pill; `countTone="critical"` fills it
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';

  interface Props {
    label: string;
    tone?: 'idle' | 'ok' | 'busy' | 'error' | 'active' | 'stale' | 'none';
    variant?: 'badge' | 'hud' | 'bar' | 'alert';
    level?: 'critical' | 'attention' | 'info';
    icon?: string;
    value?: string;
    count?: number;
    countTone?: 'neutral' | 'critical';
    keys?: string;
  }

  let { label, tone = 'none', variant = 'badge', level, icon, value, count, countTone = 'neutral', keys }: Props = $props();
</script>

<span class="chip v-{variant} tone-{tone} {level ? `lvl-${level}` : ''}" role="status">
  {#if level}
    <span class="mark" aria-hidden="true"></span>
  {:else if tone !== 'none' && tone !== 'stale'}
    <span class="dot" aria-hidden="true"></span>
  {/if}
  {#if icon}<span class="glyph"><Icon name={icon} size={14} /></span>{/if}
  <span class="label">{label}</span>
  {#if value}<span class="value num">{value}</span>{/if}
  {#if keys}<kbd class="cap">{keys}</kbd>{/if}
  {#if count !== undefined}<span class="count num" class:critical={countTone === 'critical'}>{count}</span>{/if}
</span>

<style>
  .chip {
    --dot: var(--status-idle);
    display: inline-flex;
    align-items: center;
    gap: 6px;
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
  .v-hud {
    height: 20px;
    padding: 0 6px;
    border-color: var(--border-soft);
    background: var(--bg-2);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: 0.02em;
  }
  .v-bar {
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
  .v-badge .label + .value,
  .v-bar .label {
    color: var(--text-muted);
  }
  .v-bar .label + .value {
    color: var(--fg);
  }

  /* Attention levels: shape differs per level (Night Red keeps them apart). */
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
  /* An upright mark (bar over a dot), not a triangle: the triangle means the
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
  .chip :global(kbd.cap) {
    height: 14px;
    min-width: 14px;
  }
</style>
