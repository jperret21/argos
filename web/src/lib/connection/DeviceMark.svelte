<!--
  State mark of a device or a link (01 2.3 wireframes, BRAND 4.2): the
  shape carries the state, the colour only reinforces it, so it reads in
  Night Red where the status colours fall below 3:1.
    filled = connected / reachable    ring = disconnected / unreachable
    half   = busy                      cross = error
    none   = not configured (a short dash)
  `spinning` draws the logo-like busy arc instead (connecting). Always
  decorative: the word next to it, or the tooltip and aria-label of its
  owner, says the state.
-->
<script lang="ts">
  import type { Tone } from '../app/status';
  import type { Mark } from './model';

  interface Props {
    mark: Mark | 'none';
    tone: Tone;
    spinning?: boolean;
    /** 's' 8 px (status bar), 'm' 10 px (tables). */
    size?: 's' | 'm';
  }

  let { mark, tone, spinning = false, size = 'm' }: Props = $props();
</script>

{#if spinning}
  <svg class="spin size-{size} tone-{tone}" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" />
  </svg>
{:else}
  <span class="mark {mark} size-{size} tone-{tone}" aria-hidden="true"></span>
{/if}

<style>
  .mark,
  .spin {
    --c: var(--status-idle);
    display: inline-block;
    flex: none;
    position: relative;
  }
  .size-s {
    width: 8px;
    height: 8px;
  }
  .size-m {
    width: 10px;
    height: 10px;
  }
  .spin.size-s {
    width: 12px;
    height: 12px;
  }
  .spin.size-m {
    width: 14px;
    height: 14px;
  }

  .tone-ok {
    --c: var(--status-ok);
  }
  .tone-busy {
    --c: var(--status-busy);
  }
  .tone-error {
    --c: var(--status-error);
  }
  .tone-active {
    --c: var(--accent);
  }

  .filled {
    border-radius: var(--radius-round);
    background: var(--c);
  }
  .ring {
    border-radius: var(--radius-round);
    box-shadow: inset 0 0 0 1.5px var(--c);
  }
  /* Busy: a ring, its left half filled (a shape, not a gradient effect). */
  .half {
    border-radius: var(--radius-round);
    box-shadow: inset 0 0 0 1.5px var(--c);
    overflow: hidden;
  }
  .half::before {
    content: '';
    position: absolute;
    inset: 0 50% 0 0;
    background: var(--c);
  }
  /* Error: a cross of two 2 px bars. */
  .cross::before,
  .cross::after {
    content: '';
    position: absolute;
    left: 50%;
    top: -1px;
    bottom: -1px;
    width: 2px;
    margin-left: -1px;
    border-radius: 1px;
    background: var(--c);
    transform: rotate(45deg);
  }
  .cross::after {
    transform: rotate(-45deg);
  }
  /* Not configured: a short dash. */
  .none::before {
    content: '';
    position: absolute;
    left: 1px;
    right: 1px;
    top: 50%;
    height: 1.5px;
    margin-top: -0.75px;
    background: var(--c);
  }

  .spin {
    fill: none;
    stroke: var(--c);
    stroke-width: 1.5;
    stroke-linecap: round;
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spin {
      animation: none;
    }
  }
</style>
