<!--
  Framing band (owner decision D1; promoted from src/lab/workspace/observe/bands/
  FramingBand.svelte, web/lab/PROPOSAL.md 3.1 and 6, W3): the display levels and the
  exposure check, side by side, in the space a fitted frame leaves under the image.

  - Levels: the histogram of the frame on screen with B / M / W as focusable handles,
    the clipped fractions, the transfer curve and the exact display ramp (D11); the three
    levels as numbers for typed entry (their one home: the handles carry only their
    letter). Under the fields, what the levels do: the share of pixels shown black and
    white (display only, said in the header's tooltip); the ADC's clipped count has its
    one home in the exposure check. The transfer and the display rotation sit in the
    band's header row (DisplayTools.svelte), so no row is spent on them. Display
    only: the FITS data and every measurement keep the raw values. Auto stretch follows
    each frame; touching a level freezes the levels on screen (manual). Auto and Reset
    are the toolbar's (A, Shift+A).
  - Exposure check: true-length peaks against 65 535 (ExposureCheck.svelte).
  - Below 150 px: one summary row (levels, brightest peak, clipped pixels, sky).
-->
<script lang="ts">
  import type { Theme } from '../../app/theme';
  import type { Palette } from '../../viewer/palettes/lut';
  import NumberField from '../../components/NumberField.svelte';
  import StatusBadge from '../../components/StatusBadge.svelte';
  import { fixed, int } from '../../format/number';
  import type { Histogram16, StretchParams } from '../../viewer/stretch';
  import Histogram from '../Histogram.svelte';
  import { FULL_SCALE, type ExposureCheck as Check } from './exposure';
  import ExposureCheck from './ExposureCheck.svelte';

  interface Props {
    /** Content height (band minus its header), CSS px. */
    height: number;
    compact: boolean;
    histogram: Histogram16 | null;
    levels: StretchParams | null;
    auto: boolean;
    theme: Theme;
    tint: readonly [number, number, number];
    check: Check;
    linearityAdu?: number | null;
    fullWellAdu?: number | null;
    peaksUnsupported?: boolean;
    onlevel: (patch: Partial<StretchParams>) => void;
    /** The palette the viewer draws (the ramp under the histogram shows it). */
    palette?: Palette;
    /** An exposure-check row is hovered: its stars, frame px (null: none), to mark on the image. */
    onhoverstars?: (points: { x: number; y: number }[] | null) => void;
  }

  let {
    height,
    compact,
    histogram,
    levels,
    auto,
    theme,
    tint,
    check,
    linearityAdu = null,
    fullWellAdu = null,
    peaksUnsupported = false,
    onlevel,
    onhoverstars,
    palette = 'neutral',
  }: Props = $props();

  const disabled = $derived(!levels);
  // Plot height: the content minus the padding, the readout line, the ramp and the handle track.
  const plotH = $derived(Math.max(48, Math.round(height - 2 * 8 - 18 - 9 - 22 - 4)));

  const brightest = $derived(check.rows[0] ?? null);

  /** Share of the frame's pixels the levels show pure black / pure white (display only). */
  const shown = $derived.by(() => {
    const h = histogram;
    const p = levels;
    if (!h || !p || h.n === 0) return null;
    let black = 0;
    let white = 0;
    const lo = Math.max(h.min, 0);
    for (let v = lo; v <= h.max; v++) {
      const c = h.counts[v];
      if (!c) continue;
      if (v <= p.black) black += c;
      else if (v >= p.white) white += c;
    }
    return { black: black / h.n, white: white / h.n };
  });
  const pct = (f: number) => (f === 0 ? '0 %' : f < 0.001 ? '< 0.1 %' : `${fixed(f * 100, 1)} %`);
</script>

{#if compact}
  <div class="row num" style:height="{height}px">
    <span class="k">Levels</span>
    {#if levels}
      <span>B {int(levels.black)}</span><span>M {fixed(levels.midtones, 3)}</span><span>W {int(levels.white)}</span>
    {:else}<span>—</span>{/if}
    <span class="k">{auto ? 'auto' : 'manual'}</span>
    <span class="sep" aria-hidden="true"></span>
    <span class="k">Peak</span>
    <span>{brightest ? `${brightest.state === 'clipped' ? 'clipped' : int(brightest.peak)} / ${int(FULL_SCALE)}` : '—'}</span>
    <span class="k">Clipped</span><span>{check.clipped === null ? '—' : `${int(check.clipped)} px`}</span>
    <span class="k">Sky</span><span>{check.sky === null ? '—' : `${int(Math.round(check.sky))} ADU`}</span>
  </div>
{:else}
  <div class="grid">
    <div class="hist">
      <Histogram
        {histogram}
        {levels}
        {theme}
        height={plotH}
        caption={auto ? 'Auto (A) · drag B, M, W' : 'Manual · A returns to auto'}
        handles
        clipped
        transfer
        ramp
        handleValues={false}
        {tint}
        {palette}
        onlevel={(patch) => onlevel(patch)}
      />
    </div>
    <div class="levels">
      <div class="head" title="Display only: the FITS data and every measurement keep the raw values.">
        <span class="micro">Levels · display</span>
        <StatusBadge tone={auto ? 'ok' : 'idle'} label={auto ? 'Auto' : 'Manual'} plain />
      </div>
      <div class="nums">
        <span class="key" aria-hidden="true">B</span>
        <NumberField label="Black level" hideLabel value={levels ? Math.round(levels.black) : 0} unit="ADU" min={0} max={65535} integer group {disabled} onchange={(v) => onlevel({ black: v })} />
        <span class="key" aria-hidden="true">M</span>
        <NumberField label="Midtones balance" hideLabel value={levels ? Number(levels.midtones.toFixed(3)) : 0.5} decimals={3} min={0.001} max={0.999} step={0.01} {disabled} onchange={(v) => onlevel({ midtones: v })} />
        <span class="key" aria-hidden="true">W</span>
        <NumberField label="White level" hideLabel value={levels ? Math.round(levels.white) : 65535} unit="ADU" min={0} max={65535} integer group {disabled} onchange={(v) => onlevel({ white: v })} />
      </div>
      <dl class="shown num" aria-label="What the levels show">
        <div><dt>Shown black</dt><dd>{shown ? pct(shown.black) : '—'}</dd></div>
        <div><dt>Shown white</dt><dd>{shown ? pct(shown.white) : '—'}</dd></div>
      </dl>
    </div>
    <div class="exposure">
      <div class="head"><span class="micro">Exposure check · peak, not picture</span></div>
      <ExposureCheck {check} linearityAdu={linearityAdu} fullWellAdu={fullWellAdu} unsupported={peaksUnsupported} onhover={onhoverstars} />
    </div>
  </div>
{/if}

<style>
  .grid {
    display: grid;
    grid-template-columns: minmax(240px, 1fr) 188px minmax(250px, 300px);
    height: 100%;
    min-height: 0;
  }
  .hist {
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    padding: 8px var(--space-3) 4px;
  }
  .levels,
  .exposure {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
    min-height: 0;
    padding: var(--space-2) var(--space-3);
    border-left: var(--border-w) solid var(--border-soft);
    overflow: hidden;
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    height: 18px;
  }
  .micro,
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
    white-space: nowrap;
  }
  .nums {
    display: grid;
    grid-template-columns: 14px 1fr;
    align-items: center;
    gap: var(--space-1) var(--space-2);
  }
  .shown {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin: auto 0 0;
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .shown div {
    display: flex;
    justify-content: space-between;
    gap: var(--space-2);
  }
  .shown dt {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .shown dd {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .key {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-s);
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: 0 var(--space-3);
    color: var(--fg);
    font-size: var(--text-s);
    white-space: nowrap;
    overflow: hidden;
  }
  .sep {
    width: 1px;
    height: 14px;
    background: var(--border-soft);
  }
</style>
