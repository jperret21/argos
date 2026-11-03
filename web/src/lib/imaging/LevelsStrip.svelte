<!--
  Levels strip, docked under the image (BRAND 11.1): the display stretch
  lives in the band a 16:9 frame leaves under it, instead of in the right
  rail. ImagingScreen sizes it to that band, so the image keeps its fitted
  size and the dead black bands disappear.

  Full (tall enough): the histogram with its B / M / W handles (drag them),
  the three levels as numbers (keyboard entry), then transfer and rotation.
  Compact (a narrow band, e.g. with the rail closed): one row of the three
  numbers, the transfer and, when the row is wide enough, the rotation.

  Display only: the FITS data and every measurement keep the raw values.
  While auto-stretch is on the levels follow each frame; touching any of
  them freezes the levels on screen and switches to manual. Auto stretch and
  Reset are the toolbar's (A, Shift+A).
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import NumberField from '../components/NumberField.svelte';
  import Segmented from '../components/Segmented.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { fixed, int } from '../format/number';
  import type { RotationMode } from '../viewer/rotation';
  import type { StretchMode } from '../viewer/stretch';
  import Histogram from './Histogram.svelte';

  interface Props {
    /** Height of the strip, CSS px, its top border included. */
    height: number;
    compact?: boolean;
  }

  let { height, compact = false }: Props = $props();
  const app = useApp();

  const levels = $derived(app.levels);
  const hist = $derived(app.shown?.histogram ?? null);
  const stats = $derived(app.shown?.frame.header.stats ?? null);
  const disabled = $derived(!levels);

  // Plot height: the strip minus its padding and the readout line above the plot.
  const plotH = $derived(Math.max(60, height - 1 - 2 * 10 - 20));

  const ROTATIONS: { value: RotationMode; label: string }[] = [
    { value: 'auto', label: 'Auto' },
    { value: '0', label: '0°' },
    { value: '90', label: '90°' },
    { value: '180', label: '180°' },
    { value: '270', label: '270°' },
  ];

  type StatKey = 'min' | 'median' | 'mad' | 'mean' | 'max';
  const STATS: [StatKey, string][] = [
    ['min', 'Min'],
    ['median', 'Median'],
    ['mad', 'MAD'],
    ['mean', 'Mean'],
    ['max', 'Max'],
  ];
  const formatStat = (key: StatKey, v: number) =>
    key === 'min' || key === 'max' ? int(v) : fixed(v, 1, { group: true });

  const MODES: { value: StretchMode; label: string }[] = [
    { value: 'linear', label: 'Linear' },
    { value: 'log', label: 'Log' },
    { value: 'asinh', label: 'Asinh' },
  ];
</script>

{#snippet numbers()}
  <span class="key" aria-hidden="true">Black</span>
  <NumberField
    label="Black level"
    hideLabel
    value={levels ? Math.round(levels.black) : 0}
    unit="ADU"
    min={0}
    max={65535}
    integer
    group
    {disabled}
    onchange={(v) => app.setLevel({ black: v })}
  />
  <span class="key" aria-hidden="true">Mid</span>
  <NumberField
    label="Midtones balance"
    hideLabel
    value={levels ? Number(levels.midtones.toFixed(3)) : 0.5}
    decimals={3}
    min={0.001}
    max={0.999}
    step={0.01}
    {disabled}
    onchange={(v) => app.setLevel({ midtones: v })}
  />
  <span class="key" aria-hidden="true">White</span>
  <NumberField
    label="White level"
    hideLabel
    value={levels ? Math.round(levels.white) : 65535}
    unit="ADU"
    min={0}
    max={65535}
    integer
    group
    {disabled}
    onchange={(v) => app.setLevel({ white: v })}
  />
{/snippet}

{#snippet badge()}
  <StatusBadge
    tone={app.autoStretch ? 'ok' : 'idle'}
    label={app.autoStretch ? 'Auto' : 'Manual'}
    plain
  />
{/snippet}

<section
  class="strip"
  class:compact
  style:height="{height}px"
  aria-label="Display levels"
  data-strip-height={height}
>
  {#if compact}
    <span class="micro">Levels</span>
    {@render badge()}
    <div class="numbers">{@render numbers()}</div>
    <div class="transfer">
      <Segmented
        label="Transfer function"
        options={MODES}
        value={levels?.mode ?? 'linear'}
        {disabled}
        onchange={(mode) => app.setLevel({ mode })}
      />
    </div>
    <div class="rotation">
      <Segmented
        label="Display rotation (clockwise)"
        options={ROTATIONS}
        value={app.rotation}
        onchange={(mode) => app.setRotation(mode)}
      />
    </div>
  {:else}
    <div class="plot">
      <Histogram
        histogram={hist}
        {levels}
        theme={app.theme}
        height={plotH}
        onlevel={(patch) => app.setLevel(patch)}
      />
    </div>

    <div class="column">
      <div class="head">
        <span class="micro">Levels</span>
        {@render badge()}
      </div>
      <div class="grid">{@render numbers()}</div>
    </div>

    <div class="column view">
      <div class="field">
        <span class="micro">Transfer</span>
        <Segmented
          label="Transfer function"
          options={MODES}
          value={levels?.mode ?? 'linear'}
          {disabled}
          onchange={(mode) => app.setLevel({ mode })}
        />
      </div>
      <div class="field">
        <span class="micro">Rotation (display)</span>
        <Segmented
          label="Display rotation (clockwise)"
          options={ROTATIONS}
          value={app.rotation}
          onchange={(mode) => app.setRotation(mode)}
        />
      </div>
      <!-- Exact over every pixel (server), raw ADU: what the levels are set against. -->
      <dl class="stats" aria-label="Frame statistics">
        {#each STATS as [key, label] (key)}
          <div>
            <dt>{label}</dt>
            <dd class="num">{stats ? formatStat(key, stats[key]) : '—'}</dd>
          </div>
        {/each}
      </dl>
    </div>
  {/if}
</section>

<style>
  .strip {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    gap: var(--space-4);
    padding: 10px var(--space-4);
    border-top: var(--border-w) solid var(--border);
    background: var(--bg-2);
    min-width: 0;
    overflow: hidden;
  }

  .strip.compact {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: 0 var(--space-4);
    container-type: inline-size;
  }

  .plot {
    min-width: 0;
  }

  .column {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    height: 20px;
  }

  .grid {
    display: grid;
    grid-template-columns: auto 120px;
    align-items: center;
    gap: var(--space-2) var(--space-3);
  }
  .key {
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .micro {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
    white-space: nowrap;
  }

  /* Two rows of three: grouped values ("1 656", "1 800.0") side by side need a
     column gap well above the group space, which is one full cell in Plex Mono
     (BRAND 5); five columns at 18 px do not fit the strip at 1440 px. */
  .stats {
    display: grid;
    grid-template-columns: repeat(3, auto);
    justify-content: start;
    gap: var(--space-2) var(--space-5);
    margin: var(--space-2) 0 0;
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .stats div {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .stats dt {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .stats dd {
    margin: 0;
    color: var(--fg);
    font-size: var(--readout-s); /* 13 px compact, 16 px Comfortable (D7) */
    white-space: nowrap;
  }

  /* Compact: the three numbers side by side, one row. */
  .numbers {
    display: grid;
    grid-template-columns: repeat(3, auto 112px);
    align-items: center;
    gap: var(--space-2) var(--space-3);
  }
  .transfer {
    width: 200px;
  }
  .rotation {
    width: 230px;
  }
  /* The rotation only when the row has room for it (rail closed). */
  @container (max-width: 1080px) {
    .rotation {
      display: none;
    }
  }
</style>
