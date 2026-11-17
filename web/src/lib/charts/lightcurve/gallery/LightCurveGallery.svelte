<!--
  Wave 5 gallery: LightCurvePlot in every state (development only, mounted by
  lib/components/gallery/Gallery.svelte). Each figure is [data-gallery="lc-…"]
  for element screenshots; the clocks are fixed so captures are stable.

  The stress figure builds a 50 000-frame run (target, check, five
  comparisons: 350 000 points) through the live path, then measures the full
  build of the three facets and the cost of one live append at that size
  (median and p95 of 60 appends, setData + draw of every facet). It runs on
  the button, or at load with ?lcstress=1.
-->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import type { Theme } from '../../../app/theme';
  import Button from '../../../components/Button.svelte';
  import { int } from '../../../format/number';
  import LightCurvePlot, { type LightCurveApi } from '../LightCurvePlot.svelte';
  import { LiveCurveStore } from '../store';
  import { makeRun, unixOfJd, RUN_JD0 } from './fixtures';

  let theme = $state<Theme>('observatory');
  onMount(() => {
    const read = () => (theme = (document.documentElement.dataset.theme as Theme) || 'observatory');
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  });

  // -- Runs (plain objects: the store never enters the reactive graph) -----------------------
  const live = makeRun({ n: 240, seed: 3, flags: true, phase0: 0.82 });
  const overdue = makeRun({ n: 240, seed: 3, flags: true, phase0: 0.82 });
  const whole = makeRun({ n: 840, seed: 11, flags: true, pauseAt: 420, pauseS: 900, phase0: 0.68 });
  const kept = makeRun({ n: 840, seed: 11, flags: true, pauseAt: 420, pauseS: 900, phase0: 0.68 });
  const hovered = makeRun({ n: 840, seed: 11, flags: true, pauseAt: 420, pauseS: 900, phase0: 0.68 });
  const few = makeRun({ n: 3, seed: 5 });
  const noCheck = makeRun({ n: 300, seed: 9, check: null, bjd: false });
  const noCat = makeRun({ n: 300, seed: 13, check: { catalogue: null } });
  const ratio = makeRun({ n: 400, seed: 17, ratioOnly: true });
  const empty = new LiveCurveStore();

  const fixed = (t: number) => () => t;
  const apis: Record<string, LightCurveApi> = {};
  (globalThis as unknown as { __lcApis?: Record<string, LightCurveApi> }).__lcApis = apis;
  const hook = (name: string, then?: (api: LightCurveApi) => void) => (api: LightCurveApi) => {
    const first = !apis[name];
    apis[name] = api;
    if (first && then) setTimeout(() => then(api), 400);
  };

  // A new frame every 2 s on the "live" figure: the Following view slides, a kept zoom would not.
  let liveNow = $state(live.last + 25);
  let feeding = $state(false);
  function feed(): () => void {
    const t = setInterval(() => {
      const s = live.store;
      const tgt = s.primary('target')!;
      const c = tgt.cols;
      const i = c.n - 1;
      const jd = c.jd[i] + 30 / 86400;
      s.apply({ seq: (s.seq ?? 0) + 1, key: tgt.key, role: 'target', name: tgt.name, point: { jd_utc: jd, bjd_tdb: jd + 203.9 / 86400, mag: c.mag[i] + 0.004 * (Math.random() - 0.5) + 0.003, mag_err: c.err[i], formal_mag_err: c.formal[i], sigma_syst: 0.004, airmass: c.airmass[i] }, sigma_syst: 0.004 });
      const k = s.primary('check')!;
      s.apply({ seq: (s.seq ?? 0) + 1, key: k.key, role: 'check', name: k.name, point: { jd_utc: jd, bjd_tdb: jd + 203.9 / 86400, mag: 11.442 + 0.009 * (Math.random() - 0.5), mag_err: 0.0085, formal_mag_err: 0.0075, sigma_syst: 0.004 }, sigma_syst: 0.004 });
      liveNow = unixOfJd(jd) + 5;
    }, 2000);
    return () => clearInterval(t);
  }
  let stopFeed: (() => void) | null = null;
  function toggleFeed(): void {
    if (stopFeed) {
      stopFeed();
      stopFeed = null;
      feeding = false;
    } else {
      stopFeed = feed();
      feeding = true;
    }
  }
  onMount(() => () => stopFeed?.());

  let notes = $state<string[]>([]);
  const notify = (title: string, message?: string) => (notes = [`${title}${message ? ` · ${message}` : ''}`, ...notes].slice(0, 3));

  // -- Stress: 50 000 frames --------------------------------------------------------------------
  let stress = $state.raw<LiveCurveStore | null>(null);
  let stressReport = $state<string | null>(null);
  let stressBusy = $state(false);
  const STRESS_N = 50000;

  async function runStress(): Promise<void> {
    stressBusy = true;
    stressReport = null;
    await new Promise((r) => setTimeout(r, 30));
    const t0 = performance.now();
    const run = makeRun({ n: STRESS_N, seed: 23, flags: true, cadence: 10 });
    const ingest = performance.now() - t0;
    stress = run.store;
    // Let the plots mount, then time a full push and 60 live appends.
    await new Promise((r) => setTimeout(r, 600));
    const api = apis.stress;
    if (!api) {
      stressBusy = false;
      return;
    }
    const full = api.pushNow();
    const s = run.store;
    const tgt = s.primary('target')!;
    const costs: number[] = [];
    for (let k = 0; k < 60; k++) {
      const c = tgt.cols;
      const i = c.n - 1;
      const jd = c.jd[i] + 10 / 86400;
      s.apply({ seq: (s.seq ?? 0) + 1, key: tgt.key, role: 'target', name: tgt.name, point: { jd_utc: jd, bjd_tdb: jd + 0.00236, mag: c.mag[i], mag_err: c.err[i], formal_mag_err: c.formal[i] }, sigma_syst: 0.004 });
      costs.push(api.pushNow());
      await new Promise((r) => requestAnimationFrame(() => r(null)));
    }
    costs.sort((a, b) => a - b);
    const med = costs[costs.length >> 1];
    const p95 = costs[Math.floor(costs.length * 0.95)];
    stressReport = `${int(s.points)} points (${int(STRESS_N)} frames × 7 stars) · ingest ${int(ingest)} ms · first full push ${full.toFixed(1)} ms · append + draw of 3 facets: median ${med.toFixed(1)} ms, p95 ${p95.toFixed(1)} ms`;
    (window as unknown as { __lcStress?: string }).__lcStress = stressReport;
    stressBusy = false;
  }
  onMount(() => {
    if (new URLSearchParams(location.search).has('lcstress')) untrack(() => void runStress());
  });

  const midA = unixOfJd(RUN_JD0) + 2.6 * 3600;
  const midB = midA + 50 * 60;
</script>

<section data-gallery="lightcurve" id="lightcurve">
  <h2>Light curve <span>wave 5 · LightCurvePlot (Observe band, drawer, Review) · synthetic runs through the live path</span></h2>

  <div class="grid">
    <figure data-gallery="lc-band-live">
      <div class="box band"><LightCurvePlot store={live.store} variant="band" expecting clock={() => liveNow} {theme} hooks={hook('live', (a) => a.follow())} /></div>
      <Button label={feeding ? 'Stop the feed' : 'Feed a frame every 2 s'} size="s" onclick={toggleFeed} />
      <figcaption>Observe band · live, Following · target + check · newest ringed</figcaption>
    </figure>
    <figure data-gallery="lc-band-overdue">
      <div class="box band"><LightCurvePlot store={overdue.store} variant="band" expecting clock={fixed(overdue.last + 400)} {theme} /></div>
      <figcaption>Observe band · overdue: no frame for 6m 40s, gap hatched to now</figcaption>
    </figure>
  </div>

  <div class="grid one">
    <figure data-gallery="lc-drawer-whole">
      <div class="box drawer"><LightCurvePlot store={whole.store} facets={['target', 'check', 'ensemble']} {theme} {notify} hooks={hook('whole')} /></div>
      <figcaption>Drawer · Whole run · 840 frames, a 15 min pause (band broken), suspect hollow, saturated x at maximum light</figcaption>
    </figure>
    <figure data-gallery="lc-drawer-kept">
      <div class="box drawer"><LightCurvePlot store={kept.store} facets={['target', 'check', 'ensemble']} axis="jd" {theme} hooks={hook('kept', (a) => (a.zoomTo(midA, midB), a.select(midA + 20 * 60)))} /></div>
      <figcaption>Drawer · Zoom kept on the past · JD axis · a selected frame (rings and line in every facet)</figcaption>
    </figure>
    <figure data-gallery="lc-drawer-hover">
      <div class="box drawer"><LightCurvePlot store={hovered.store} facets={['target', 'check', 'ensemble']} axis="bjd" {theme} hooks={hook('hover', (a) => a.hoverAt(0.62, 'target'))} /></div>
      <figcaption>Drawer · BJD_TDB axis · one readout for every series (UTC, JD, BJD to 5 decimals)</figcaption>
    </figure>
  </div>

  <div class="grid">
    <figure data-gallery="lc-few">
      <div class="box band"><LightCurvePlot store={few.store} variant="band" expecting clock={fixed(few.last + 20)} {theme} /></div>
      <figcaption>3 frames · sparse 8 px markers, capped bars, no spread claimed</figcaption>
    </figure>
    <figure data-gallery="lc-empty">
      <div class="box band"><LightCurvePlot store={empty} variant="band" expecting {theme} /></div>
      <figcaption>Live, no point yet</figcaption>
    </figure>
    <figure data-gallery="lc-no-check">
      <div class="box drawer-s"><LightCurvePlot store={noCheck.store} facets={['target', 'check', 'ensemble']} {theme} /></div>
      <figcaption>No check star · no site (BJD unavailable)</figcaption>
    </figure>
    <figure data-gallery="lc-no-catalogue">
      <div class="box drawer-s"><LightCurvePlot store={noCat.store} facets={['target', 'check']} {theme} /></div>
      <figcaption>Check without a catalogue magnitude: drawn as measured, said so</figcaption>
    </figure>
    <figure data-gallery="lc-flux">
      <div class="box drawer-s"><LightCurvePlot store={ratio.store} facets={['target', 'check', 'ensemble']} flux {theme} /></div>
      <figcaption>Relative flux · ratio-only points (comparisons without magnitudes, S18)</figcaption>
    </figure>
  </div>

  <div class="grid one">
    <figure data-gallery="lc-stress">
      <div class="box drawer">
        {#if stress}
          <LightCurvePlot store={stress} facets={['target', 'check', 'ensemble']} {theme} hooks={hook('stress')} />
        {:else}
          <p class="placeholder">50 000 frames: run the check</p>
        {/if}
      </div>
      <Button label="Run the 50 000-frame check" size="s" busy={stressBusy} onclick={runStress} />
      <figcaption>Stress · <span class="num" data-lc-stress>{stressReport ?? (stressBusy ? 'building…' : 'not run')}</span></figcaption>
    </figure>
  </div>
  {#if notes.length}<p class="notes">{notes[0]}</p>{/if}
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
  .grid {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-5);
    margin-bottom: var(--space-5);
  }
  .grid.one {
    flex-direction: column;
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
    font-size: var(--text-xs);
  }
  .box {
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    overflow: hidden;
  }
  .band {
    width: 640px;
    height: 236px;
  }
  .drawer {
    width: 1200px;
    height: 400px;
  }
  .drawer-s {
    width: 640px;
    height: 330px;
  }
  .placeholder {
    margin: 0;
    padding: var(--space-6);
    color: var(--text-muted);
  }
  .notes {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
