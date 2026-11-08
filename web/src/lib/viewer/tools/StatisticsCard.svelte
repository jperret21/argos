<!--
  Statistics card (decision D9: a rail card, hidden by default, toggled by I; web/spec/
  04-viewer-and-image-tools.md 2.2 rows 1.7 and 1.5 ROI, 2.3 "Rail cards"; Qt
  statistics_dock.py:22, R1-R11). Three blocks of structured key / value rows in mono:

  - FRAME: mean, median, std, MAD, min, max of every raw sample of the frame on screen
    (ADU), exact from the viewer's histogram; the effective ADC depth from the quantization
    step ("12-bit (16 ADU steps)", Q-O21).
  - STARS: the server's frame_metrics (A26, measured by the core on the full frame, on the
    green plane: sizes in green px, half the raw px of a colour sensor), the population in
    the tooltip (P29), and the star aperture (`imaging.star_radius_px`, 2-30 px, Q-O19)
    that defines them. Metrics of another frame say which.
  - REGION (R): the region box's statistics on raw samples (tools/region.ts), with its
    place; per-colour medians on a colour sensor.
  No value here is the picture's: a palette or a CFA preview never changes them.
-->
<script lang="ts">
  import Card from '../../components/Card.svelte';
  import NumberField from '../../components/NumberField.svelte';
  import { fixed, int } from '../../format/number';
  import type { FrameMetricsRecord } from '../../imaging/modes/exposure';
  import type { Histogram16 } from '../stretch';
  import type { RegionStats } from './region';
  import { adcText, frameStatistics } from './statistics';

  interface Props {
    open?: boolean;
    histogram: Histogram16 | null;
    seq: number | null;
    /** The frame is a colour sensor's mosaic (the Stars block says "green plane"). */
    cfa?: boolean;
    metrics: FrameMetricsRecord | null;
    region: RegionStats | null;
    regionOn: boolean;
    /** `imaging.star_radius_px` (null: unknown). */
    starRadius: number | null;
    /** Save a new star aperture; reject with the server's words to refuse it. */
    onradius?: (px: number) => Promise<unknown>;
    /** Turn the region tool on (R). */
    onregion?: () => void;
    regionKey?: string;
  }

  let { open = $bindable(true), histogram, seq, cfa = false, metrics, region, regionOn, starRadius, onradius, onregion, regionKey }: Props = $props();

  const s = $derived(frameStatistics(histogram));
  const m = $derived(metrics);
  const behind = $derived(m && seq !== null && m.seq !== seq ? `#${int(m.seq)}` : null);
  const dash = '—';
  /** ADU with thousands grouped (BRAND 5, D5), as int() does. */
  const adu = (v: number, d: number) => fixed(v, d, { group: true });
  const num = (v: number | null | undefined, d: number) => (typeof v === 'number' && Number.isFinite(v) ? fixed(v, d) : dash);
  const whole = (v: number | null | undefined) => (typeof v === 'number' && Number.isFinite(v) ? int(v) : dash);
  const pop = $derived(m ? `Measured on ${int(m.n_detected)} detected star${m.n_detected === 1 ? '' : 's'} of frame #${int(m.seq)}` : '');
  /** The core measures on the green plane (raw / 2 on a CFA; the 2 x 2 average on a mono frame too). */
  const green = $derived((m?.plane ?? (cfa ? 'green' : null)) === 'green');
  // The block header names the plane once ("green plane"); the values keep plain px.
  const unit = 'px';
</script>

<Card title="Statistics" icon="statistics" collapsible bind:open>
  {#snippet status()}
    {#if seq !== null}<span class="seq num">#{int(seq)}</span>{/if}
  {/snippet}
  {#snippet summary()}
    {#if s}Median {int(s.median)} · σ {adu(s.std, 1)}{m ? ` · HFD ${num(m.hfd_px, 2)}` : ''}{/if}
  {/snippet}

  <section aria-label="Frame">
    <h3>Frame <span>raw ADU, all pixels</span></h3>
    {#if s}
      <dl class="grid">
        <div><dt>Mean</dt><dd class="num">{adu(s.mean, 1)}</dd></div>
        <div><dt>Median</dt><dd class="num">{adu(s.median, s.median % 1 ? 1 : 0)}</dd></div>
        <div><dt>Std</dt><dd class="num">{adu(s.std, 1)}</dd></div>
        <div><dt>MAD</dt><dd class="num">{adu(s.mad, 1)}</dd></div>
        <div><dt>Min</dt><dd class="num">{int(s.min)}</dd></div>
        <div><dt>Max</dt><dd class="num">{int(s.max)}</dd></div>
        <div class="wide"><dt>ADC</dt><dd class="num" title="From the quantization step of the data: values come in steps of {s.step} ADU">{adcText(s)}</dd></div>
      </dl>
    {:else}
      <p class="none">No frame yet.</p>
    {/if}
  </section>

  <section aria-label="Stars">
    <h3>Stars <span>{green ? 'green plane, server' : 'server'}{behind ? ` · frame ${behind}` : ''}</span></h3>
    <dl class="grid" class:stale={!!behind}>
      <div title={pop}><dt>Stars</dt><dd class="num">{m ? whole(m.star_count) : dash}</dd></div>
      <div title={pop}><dt>HFD</dt><dd class="num">{m ? `${num(m.hfd_px, 2)} ${unit}` : dash}</dd></div>
      <div title={pop}><dt>FWHM</dt><dd class="num">{m ? `${num(m.fwhm_px, 2)} ${unit}` : dash}</dd></div>
      <div title={pop}><dt>Ecc.</dt><dd class="num">{m ? num(m.eccentricity, 3) : dash}</dd></div>
    </dl>
    <div class="radius">
      <NumberField
        label="Star aperture"
        value={starRadius ?? 5}
        unit="px"
        min={2}
        max={30}
        integer
        width="72px"
        hint="HFD and FWHM measurement radius, green px"
        disabledReason={starRadius === null ? 'the server configuration is not loaded yet' : null}
        appliedWord="Saved"
        dirtyWord="Not saved"
        commitVerb="saves"
        send={(v) => onradius?.(v)}
      />
    </div>
  </section>

  <section aria-label="Region">
    <h3>Region <kbd>{regionKey ?? 'R'}</kbd>{#if region}<span class="num">x {int(region.rect.x0)}–{int(region.rect.x1 - 1)} · y {int(region.rect.y0)}–{int(region.rect.y1 - 1)}</span>{/if}</h3>
    {#if regionOn && region}
      <dl class="grid">
        <div><dt>Mean</dt><dd class="num">{adu(region.mean, 1)}</dd></div>
        <div><dt>Median</dt><dd class="num">{adu(region.median, region.median % 1 ? 1 : 0)}</dd></div>
        <div><dt>Std</dt><dd class="num">{adu(region.std, 1)}</dd></div>
        <div><dt>Min</dt><dd class="num">{int(region.min)}</dd></div>
        <div><dt>Max</dt><dd class="num">{int(region.max)}</dd></div>
        <div><dt>N</dt><dd class="num">{int(region.n)}</dd></div>
        {#if region.channels}
          <div class="wide" title="Median of each colour's real samples in the box (the sky per channel)">
            <dt>Median R · G · B</dt>
            <dd class="num">{adu(region.channels.r, region.channels.r % 1 ? 1 : 0)} · {adu(region.channels.g, region.channels.g % 1 ? 1 : 0)} · {adu(region.channels.b, region.channels.b % 1 ? 1 : 0)}</dd>
          </div>
        {/if}
        {#if region.clipped !== null && region.clipped > 0}
          <div class="wide"><dt>Clipped</dt><dd class="num">{int(region.clipped)} px at or above the full well</dd></div>
        {/if}
      </dl>
    {:else}
      <p class="none">
        {regionOn ? 'No frame to measure.' : 'Region statistics are off.'}
        {#if !regionOn && onregion}<button type="button" class="link" onclick={onregion}>Measure a region</button>{/if}
      </p>
    {/if}
  </section>
</Card>

<style>
  section + section {
    margin-top: var(--space-4);
    padding-top: var(--space-3);
    border-top: var(--border-w) solid var(--border-soft);
  }
  h3 {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    margin: 0 0 var(--space-2);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  h3 span {
    color: var(--text-muted);
    letter-spacing: normal;
    text-transform: none;
  }
  kbd {
    padding: 0 3px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    color: var(--fg-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-2) var(--space-3);
    margin: 0;
  }
  .grid div {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .grid .wide {
    grid-column: 1 / -1;
  }
  dt {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
  }
  dd {
    margin: 0;
    color: var(--fg);
    font-size: var(--readout-s);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .stale dd {
    color: var(--text-muted);
  }
  .seq {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .radius {
    margin-top: var(--space-3);
  }
  .none {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .link {
    padding: 0;
    border: 0;
    background: none;
    color: var(--fg);
    font: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;
    cursor: pointer;
  }
  .link:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
</style>
