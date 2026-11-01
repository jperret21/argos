<!--
  Time ring (proposal): a circle around a glyph whose arc is the elapsed
  fraction of a timed operation, one vocabulary for the whole UI:

  - track only        this control is HOLD-to-confirm (affordance at rest);
  - arc filling       time elapsed: a hold, an exposure, an autofocus sweep;
  - stepped           reduced motion: the arc advances in quarters (state
                      changes stay visible, nothing glides).

  The arc is exact elapsed time (linear), never eased: a ring that eased
  would misstate how long is left. Butt caps, so 0 draws nothing. Drawn
  with currentColor and tokens only (Night Red safe).
-->
<script lang="ts">
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

  const stroke = 1.5;
  const r = $derived((size - stroke) / 2);
  const shown = $derived(value === null ? null : stepped ? Math.floor(Math.min(1, Math.max(0, value)) * 4 + 1e-9) / 4 : Math.min(1, Math.max(0, value)));
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
    stroke-width: 1.5;
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
