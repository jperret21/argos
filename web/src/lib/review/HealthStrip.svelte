<!--
  The wall's health strip (lab P12, PROPOSAL §6 W7): the morning-after triage on the wall's
  time axis, four lanes of 12 px, each named at its left and counted in its tooltip:
  - frames: light-frame coverage; a gap (no frame for max(2 × cadence, cadence + 60 s)) is
    left empty, a frame whose FITS is missing is a hollow tick;
  - HFD: episodes of three frames or more above 1.5 × the session's median HFD (hatched);
  - comps: target points measured with fewer comparisons than the run's best frame (the
    tick as tall as the shortfall);
  - flags: suspect target points (hollow tick), saturated ones (×), and the points the server
    flagged from the run's flight recorder (A69: zero point more than 1 mag off its median,
    or SNR below 3 on that frame; a filled tick: drawn, exported, worth a look).
  Neutral inks; warning only for the HFD episodes (BRAND 10). Shares the CurveLink (zoom,
  crosshair, selected time); a click selects the nearest target point.
-->
<script lang="ts">
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import '../charts/plot-host.css';
  import { untrack } from 'svelte';
  import { readInks, type ChartInks } from '../charts/ink';
  import { drawText } from '../charts/text';
  import { PlotHost } from '../charts/uplot/host';
  import type { CurveLink } from '../charts/lightcurve/link.svelte';
  import { int } from '../format/number';
  import { tooltip } from '../components/tooltip';
  import { flagWord } from './source';
  import type { HealthLanes } from './wall';

  /** The recorder flags in words (protocol A69 "Flags"). */
  const FLAG_TIP: Record<string, string> = {
    zp_outlier: 'on a frame whose zero point is more than 1 mag off the run median',
    low_snr: 'with an SNR below 3 on its frame',
    few_anchors: 'measured while fewer than 3 comparison or check stars reached SNR 10 (S56: lock not verified)',
  };

  interface Props {
    lanes: HealthLanes;
    /** The times a click can select (the target's points, else the frames). */
    times: ArrayLike<number>;
    link: CurveLink;
    theme?: unknown;
  }
  let { lanes, times, link, theme }: Props = $props();

  const LANES = ['frames', 'HFD', 'comps', 'flags'] as const;
  let root: HTMLDivElement;
  let host: PlotHost | null = null;
  let inks: ChartInks | null = null;

  function draw(u: uPlot): void {
    const ink = inks;
    if (!ink) return;
    const dpr = uPlot.pxRatio;
    const { ctx } = u;
    const { left, top, width, height } = u.bbox;
    const laneH = height / LANES.length;
    const X = (t: number) => u.valToPos(t, 'x', true);
    const L = lanes;
    ctx.save();
    // The micro-label token (--text-2xs: 10 px mono, uppercase).
    LANES.forEach((l, k) => drawText(ctx, l.toUpperCase(), left - 6 * dpr, top + laneH * (k + 0.5), { font: `400 ${10 * dpr}px ${ink.mono}`, fill: ink.text.a(), align: 'right', baseline: 'middle' }));
    ctx.beginPath();
    ctx.rect(left, top, width, height);
    ctx.clip();
    ctx.strokeStyle = ink.borderSoft.a();
    ctx.lineWidth = dpr;
    ctx.beginPath();
    for (let k = 1; k < LANES.length; k++) {
      ctx.moveTo(left, Math.round(top + laneH * k) + 0.5);
      ctx.lineTo(left + width, Math.round(top + laneH * k) + 0.5);
    }
    ctx.stroke();
    const pad = 2 * dpr;
    const y0 = (k: number) => top + laneH * k + pad;
    const h = laneH - 2 * pad;
    // Lane 0: coverage (gaps empty), missing FITS as hollow ticks.
    ctx.fillStyle = ink.fgMuted.a(0.55);
    for (const e of L.coverage) ctx.fillRect(X(e.from), y0(0), Math.max(2 * dpr, X(e.to) - X(e.from)), h);
    ctx.strokeStyle = ink.fg.a(0.9);
    for (const t of L.missing) ctx.strokeRect(Math.round(X(t)) - 1.5 * dpr, y0(0) + 0.5, 3 * dpr, h - 1);
    // Lane 1: HFD episodes, hatched (BRAND 10: the period a rule holds; no long golden
    // fill beside the target's series, BRAND 3), a 1 px tick where each starts.
    ctx.strokeStyle = ink.warning.a(0.85);
    ctx.lineWidth = dpr;
    for (const e of L.hfd) {
      const x0 = X(e.from);
      const w = Math.max(2 * dpr, X(e.to) - x0);
      ctx.save();
      ctx.beginPath();
      ctx.rect(x0, y0(1), w, h);
      ctx.clip();
      ctx.beginPath();
      for (let x = x0 - h; x < x0 + w; x += 5 * dpr) {
        ctx.moveTo(x, y0(1) + h);
        ctx.lineTo(x + h, y0(1));
      }
      ctx.stroke();
      ctx.restore();
      ctx.beginPath();
      ctx.moveTo(Math.round(x0) + 0.5, y0(1));
      ctx.lineTo(Math.round(x0) + 0.5, y0(1) + h);
      ctx.stroke();
    }
    // Lane 2: fewer comparisons than the run's best frame, as tall as the shortfall.
    ctx.fillStyle = ink.fg.a(0.7);
    L.fewComps.forEach((t, k) => {
      const hh = Math.max(2 * dpr, h * L.fewCompsDeficit[k]);
      ctx.fillRect(Math.round(X(t)) - dpr, y0(2) + h - hh, 2 * dpr, hh);
    });
    // Lane 3: recorder flags filled, suspect hollow, saturated ×.
    ctx.fillStyle = ink.fg.a(0.7);
    for (const t of L.flagged) ctx.fillRect(Math.round(X(t)) - dpr, y0(3), 2 * dpr, h);
    ctx.strokeStyle = ink.fg.a(0.9);
    ctx.lineWidth = dpr;
    for (const t of L.suspect) ctx.strokeRect(Math.round(X(t)) - 2 * dpr + 0.5, y0(3) + 1, 4 * dpr - 1, h - 2);
    ctx.beginPath();
    for (const t of L.saturated) {
      const x = Math.round(X(t));
      const r = Math.min(3 * dpr, h / 2);
      const cy = y0(3) + h / 2;
      ctx.moveTo(x - r, cy - r);
      ctx.lineTo(x + r, cy + r);
      ctx.moveTo(x - r, cy + r);
      ctx.lineTo(x + r, cy - r);
    }
    ctx.stroke();
    const st = link.selection.t;
    if (st !== null) {
      const x = Math.round(X(st)) + 0.5;
      ctx.strokeStyle = ink.highlight.a(0.9);
      ctx.setLineDash([4 * dpr, 3 * dpr]);
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, top + height);
      ctx.stroke();
    }
    ctx.restore();
  }

  function options(): uPlot.Options {
    const ink = inks!;
    return {
      width: 100,
      height: 100,
      padding: [2, 18, 2, 0],
      legend: { show: false },
      cursor: { sync: { key: link.syncKey, setSeries: false }, points: { show: false }, drag: { x: true, y: false, setScale: true, dist: 5 }, bind: { dblclick: () => () => null }, focus: { prox: -1 } },
      scales: { x: { time: false }, y: { range: [0, 1] } },
      axes: [
        { show: false },
        { stroke: ink.text.a(), size: 50, ticks: { show: false }, grid: { show: false }, splits: () => [], values: () => [] },
      ],
      series: [{}, { show: false }],
      plugins: [link.zoom.plugin(), { hooks: { draw: [draw] } }],
      hooks: {
        init: [
          (u) => {
            u.over.addEventListener('click', (e) => {
              if (!times.length) return;
              const rect = u.over.getBoundingClientRect();
              const t = u.posToVal(e.clientX - rect.left, 'x');
              let best = 0;
              for (let i = 1; i < times.length; i++) if (Math.abs(times[i] - t) < Math.abs(times[best] - t)) best = i;
              const px = u.valToPos(times[best], 'x');
              link.select(Math.abs(px - (e.clientX - rect.left)) <= 12 ? times[best] : null);
            });
          },
        ],
      },
    };
  }

  function data(): uPlot.AlignedData {
    // One x sample at each end so uPlot keeps the group's x scale.
    const ex = link.zoom.fitView() ?? [0, 1];
    return [new Float64Array(ex), new Float64Array([0, 0])] as unknown as uPlot.AlignedData;
  }

  function attach(el: HTMLElement) {
    inks ??= readInks(el);
    host = new PlotHost(el, () => ({ opts: options(), data: data() }), (u) => link.zoom.batch(u, () => {}));
    return () => {
      host?.destroy();
      host = null;
    };
  }

  $effect(() => {
    void theme;
    void lanes;
    untrack(() => {
      if (!root) return;
      inks = readInks(root);
      host?.build();
    });
  });
  $effect(() => {
    void link.selection.t;
    untrack(() => host?.u?.redraw(false, false));
  });

  const tips = $derived([
    `${int(lanes.lights)} light frames${lanes.gaps.length ? ` · ${lanes.gaps.length} gap${lanes.gaps.length === 1 ? '' : 's'}` : ''}${lanes.missing.length ? ` · ${lanes.missing.length} FITS missing (hollow)` : ''}`,
    lanes.hfdBase !== null ? `${lanes.hfd.length} HFD episode${lanes.hfd.length === 1 ? '' : 's'} above 1.5 × the median ${lanes.hfdBase.toFixed(2)} px (3 frames or more)` : 'No HFD recorded',
    lanes.compsBest > 0
      ? `${int(lanes.fewComps.length)} target points measured with fewer than ${lanes.compsBest} comparisons, the most this run used (the ensemble holds ${lanes.ensemble}); a tick is as tall as the shortfall`
      : 'No comparison count recorded',
    [
      `${int(lanes.suspect.length)} suspect (hollow) · ${int(lanes.saturated.length)} saturated (×) target points`,
      ...Object.entries(lanes.flaggedBy).map(([code, k]) => `${int(k)} target point${k === 1 ? '' : 's'} ${FLAG_TIP[code] ?? flagWord(code)} (filled)`),
    ].join(' · '),
  ]);
</script>

<div class="hs" bind:this={root} role="group" aria-label="Session health: {tips.join('; ')}">
  <div class="names" aria-hidden="true">
    {#each LANES as l, k (l)}
      <span use:tooltip={{ text: tips[k] }}></span>
    {/each}
  </div>
  <div class="plot-host plot" {@attach attach}></div>
</div>

<style>
  .hs {
    position: relative;
    height: 100%;
    padding: 0 var(--space-2) 0 var(--space-1);
  }
  .plot {
    height: 100%;
  }
  /* Hover targets over the lane names (the canvas draws the words): each lane's count. */
  .names {
    position: absolute;
    z-index: 1;
    top: 2px;
    bottom: 2px;
    left: var(--space-1);
    width: 50px;
    display: grid;
    grid-template-rows: repeat(4, 1fr);
  }
</style>
