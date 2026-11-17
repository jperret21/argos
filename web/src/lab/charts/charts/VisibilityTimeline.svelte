<!--
  Visibility timeline for the night (spec 06 1.7 / 2.3.1, Q-P6).

  - Twilight as luminance steps of --fg-muted (day, civil, nautical,
    astronomical, night): no hue, so Night Red keeps them apart.
  - Target altitude in --chart-1; the part below the minimum altitude is
    dashed, so "too low" never rests on colour. The Moon is a thin dashed
    neutral line with a direct label (phase in words, not a pictograph).
  - Minimum altitude: a reference line with a handle (a site setting,
    Q-P6); the window above it and the planning check update as it moves.
  - Meridian transit, the planned run (outlined band, as the spec asks),
    the frames already taken (a rug in that band) and the now-line.
  - Two label rows on one x scale: UTC under the plot, local time above
    (spec 06: local, UTC on hover; BRAND: UTC named). Not a second y axis.
-->
<script lang="ts">
  import uPlot from 'uplot';
  import { untrack } from 'svelte';
  import { tooltip } from '../../../lib/components/tooltip';
  import { env } from '../env.svelte';
  import { clock } from '../sim/stream.svelte';
  import { RUN_END, RUN_START, SITE, TARGET } from '../sim/night';
  import { airmass, crossings, horizontal, maximum, moonAltitude, moonPosition, jdFromUnix, separation, sunAltitude, TWILIGHT, type RaDec } from '../sim/astro';
  import { readInks, type ChartInks } from '../core/palette';
  import { PlotHost } from '../core/uplot/host';
  import { annotations, type Annotation } from '../core/uplot/overlays';
  import { utcTz, valueAxis } from '../core/uplot/axes';
  import { clockUtc, degrees, duration, fixed } from '../core/format';

  interface Props {
    compact?: boolean;
  }
  let { compact = false }: Props = $props();

  interface Tgt {
    id: string;
    label: string;
    pos: RaDec;
    note: string;
  }
  const hms = (h: number, m: number, s: number) => (h + m / 60 + s / 3600) * 15;
  const TARGETS: Tgt[] = [
    { id: 'swand', label: TARGET.label, pos: TARGET.pos, note: 'RRab, tonight’s run' },
    { id: 'rrlyr', label: 'RR Lyr', pos: { ra: hms(19, 25, 27.9), dec: 42 + 47 / 60 + 4 / 3600 }, note: 'sets early in November' },
    { id: 'tcrb', label: 'T CrB', pos: { ra: hms(15, 59, 30.2), dec: 25 + 55 / 60 + 13 / 3600 }, note: 'too low tonight' },
  ];

  const T0 = Date.UTC(2026, 10, 1, 15, 30) / 1000;
  const T1 = Date.UTC(2026, 10, 2, 7, 30) / 1000;
  const STEP = 120;

  const q = new URLSearchParams(location.search);
  let targetId = $state(TARGETS.some((t) => t.id === q.get('target')) ? (q.get('target') as string) : 'swand');
  const target = $derived(TARGETS.find((t) => t.id === targetId) ?? TARGETS[0]);
  let minAlt = $state(30);
  let hoverIdx = $state<number | null>(null);
  let hoverLeft = $state(0);
  let handleY = $state<number | null>(null);
  let dragging = $state(false);
  let plotW = $state(0);

  let root: HTMLDivElement;
  let host: PlotHost | null = null;
  let inks: ChartInks | null = null;

  // -- Sky geometry for the night (computed once per target) -----------------------
  const n = Math.floor((T1 - T0) / STEP) + 1;
  const ts = new Float64Array(n);
  const sun = new Float64Array(n);
  const moon = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    ts[i] = T0 + i * STEP;
    sun[i] = sunAltitude(SITE, ts[i]);
    moon[i] = moonAltitude(SITE, ts[i]);
  }
  const sunF = (t: number) => sunAltitude(SITE, t);
  const ev = {
    sunset: crossings(sunF, TWILIGHT.sunset, T0, T1).find((c) => !c.rising)?.t ?? NaN,
    sunrise: crossings(sunF, TWILIGHT.sunset, T0, T1).find((c) => c.rising)?.t ?? NaN,
    civil: crossings(sunF, TWILIGHT.civil, T0, T1),
    nautical: crossings(sunF, TWILIGHT.nautical, T0, T1),
    astro: crossings(sunF, TWILIGHT.astronomical, T0, T1),
  };
  const dusk = ev.astro.find((c) => !c.rising)?.t ?? NaN;
  const dawn = ev.astro.find((c) => c.rising)?.t ?? NaN;
  const moonF = (t: number) => moonAltitude(SITE, t);
  const moonRise = crossings(moonF, 0, T0, T1).find((c) => c.rising)?.t ?? null;
  const moonIllum = moonPosition(jdFromUnix((T0 + T1) / 2)).illumination;

  const geo = $derived.by(() => {
    const pos = target.pos;
    const alt = new Float64Array(n);
    for (let i = 0; i < n; i++) alt[i] = horizontal(pos, SITE, ts[i]).alt;
    const f = (t: number) => horizontal(pos, SITE, t).alt;
    const peak = maximum(f, T0, T1);
    return { alt, f, peak };
  });

  const aboveWin = $derived.by(() => {
    const c = crossings(geo.f, minAlt, T0, T1);
    let start = geo.f(T0) >= minAlt ? T0 : (c.find((x) => x.rising)?.t ?? null);
    let end = c.find((x) => !x.rising && (start === null || x.t > start))?.t ?? (geo.f(T1) >= minAlt && start !== null ? T1 : null);
    // Clip to the astronomical night.
    if (start !== null && end !== null) {
      start = Math.max(start, dusk);
      end = Math.min(end, dawn);
      if (end <= start) return null;
      return { start, end };
    }
    return null;
  });

  const runCheck = $derived.by(() => {
    if (!aboveWin) return { ok: false, text: `${target.label} never reaches ${minAlt}° during the astronomical night` };
    const before = Math.max(0, aboveWin.start - RUN_START);
    const after = Math.max(0, RUN_END - aboveWin.end);
    if (!before && !after) return { ok: true, text: `Planned run ${clockUtc(RUN_START, false)} → ${clockUtc(RUN_END, false)} stays above ${minAlt}°` };
    const parts = [];
    if (before) parts.push(`first ${duration(before)}`);
    if (after) parts.push(`last ${duration(after)}`);
    return { ok: false, text: `Planned run: ${parts.join(' and ')} below ${minAlt}°` };
  });

  function dataNow(): uPlot.AlignedData {
    const above = new Float64Array(n);
    const below = new Float64Array(n);
    const alt = geo.alt;
    for (let i = 0; i < n; i++) {
      const a = alt[i];
      // Each part keeps the sample next to the crossing so the two lines join.
      const nextAbove = i + 1 < n && alt[i + 1] >= minAlt;
      const prevAbove = i > 0 && alt[i - 1] >= minAlt;
      above[i] = a >= minAlt || nextAbove || prevAbove ? a : NaN;
      below[i] = a < minAlt || (i + 1 < n && alt[i + 1] < minAlt) || (i > 0 && alt[i - 1] < minAlt) ? a : NaN;
    }
    return [ts, nanToNull(above), nanToNull(below), nanToNull(moon.map((m) => (m > -2 ? m : NaN)))];
  }
  const nanToNull = (a: Float64Array) => Array.from(a, (v) => (Number.isFinite(v) ? v : null));

  function bands(): Annotation[] {
    const ink = inks!;
    const tw = ink.lab.twilight;
    const out: Annotation[] = [];
    // Contiguous spans by twilight level, from the sampled Sun altitude.
    const level = (s: number) => (s > TWILIGHT.sunset ? 4 : s > TWILIGHT.civil ? 3 : s > TWILIGHT.nautical ? 2 : s > TWILIGHT.astronomical ? 1 : 0);
    let i0 = 0;
    for (let i = 1; i <= n; i++) {
      if (i === n || level(sun[i]) !== level(sun[i0])) {
        const lv = level(sun[i0]);
        if (lv > 0) out.push({ kind: 'vspan', from: ts[i0] - STEP / 2, to: ts[Math.min(n - 1, i)] - STEP / 2, fill: ink.fgMuted.a(tw[lv]) });
        i0 = i;
      }
    }
    return out;
  }

  function annFor(): Annotation[] {
    const ink = inks!;
    const out = bands();
    const lbl = (t: number, text: string) => out.push({ kind: 'vline', x: t, color: ink.border.a(0), label: { text, at: 'top' } });
    out.push({ kind: 'vspan', from: RUN_START, to: RUN_END, y0: 0.95, y1: 1, outline: ink.fg.a(0.55), label: { text: `planned run ${clockUtc(RUN_START, false)} → ${clockUtc(RUN_END, false)}`, at: 'top', dy: -18 }, layer: 'over' });
    out.push({ kind: 'hline', y: minAlt, color: ink.reference.a(), dash: [5, 3], label: { text: `min. altitude ${minAlt}°`, at: 'left', dx: 30 } });
    out.push({ kind: 'vline', x: geo.peak.t, color: ink.reference.a(0.7), dash: [1, 3] });
    if (Number.isFinite(ev.sunset)) lbl(ev.sunset, `sunset ${clockUtc(ev.sunset, false)}`);
    if (Number.isFinite(dusk)) lbl(dusk, `dusk ${clockUtc(dusk, false)}`);
    if (Number.isFinite(dawn)) lbl(dawn, `dawn ${clockUtc(dawn, false)}`);
    if (Number.isFinite(ev.sunrise)) lbl(ev.sunrise, `sunrise ${clockUtc(ev.sunrise, false)}`);
    out.push({ kind: 'vline', x: clock.now, color: ink.highlight.a(0.9), label: { text: `now ${clockUtc(clock.now, false)}`, at: 'top', dy: 18 } });
    return out;
  }

  /** Frames taken so far: coverage segments inside the planned-run band (gaps = pauses). */
  function framesRug(): uPlot.Plugin {
    return {
      hooks: {
        draw: [
          (u) => {
            const dpr = uPlot.pxRatio;
            const { ctx } = u;
            const { left, top, width, height } = u.bbox;
            if (targetId === 'swand') {
              const c = clock.night.cols;
              const k = clock.night.n;
              const y0 = top + height * 0.95 + 4 * dpr;
              const h = Math.max(3 * dpr, height * 0.05 - 8 * dpr);
              ctx.save();
              // Neutral: a coverage block is a large area, and large areas never
              // wear a role or accent colour (lab synthesis, brass scarcity).
              ctx.fillStyle = inks!.fgMuted.a(0.55);
              let i0 = 0;
              for (let i = 1; i <= k; i++) {
                if (i === k || c.t[i] - c.t[i - 1] > 150) {
                  if (k > 0) {
                    const xa = u.valToPos(c.t[i0], 'x', true);
                    const xb = u.valToPos(c.t[i - 1], 'x', true);
                    ctx.fillRect(Math.round(xa), y0, Math.max(dpr, Math.round(xb - xa)), h);
                  }
                  i0 = i;
                }
              }
              ctx.restore();
            }
            // Name the two time rows (same x scale).
            ctx.save();
            ctx.font = `500 ${9 * dpr}px ${inks!.mono}`;
            ctx.fillStyle = inks!.textMuted.a();
            ctx.textAlign = 'left';
            ctx.textBaseline = 'middle';
            ctx.fillText(`UTC+${SITE.utcOffsetH}`, left + width + 6 * dpr, top - 10 * dpr);
            ctx.fillText('UTC', left + width + 6 * dpr, top + height + 13 * dpr);
            // Transit: a direct label above the vertex.
            const px = u.valToPos(geo.peak.t, 'x', true);
            const py = u.valToPos(geo.peak.value, 'y', true);
            ctx.textAlign = 'center';
            ctx.textBaseline = 'bottom';
            ctx.font = `500 ${10 * dpr}px ${inks!.mono}`;
            ctx.fillStyle = inks!.text.a();
            if (px > left && px < left + width) ctx.fillText(`transit ${clockUtc(geo.peak.t, false)} · ${degrees(geo.peak.value, 1)}`, px, py - 8 * dpr);
            ctx.restore();
            const y = u.valToPos(minAlt, 'y');
            handleY = y + u.over.offsetTop;
          },
        ],
      },
    };
  }

  function options(): uPlot.Options {
    const ink = inks!;
    const font = `400 10px ${ink.mono}`;
    const local = (v: number) => clockUtc(v + SITE.utcOffsetH * 3600, false);
    return {
      width: 100,
      height: 100,
      padding: [compact ? 4 : 8, 40, 0, 8],
      legend: { show: false },
      tzDate: utcTz,
      cursor: {
        points: { size: 9, width: 1.5, stroke: () => ink.highlight.a(), fill: () => 'rgba(0,0,0,0)', show: ((_u: uPlot, si: number) => (si === 1 || si === 2 ? pointEl() : undefined)) as unknown as boolean },
        drag: { x: false, y: false, setScale: false },
        focus: { prox: -1 },
      },
      scales: { x: { time: true, range: [T0, T1] }, y: { range: [0, 90] } },
      axes: [
        {
          stroke: ink.text.a(),
          font,
          size: 24,
          gap: 3,
          space: 56,
          ticks: { stroke: ink.axis.a(), width: 1, size: 3 },
          grid: { stroke: ink.grid.a(), width: 1 },
          border: { show: true, stroke: ink.axis.a(), width: 1 },
          values: (_u, splits) => splits.map((v) => clockUtc(v, false)),
        },
        {
          scale: 'x',
          side: 0,
          stroke: ink.text.a(0.75),
          font,
          size: compact ? 18 : 20,
          gap: 2,
          space: 56,
          ticks: { show: false },
          grid: { show: false },
          values: (_u, splits) => splits.map((v) => local(v)),
        },
        valueAxis(ink, { format: (v) => `${v}°`, size: 40, space: 22, splits: () => [0, 15, 30, 45, 60, 75, 90].filter((v) => Math.abs(v - minAlt) > 5) }),
      ],
      series: [
        {},
        { stroke: ink.target.a(), width: 2, spanGaps: false, points: { show: false } },
        { stroke: ink.target.a(0.75), width: 1.5, dash: [5, 4], spanGaps: false, points: { show: false } },
        { stroke: ink.fgMuted.a(0.8), width: 1, dash: [2, 3], spanGaps: false, points: { show: false } },
      ],
      plugins: [annotations(annFor, () => inks!), framesRug(), moonLabel()],
      hooks: {
        setCursor: [
          (u) => {
            const i = u.cursor.idx;
            hoverIdx = i == null || (u.cursor.left ?? -1) < 0 ? null : i;
            hoverLeft = (u.cursor.left ?? 0) + u.over.offsetLeft;
          },
        ],
      },
    };
  }

  function pointEl(): HTMLElement {
    const el = document.createElement('div');
    el.style.cssText = 'width:9px;height:9px;margin:-4.5px 0 0 -4.5px';
    return el;
  }

  /** Direct label on the Moon line (BRAND 10: selective direct labels). */
  function moonLabel(): uPlot.Plugin {
    return {
      hooks: {
        draw: [
          (u) => {
            let best = -1;
            for (let i = 0; i < n; i++) if (moon[i] > 4 && (best < 0 || moon[i] > moon[best])) best = i;
            if (best < 0) return;
            const dpr = uPlot.pxRatio;
            const x = u.valToPos(ts[best], 'x', true);
            const y = u.valToPos(moon[best], 'y', true);
            const { ctx } = u;
            ctx.save();
            ctx.font = `500 ${10 * dpr}px ${inks!.mono}`;
            ctx.fillStyle = inks!.textMuted.a();
            ctx.textAlign = 'right';
            ctx.textBaseline = 'bottom';
            ctx.fillText(`Moon · ${Math.round(moonIllum * 100)} % lit`, Math.min(x, u.bbox.left + u.bbox.width - 4 * dpr), y - 5 * dpr);
            ctx.restore();
          },
        ],
      },
    };
  }

  function attach(el: HTMLElement) {
    host = new PlotHost(el, () => ({ opts: options(), data: dataNow() }));
    return () => {
      host?.destroy();
      host = null;
    };
  }

  $effect(() => {
    void env.theme;
    void targetId;
    untrack(() => {
      inks = readInks(root);
      host?.build();
    });
  });

  $effect(() => {
    void minAlt;
    untrack(() => host?.u?.setData(dataNow(), false));
  });

  // Now-line and frames rug: once per simulated minute is plenty.
  let lastMinute = 0;
  $effect(() => {
    const id = setInterval(() => {
      const m = Math.floor(clock.now / 60);
      if (m !== lastMinute) {
        lastMinute = m;
        host?.u?.redraw(false, false);
      }
    }, 250);
    return () => clearInterval(id);
  });

  function limitHandle(el: HTMLElement) {
    const toAlt = (clientY: number) => {
      const u = host?.u;
      if (!u) return null;
      return Math.round(Math.min(60, Math.max(10, u.posToVal(clientY - u.over.getBoundingClientRect().top, 'y'))));
    };
    const down = (e: PointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      dragging = true;
    };
    const move = (e: PointerEvent) => {
      if (!dragging) return;
      const a = toAlt(e.clientY);
      if (a !== null) minAlt = a;
    };
    const up = (e: PointerEvent) => {
      dragging = false;
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
    };
    const key = (e: KeyboardEvent) => {
      const s = e.shiftKey ? 5 : 1;
      if (e.key === 'ArrowUp') minAlt = Math.min(60, minAlt + s);
      else if (e.key === 'ArrowDown') minAlt = Math.max(10, minAlt - s);
      else return;
      e.preventDefault();
    };
    el.addEventListener('pointerdown', down);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
    el.addEventListener('keydown', key);
    return () => {
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      el.removeEventListener('keydown', key);
    };
  }

  const phaseName = (s: number) => (s > TWILIGHT.sunset ? 'day' : s > TWILIGHT.civil ? 'civil twilight' : s > TWILIGHT.nautical ? 'nautical twilight' : s > TWILIGHT.astronomical ? 'astronomical twilight' : 'night');

  const hoverRead = $derived.by(() => {
    if (hoverIdx === null) return null;
    const t = ts[hoverIdx];
    const h = horizontal(target.pos, SITE, t);
    const m = moonPosition(jdFromUnix(t));
    return {
      utc: clockUtc(t, false),
      local: clockUtc(t + SITE.utcOffsetH * 3600, false),
      alt: degrees(h.alt, 1),
      az: degrees(h.az, 1),
      airmass: h.alt > 0 ? fixed(airmass(h.alt), 2) : '—',
      ha: `${h.ha >= 0 ? '+' : '−'}${fixed(Math.abs(h.ha) / 15, 2)} h`,
      sun: `${degrees(sun[hoverIdx], 1)} · ${phaseName(sun[hoverIdx])}`,
      moon: `${degrees(moon[hoverIdx], 1)} · ${Math.round(separation(m, target.pos))}° away`,
    };
  });

  const facts = $derived([
    { k: 'Sunset', v: clockUtc(ev.sunset, false) },
    { k: 'Astro. dusk', v: clockUtc(dusk, false) },
    { k: 'Astro. dawn', v: clockUtc(dawn, false) },
    { k: 'Sunrise', v: clockUtc(ev.sunrise, false) },
    { k: 'Moon', v: `${Math.round(moonIllum * 100)} % lit · rises ${moonRise ? clockUtc(moonRise, false) : '—'}` },
    { k: 'Transit', v: `${clockUtc(geo.peak.t, false)} · ${degrees(geo.peak.value, 1)}` },
    { k: `Above ${minAlt}°`, v: aboveWin ? `${clockUtc(aboveWin.start, false)} → ${clockUtc(aboveWin.end, false)} · ${duration(aboveWin.end - aboveWin.start)}` : 'not tonight' },
  ]);
</script>

<div class="vis" class:compact bind:this={root}>
  <div class="bar">
    {#if !compact}
      <div class="lab-seg" role="radiogroup" aria-label="Target">
        {#each TARGETS as t (t.id)}
          <button role="radio" aria-checked={targetId === t.id} onclick={() => (targetId = t.id)}>{t.label}</button>
        {/each}
      </div>
    {/if}
    <span class="head"><b>{target.label}</b> · {SITE.name} ({fixed(SITE.lat, 2)}° N) · night of 2026-11-01 · {target.note}</span>
    <span class="grow"></span>
    <span class="lab-chip" class:attention={!runCheck.ok}><span class="lab-dot {runCheck.ok ? 'ok' : 'busy'}"></span>{runCheck.text}</span>
  </div>
  <div class="body">
    <div class="lab-plot-host plot" bind:clientWidth={plotW} {@attach attach} role="img" aria-label="Altitude of {target.label} over the night, with twilight, the minimum altitude, the Moon and the planned run">
      {#if handleY !== null}
        <div
          class="limit"
          class:dragging
          style:top="{handleY}px"
          role="slider"
          tabindex="0"
          aria-label="Minimum altitude (site setting)"
          aria-orientation="vertical"
          aria-valuemin={10}
          aria-valuemax={60}
          aria-valuenow={minAlt}
          aria-valuetext="{minAlt} degrees"
          use:tooltip={{ text: 'Minimum altitude: drag or use the arrow keys' }}
          {@attach limitHandle}
        >
          <span class="num">{minAlt}°</span>
        </div>
      {/if}
      {#if hoverRead}
        <div class="lab-readout" style:left="{hoverLeft + 230 > plotW ? hoverLeft - 224 : hoverLeft + 14}px" style:top="56px" aria-hidden="true">
          <div class="t">{hoverRead.utc} UTC · {hoverRead.local} local</div>
          <hr />
          <div>{target.label} <span class="v">{hoverRead.alt}</span> · az <span class="v">{hoverRead.az}</span></div>
          <div>airmass <span class="v">{hoverRead.airmass}</span> · HA <span class="v">{hoverRead.ha}</span></div>
          <hr />
          <div>Sun <span class="v">{hoverRead.sun}</span></div>
          <div>Moon <span class="v">{hoverRead.moon}</span></div>
        </div>
      {/if}
    </div>
    {#if !compact}
      <aside class="facts">
        <p class="lab-eyebrow">Tonight · UTC</p>
        <dl>
          {#each facts as f (f.k)}
            <dt>{f.k}</dt>
            <dd class="num">{f.v}</dd>
          {/each}
        </dl>
        <p class="lab-eyebrow">Key</p>
        <ul class="key">
          <li><i class="sw tgt"></i>{target.label}, above the limit</li>
          <li><i class="sw tgt dash"></i>below the limit</li>
          <li><i class="sw moon"></i>Moon</li>
          <li><i class="sw band"></i>planned run · frames taken so far</li>
          <li><i class="sw tw4"></i><i class="sw tw2"></i><i class="sw tw0"></i>day → twilight → night</li>
        </ul>
        <p class="note">Altitudes from low-precision formulae (Sun ≈ 0.01°, Moon ≈ 0.3°); the server computes them with astropy (A65).</p>
      </aside>
    {/if}
  </div>
</div>

<style>
  .vis {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--chart-surface);
  }
  .bar {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: var(--lab-chart-toolbar-h);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    background: var(--bg);
    flex: none;
    min-width: 0;
  }
  .compact .bar {
    height: 30px;
  }
  .head {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }
  .head b {
    color: var(--fg);
    font-weight: var(--weight-semibold);
  }
  .grow {
    flex: 1;
  }
  .body {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) 280px;
  }
  .compact .body {
    grid-template-columns: minmax(0, 1fr);
  }
  .plot {
    margin: var(--space-2) var(--space-2) var(--space-2) var(--space-2);
  }
  .limit {
    position: absolute;
    left: 2px;
    z-index: 3;
    display: flex;
    align-items: center;
    height: 18px;
    padding: 0 5px;
    transform: translateY(-50%);
    border: 1px solid var(--accent);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-2xs);
    cursor: ns-resize;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
  }
  .limit:hover,
  .limit.dragging {
    background: var(--surface);
  }
  .facts {
    padding: var(--space-4);
    border-left: var(--border-w) solid var(--border-soft);
    background: var(--bg);
    overflow: auto;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px var(--space-3);
    margin: var(--space-2) 0 var(--space-5);
    font-size: var(--text-s);
  }
  dt {
    color: var(--text-muted);
  }
  dd {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-xs);
    text-align: right;
  }
  .key {
    margin: var(--space-2) 0 var(--space-5);
    padding: 0;
    list-style: none;
    color: var(--text-muted);
    font-size: var(--text-xs);
    display: grid;
    gap: 6px;
  }
  .key li {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .sw {
    display: inline-block;
    width: 18px;
    height: 10px;
    flex: none;
  }
  .sw.tgt {
    height: 0;
    border-top: 2px solid var(--chart-1);
  }
  .sw.tgt.dash {
    border-top-style: dashed;
  }
  .sw.moon {
    height: 0;
    border-top: 1px dashed var(--fg-muted);
  }
  .sw.band {
    border: 1px solid var(--fg-muted);
  }
  .sw.tw4 {
    width: 10px;
    background: color-mix(in srgb, var(--fg-muted) 15%, transparent);
  }
  .sw.tw2 {
    width: 10px;
    background: color-mix(in srgb, var(--fg-muted) 6.5%, transparent);
  }
  .sw.tw0 {
    width: 10px;
    border: 1px solid var(--border-soft);
  }
  .note {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-relaxed);
  }
</style>
