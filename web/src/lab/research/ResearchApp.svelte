<!--
  Lab shell: one demo at a time on a full stage (like a section of the app),
  chosen by tab or ?demo=<id>, so each demo can be judged and screenshotted
  at 1440 x 900 / 1280 x 800. Theme and motion switches apply to all demos.
-->
<script lang="ts">
  import Icon from '../../lib/components/Icon.svelte';
  import type { Component } from 'svelte';
  import CurveWall from './curve/CurveWall.svelte';
  import { detectEngine, env, LAB_THEMES, type LabTheme, type MotionPref, setMotion, setTheme } from './env.svelte';
  import FramePipeline from './frame/FramePipeline.svelte';
  import MotionDemo from './motion/MotionDemo.svelte';
  import PopoverDemo from './popover/PopoverDemo.svelte';
  import SpaceDemo from './space/SpaceDemo.svelte';
  import SupportMatrix from './support/SupportMatrix.svelte';
  import VirtualTableDemo from './table/VirtualTableDemo.svelte';

  interface Demo {
    id: string;
    n: number;
    title: string;
    proves: string;
    component: Component;
  }

  const DEMOS: Demo[] = [
    { id: 'curve', n: 1, title: 'Light curve', proves: 'uPlot: shape-coded markers and error bars, a native band of the check star\'s scatter, a draggable HFD threshold that flags frames, synced crosshair, linked zoom, live append that keeps a manual zoom.', component: CurveWall },
    { id: 'frame', n: 2, title: 'Frame 1 fps', proves: 'Worker statistics with zero-copy transfer, WebGL2 R16UI upload, OKLCH false-colour LUTs, gestures as a Svelte attachment, Canvas 2D sparklines.', component: FramePipeline },
    { id: 'motion', n: 3, title: 'Motion', proves: 'svelte/motion Spring and Tween, animate:flip, hold-to-confirm, a segmented control whose indicator is anchored by CSS: motion for orientation only, values jump.', component: MotionDemo },
    { id: 'space', n: 4, title: 'Space', proves: 'Resizable rail and drawer (pointer capture, keyboard), container queries that reflow one card from rail to drawer, subgrid alignment, :has().', component: SpaceDemo },
    { id: 'popover', n: 5, title: 'Popover', proves: 'Popover API + CSS anchor positioning + @starting-style, with a JavaScript placement fallback that renders the same.', component: PopoverDemo },
    { id: 'table', n: 6, title: 'Table', proves: '10 000 frames in a 24 px-row table with constant DOM size, keyboard selection, sort, data bars, CSS Custom Highlight API for the filter.', component: VirtualTableDemo },
    { id: 'support', n: 7, title: 'Support', proves: 'Feature detection and micro-benchmarks in the engine that opens this page, beside the results recorded in Chromium 156 and WebKit 26.5 (WKWebView).', component: SupportMatrix },
  ];

  function initialDemo(): string {
    const id = new URLSearchParams(location.search).get('demo');
    return DEMOS.some((d) => d.id === id) ? (id as string) : 'curve';
  }

  let current = $state(initialDemo());
  const demo = $derived(DEMOS.find((d) => d.id === current) ?? DEMOS[0]);
  const engine = detectEngine();

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

  const THEME_LABEL: Record<LabTheme, string> = { observatory: 'Observatory', charcoal: 'Charcoal', 'night-red': 'Night Red' };
  const MOTION: { id: MotionPref; label: string }[] = [
    { id: 'system', label: 'System' },
    { id: 'reduced', label: 'Reduced' },
  ];

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
</script>

<div class="lab">
  <header class="bar">
    <div class="brand">
      <span class="mark"><Icon name="about" size={22} /></span>
      <span class="word">ARGOS</span>
      <span class="divider"></span>
      <span class="lab-eyebrow">Lab · stack research</span>
    </div>

    <div class="tabs" role="tablist" aria-label="Demos" tabindex="-1" onkeydown={tabKey}>
      {#each DEMOS as d (d.id)}
        <button
          id="lab-tab-{d.id}"
          role="tab"
          aria-selected={d.id === current}
          aria-controls="lab-stage"
          tabindex={d.id === current ? 0 : -1}
          onclick={() => choose(d.id)}
        >
          <span class="n num">{d.n}</span>{d.title}
        </button>
      {/each}
    </div>

    <span class="lab-chip engine">{engine.family} <b>{engine.version}</b>{engine.embedded ? ' · embedded' : ''}</span>
  </header>

  <div class="sub">
    <p class="proves"><span class="num n">{demo.n}</span><b>{demo.title}.</b> {demo.proves}</p>
    <div class="controls">
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

  <main class="stage">
    <div id="lab-stage" class="panel" role="tabpanel" aria-labelledby="lab-tab-{demo.id}">
      {#key demo.id}
        <demo.component />
      {/key}
    </div>
  </main>
</div>

<style>
  .lab {
    display: grid;
    grid-template-rows: 44px auto minmax(0, 1fr);
    height: 100vh;
    min-width: 1024px;
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
  .tabs button:hover {
    color: var(--fg);
  }
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

  .controls {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex: none;
  }
  .controls .lab-eyebrow + .lab-seg {
    margin-right: var(--space-3);
  }

  .engine {
    flex: none;
  }

  .sub {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    padding: var(--space-2) var(--space-4);
    background: var(--bg-2);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .proves {
    flex: 1;
    min-width: 0;
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .proves b {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .proves .n {
    margin-right: var(--space-2);
  }

  .stage {
    min-height: 0;
    overflow: hidden;
  }
  .panel {
    height: 100%;
  }
</style>
