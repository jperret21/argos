<!--
  Component gallery, wave 3, workspace / viewer / charts (development only, part of
  /?gallery=1): the Observe task modes (ModeBar, Arrange, Band), the image HUD, the
  extended Histogram, the exposure check, the V-curve, the Conditions timeline and the
  mini charts, each in its states, on deterministic synthetic data (fixtures.ts).
  Sections are [data-gallery="w3-<name>"] for element screenshots.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import type { Theme } from '../../../app/theme';
  import { ConditionsStore } from '../../../charts/conditions.svelte';
  import ConditionsTimeline from '../../../charts/ConditionsTimeline.svelte';
  import ConditionsTools from '../../../charts/ConditionsTools.svelte';
  import { ConditionsView } from '../../../charts/conditionsView.svelte';
  import AgeMeter from '../../../charts/mini/AgeMeter.svelte';
  import Sparkline from '../../../charts/mini/Sparkline.svelte';
  import VCurvePlot from '../../../charts/VCurvePlot.svelte';
  import { verdict } from '../../../charts/vcurve';
  import { int, fixed, seconds } from '../../../format/number';
  import Hud from '../../../viewer/Hud.svelte';
  import { cursorReadout, frameChips, miniHistogram, type FrameHeaderV3 } from '../../../viewer/hud';
  import { autoStf, histogram16, type StretchParams } from '../../../viewer/stretch';
  import Histogram from '../../Histogram.svelte';
  import ArrangePopover from '../ArrangePopover.svelte';
  import Band from '../Band.svelte';
  import { exposureCheck } from '../exposure';
  import ExposureCheck from '../ExposureCheck.svelte';
  import ModeBar from '../ModeBar.svelte';
  import { ObserveWorkspace } from '../workspace.svelte';
  import { autofocus, conditionsRows, NOW } from './fixtures';

  let theme = $state<Theme>('observatory');
  onMount(() => {
    const read = () => (theme = (document.documentElement.dataset.theme as Theme) || 'observatory');
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  });

  // -- Modes -------------------------------------------------------------------------------
  const ws = new ObserveWorkspace({ store: null });
  const wsChanged = new ObserveWorkspace({ store: null });
  wsChanged.setCard('mount', 'hidden');
  wsChanged.setBandHeight(220);
  const keyFor = (id: string) => ({ 'observe.mode.framing': 'Alt+1', 'observe.mode.focus': 'Alt+2' })[id];

  // -- HUD -----------------------------------------------------------------------------------
  const header = (extra: Partial<FrameHeaderV3>): FrameHeaderV3 => ({
    seq: 1284,
    width: 1080,
    height: 1920,
    channels: 1,
    dtype: 'uint16',
    pixel_offset: 256,
    exposure_s: 2,
    timestamp: '2026-11-08T21:34:05Z',
    source: 'simulator',
    stats: { min: 1600, max: 65535, median: 1800, mad: 25, mean: 1830 },
    origin: 'live',
    filter: 'IR',
    frame_type: 'light',
    ...extra,
  });

  // A synthetic frame histogram: sky 1 800 +/- 25, a tail of stars, 40 px clipped.
  const pixels = (() => {
    const px = new Uint16Array(400_000);
    let s = 1;
    const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
    for (let i = 0; i < px.length; i++) {
      const g = (rnd() + rnd() + rnd() + rnd() - 2) * 25 * 1.7;
      px[i] = Math.max(0, Math.round(1800 + g + (rnd() < 0.0015 ? 30000 * rnd() ** 3 : 0)));
    }
    for (let i = 0; i < 40; i++) px[i * 997] = 65535;
    return px;
  })();
  const hist = histogram16(pixels);
  let levels = $state<StretchParams>({ ...autoStf(hist), mode: 'linear' });
  const mini = $derived(miniHistogram(hist, levels));
  const TINTS: Record<Theme, [number, number, number]> = { observatory: [1, 1, 1], charcoal: [1, 1, 1], 'night-red': [0.847, 0, 0] };

  // -- Exposure check ---------------------------------------------------------------------------
  const clip = { topCode: 65535, step: 1, clipped: 40, aboveLevel: 52, fraction: 40 / 400000 };
  const peaks = (seq: number, values: number[]) => ({ seq, result: { stars: values.map((peak, i) => ({ peak, x: 100 * i, y: 50 * i })), sky: 1800, sigma: 25, maxima: 300 } });
  const checkMixed = exposureCheck({ seq: 9, peaks: peaks(9, [65535, 53800, 41200, 30100, 22050]), clip, metrics: { seq: 9, hfd_px: 2.64, fwhm_px: 1.71, star_count: 238, sky_adu: 1799.5 }, linearity: 50000, fullWell: 60000 });
  const checkSafe = exposureCheck({ seq: 9, peaks: peaks(9, [38200, 31000, 24400, 19800]), clip: { ...clip, clipped: 0 }, metrics: null, linearity: 50000, fullWell: 60000, rows: 4 });
  const checkWaiting = exposureCheck({ seq: 10, peaks: peaks(9, [40000]), clip, metrics: null, linearity: 50000, fullWell: 60000 });

  // -- V-curve ------------------------------------------------------------------------------------
  const AF = (['coarse', 'fine', 'done', 'rejected', 'stopping', 'cancelled'] as const).map((k) => ({ k, af: autofocus(k) }));
  const pos = (v: number) => int(Math.round(v));
  const px = (v: number) => `${fixed(v, 2)} px`;

  // -- Conditions ---------------------------------------------------------------------------------
  const store = new ConditionsStore();
  store.cols.fill({ rows: conditionsRows(), first_seq: 1, last_seq: null, boot_id: 'gallery' });
  store.version++;
  const stale = new ConditionsStore();
  stale.cols.fill({ rows: conditionsRows(1700, 400), first_seq: 1, last_seq: null, boot_id: 'gallery' });
  stale.version++;
  const empty = new ConditionsStore();
  const view = new ConditionsView(['focus', 'stars', 'sky'], false);
  const view2 = new ConditionsView(['focus', 'airmass'], false);
  const clock = () => NOW;
  const clockLate = () => NOW;
</script>

<section data-gallery="w3-modes" id="w3-modes">
  <h2>Observe task modes <span>D1: Framing, Focus and Field (wave 4) in this version; Run (waves 5, 6) listed, unavailable with the reason; a dot marks a mode whose layout changed</span></h2>
  <div class="row top">
    <figure><ModeBar {ws} {keyFor} /><figcaption>live: click, arrows, Alt+1 / Alt+2</figcaption></figure>
    <figure><ModeBar ws={wsChanged} {keyFor} /><figcaption>Framing changed (dot)</figcaption></figure>
    <figure><ArrangePopover ws={wsChanged} preview /><figcaption>Arrange, Framing changed</figcaption></figure>
  </div>
  <div class="row top">
    <figure class="wide">
      <div class="band-demo" style:height="120px">
        <Band mode="framing" height={120} compact={false} userHeight={null} hideKey="H" onhide={() => {}} onfit={() => {}}>
          {#snippet children({ height })}<p class="filler num">content {height} px</p>{/snippet}
        </Band>
      </div>
      <figcaption>band, fits the image</figcaption>
    </figure>
    <figure class="wide">
      <div class="band-demo" style:height="120px">
        <Band mode="focus" height={120} compact={false} userHeight={180} hideKey="H" onhide={() => {}} onfit={() => {}}>
          {#snippet children({ height })}<p class="filler num">content {height} px</p>{/snippet}
        </Band>
      </div>
      <figcaption>band, set by the observer: Fit to image</figcaption>
    </figure>
  </div>
</section>

<section data-gallery="w3-hud" id="w3-hud">
  <h2>Image HUD <span>screen space; the frame on screen, never the next one; cursor readout on the image (D6); 64-bin histogram when the band does not show the levels</span></h2>
  <div class="row top">
    {#each [
      { cap: 'live, cursor, histogram', chips: frameChips({ header: header({}), live: true, exposing: false, stale: false, object: 'RR Lyr' }, seconds), cursor: cursorReadout({ x: 512, y: 1001, value: 1834 }), mini },
      { cap: 'Dark shot, saved; RA / Dec (W4)', chips: frameChips({ header: header({ origin: 'single', frame_type: 'dark', filter: 'Dark' }), live: false, exposing: false, stale: false, object: 'RR Lyr', savedName: 'RR_Lyr_Dark_Dark_e2000ms_g80_1.fit' }, seconds), cursor: cursorReadout({ x: 12, y: 1900, value: 1601 }, { ra: '19h 25m 27.9s', dec: '+42° 47′ 04″' }), mini: null },
      { cap: 'not current: last frame', chips: frameChips({ header: header({}), live: true, exposing: false, stale: true, object: 'RR Lyr', cropped: true }, seconds), cursor: null, mini: null },
      { cap: 'opened file', chips: frameChips({ header: header({ source: 'file', origin: 'file', file_name: 'RR_Lyr_IR_Light_e30000ms_g80_212.fit', epoch_utc: '2026-09-25T20:05:16Z' }), live: false, exposing: false, stale: false }, seconds), cursor: null, mini },
    ] as h (h.cap)}
      <figure>
        <div class="hud-demo">
          <Hud chips={h.chips} cursor={h.cursor} mini={h.mini} rect={{ left: 0, top: 0, width: 520, height: 150 }} stage={{ width: 520, height: 150 }} {theme} />
        </div>
        <figcaption>{h.cap}</figcaption>
      </figure>
    {/each}
    <figure>
      <div class="hud-demo">
        <Hud chips={[]} cursor={null} mini={null} rect={null} stage={{ width: 520, height: 150 }} dragReadout="Band 220 px · image 728 × 410 · side margins 110 px" {theme} />
      </div>
      <figcaption>a separator dragged: the layout cost</figcaption>
    </figure>
  </div>
</section>

<section data-gallery="w3-histogram" id="w3-histogram">
  <h2>Histogram, wave 3 <span>B / M / W focusable (arrows one ADU step, Shift ×10), clipped fractions, transfer curve, the exact display ramp (D11)</span></h2>
  <div class="row top">
    <figure class="hist-demo">
      <Histogram histogram={hist} {levels} {theme} height={150} handles clipped transfer ramp tint={TINTS[theme]} onlevel={(p) => (levels = { ...levels, ...p })} />
      <figcaption>live: drag or focus a handle</figcaption>
    </figure>
    <figure class="hist-demo">
      <Histogram histogram={hist} levels={{ ...levels, mode: 'asinh', black: 1700, white: 2600 }} {theme} height={150} handles clipped transfer ramp tint={TINTS[theme]} />
      <figcaption>asinh, wider window</figcaption>
    </figure>
  </div>
</section>

<section data-gallery="w3-exposure" id="w3-exposure">
  <h2>Exposure check <span>peak, not picture: true-length bars to 65 535 with the linearity limit (dashed) and full well; words, never an OK badge</span></h2>
  <div class="row top">
    <figure class="check-demo"><ExposureCheck check={checkMixed} linearityAdu={50000} fullWellAdu={60000} /><figcaption>clipped, non-linear, fine</figcaption></figure>
    <figure class="check-demo"><ExposureCheck check={checkSafe} linearityAdu={50000} fullWellAdu={60000} /><figcaption>every star linear; metrics not arrived</figcaption></figure>
    <figure class="check-demo"><ExposureCheck check={checkWaiting} /><figcaption>measuring this frame</figcaption></figure>
    <figure class="check-demo"><ExposureCheck check={checkWaiting} unsupported /><figcaption>no worker in this engine</figcaption></figure>
  </div>
</section>

<section data-gallery="w3-vcurve" id="w3-vcurve">
  <h2>V-curve <span>fitted filled, the rest hollow; hyperbola ± 1σ and asymptotes (display model); the worker’s parabola dotted; provisional vertex dashed; the decision in brass</span></h2>
  <div class="vgrid">
    {#each AF as { k, af } (k)}
      {@const v = verdict(af, pos, px)}
      <figure class="vc-demo">
        <div class="vc-plot"><VCurvePlot {af} {theme} legend={k === 'done'} /></div>
        <figcaption>{k} · {v.state}: {v.text}</figcaption>
      </figure>
    {/each}
  </div>
</section>

<section data-gallery="w3-conditions" id="w3-conditions">
  <h2>Conditions timeline <span>D6: up to three small multiples to now; the gap after the newest point is the age of the last frame; overdue gaps hatched and named; drag to zoom (kept), F fits</span></h2>
  <figure class="cond-demo">
    <div class="cond-tools"><ConditionsTools {store} {view} {clock} /></div>
    <div class="cond-plot"><ConditionsTimeline {store} {view} {theme} {clock} rows /></div>
    <figcaption>drawer tab: values of the last frame with their sparklines, three plots</figcaption>
  </figure>
  <div class="row top">
    <figure class="cond-small">
      <div class="cond-plot"><ConditionsTimeline store={stale} view={view2} {theme} clock={clockLate} expecting /></div>
      <figcaption>live view on, no frame for 6 min 40 s: overdue, hatched</figcaption>
    </figure>
    <figure class="cond-small">
      <div class="cond-plot"><ConditionsTimeline {store} {view} {theme} {clock} window={1800} metrics={['focus']} /></div>
      <figcaption>Focus band trend: HFD and FWHM, last 30 min</figcaption>
    </figure>
    <figure class="cond-small">
      <div class="cond-plot"><ConditionsTimeline store={empty} {view} {theme} {clock} /></div>
      <figcaption>no frame yet</figcaption>
    </figure>
  </div>
</section>

<section data-gallery="w3-mini" id="w3-mini">
  <h2>Mini charts <span>neutral inks; the newest value a dot; age against the observed cadence</span></h2>
  <div class="row">
    <figure>
      <Sparkline width={120} height={26} version={1} {theme} label="HFD, last hour" spec={(ink) => ({ xs: store.cols.cols.t, ys: store.cols.cols.hfd, n: store.cols.n, x0: NOW - 3600, x1: NOW, color: ink.fgMuted.a(), lastDot: true })} />
      <figcaption>HFD, last hour</figcaption>
    </figure>
    <figure>
      <Sparkline width={120} height={26} version={1} {theme} label="Airmass, inverted" spec={(ink) => ({ xs: store.cols.cols.t, ys: store.cols.cols.airmassMount, n: store.cols.n, invert: true, color: ink.fgMuted.a(), lastDot: true, ref: 1.5 })} />
      <figcaption>airmass (1.0 up), limit</figcaption>
    </figure>
    <figure><AgeMeter age={3} cadence={4} /><figcaption>fresh</figcaption></figure>
    <figure><AgeMeter age={50} cadence={4} /><figcaption>late, not overdue</figcaption></figure>
    <figure><AgeMeter age={400} cadence={4} /><figcaption>overdue (live)</figcaption></figure>
    <figure><AgeMeter age={400} cadence={4} expecting={false} /><figcaption>idle: nothing expected</figcaption></figure>
    <figure><AgeMeter age={null} cadence={null} /><figcaption>no frame</figcaption></figure>
  </div>
</section>

<style>
  section {
    padding: var(--space-5) 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  h2 {
    margin: 0 0 var(--space-4);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  h2 span {
    margin-left: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-regular);
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-5);
  }
  .row.top {
    align-items: flex-start;
  }
  .row + .row,
  figure + .row {
    margin-top: var(--space-5);
  }
  figure {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
    margin: 0;
  }
  figcaption {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .wide {
    width: 560px;
  }
  .band-demo {
    width: 100%;
    border: var(--border-w) solid var(--border);
  }
  .filler {
    margin: 0;
    padding: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .hud-demo {
    position: relative;
    width: 520px;
    height: 150px;
    border: var(--border-w) solid var(--border);
    background: var(--viewer-bg);
    overflow: hidden;
  }
  .hist-demo {
    align-items: stretch;
    width: 520px;
    padding: var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    background: var(--bg-2);
  }
  .check-demo {
    width: 300px;
    padding: var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    background: var(--bg-2);
  }
  .vgrid {
    display: grid;
    grid-template-columns: repeat(3, 440px);
    gap: var(--space-5);
  }
  .vc-demo figcaption {
    text-transform: none;
    letter-spacing: 0;
    font-family: var(--font-ui);
    font-size: var(--text-xs);
  }
  .vc-plot {
    width: 440px;
    height: 230px;
    padding: var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    background: var(--bg-2);
  }
  .cond-demo {
    width: 940px;
  }
  .cond-tools {
    display: flex;
    justify-content: flex-end;
    width: 100%;
    padding: var(--space-1);
    border: var(--border-w) solid var(--border-soft);
    border-bottom: none;
    background: var(--bg-2);
  }
  .cond-demo .cond-plot {
    width: 100%;
    height: 184px;
  }
  .cond-plot {
    border: var(--border-w) solid var(--border-soft);
    background: var(--bg-2);
  }
  .cond-small .cond-plot {
    width: 420px;
    height: 170px;
  }
</style>
