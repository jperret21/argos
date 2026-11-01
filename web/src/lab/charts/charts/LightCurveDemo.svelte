<!--
  Tab 1: the live light curve, in the three spaces it will live in (the
  whole stage, the Observe band under the image at 1440 x 900, the drawer),
  on the real-cadence night or on the 4 s stress run (5 000 points preloaded,
  then one new frame per animation frame) to measure live updates.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import LightCurve from './LightCurve.svelte';
  import { clock, FrameStream, fastNight } from '../sim/stream.svelte';
  import type { PerfSummary } from '../core/perf';
  import { grouped } from '../core/format';

  type Frame = 'stage' | 'band' | 'drawer';
  type Source = 'night' | 'stress';

  const params = new URLSearchParams(location.search);
  let frame = $state<Frame>((params.get('frame') as Frame) ?? 'stage');
  let source = $state<Source>('night');
  let stress = $state.raw<FrameStream | null>(null);
  const stream = $derived(source === 'stress' && stress ? stress : clock.night);

  function choose(s: Source): void {
    if (s === 'stress' && !stress) stress = new FrameStream(fastNight());
    source = s;
  }
  if (params.get('source') === 'stress') choose('stress');

  let perf = $state<PerfSummary | null>(null);
  let points = $state(0);
  let fps = $state(0);
  let running = $state(false);
  let finished = $state<{ points: number; median: number; p95: number; max: number; fps: number } | null>(null);

  // Stress driver: preload 5 000 points, then append one per animation frame.
  $effect(() => {
    if (source !== 'stress') return;
    const s = stream;
    untrack(() => {
      s.setCount(5000);
      finished = null;
    });
    running = true;
    let raf = 0;
    const frames: number[] = [];
    let fpsSum = 0;
    let fpsN = 0;
    const loop = (ts: number) => {
      frames.push(ts);
      while (frames.length && ts - frames[0] > 1000) frames.shift();
      fps = frames.length;
      if (s.n >= s.total) {
        running = false;
        if (perf) finished = { points: s.n, median: perf.median, p95: perf.p95, max: perf.max, fps: fpsN ? Math.round(fpsSum / fpsN) : 0 };
        exposeFacts();
        return;
      }
      if (s.n > 5060) {
        fpsSum += fps;
        fpsN++;
      }
      s.setCount(s.n + 1);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      running = false;
    };
  });

  function exposeFacts(): void {
    const el = document.querySelector('[data-lab-facts]');
    el?.setAttribute('data-lab-facts', JSON.stringify({ perf, points, fps, finished, ua: navigator.userAgent }));
  }

  const FRAMES: { id: Frame; label: string }[] = [
    { id: 'stage', label: 'Stage' },
    { id: 'band', label: 'Observe band 928 × 299' },
    { id: 'drawer', label: 'Drawer 1 348 × 216' },
  ];
</script>

<div class="demo" data-lab-facts="">
  <div class="opts">
    <span class="lab-eyebrow">Space</span>
    <div class="lab-seg" role="radiogroup" aria-label="Space">
      {#each FRAMES as f (f.id)}
        <button role="radio" aria-checked={frame === f.id} onclick={() => (frame = f.id)} data-shot="frame-{f.id}">{f.label}</button>
      {/each}
    </div>
    <span class="lab-eyebrow">Data</span>
    <div class="lab-seg" role="radiogroup" aria-label="Data">
      <button role="radio" aria-checked={source === 'night'} onclick={() => choose('night')}>Night · 51.5 s cadence</button>
      <button role="radio" aria-checked={source === 'stress'} onclick={() => choose('stress')} data-shot="stress">Stress · 5 000 + 1 per frame</button>
    </div>
    <span class="grow"></span>
    {#if source === 'stress'}
      <span class="lab-chip"><span class="lab-dot {running ? 'busy' : 'ok'}"></span>{running ? 'appending at display rate' : 'done'}</span>
      <span class="lab-chip"><b>{grouped(points)}</b> pts × 3 facets</span>
      <span class="lab-chip"><b>{fps}</b> fps</span>
      {#if perf}
        <span class="lab-chip">update median <b>{perf.median.toFixed(1)}</b> · p95 <b>{perf.p95.toFixed(1)}</b> · max <b>{perf.max.toFixed(1)}</b> ms</span>
      {/if}
    {/if}
  </div>
  <div class="stage frame-{frame}">
    <div class="frame">
      {#key frame}
        <LightCurve
          {stream}
          compact={frame !== 'stage'}
          facets={frame === 'stage' ? ['target', 'check', 'ensemble'] : ['target', 'check']}
          onperf={(s, n) => {
            perf = s;
            points = n;
          }}
          hooks={(api) => ((window as unknown as { __lc?: unknown }).__lc = api)}
        />
      {/key}
    </div>
    {#if frame !== 'stage'}
      <p class="note">
        {frame === 'band'
          ? 'The band under the image in Observe › Run (layout.ts: 299 px at 1440 × 900 with the rail open). Target over check, one time axis; the ensemble facet stays in the stage and Review.'
          : 'The Observe drawer (full width, 216 px): two facets still readable; legends shrink to their keys.'}
      </p>
    {/if}
  </div>
</div>

<style>
  .demo {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .opts {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: 36px;
    padding: 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
    flex: none;
  }
  .opts .lab-seg + .lab-eyebrow {
    margin-left: var(--space-4);
  }
  .grow {
    flex: 1;
  }
  .stage {
    flex: 1;
    min-height: 0;
    position: relative;
  }
  .frame {
    height: 100%;
  }
  .frame-band,
  .frame-drawer {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    padding: var(--space-5);
    gap: var(--space-3);
    background: var(--bg);
  }
  .frame-band .frame {
    width: 928px;
    height: 299px;
    border: var(--border-w) solid var(--border);
    flex: none;
  }
  .frame-drawer .frame {
    width: min(1348px, 100%);
    height: 216px;
    border: var(--border-w) solid var(--border);
    flex: none;
  }
  .note {
    max-width: 928px;
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>
