<!--
  State badge: a status dot plus the state in words. The dot carries the tone
  (--status-* tokens); the label stays --fg, so the state is never colour
  alone (BRAND 4.2: Night Red dots sit below 3:1, the label carries it).
-->
<script lang="ts">
  import type { Tone } from '../app/status';

  interface Props {
    tone: Tone;
    label: string;
    /** Quieter variant for dense rows (no outline). */
    plain?: boolean;
  }

  let { tone, label, plain = false }: Props = $props();
</script>

<span class="badge tone-{tone}" class:plain role="status">
  <span class="dot" aria-hidden="true"></span>
  <span class="label">{label}</span>
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
</style>
