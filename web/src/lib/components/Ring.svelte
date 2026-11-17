<!--
  Time ring: a circle around a glyph whose arc is the elapsed fraction of a
  timed operation. One vocabulary for the whole UI (BRAND 2.6 and 8):

  - track only        this control is HOLD-to-confirm (the affordance at rest);
  - arc filling       time elapsed: a hold, an exposure, an autofocus sweep;
  - stepped           reduced motion: the arc advances in quarters (the state
                      stays visible, nothing glides; the numbers stay exact
                      in the tooltip and aria-valuetext).

  The arc is exact elapsed time (linear), never eased: an eased ring would
  misstate how long is left. Butt caps, so 0 draws nothing. currentColor and
  tokens only (Night Red safe); stroke --ring-w.

  Promoted from src/lab/controls/components/Ring.svelte (PROPOSAL 6, W2).
-->
<script lang="ts">
  import { ringFraction } from './values';

  interface Props {
    /** Diameter in px. */
    size: number;
    /** 0..1, or null for the track alone. */
    value?: number | null;
    track?: boolean;
    /** Quantise to quarters (reduced motion). */
    stepped?: boolean;
    tone?: 'accent' | 'danger' | 'current' | 'muted';
  }

  let { size, value = null, track = false, stepped = false, tone = 'accent' }: Props = $props();

  const shown = $derived(ringFraction(value, stepped));
  const r = $derived((size - 1.5) / 2);
</script>

<svg class="ring tone-{tone}" width={size} height={size} viewBox="0 0 {size} {size}" aria-hidden="true">
  {#if track}
    <circle class="track" cx={size / 2} cy={size / 2} {r} />
  {/if}
  {#if shown !== null && shown > 0}
    <circle
      class="arc"
      cx={size / 2}
      cy={size / 2}
      {r}
      pathLength="100"
      stroke-dasharray="{shown * 100} 100"
      transform="rotate(-90 {size / 2} {size / 2})"
    />
  {/if}
</svg>

<style>
  .ring {
    position: absolute;
    left: 50%;
    top: 50%;
    translate: -50% -50%;
    overflow: visible;
    pointer-events: none;
  }
  circle {
    fill: none;
    stroke-width: var(--ring-w);
  }
  .track {
    stroke: var(--border);
  }
  .arc {
    stroke-linecap: butt;
  }
  .tone-accent .arc {
    stroke: var(--accent);
  }
  .tone-danger .arc {
    stroke: var(--danger);
  }
  .tone-current .arc {
    stroke: currentColor;
  }
  .tone-muted .arc {
    stroke: var(--fg-muted);
  }
</style>
