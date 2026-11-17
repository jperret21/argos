<!--
  Conditions timeline (spec D6): up to three small multiples on one UTC axis,
  chosen by metric chips, beside the rail card that shows every metric as a
  number with its sparkline.

  - The x range runs to "now", not to the last frame: the gap between the
    newest point and the now-line IS the age of the last frame. When no
    frame arrived for max(2 x cadence, cadence + 60 s) the gap is hatched
    and labelled ("no frame for 3m 12s"): a frozen run never looks healthy.
  - HFD carries the proposed attention rule (functional-spaces 4.10):
    baseline = median of the first 20 frames, threshold = factor x baseline
    (a draggable, keyboard-operable handle), an episode is 3 frames in a row
    above it; drawn as a span from the frame where it fired, with a rug on
    every frame above the line, and stated in words in the header.
  - Two series at most per plot and one unit per axis: HFD and FWHM share
    "px"; airmass is drawn with 1.0 at the top (up = better, like altitude).
  - Conditions are not photometric roles: neutral inks (--fg, --fg-muted
    dashed), never the role colours.
-->
<script lang="ts">
  import uPlot from 'uplot';
  import { untrack } from 'svelte';
  import Icon from '../../../lib/components/Icon.svelte';
  import { tooltip } from '../../../lib/components/tooltip';
  import { env, reducedMotion } from '../env.svelte';
  import { clock, observedCadence } from '../sim/stream.svelte';
  import { AUTOFOCUS, hfdBaseline, hfdEpisodes, type NightColumns } from '../sim/night';
  import { readInks, type ChartInks } from '../core/palette';
  import { PlotHost } from '../core/uplot/host';
  import { TimeZoom, type ZoomMode } from '../core/uplot/zoom';
  import { annotations, type Annotation } from '../core/uplot/overlays';
  import { paddedRange, timeAxis, utcTz, valueAxis } from '../core/uplot/axes';
  import { clockUtc, duration, fixed, grouped } from '../core/format';
  import Sparkline from '../mini/Sparkline.svelte';

  type MetricId = 'focus' | 'stars' | 'sky' | 'airmass' | 'sensor' | 'focuser';
  type Col = 'hfd' | 'fwhm' | 'stars' | 'sky' | 'airmass' | 'sensorC' | 'focuser';
  interface Metric {
    label: string;
    unit: string;
    cols: Col[];
    digits: number;
    minSpan: number;
    invert?: boolean;
    sub: string;
  }
  const METRICS: Record<MetricId, Metric> = {
    focus: { label: 'Focus', unit: 'px', cols: ['hfd', 'fwhm'], digits: 1, minSpan: 1, sub: 'HFD and FWHM (green plane), px' },
    stars: { label: 'Stars', unit: '', cols: ['stars'], digits: 0, minSpan: 100, sub: 'detected stars per frame' },
    sky: { label: 'Sky', unit: 'ADU', cols: ['sky'], digits: 0, minSpan: 40, sub: 'median background, ADU' },
    airmass: { label: 'Airmass', unit: '', cols: ['airmass'], digits: 2, minSpan: 0.05, invert: true, sub: 'of the target · 1.0 at the top' },
    sensor: { label: 'Sensor', unit: '°C', cols: ['sensorC'], digits: 1, minSpan: 1, sub: 'sensor temperature, °C' },
    focuser: { label: 'Focuser', unit: 'steps', cols: ['focuser'], digits: 0, minSpan: 20, sub: 'focuser position, steps' },
  };
  const ORDER: MetricId[] = ['focus', 'stars', 'sky', 'airmass', 'sensor', 'focuser'];
  const ROWS: { col: Col; label: string; unit: string; digits: number; invert?: boolean }[] = [
    { col: 'hfd', label: 'HFD', unit: 'px', digits: 2 },
    { col: 'fwhm', label: 'FWHM', unit: 'px', digits: 2 },
    { col: 'stars', label: 'Stars', unit: '', digits: 0 },
    { col: 'sky', label: 'Sky', unit: 'ADU', digits: 0 },
    { col: 'airmass', label: 'Airmass', unit: '', digits: 3, invert: true },
    { col: 'sensorC', label: 'Sensor', unit: '°C', digits: 1 },
    { col: 'focuser', label: 'Focuser', unit: 'steps', digits: 0 },
  ];

  interface Props {
    /** Hide the rail card (the In context tab places its own). */
    railCard?: boolean;
    initial?: MetricId[];
  }
  let { railCard = true, initial = ['focus', 'stars', 'sky'] }: Props = $props();

  const stream = clock.night;
  let root: HTMLDivElement;
  let wall: HTMLDivElement;
  const hosts = new Map<MetricId, PlotHost>();
  let inks: ChartInks | null = null;
  const syncKey = `cond-${Math.random().toString(36).slice(2, 8)}`;

  let selectedMetrics = $state<MetricId[]>(untrack(() => [...initial]));
  let factor = $state(1.5);
  let count = $state(0);
  let nowTick = $state(0);
  let mode = $state<ZoomMode>('fit');
  let hover = $state<{ idx: number; left: number; top: number } | null>(null);
  let handleY = $state<number | null>(null);
  let dragging = $state(false);
  let activeFacet: MetricId | null = null;

  const cols = (): NightColumns => stream.cols;
  const col = (c: Col) => cols()[c] as Float64Array;

  const zoom = new TimeZoom({
    extent: () => {
      const n = stream.n;
      if (!n) return null;
      return [cols().t[0], Math.max(cols().t[n - 1], clock.now)];
    },
    minSpan: 600,
    padRight: 0.02,
    reducedMotion,
    onChange: (m) => (mode = m),
  });

  const baseline = $derived.by(() => {
    void count;
    return hfdBaseline(cols(), stream.n);
  });
  const threshold = $derived(baseline !== null ? baseline * factor : null);
  const episodes = $derived.by(() => {
    void count;
    return hfdEpisodes(cols(), stream.n, factor);
  });
  const cadence = $derived.by(() => {
    void count;
    return observedCadence(stream);
  });
  const lastT = $derived.by(() => {
    void count;
    return stream.n ? cols().t[stream.n - 1] : null;
  });
  const age = $derived.by(() => {
    void nowTick;
    return lastT !== null ? Math.max(0, clock.now - lastT) : null;
  });
  const staleAfter = $derived(cadence !== null ? Math.max(2 * cadence, cadence + 60) : 120);
  const stale = $derived(age !== null && age > staleAfter);
  const openEpisode = $derived(episodes.length > 0 && episodes[episodes.length - 1].end === null ? episodes[episodes.length - 1] : null);

  function dataFor(id: MetricId): uPlot.AlignedData {
    const n = stream.n;
    const t = cols().t.subarray(0, n);
    return [t, ...METRICS[id].cols.map((c) => col(c).subarray(0, n))];
  }

  function annFor(id: MetricId, first: boolean): Annotation[] {
    const ink = inks!;
    const out: Annotation[] = [];
    for (const t of AUTOFOCUS) if (t < clock.now) out.push({ kind: 'vline', x: t + 100, color: ink.reference.a(0.5), dash: [2, 3], label: first ? { text: 'AF' } : undefined });
    if (lastT !== null && stale) {
      out.push({ kind: 'vspan', from: lastT, to: clock.now, hatch: ink.warning.a(0.45), edge: ink.warning.a(0.8), layer: 'over' });
    }
    const nowText = `now ${clockUtc(clock.now)}${stale && lastT !== null ? ` · no frame for ${duration(clock.now - lastT)}` : ''}`;
    out.push({ kind: 'vline', x: clock.now, color: ink.highlight.a(0.85), label: first ? { text: nowText, at: 'top', color: stale ? ink.fg.a() : undefined } : undefined });
    if (id === 'focus' && baseline !== null && threshold !== null) {
      for (const e of episodes) {
        const from = cols().t[e.fired];
        const to = e.end !== null ? cols().t[e.end] : Math.max(cols().t[stream.n - 1], clock.now);
        out.push({
          kind: 'vspan',
          from,
          to,
          fill: ink.warning.a(0.1),
          edge: ink.warning.a(0.7),
          label: { text: `HFD > ${factor.toFixed(2)}× baseline · fired ${clockUtc(from)}${e.end !== null ? ` · cleared ${clockUtc(to)}` : ''}`, color: ink.fg.a(), at: 'bottom', dy: -8 },
        });
      }
      out.push({ kind: 'hline', y: baseline, color: ink.reference.a(0.9), dash: [3, 3], label: { text: `baseline ${fixed(baseline, 2)} px · median of first 20`, at: 'left' } });
      out.push({ kind: 'hline', y: threshold, color: ink.warning.a(0.95), dash: [6, 3] });
    }
    return out;
  }

  /** Rug of the frames above the HFD threshold, on the x axis line. */
  function rug(): uPlot.Plugin {
    return {
      hooks: {
        draw: [
          (u) => {
            const thr = threshold;
            if (thr === null) return;
            const dpr = uPlot.pxRatio;
            const { ctx } = u;
            const { left, top, width, height } = u.bbox;
            const xs = u.data[0];
            const ys = u.data[1] as ArrayLike<number>;
            ctx.save();
            ctx.beginPath();
            ctx.rect(left, top, width, height);
            ctx.clip();
            ctx.strokeStyle = inks!.warning.a();
            ctx.lineWidth = 1.5 * dpr;
            ctx.beginPath();
            for (let i = 0; i < xs.length; i++) {
              if (!(ys[i] > thr)) continue;
              const x = Math.round(u.valToPos(xs[i], 'x', true)) + 0.5;
              ctx.moveTo(x, top + height);
              ctx.lineTo(x, top + height - 6 * dpr);
            }
            ctx.stroke();
            ctx.restore();
            const y = u.valToPos(thr, 'y');
            const inside = y >= 0 && y <= u.over.clientHeight;
            handleY = inside ? y + u.over.offsetTop : null;
          },
        ],
      },
    };
  }

  function options(id: MetricId, first: boolean, last: boolean): uPlot.Options {
    const ink = inks!;
    const m = METRICS[id];
    const series: uPlot.Series[] = [{}];
    m.cols.forEach((_c, k) => {
      series.push({
        stroke: k === 0 ? ink.fg.a(0.92) : ink.fgMuted.a(0.9),
        width: k === 0 ? 1.5 : 1.25,
        dash: k === 0 ? undefined : [4, 3],
        points: { show: (u: uPlot) => (u.series[0].idxs ? u.series[0].idxs[1] - u.series[0].idxs[0] : 999) < 220, size: 4, fill: k === 0 ? ink.fg.a() : ink.fgMuted.a(), stroke: 'rgba(0,0,0,0)' } as uPlot.Series.Points,
        spanGaps: false,
      });
    });
    return {
      width: 100,
      height: 100,
      padding: [8, 26, last ? 0 : 2, 0],
      legend: { show: false },
      tzDate: utcTz,
      cursor: {
        sync: { key: syncKey, setSeries: false },
        points: { size: 9, width: 1.5, stroke: () => ink.highlight.a(), fill: () => 'rgba(0,0,0,0)' },
        drag: { x: true, y: false, setScale: true, dist: 5 },
        bind: TimeZoom.cursorBind(),
        focus: { prox: -1 },
      },
      scales: {
        x: { time: true },
        y: { dir: m.invert ? -1 : 1, range: paddedRange(m.minSpan, 0.12, id === 'focus' ? () => (threshold !== null ? [threshold, baseline ?? threshold] : []) : undefined) },
      },
      axes: [
        timeAxis(ink, { mode: 'utc', jd0: 0, labels: last }),
        valueAxis(ink, { format: (v) => (m.digits === 0 ? grouped(v) : fixed(v, m.digits)), size: 50, space: 24 }),
      ],
      series,
      plugins: [zoom.plugin(), annotations(() => annFor(id, first), () => inks!), ...(id === 'focus' ? [rug()] : [])],
      hooks: {
        init: [
          (u) => {
            u.over.addEventListener('mouseenter', () => (activeFacet = id));
            u.over.addEventListener('mouseleave', () => {
              if (activeFacet === id) activeFacet = null;
              hover = null;
            });
          },
        ],
        setCursor: [
          (u) => {
            if (activeFacet !== id) return;
            const i = u.cursor.idx;
            const left = u.cursor.left ?? -1;
            if (i == null || left < 0) {
              hover = null;
              return;
            }
            const wr = wall.getBoundingClientRect();
            const or = u.over.getBoundingClientRect();
            hover = { idx: i, left: or.left - wr.left + left, top: or.top - wr.top + (u.cursor.top ?? 0) };
          },
        ],
      },
    };
  }

  function facetHost(id: MetricId, first: boolean, last: boolean) {
    return (el: HTMLElement) => {
      const h = new PlotHost(el, () => ({ opts: options(id, first, last), data: dataFor(id) }));
      hosts.set(id, h);
      return () => {
        h.destroy();
        hosts.delete(id);
      };
    };
  }

  function rebuild(): void {
    inks = readInks(root);
    zoom.update();
    for (const h of hosts.values()) h.build();
  }

  function push(): void {
    if (!inks) return;
    zoom.update();
    for (const [id, h] of hosts) {
      const u = h.u;
      if (u) zoom.batch(u, () => u.setData(dataFor(id), false));
    }
    zoom.notify();
    count = stream.n;
  }

  let raf = 0;
  const schedule = () => {
    if (!raf)
      raf = requestAnimationFrame(() => {
        raf = 0;
        push();
      });
  };

  $effect(() => untrack(() => stream.onAppend(schedule)));

  // The now-line and the age tick with the simulated clock (4 Hz is enough).
  $effect(() => {
    const id = setInterval(() => {
      if (Math.floor(clock.now) !== nowTick) {
        nowTick = Math.floor(clock.now);
        schedule();
      }
    }, 250);
    return () => clearInterval(id);
  });

  $effect(() => {
    void env.theme;
    void selectedMetrics.length;
    untrack(rebuild);
  });

  $effect(() => {
    void factor;
    untrack(() => {
      hosts.get('focus')?.u?.redraw(false, true);
    });
  });

  function toggleMetric(id: MetricId): void {
    const i = selectedMetrics.indexOf(id);
    if (i >= 0) {
      if (selectedMetrics.length > 1) selectedMetrics.splice(i, 1);
    } else if (selectedMetrics.length < 3) {
      selectedMetrics.push(id);
      selectedMetrics.sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b));
    }
  }

  // Threshold handle: the value follows the pointer exactly (no spring).
  function handle(el: HTMLElement) {
    const toFactor = (clientY: number) => {
      const u = hosts.get('focus')?.u;
      if (!u || baseline === null) return null;
      const v = u.posToVal(clientY - u.over.getBoundingClientRect().top, 'y');
      return Math.round(Math.min(4, Math.max(1.05, v / baseline)) * 100) / 100;
    };
    const down = (e: PointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      dragging = true;
    };
    const move = (e: PointerEvent) => {
      if (!dragging) return;
      const f = toFactor(e.clientY);
      if (f !== null) factor = f;
    };
    const up = (e: PointerEvent) => {
      dragging = false;
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
    };
    const key = (e: KeyboardEvent) => {
      const s = e.shiftKey ? 0.25 : 0.05;
      if (e.key === 'ArrowUp') factor = Math.min(4, +(factor + s).toFixed(2));
      else if (e.key === 'ArrowDown') factor = Math.max(1.05, +(factor - s).toFixed(2));
      else if (e.key === 'Home') factor = 1.05;
      else if (e.key === 'End') factor = 4;
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

  function onKey(e: KeyboardEvent): void {
    if (e.metaKey || e.ctrlKey || e.altKey || (e.target as HTMLElement).getAttribute('role') === 'slider') return;
    const k = e.key;
    if (k === 'f' || k === 'F') zoom.fit(true);
    else if (k === '+' || k === '=') zoom.zoomBy(1 / 1.6, undefined, true);
    else if (k === '-' || k === '_') zoom.zoomBy(1.6, undefined, true);
    else if (k === 'ArrowLeft') zoom.panBy(-0.25, true);
    else if (k === 'ArrowRight') zoom.panBy(0.25, true);
    else if (k === 'End') zoom.follow(true);
    else return;
    e.preventDefault();
  }

  const fmtCol = (_c: Col, v: number, digits: number) => (Number.isFinite(v) ? (digits === 0 ? grouped(v) : fixed(v, digits)) : '—');

  // Rail rows: the last hour.
  const WINDOW = 3600;
  const rowState = $derived.by(() => {
    void count;
    const n = stream.n;
    const c = cols();
    return ROWS.map((r) => {
      const a = c[r.col] as Float64Array;
      let lo = Infinity;
      let hi = -Infinity;
      const tEnd = n ? c.t[n - 1] : 0;
      for (let i = n - 1; i >= 0 && c.t[i] >= tEnd - WINDOW; i--) {
        lo = Math.min(lo, a[i]);
        hi = Math.max(hi, a[i]);
      }
      return { ...r, value: n ? a[n - 1] : NaN, lo, hi };
    });
  });

  const hoverRead = $derived.by(() => {
    if (!hover) return null;
    const c = cols();
    const i = hover.idx;
    return {
      t: clockUtc(c.t[i]),
      frame: i + 1,
      rows: ROWS.map((r) => ({ label: r.label, unit: r.unit, v: fmtCol(r.col, (c[r.col] as Float64Array)[i], r.digits) })),
      above: threshold !== null && c.hfd[i] > threshold,
    };
  });

  const tipStyle = $derived.by(() => {
    if (!hover || !wall) return '';
    const w = wall.clientWidth;
    const left = hover.left + 16 + 210 > w ? hover.left - 16 - 210 : hover.left + 16;
    const top = Math.max(4, Math.min(wall.clientHeight - 230, hover.top - 60));
    return `left:${left}px;top:${top}px`;
  });
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div class="cond" class:with-rail={railCard} bind:this={root} role="region" aria-label="Conditions timeline" tabindex="0" onkeydown={onKey}>
  {#if railCard}
    <aside class="card" aria-label="Conditions card">
      <header class="card-head">
        <Icon name="session-metrics" size={16} />
        <h3>Conditions</h3>
        <span class="grow"></span>
        {#if openEpisode}
          <span class="lab-chip attention"><span class="lab-dot busy"></span>Attention</span>
        {:else}
          <span class="lab-chip"><span class="lab-dot ok"></span>Steady</span>
        {/if}
      </header>
      <p class="card-sub num">last 60 min · {grouped(count)} frames tonight</p>
      <ul class="rows">
        {#each rowState as r (r.col)}
          {@const alert = r.col === 'hfd' && openEpisode !== null}
          <li class:alert>
            <span class="lab-eyebrow">{r.label}</span>
            <span class="val num"><b>{fmtCol(r.col, r.value, r.digits)}</b>{#if r.unit}<small>{r.unit}</small>{/if}</span>
            <Sparkline
              width={120}
              height={26}
              version={`${count}-${factor}`}
              label="{r.label}, last 60 minutes, from {fmtCol(r.col, r.lo, r.digits)} to {fmtCol(r.col, r.hi, r.digits)}"
              spec={(ink) => {
                const n = stream.n;
                const tEnd = n ? cols().t[n - 1] : 0;
                return {
                  xs: cols().t,
                  ys: cols()[r.col] as Float64Array,
                  n,
                  x0: tEnd - WINDOW,
                  x1: tEnd,
                  invert: r.invert,
                  color: alert ? ink.fg.a() : ink.fgMuted.a(),
                  lastDot: true,
                  ref: r.col === 'hfd' && threshold !== null ? threshold : undefined,
                  markOut: r.col === 'hfd',
                };
              }}
            />
            <span class="range num">{fmtCol(r.col, r.lo, r.digits)}–{fmtCol(r.col, r.hi, r.digits)}</span>
            {#if alert}
              <span class="why">above {factor.toFixed(2)}× baseline since {clockUtc(cols().t[openEpisode.fired], false)}</span>
            {/if}
          </li>
        {/each}
      </ul>
    </aside>
  {/if}

  <section class="main">
    <div class="bar">
      <div class="chips" role="group" aria-label="Metrics (up to 3)">
        {#each ORDER as id (id)}
          {@const on = selectedMetrics.includes(id)}
          <button
            class="metric"
            aria-pressed={on}
            aria-disabled={!on && selectedMetrics.length >= 3}
            use:tooltip={{ text: !on && selectedMetrics.length >= 3 ? 'Three plots at most: hide one first' : METRICS[id].sub }}
            onclick={() => toggleMetric(id)}
          >
            {METRICS[id].label}
          </button>
        {/each}
      </div>
      <span class="lab-sep"></span>
      <button class="lab-tool" aria-label="Fit" aria-keyshortcuts="F" use:tooltip={{ text: 'Fit the night so far', shortcut: 'F' }} onclick={() => zoom.fit(true)}>
        <Icon name="zoom-fit" size={16} />
      </button>
      <span class="lab-chip mode">{mode === 'fit' ? 'Run to now' : mode === 'follow' ? 'Following now' : 'Zoom kept · F fits'}</span>
      <span class="grow"></span>
      {#if lastT !== null && age !== null}
        <span class="lab-chip" class:attention={stale} data-shot="age">
          <span class="lab-dot {stale ? 'busy' : 'ok'}"></span>
          {#if stale}
            No frame for <b>{duration(age)}</b> · expected every {cadence ? duration(cadence) : '—'}
          {:else}
            Last frame <b>{duration(age)}</b> ago · every {cadence ? duration(cadence) : '—'}
          {/if}
        </span>
      {/if}
      {#if threshold !== null}
        <span class="lab-chip" class:attention={openEpisode !== null}>
          <span class="lab-dot {openEpisode ? 'busy' : 'ok'}"></span>
          {#if openEpisode}HFD &gt; {factor.toFixed(2)}× baseline since <b>{clockUtc(cols().t[openEpisode.fired], false)}</b>{:else}HFD within {factor.toFixed(2)}× baseline{/if}
        </span>
      {/if}
    </div>

    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="wall" bind:this={wall} onpointerleave={() => (hover = null)}>
      {#each selectedMetrics as id, i (id)}
        {@const m = METRICS[id]}
        {@const last = i === selectedMetrics.length - 1}
        <section class="facet" style:flex-basis={last ? '24px' : '0px'} aria-label={m.sub}>
          <header>
            <h4>{m.label}</h4>
            {#if id === 'focus'}
              <span class="key"><i class="line"></i>HFD</span>
              <span class="key"><i class="line dash"></i>FWHM</span>
            {/if}
            <span class="sub">{m.sub}</span>
          </header>
          <div class="lab-plot-host plot" {@attach facetHost(id, i === 0, last)}>
            {#if id === 'focus' && handleY !== null && threshold !== null}
              <div
                class="thr"
                class:dragging
                style:top="{handleY}px"
                role="slider"
                tabindex="0"
                aria-label="HFD attention threshold, times the baseline"
                aria-orientation="vertical"
                aria-valuemin={1.05}
                aria-valuemax={4}
                aria-valuenow={factor}
                aria-valuetext="{factor.toFixed(2)} times the baseline, {fixed(threshold, 2)} px"
                {@attach handle}
              >
                <span class="num">{factor.toFixed(2)}× · {fixed(threshold, 2)} px</span>
              </div>
            {/if}
          </div>
        </section>
      {/each}
      {#if hoverRead}
        <div class="lab-readout" style={tipStyle} aria-hidden="true">
          <div class="t">{hoverRead.t} UTC · frame {hoverRead.frame}</div>
          <hr />
          {#each hoverRead.rows as r (r.label)}
            <div class="kv"><span>{r.label}</span><span class="v">{r.v}{r.unit ? ` ${r.unit}` : ''}</span></div>
          {/each}
          {#if hoverRead.above}<hr /><div class="flag">HFD above the threshold</div>{/if}
        </div>
      {/if}
    </div>
  </section>
</div>

<style>
  .cond {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    height: 100%;
    min-height: 0;
    background: var(--chart-surface);
    outline-offset: -2px;
  }
  .cond.with-rail {
    grid-template-columns: 360px minmax(0, 1fr);
  }
  @media (max-width: 1360px) {
    .cond.with-rail {
      grid-template-columns: 300px minmax(0, 1fr);
    }
  }
  /* Status chips shrink (ellipsis) before anything overflows the bar. */
  .bar .lab-chip {
    flex-shrink: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .card {
    display: flex;
    flex-direction: column;
    min-height: 0;
    padding: var(--space-4) var(--space-4) var(--space-3);
    border-right: var(--border-w) solid var(--border);
    background: var(--bg);
    overflow: auto;
  }
  .card-head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--fg-muted);
  }
  .card-head h3 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .card-sub {
    margin: 2px 0 var(--space-3) 24px;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .rows {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .rows li {
    display: grid;
    grid-template-columns: 62px minmax(0, 1fr) 120px;
    grid-template-rows: auto auto;
    align-items: center;
    column-gap: var(--space-3);
    padding: 7px 0 6px var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
    border-left: 2px solid transparent;
  }
  .rows li.alert {
    border-left-color: var(--warning);
  }
  .val {
    font-size: var(--text-xl);
    font-weight: var(--weight-medium);
    line-height: 1.1;
    white-space: nowrap;
  }
  .val b {
    font-weight: var(--weight-medium);
  }
  .val small {
    margin-left: 4px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-regular);
  }
  .range {
    grid-column: 3;
    justify-self: end;
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }
  .why {
    grid-column: 1 / 3;
    color: var(--fg);
    font-size: var(--text-xs);
  }

  .main {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }
  .bar {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: var(--lab-chart-toolbar-h);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    background: var(--bg);
    flex: none;
  }
  .chips {
    display: inline-flex;
    gap: 2px;
  }
  .metric {
    height: 24px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    cursor: pointer;
  }
  .metric:hover {
    color: var(--fg);
    background: var(--hover-bg);
  }
  .metric[aria-pressed='true'] {
    border-color: var(--border);
    background: var(--toggled-bg);
    color: var(--fg);
  }
  .metric[aria-disabled='true'] {
    color: var(--fg-disabled);
    cursor: default;
    background: transparent;
  }
  .grow {
    flex: 1;
  }
  .wall {
    position: relative;
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 2px var(--space-3) var(--space-2) var(--space-2);
  }
  .facet {
    display: flex;
    flex-direction: column;
    flex-grow: 1;
    min-height: 80px;
  }
  .facet + .facet {
    border-top: var(--border-w) solid var(--border-soft);
  }
  .facet header {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: var(--lab-chart-header-h);
    padding-left: 50px;
    flex: none;
  }
  h4 {
    margin: 0;
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
  }
  .sub {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .key {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .key .line {
    display: inline-block;
    width: 16px;
    border-top: 1.5px solid var(--fg);
  }
  .key .line.dash {
    border-top: 1.5px dashed var(--fg-muted);
  }
  .plot {
    flex: 1;
    min-height: 50px;
  }
  .thr {
    position: absolute;
    right: 2px;
    z-index: 3;
    display: flex;
    align-items: center;
    height: 18px;
    padding: 0 6px;
    transform: translateY(-50%);
    border: 1px solid var(--warning);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-2xs);
    cursor: ns-resize;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
  }
  .thr:hover,
  .thr.dragging {
    background: var(--surface);
  }
  .kv {
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
  }
</style>
