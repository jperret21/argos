<!--
  Framing band: the display levels (the app's Histogram with B / M / W
  handles, unchanged) and the EXPOSURE CHECK the guide asks for: "check the
  peak, not the picture". The peaks are measured on the frame on screen,
  shown against full scale (65 535) as true-length bars, never as an "OK"
  badge (the saturation flag threshold is not trustworthy, method 3.5).
-->
<script lang="ts">
  import Histogram from '../../../../lib/imaging/Histogram.svelte';
  import type { StretchParams } from '../../../../lib/viewer/stretch';
  import { env } from '../../model/env.svelte';
  import { sim, ws } from '../../model/app.svelte';
  import { NAMED_STARS, TARGET_ID } from '../../model/field';
  import { fixed, int } from '../../model/format';

  interface Props {
    compact: boolean;
    /** Content height (band minus its header), CSS px. */
    height?: number;
  }
  let { compact, height = 260 }: Props = $props();

  const FULL = 65535;
  /** Bar fraction; an unknown peak draws an empty bar, never a full one. */
  const frac = (v: number) => (Number.isFinite(v) ? Math.min(1, Math.max(0, v / FULL)) : 0);
  const levels: StretchParams | null = $derived(ws.autoStretch || !ws.stretch ? (ws.display?.auto ?? null) : ws.stretch);

  const peakTarget = $derived(sim.measured.peaks[TARGET_ID] ?? NaN);
  const comps = $derived(
    NAMED_STARS.filter((s) => s.role === 'comparison')
      .map((s) => ({ s, p: sim.measured.peaks[s.id] ?? NaN }))
      .sort((a, b) => b.p - a.p),
  );
  const brightestComp = $derived(comps[0] ?? null);
  const clipStar = $derived(NAMED_STARS.find((s) => s.id === 9));
  const peakClip = $derived(clipStar ? (sim.measured.peaks[clipStar.id] ?? NaN) : NaN);

  function onlevel(patch: Partial<Omit<StretchParams, 'mode'>>): void {
    const base = levels ?? { black: 0, white: 65535, midtones: 0.5, mode: 'linear' as const };
    ws.stretch = { ...base, ...patch };
    ws.autoStretch = false;
  }

</script>

{#if compact}
  <div class="row num">
    <span class="k">LEVELS</span>
    {#if levels}<span>B {int(levels.black)}</span><span>M {fixed(levels.midtones, 3)}</span><span>W {int(levels.white)}</span>{/if}
    <span class="k">PEAK</span><span>{int(peakTarget)} / {int(FULL)} ADU</span>
    <span class="k">SKY</span><span>{int(sim.measured.sky)} ADU</span>
  </div>
{:else}
  <div class="grid">
    <div class="hist">
      <Histogram
        histogram={ws.display?.histogram ?? null}
        {levels}
        theme={env.theme}
        height={Math.max(80, height - 40)}
        caption={ws.autoStretch ? 'Auto stretch (A) · drag B, M, W to set the levels' : 'Manual levels · A returns to auto'}
        {onlevel}
      />
    </div>
    <div class="levels">
      <h3 class="lab-caps">Levels</h3>
      <dl class="num">
        <dt>Black</dt><dd>{levels ? int(levels.black) : '—'}<span class="u">ADU</span></dd>
        <dt>Mid</dt><dd>{levels ? fixed(levels.midtones, 3) : '—'}<span class="u"></span></dd>
        <dt>White</dt><dd>{levels ? int(levels.white) : '—'}<span class="u">ADU</span></dd>
      </dl>
      <p class="mode">{ws.autoStretch ? 'Auto · linear' : 'Manual · linear'}</p>
    </div>
    <div class="check">
      <h3 class="lab-caps">Exposure check · peak, not picture</h3>
      <ul>
        <li>
          <span class="who"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="5" class="t" /></svg>RR Lyr</span>
          <span class="meter" style:--f={frac(peakTarget)}></span>
          <span class="val num">{int(peakTarget)}</span>
        </li>
        {#if brightestComp}
          <li>
            <span class="who"><svg viewBox="0 0 20 20" aria-hidden="true"><rect x="5.5" y="5.5" width="9" height="9" class="c" /></svg>{brightestComp.s.name?.slice(-3)} · brightest comp.</span>
            <span class="meter" style:--f={frac(brightestComp.p)}></span>
            <span class="val num">{int(brightestComp.p)}</span>
          </li>
        {/if}
        <li class:clip={peakClip >= FULL}>
          <span class="who"><svg viewBox="0 0 20 20" aria-hidden="true"><rect x="5.5" y="5.5" width="9" height="9" class="o" /></svg>{clipStar?.name?.slice(-3)} · candidate</span>
          <span class="meter" style:--f={frac(peakClip)}></span>
          <span class="val num">{peakClip >= FULL ? 'clipped' : int(peakClip)}</span>
        </li>
      </ul>
      <p class="scale num">bars run from 0 to full scale, {int(FULL)} ADU</p>
      <dl class="facts num">
        <dt>Clipped px</dt><dd>{Number.isFinite(sim.measured.clipped) ? int(sim.measured.clipped) : '—'}</dd>
        <dt>Sky</dt><dd>{int(sim.measured.sky)} ADU</dd>
        <dt>HFD</dt><dd>{sim.source === 'server' ? '—' : '6.3 px'}</dd>
        <dt>Stars</dt><dd>{sim.source === 'server' ? '—' : int(2906)}</dd>
      </dl>
    </div>
  </div>
{/if}

<style>
  .grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 128px 372px;
    gap: 0;
    height: 100%;
  }
  .hist {
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    padding: var(--space-2) var(--space-3) var(--space-2) var(--space-3);
  }
  .levels,
  .check {
    padding: var(--space-3) var(--space-4);
    border-left: var(--border-w) solid var(--border-soft);
    min-width: 0;
  }
  h3 {
    margin: 0 0 var(--space-3);
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: var(--space-2) var(--space-3);
    margin: 0;
    align-items: baseline;
  }
  dt {
    color: var(--text-muted);
    font-family: var(--font-ui);
    font-size: var(--text-s);
  }
  dd {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-l);
    text-align: right;
  }
  .u {
    display: inline-block;
    width: 28px;
    margin-left: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    text-align: left;
  }
  .mode {
    margin: var(--space-3) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  li {
    display: grid;
    grid-template-columns: 156px 1fr 64px;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-xs);
  }
  .who {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    color: var(--fg);
    white-space: nowrap;
    overflow: hidden;
  }
  .who svg {
    width: 14px;
    height: 14px;
    flex: none;
  }
  .who .t {
    fill: none;
    stroke: var(--role-target);
    stroke-width: 1.5;
  }
  .who .c {
    fill: none;
    stroke: var(--role-comparison);
    stroke-width: 1.5;
  }
  .who .o {
    fill: none;
    stroke: var(--overlay-other);
    stroke-width: 1.5;
    stroke-dasharray: 2 2;
  }
  /* A true-length bar from zero to full scale. */
  .meter {
    position: relative;
    height: 8px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: 1px;
    background: var(--bg-2);
  }
  .meter::before {
    content: '';
    position: absolute;
    inset: 0;
    transform-origin: left;
    transform: scaleX(var(--f));
    background: var(--fg-muted);
  }
  .clip .meter {
    border-color: var(--warning);
  }

  .val {
    color: var(--fg);
    text-align: right;
    font-size: var(--text-s);
  }
  .scale {
    margin: var(--space-1) 0 var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    text-align: right;
  }
  .facts {
    grid-template-columns: auto 1fr auto 1fr;
  }
  .facts dd {
    font-size: var(--text-s);
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 100%;
    padding: 0 var(--space-3);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    color: var(--fg);
  }
  .k {
    color: var(--text-muted);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
  }
</style>
