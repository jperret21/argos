<!--
  Chart lab shell: one chart family per tab on a full stage (like a section
  of the app), chosen by tab or ?demo=<id>, judged and screenshotted at
  1440 x 900 / 1280 x 800. One simulated clock drives every live chart: the
  night of 2026-11-01 replays at x1 to x600 (the real cadence is ~51.5 s per
  frame, so x60 gives about one frame a second).
-->
<script lang="ts">
  import type { Component } from 'svelte';
  import Icon from '../../lib/components/Icon.svelte';
  import { tooltip } from '../../lib/components/tooltip';
  import { engineName, env, LAB_THEMES, type MotionPref, setMotion, setTheme, THEME_LABEL, toasts } from './env.svelte';
  import { clock, SCENES, type Speed } from './sim/stream.svelte';
  import { clockUtc, grouped } from './core/format';
  import LightCurveDemo from './charts/LightCurveDemo.svelte';
  import PlotWall from './charts/PlotWall.svelte';
  import VCurve from './charts/VCurve.svelte';
  import ConditionsTimeline from './charts/ConditionsTimeline.svelte';
  import VisibilityTimeline from './charts/VisibilityTimeline.svelte';
  import HistogramStretch from './charts/HistogramStretch.svelte';
  import MiniCharts from './mini/MiniCharts.svelte';
  import InContext from './charts/InContext.svelte';

  interface Demo {
    id: string;
    n: number;
    title: string;
    proves: string;
    component: Component;
  }

  const DEMOS: Demo[] = [
    { id: 'curve', n: 1, title: 'Light curve', proves: 'Target, check and comparison ensemble on one linked UTC / JD / BJD axis; shape-coded flags; live append that never moves a manual zoom; follow mode; one cursor readout for every series; TSV / PNG hooks; update cost measured.', component: LightCurveDemo },
    { id: 'wall', n: 2, title: 'Plot wall', proves: 'Review small multiples: one star per cell, a session health strip, linked time cursor and zoom, click-to-select a time across every cell, cell menu (copy, PNG, expand).', component: PlotWall },
    { id: 'vcurve', n: 3, title: 'V-curve', proves: 'Autofocus building point by point: coarse then fine sweep, weighted hyperbola fit with its uncertainty, the asymptotes, the chosen position and the verdict.', component: VCurve },
    { id: 'conditions', n: 4, title: 'Conditions', proves: 'HFD / FWHM, sky, stars, airmass as small multiples with a now-line that shows the age of the last frame, the attention rule drawn where it fired, a draggable threshold.', component: ConditionsTimeline },
    { id: 'visibility', n: 5, title: 'Visibility', proves: 'Altitude over the night: twilight as luminance steps, minimum altitude, meridian, Moon, planned run, now-line, frames taken so far.', component: VisibilityTimeline },
    { id: 'histogram', n: 6, title: 'Histogram', proves: 'Live frame histogram with keyboard-operable B / M / W handles, clipped fractions, the display transfer and ramp, sensor saturation, linear / log counts.', component: HistogramStretch },
    { id: 'mini', n: 7, title: 'Mini charts', proves: 'Glanceable sparklines and meters for status chips, rail rows and the glance view: frame age against cadence, run progress, HFD with its rule, altitude to the limit.', component: MiniCharts },
    { id: 'context', n: 8, title: 'In context', proves: 'The charts in the Observe › Run space at full size: light curve in the band under the image, Run and Conditions cards with mini-charts, status-bar chips.', component: InContext },
  ];

  function initialDemo(): string {
    const id = new URLSearchParams(location.search).get('demo');
    return DEMOS.some((d) => d.id === id) ? (id as string) : 'curve';
  }

  let current = $state(initialDemo());
  const demo = $derived(DEMOS.find((d) => d.id === current) ?? DEMOS[0]);
  const engine = engineName();

  function choose(id: string): void {
    current = id;
    try {
      const url = new URL(location.href);
      url.searchParams.set('demo', id);
      history.replaceState(null, '', url);
    } catch {
      /* the URL is a convenience */
    }
  }

  function tabKey(e: KeyboardEvent): void {
    const i = DEMOS.findIndex((d) => d.id === current);
    let j = i;
    if (e.key === 'ArrowRight') j = (i + 1) % DEMOS.length;
    else if (e.key === 'ArrowLeft') j = (i - 1 + DEMOS.length) % DEMOS.length;
    else return;
    e.preventDefault();
    choose(DEMOS[j].id);
    document.getElementById(`lab-tab-${DEMOS[j].id}`)?.focus();
  }

  const MOTION: { id: MotionPref; label: string }[] = [
    { id: 'system', label: 'System' },
    { id: 'reduced', label: 'Reduced' },
  ];
  const SPEEDS: Speed[] = [1, 10, 60, 600];

  // URL: ?t=22:41 seeks, ?speed=600, ?paused=1 (screenshots).
  {
    const q = new URLSearchParams(location.search);
    const t = q.get('t');
    if (t && /^\d\d:\d\d(:\d\d)?$/.test(t)) {
      const [h, m, s = '0'] = t.split(':');
      const day = Number(h) < 12 ? 2 : 1;
      clock.seek(Date.UTC(2026, 10, day, Number(h), Number(m), Number(s)) / 1000);
    }
    const sp = Number(q.get('speed'));
    if (SPEEDS.includes(sp as Speed)) clock.speed = sp as Speed;
    if (q.get('paused') === '1') clock.playing = false;
    if (q.get('stalled') === '1') clock.stalled = true;
  }
  clock.start();
  // ?chrome=0: no lab header, the stage is the whole window (true 1440 x 900 compositions).
  const chrome = new URLSearchParams(location.search).get('chrome') !== '0';

  const nowText = $derived(clockUtc(clock.now));
</script>

<div class="lab" class:bare={!chrome}>
  {#if chrome}
  <header class="bar">
    <div class="brand">
      <span class="mark"><Icon name="about" size={22} /></span>
      <span class="word">ARGOS</span>
      <span class="divider"></span>
      <span class="lab-eyebrow">Lab · live charts</span>
    </div>
    <div class="tabs" role="tablist" aria-label="Charts" tabindex="-1" onkeydown={tabKey}>
      {#each DEMOS as d (d.id)}
        <button id="lab-tab-{d.id}" role="tab" aria-selected={d.id === current} aria-controls="lab-stage" tabindex={d.id === current ? 0 : -1} onclick={() => choose(d.id)}>
          <span class="n num">{d.n}</span>{d.title}
        </button>
      {/each}
    </div>
    <span class="lab-chip engine">{engine}</span>
  </header>

  <div class="sub">
    <p class="proves"><b>{demo.title}.</b> {demo.proves}</p>
    <div class="controls">
      <div class="clock" role="group" aria-label="Simulated clock">
        <button
          class="lab-tool s"
          aria-label={clock.playing ? 'Pause the simulated night' : 'Resume the simulated night'}
          use:tooltip={{ text: clock.playing ? 'Pause the night' : 'Resume the night' }}
          onclick={() => (clock.playing = !clock.playing)}
        >
          <Icon name={clock.playing ? 'pause' : 'start'} size={16} />
        </button>
        <span class="now num"><b>{nowText}</b> UTC</span>
        <span class="frames num">{grouped(clock.night.n)} frames</span>
        <div class="lab-seg mono" role="radiogroup" aria-label="Clock speed">
          {#each SPEEDS as s (s)}
            <button role="radio" aria-checked={clock.speed === s} onclick={() => (clock.speed = s)}>×{s}</button>
          {/each}
        </div>
        <div class="lab-seg mono" role="radiogroup" aria-label="Jump to a moment of the night">
          {#each SCENES as sc (sc.id)}
            <button role="radio" aria-checked={Math.abs(clock.now - sc.t) < 30} onclick={() => clock.seek(sc.t)}>{sc.label}</button>
          {/each}
        </div>
        <button class="lab-btn stall" aria-pressed={clock.stalled} onclick={() => (clock.stalled = !clock.stalled)} use:tooltip={{ text: 'Stop new frames while the clock runs (a frozen run)' }}>No frames</button>
      </div>
      <span class="lab-eyebrow">Motion</span>
      <div class="lab-seg" role="radiogroup" aria-label="Motion">
        {#each MOTION as m (m.id)}
          <button role="radio" aria-checked={env.motion === m.id} onclick={() => setMotion(m.id)}>{m.label}</button>
        {/each}
      </div>
      <span class="lab-eyebrow">Theme</span>
      <div class="lab-seg" role="radiogroup" aria-label="Theme">
        {#each LAB_THEMES as t (t)}
          <button role="radio" aria-checked={env.theme === t} onclick={() => setTheme(t)}>{THEME_LABEL[t]}</button>
        {/each}
      </div>
    </div>
  </div>
  {/if}

  <main class="stage">
    <div id="lab-stage" class="panel" role="tabpanel" aria-labelledby="lab-tab-{demo.id}">
      {#key demo.id}
        <demo.component />
      {/key}
    </div>
  </main>

  <div class="toasts" role="status" aria-live="polite">
    {#each toasts as t (t.id)}
      <div class="toast">{t.text}</div>
    {/each}
  </div>
</div>

<style>
  .lab {
    display: grid;
    grid-template-rows: 40px 34px minmax(0, 1fr);
    height: 100vh;
    min-width: 1024px;
  }
  .lab.bare {
    grid-template-rows: minmax(0, 1fr);
  }
  .bar {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    padding: 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex: none;
  }
  .mark {
    display: inline-flex;
    color: var(--accent);
  }
  .word {
    font-weight: var(--weight-semibold);
    font-size: 15px;
    letter-spacing: -0.065em;
    padding-right: 2px;
  }
  .divider {
    width: 1px;
    height: 16px;
    margin: 0 var(--space-2);
    background: var(--border);
  }
  .tabs {
    display: flex;
    align-items: stretch;
    height: 100%;
    flex: 1;
    min-width: 0;
    overflow: hidden;
  }
  .tabs button {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: 0 var(--space-3);
    border: 0;
    background: none;
    color: var(--text-muted);
    font-size: var(--text-s);
    white-space: nowrap;
    cursor: pointer;
  }
  .tabs button:hover,
  .tabs button[aria-selected='true'] {
    color: var(--fg);
  }
  .tabs button[aria-selected='true']::after {
    content: '';
    position: absolute;
    left: var(--space-3);
    right: var(--space-3);
    bottom: -1px;
    height: 2px;
    background: var(--accent);
  }
  .n {
    color: var(--fg-muted);
    font-size: var(--text-2xs);
  }
  .engine {
    flex: none;
  }
  .sub {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    padding: 0 var(--space-4);
    background: var(--bg-2);
    border-bottom: var(--border-w) solid var(--border-soft);
    min-width: 0;
  }
  .proves {
    flex: 1;
    min-width: 0;
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .proves b {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .controls {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex: none;
  }
  .controls .lab-seg + .lab-eyebrow {
    margin-left: var(--space-2);
  }
  .clock {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding-right: var(--space-3);
    margin-right: var(--space-1);
    border-right: var(--border-w) solid var(--border-soft);
  }
  .now {
    color: var(--text-muted);
    font-size: var(--text-xs);
    min-width: 92px;
  }
  .now b {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .frames {
    color: var(--text-muted);
    font-size: var(--text-xs);
    min-width: 70px;
  }
  .stall {
    height: 24px;
    font-size: var(--text-xs);
  }
  .stage {
    min-height: 0;
    overflow: hidden;
  }
  .panel {
    height: 100%;
  }
  .toasts {
    position: fixed;
    right: var(--space-4);
    bottom: var(--space-4);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    z-index: var(--z-toast);
    pointer-events: none;
  }
  .toast {
    padding: var(--space-2) var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--surface);
    box-shadow: var(--shadow-2);
    color: var(--fg);
    font-size: var(--text-s);
  }
</style>
