<!--
  Wave 6b gallery: Observe Run mode (development only, mounted by
  lib/components/gallery/Gallery.svelte). The Run band at the sizes the layout gives it
  (1440 x 900 and 1280 x 800 with the rail open: 948 x 291 and 788 x 281 px, the separator
  included), its one-row summary below 150 px, the HFD rule drawn, an overdue frame, a
  mid-run autofocus, the empty band; the drawer's tab row with the curve tools (the wave 5
  carry-over) at both widths; the Run suggestion chip. Synthetic data (fixtures.ts), fixed
  clocks. Figures are [data-gallery="w6b-…"] for element screenshots.

  Long-run check (?runstress=1): a 6 000-frame run at 5 s (8 h 20 min; target, check, five
  comparisons: 42 000 points, 6 000 condition rows) in the band, its API on
  globalThis.__runStress (pushNow: one full update of the curve, ms).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import type { Theme } from '../../../app/theme';
  import { ConditionsStore } from '../../../charts/conditions.svelte';
  import CurveTools from '../../../charts/lightcurve/CurveTools.svelte';
  import LightCurvePlot, { type LightCurveApi } from '../../../charts/lightcurve/LightCurvePlot.svelte';
  import { LiveCurveStore } from '../../../charts/lightcurve/store';
  import { CurveDisplay, CurveView } from '../../../charts/lightcurve/view.svelte';
  import Drawer from '../../../components/Drawer.svelte';
  import Band from '../../modes/Band.svelte';
  import { DRAWER_TABS } from '../../modes/layout';
  import ModeSuggestion from '../../modes/ModeSuggestion.svelte';
  import { ObserveWorkspace } from '../../modes/workspace.svelte';
  import LightCurveTools from '../../photometry/LightCurveTools.svelte';
  import { verdict } from '../../photometry/present';
  import { REPORT_OK } from '../../photometry/gallery/fixtures';
  import RunBand from '../RunBand.svelte';
  import { makeRunFixture, type RunFixture } from './fixtures';

  let theme = $state<Theme>('observatory');
  onMount(() => {
    const read = () => (theme = (document.documentElement.dataset.theme as Theme) || 'observatory');
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  });

  const display = new CurveDisplay();
  const rise = makeRunFixture({ n: 176, rise: true });
  const rise1280 = makeRunFixture({ n: 176, rise: true });
  const steady = makeRunFixture({ n: 96, seed: 5 });
  const overdue = makeRunFixture({ n: 120, seed: 9, nowAfter: 420 });
  const af = makeRunFixture({ n: 120, seed: 9, state: 'autofocus', nowAfter: 40 });
  const tab = makeRunFixture({ n: 176, rise: true });
  const tab1280 = makeRunFixture({ n: 176, rise: true });
  const empty: RunFixture = { ...makeRunFixture({ n: 4, seed: 3 }), run: { store: new LiveCurveStore(), first: 0, last: 0, events: 0 }, conditions: new ConditionsStore(null) };

  const stress = typeof location !== 'undefined' && new URLSearchParams(location.search).has('runstress');
  const long = stress ? makeRunFixture({ n: 6000, rise: true, cadence: 5 }) : null;
  const stressHook = (api: LightCurveApi) => {
    (globalThis as unknown as { __runStress?: { api: LightCurveApi; fixture: RunFixture | null } }).__runStress = { api, fixture: long };
  };

  const views = new Map<string, CurveView>();
  const viewOf = (k: string) => {
    let v = views.get(k);
    if (!v) views.set(k, (v = new CurveView(display)));
    return v;
  };
  const clockOf = (f: RunFixture) => () => f.now;

  const ws = new ObserveWorkspace({ store: null });
  ws.setMode('framing');
  ws.suggest('run', 'Run started · RR Lyr (simulated) · 300 frames');
  const keyFor = (id: string) => (id === 'observe.mode.run' ? 'Alt+4' : undefined);
  const noop = () => {};
  const tabs = DRAWER_TABS.filter((t) => t.id !== 'log');
</script>

{#snippet band(f: RunFixture, key: string, w: number, h: number, compact = false, hooks?: (api: LightCurveApi) => void)}
  {@const v = viewOf(key)}
  <div class="band-demo" style:width="{w}px" style:height="{h}px">
    <Band mode="run" height={h} {compact} userHeight={null} hideKey="H" onhide={noop} onfit={noop}>
      {#snippet tools()}<CurveTools view={v} variant="band" />{/snippet}
      {#snippet children({ height, compact: c })}
        <RunBand
          store={f.run.store}
          view={v}
          {height}
          compact={c}
          {theme}
          expecting={f.seq.state === 'running'}
          seq={f.seq}
          now={f.now}
          frameTimes={f.frameTimes}
          marks={f.marks}
          afStep={f.seq.state === 'autofocus' ? { done: 4, total: 9 } : null}
          conditions={f.conditions}
          items={f.items}
          thresholds={f.thresholds}
          onrule={noop}
          clock={clockOf(f)}
          {hooks}
          emptyText={f.run.store.points ? null : 'Waiting for the first measured frame of the run'}
        />
      {/snippet}
    </Band>
  </div>
{/snippet}

<section data-gallery="w6b-run" id="w6b-run">
  <h2>Run mode <span>wave 6b: the live curve under the image (target and check, D25), the run's mini charts, the attention rule drawn read-only with "Change rule…"; synthetic run (the HFD rise near frame 150 of functional-spaces 4.10)</span></h2>
  <div class="col">
    <figure data-gallery="w6b-band-1440">{@render band(rise, 'rise', 948, 290)}<figcaption>1440 x 900, rail open: 948 x 290 px; the HFD rule holds from frame 153 (hatched, dashed line, its threshold on the HFD sparkline)</figcaption></figure>
    <figure data-gallery="w6b-band-1280">{@render band(rise1280, 'rise1280', 788, 280)}<figcaption>1280 x 800, rail open: 788 x 280 px; the mini column narrows (184 px)</figcaption></figure>
    <figure data-gallery="w6b-band-steady">{@render band(steady, 'steady', 948, 290)}<figcaption>a steady run, the newest frame 9 s old</figcaption></figure>
    <figure data-gallery="w6b-band-overdue">{@render band(overdue, 'overdue', 948, 290)}<figcaption>no frame for 7 min: the gap hatched on the curve, the age meter overdue</figcaption></figure>
    <figure data-gallery="w6b-band-af">{@render band(af, 'af', 948, 290)}<figcaption>mid-run autofocus: "Autofocus · 4 of 9" (the record's afStep), no frame expected meanwhile</figcaption></figure>
    <figure data-gallery="w6b-band-compact">{@render band(rise, 'rise-c', 948, 120, true)}<figcaption>below 150 px (120 px, the drawer open): the summary row, then the target's curve alone</figcaption></figure>
    <figure data-gallery="w6b-band-row">{@render band(rise, 'rise-r', 948, 36, true)}<figcaption>36 px: the summary row</figcaption></figure>
    <figure data-gallery="w6b-band-empty">{@render band(empty, 'empty', 948, 290)}<figcaption>a run started, no point measured yet</figcaption></figure>
    {#if long}
      <figure data-gallery="w6b-band-long">{@render band(long, 'long', 948, 290, false, stressHook)}<figcaption>long run: 6 000 frames at 5 s (42 000 points), ?runstress=1</figcaption></figure>
    {/if}
  </div>
</section>

<section data-gallery="w6b-tabrow" id="w6b-tabrow">
  <h2>Drawer tab row <span>the light curve's tools moved out of the plot (wave 5 carry-over): verdict, time axis, zoom, the zoom state's name, U, M, Copy; the plot keeps the drawer's height; narrow headers show the unselected tabs as icons</span></h2>
  <div class="col">
    {#each [{ f: tab, k: 'tab', w: 948 }, { f: tab1280, k: 'tab1280', w: 788 }] as d (d.k)}
      {@const v = viewOf(d.k)}
      <figure data-gallery="w6b-tabrow-{d.w}">
        <div class="drawer-demo" style:width="{d.w}px">
          <Drawer label="Observe drawer" {tabs} tab="light-curve" resizable={false} onclose={noop}>
            {#snippet tools(id: string)}
              {#if id === 'light-curve'}<LightCurveTools view={v} verdict={verdict(REPORT_OK)} />{/if}
            {/snippet}
            {#snippet children(id: string)}
              {#if id === 'light-curve'}
                <LightCurvePlot store={d.f.run.store} view={v} facets={['target', 'check']} variant="drawer" {theme} clock={clockOf(d.f)} label="Live light curve" />
              {/if}
            {/snippet}
          </Drawer>
        </div>
        <figcaption>{d.w} px wide, 216 px tall</figcaption>
      </figure>
    {/each}
  </div>
</section>

<section data-gallery="w6b-suggest" id="w6b-suggest">
  <h2>Run suggestion <span>D1: when a run starts the app proposes Run mode on the image; it never switches by itself</span></h2>
  <figure>
    <div class="viewer-demo"><ModeSuggestion {ws} {keyFor} /></div>
    <figcaption>the button switches (or Alt+4), × dismisses</figcaption>
  </figure>
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
  .col {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
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
  .band-demo {
    border: var(--border-w) solid var(--border);
    border-top-width: 1px;
    background: var(--bg-2);
  }
  .drawer-demo {
    height: 216px;
    border: var(--border-w) solid var(--border);
    background: var(--bg);
  }
  .viewer-demo {
    position: relative;
    width: 640px;
    height: 120px;
    border: var(--border-w) solid var(--border);
    background: var(--viewer-bg);
  }
</style>
