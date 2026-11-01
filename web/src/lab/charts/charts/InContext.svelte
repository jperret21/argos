<!--
  The charts in their functional space: Observe › Run during the long
  watch of the night (functional-spaces 4.6, W4), at the reference sizes.
  92 px nav rail, 46 px toolbar, the 16:9 image, the band under it sized as
  layout.ts sizes it (299 px at 1440 x 900), a 420 px right rail, the 32 px
  status bar. Everything except the charts is a static mock (the image is
  a synthetic star field drawn here, the toolbar does nothing).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import Icon from '../../../lib/components/Icon.svelte';
  import { env } from '../env.svelte';
  import { clock, observedCadence } from '../sim/stream.svelte';
  import { AUTOFOCUS, COMPS, hfdBaseline, hfdEpisodes, prng, RUN_END, RUN_START, SITE, TARGET } from '../sim/night';
  import { crossings, horizontal } from '../sim/astro';
  import { readInks, type ChartInks } from '../core/palette';
  import { clockUtc, duration, fixed, grouped } from '../core/format';
  import { rms } from '../core/stats';
  import LightCurve from './LightCurve.svelte';
  import Sparkline from '../mini/Sparkline.svelte';
  import AgeMeter from '../mini/AgeMeter.svelte';
  import RunProgress from '../mini/RunProgress.svelte';
  import type { SparkSpec } from '../mini/spark';

  const s = clock.night;
  const c = s.cols;
  let tick = $state(0);
  $effect(() => {
    const id = setInterval(() => (tick = Math.floor(clock.now)), 250);
    return () => clearInterval(id);
  });
  const n = $derived(s.n);
  const last = $derived(n - 1);
  const cadence = $derived.by(() => {
    void n;
    return observedCadence(s);
  });
  const age = $derived.by(() => {
    void tick;
    return n ? Math.max(0, clock.now - c.t[last]) : null;
  });
  const base = $derived.by(() => {
    void n;
    return hfdBaseline(c, n);
  });
  const thr = $derived(base !== null ? base * 1.5 : null);
  const episode = $derived.by(() => {
    void n;
    const e = hfdEpisodes(c, n, 1.5);
    const x = e[e.length - 1];
    return x && x.end === null ? x : null;
  });
  const checkRms = $derived.by(() => {
    void n;
    return rms(c.checkDelta, Math.max(0, n - 60), n);
  });
  const limitAt = crossings((t) => horizontal(TARGET.pos, SITE, t).alt, 30, RUN_START, RUN_END + 7200).find((x) => !x.rising)?.t ?? null;

  const ALT_T = new Float64Array(181);
  const ALT_V = new Float64Array(181);
  for (let i = 0; i <= 180; i++) {
    ALT_T[i] = RUN_START - 3600 + i * ((RUN_END - RUN_START + 7200) / 180);
    ALT_V[i] = horizontal(TARGET.pos, SITE, ALT_T[i]).alt;
  }

  const lastHour = (ys: Float64Array, extra: Partial<SparkSpec> = {}) => (ink: ChartInks): SparkSpec => {
    const t1 = n ? c.t[last] : 0;
    return { xs: c.t, ys, n, x0: t1 - 3600, x1: t1, color: ink.fgMuted.a(), lastDot: true, ...extra };
  };
  const ROWS: { label: string; col: 'hfd' | 'stars' | 'sky' | 'airmass'; unit: string; digits: number; invert?: boolean }[] = [
    { label: 'HFD', col: 'hfd', unit: 'px', digits: 2 },
    { label: 'Stars', col: 'stars', unit: '', digits: 0 },
    { label: 'Sky', col: 'sky', unit: 'ADU', digits: 0 },
    { label: 'Airmass', col: 'airmass', unit: '', digits: 3, invert: true },
  ];

  // -- Synthetic star field (the viewer is another team's: this is a stand-in) ----------
  let field: HTMLCanvasElement;
  let fieldBox: HTMLDivElement;
  let fw = $state(0);
  let fh = $state(0);
  let drawnFor = '';

  interface Star {
    x: number;
    y: number;
    f: number;
  }
  const rand = prng(42);
  const STARS: Star[] = Array.from({ length: 520 }, () => ({ x: rand(), y: rand(), f: Math.pow(rand(), 3.2) }));
  // Photometry stars, in field fractions (target near the centre).
  const MARKS = [
    { role: 'target', x: 0.5, y: 0.48, label: TARGET.label },
    { role: 'check', x: 0.63, y: 0.3, label: 'K' },
    { role: 'comparison', x: 0.36, y: 0.62, label: 'C1' },
    { role: 'comparison', x: 0.7, y: 0.66, label: 'C2' },
    { role: 'comparison', x: 0.28, y: 0.3, label: 'C3' },
    { role: 'comparison', x: 0.57, y: 0.78, label: 'C4' },
    { role: 'comparison', x: 0.43, y: 0.19, label: 'C5' },
  ] as const;
  for (const m of MARKS) STARS.push({ x: m.x, y: m.y, f: m.role === 'target' ? 0.85 : 0.45 });

  function drawField(): void {
    if (!field || fw < 10) return;
    const hfd = n ? c.hfd[last] : 2.2;
    const key = `${env.theme}-${fw}-${fh}-${Math.round(hfd * 4)}`;
    if (key === drawnFor) return;
    drawnFor = key;
    const ink = readInks(field);
    const dpr = 1; // a stand-in: 1:1 is enough
    field.width = fw * dpr;
    field.height = fh * dpr;
    field.style.width = `${fw}px`;
    field.style.height = `${fh}px`;
    const ctx = field.getContext('2d');
    if (!ctx) return;
    const W = field.width;
    const H = field.height;
    const img = ctx.createImageData(W, H);
    const buf = new Float32Array(W * H);
    const r2 = prng(9);
    for (let i = 0; i < buf.length; i++) buf[i] = 0.035 + 0.014 * (r2() + r2() + r2() - 1.5);
    const sig = Math.max(0.8, (hfd * 0.55 * W) / 1920);
    for (const st of STARS) {
      const cx = st.x * W;
      const cy = st.y * H;
      const amp = 0.08 + 1.6 * st.f * (2.2 / Math.max(2.2, hfd)) ** 2;
      const R = Math.ceil(sig * 3.5 + st.f * 3);
      for (let y = Math.max(0, Math.floor(cy - R)); y < Math.min(H, cy + R); y++) {
        for (let x = Math.max(0, Math.floor(cx - R)); x < Math.min(W, cx + R); x++) {
          const d2 = (x - cx) ** 2 + (y - cy) ** 2;
          buf[y * W + x] += amp * Math.exp(-d2 / (2 * sig * sig));
        }
      }
    }
    const [tr, tg, tb] = ink.viewerTint.rgb01;
    for (let i = 0; i < buf.length; i++) {
      const v = Math.min(1, Math.max(0, buf[i]));
      const k = Math.pow(v, 0.55) * 255;
      img.data[i * 4] = k * tr;
      img.data[i * 4 + 1] = k * tg;
      img.data[i * 4 + 2] = k * tb;
      img.data[i * 4 + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    // Role overlays: the same shapes as in the plots (BRAND 2.6).
    ctx.lineWidth = 1.5;
    ctx.font = `500 11px ${ink.mono}`;
    for (const m of MARKS) {
      const x = m.x * W;
      const y = m.y * H;
      const col = m.role === 'target' ? ink.target : m.role === 'check' ? ink.check : ink.comparison;
      ctx.strokeStyle = col.a();
      ctx.beginPath();
      const r = 13;
      if (m.role === 'target') ctx.arc(x, y, r, 0, Math.PI * 2);
      else if (m.role === 'comparison') ctx.rect(x - r * 0.886, y - r * 0.886, r * 1.772, r * 1.772);
      else {
        const k = r * 1.347;
        ctx.moveTo(x, y - k);
        ctx.lineTo(x + k * 0.866, y + k * 0.5);
        ctx.lineTo(x - k * 0.866, y + k * 0.5);
        ctx.closePath();
      }
      ctx.stroke();
      ctx.lineWidth = 3;
      ctx.strokeStyle = 'rgba(0,0,0,0.9)';
      ctx.strokeText(m.label, x + r + 4, y - r + 2);
      ctx.fillStyle = ink.fg.a();
      ctx.fillText(m.label, x + r + 4, y - r + 2);
      ctx.lineWidth = 1.5;
    }
  }

  $effect(() => {
    void env.theme;
    void fw;
    void fh;
    void n;
    untrack(drawField);
  });

  $effect(() => {
    const ro = new ResizeObserver((e) => {
      const r = e[e.length - 1].contentRect;
      fw = Math.floor(r.width);
      fh = Math.floor(r.height);
    });
    ro.observe(fieldBox);
    return () => ro.disconnect();
  });

  const altSpec = (ink: ChartInks): SparkSpec => ({ xs: ALT_T, ys: ALT_V, n: ALT_T.length, y0: 0, y1: 90, ref: 30, refBelow: true, now: clock.now, area: true, color: ink.fg.a() });
  const altNow = $derived.by(() => {
    void tick;
    return horizontal(TARGET.pos, SITE, clock.now).alt;
  });
</script>

<div class="ctx">
  <nav class="nav" aria-label="Sections (mock)">
    <span class="mark"><Icon name="about" size={24} /></span>
    {#each [{ i: 'nav-connection', l: 'Connection' }, { i: 'nav-imaging', l: 'Observe', on: true }, { i: 'nav-sequencer', l: 'Plan' }, { i: 'nav-analyze', l: 'Review' }] as e (e.l)}
      <span class="entry" class:on={e.on}><Icon name={e.i} size={22} /><small>{e.l}</small></span>
    {/each}
    <span class="grow"></span>
    <span class="entry"><Icon name="settings" size={22} /><small>Settings</small></span>
  </nav>

  <header class="tools">
    <span class="eq"><i class="d ok"></i>Seestar S50</span>
    <span class="modes" role="group" aria-label="Task modes (proposal, functional-spaces P1)">
      <span>Framing</span><span>Focus</span><span>Field</span><span class="on"><Icon name="light-curve" size={14} />Run</span>
    </span>
    <span class="sep"></span>
    <Icon name="capture" size={20} /><Icon name="live" size={20} />
    <span class="sep"></span>
    <Icon name="zoom-fit" size={20} /><Icon name="sky-grid" size={20} /><Icon name="catalogue" size={20} /><Icon name="error-bars" size={20} /><Icon name="relative-flux" size={20} />
    <span class="grow"></span>
    <Icon name="panels" size={20} />
  </header>

  <main class="center">
    <div class="image" bind:this={fieldBox}>
      <canvas bind:this={field} aria-label="Synthetic star field (stand-in for the viewer)"></canvas>
      <div class="hud num">
        <span class="hchip"><b>#{n}</b></span><span class="hchip">10.0 s</span><span class="hchip">IR</span><span class="hchip">{TARGET.label}</span>
      </div>
      <div class="hud right num"><span class="hchip">field tracked · re-identified 21 s ago</span></div>
    </div>
    <div class="band">
      <LightCurve compact facets={['target', 'check']} />
    </div>
  </main>

  <aside class="rail">
    <section class="card">
      <header>
        <Icon name="nav-sequencer" size={16} /><h3>Run</h3><span class="grow"></span>
        <span class="lab-chip"><span class="lab-dot busy"></span>Running</span>
      </header>
      <div class="line"><span>{TARGET.label} · step 1 / 1</span><span class="num"><b>{grouped(n)}</b> / {grouped(s.total)}</span></div>
      <RunProgress start={RUN_START} end={RUN_END} now={clock.now} times={c.t} {n} marks={AUTOFOCUS} width={370} height={8} />
      <div class="line"><span>Last frame</span><AgeMeter {age} {cadence} width={130} /></div>
      <div class="line"><span>Ends</span><span class="num"><b>{clockUtc(RUN_END, false)}</b> UTC · in {duration(RUN_END - clock.now)}</span></div>
      <div class="actions"><span class="btn"><Icon name="pause" size={16} />Pause</span><span class="btn danger"><Icon name="stop" size={16} />Stop…</span></div>
    </section>
    <section class="card">
      <header>
        <Icon name="photometry" size={16} /><h3>Photometry</h3><span class="grow"></span>
        <span class="lab-chip"><span class="lab-dot ok"></span>Consistent</span>
      </header>
      <div class="phot">
        <p class="big num">{n ? fixed(c.target[last], 3) : '—'}<small>± {n ? fixed(c.targetErr[last], 3) : '—'} V</small></p>
        <span class="num small">check rms <b>{fixed(checkRms, 3)}</b> · comps <b>{n ? c.nUsed[last] : '—'}</b>/{COMPS.length}</span>
      </div>
    </section>
    <section class="card">
      <header>
        <Icon name="session-metrics" size={16} /><h3>Conditions</h3><span class="grow"></span>
        {#if episode}<span class="lab-chip attention"><span class="lab-dot busy"></span>Attention</span>{:else}<span class="lab-chip"><span class="lab-dot ok"></span>Steady</span>{/if}
      </header>
      {#each ROWS as r (r.col)}
        {@const alert = r.col === 'hfd' && episode !== null}
        <div class="crow" class:alert>
          <span class="lab-eyebrow">{r.label}</span>
          <span class="num val"><b>{n ? (r.digits ? fixed(c[r.col][last], r.digits) : grouped(c[r.col][last])) : '—'}</b>{#if r.unit}<small>{r.unit}</small>{/if}</span>
          <Sparkline width={130} height={22} version={`${n}`} label="{r.label}, last hour" spec={(ink) => ({ ...lastHour(c[r.col], { invert: r.invert })(ink), color: alert ? ink.fg.a() : ink.fgMuted.a(), ref: r.col === 'hfd' && thr !== null ? thr : undefined, markOut: r.col === 'hfd' })} />
        </div>
        {#if alert}<p class="why">HFD above 1.5× baseline since {clockUtc(c.t[episode.fired], false)} · 3 frames rule</p>{/if}
      {/each}
      <div class="crow">
        <span class="lab-eyebrow">Alt</span>
        <span class="num val"><b>{fixed(altNow, 0)}°</b><small>{limitAt ? `30° at ${clockUtc(limitAt, false)}` : ''}</small></span>
        <Sparkline width={130} height={22} version={`${tick >> 6}`} label="Altitude over the night" spec={altSpec} />
      </div>
    </section>
    <section class="card">
      <header>
        <Icon name="visibility" size={16} /><h3>Visibility</h3><span class="grow"></span>
        <span class="num small">{SITE.name} · min. 30°</span>
      </header>
      <Sparkline width={370} height={64} version={`${tick >> 6}`} label="Altitude of {TARGET.label} over the night, the 30° limit and now" spec={altSpec} />
      <div class="line"><span>Above 30° until</span><span class="num"><b>{limitAt ? clockUtc(limitAt, false) : '—'}</b> UTC · run ends {clockUtc(RUN_END, false)}</span></div>
    </section>
  </aside>

  <footer class="status">
    <span class="seg"><i class="d ok"></i>Seestar <i class="d ok"></i>Net</span>
    <span class="seg">Mount <b>Tracking</b></span>
    <span class="chip"><i class="rec"></i><b>REC</b> {TARGET.label} <RunProgress start={RUN_START} end={RUN_END} now={clock.now} times={c.t} {n} marks={AUTOFOCUS} width={70} /> <span class="num"><b>{grouped(n)}</b>/{grouped(s.total)}</span></span>
    <span class="chip"><AgeMeter {age} {cadence} width={40} /></span>
    {#if episode}<span class="chip attention"><span class="lab-dot busy"></span><b>Attention 1</b> · HFD</span>{/if}
    <span class="grow"></span>
    <span class="seg num">{clockUtc(clock.now)} UTC</span>
    <span class="seg"><Icon name="log" size={16} />Log</span>
  </footer>
</div>

<style>
  .ctx {
    display: grid;
    grid-template-columns: 92px minmax(0, 1fr) 420px;
    grid-template-rows: 46px minmax(0, 1fr) 32px;
    height: 100%;
    background: var(--bg);
  }
  .nav {
    grid-row: 1 / 3;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding-top: 10px;
    border-right: var(--border-w) solid var(--border);
    color: var(--fg-muted);
  }
  .nav .mark {
    color: var(--accent);
    margin-bottom: 14px;
  }
  .entry {
    position: relative;
    display: grid;
    justify-items: center;
    gap: 3px;
    width: 100%;
    padding: 10px 0;
  }
  .entry small {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .entry.on {
    background: var(--surface);
    color: var(--toggled-fg);
  }
  .entry.on small {
    color: var(--toggled-fg);
  }
  .entry.on::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: var(--accent);
  }
  .grow {
    flex: 1;
  }
  .tools {
    grid-column: 2 / 4;
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border);
    color: var(--fg-muted);
  }
  .eq {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .d {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--status-ok);
  }
  .modes {
    display: inline-flex;
    padding: 1px;
    border: 1px solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .modes span {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    height: 26px;
    padding: 0 10px;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .modes .on {
    background: var(--toggled-bg);
    border: 1px solid var(--border);
    color: var(--fg);
  }
  .sep {
    width: 1px;
    height: 20px;
    background: var(--border-soft);
  }
  .center {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }
  .image {
    position: relative;
    aspect-ratio: 16 / 9;
    width: 100%;
    flex: none;
    background: var(--viewer-bg);
    overflow: hidden;
  }
  .image canvas {
    display: block;
  }
  .hud {
    position: absolute;
    top: 8px;
    left: 8px;
    display: flex;
    gap: 4px;
  }
  .hud.right {
    left: auto;
    right: 8px;
  }
  .hchip {
    padding: 1px 6px;
    border-radius: var(--radius-s);
    background: var(--scrim);
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .band {
    flex: 1;
    min-height: 0;
    border-top: var(--border-w) solid var(--border);
  }
  .rail {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-2);
    border-left: var(--border-w) solid var(--border);
    overflow: hidden;
  }
  .card {
    display: grid;
    gap: 6px;
    padding: 10px 14px 10px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
  }
  .card header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--fg-muted);
  }
  .card h3 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .line {
    display: flex;
    align-items: center;
    justify-content: space-between;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .line b,
  .small b {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .line .num {
    font-size: var(--text-xs);
  }
  .actions {
    display: flex;
    gap: var(--space-2);
    margin-top: 2px;
  }
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 28px;
    padding: 0 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
  }
  .btn.danger :global(.icon) {
    color: var(--danger);
  }
  .btn.danger {
    border-color: var(--danger);
  }
  .phot {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
  }
  .big {
    margin: 0;
    font-size: var(--text-xl);
    font-weight: var(--weight-medium);
  }
  .big small {
    margin-left: 6px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-regular);
  }
  .small {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .crow {
    display: grid;
    grid-template-columns: 56px 1fr 130px;
    align-items: center;
    gap: var(--space-2);
    padding: 3px 0 3px 6px;
    border-left: 2px solid transparent;
  }
  .crow.alert {
    border-left-color: var(--warning);
  }
  .val {
    font-size: var(--text-m);
    white-space: nowrap;
  }
  .val b {
    font-weight: var(--weight-medium);
  }
  .val small {
    margin-left: 5px;
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }
  .why {
    margin: 0 0 2px 8px;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .status {
    grid-column: 1 / 4;
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: 0 var(--space-3);
    border-top: var(--border-w) solid var(--border);
    color: var(--text-muted);
    font-size: var(--text-s);
    white-space: nowrap;
  }
  .status .seg {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .status b {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 22px;
    padding: 0 7px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    font-size: var(--text-xs);
  }
  .chip.attention {
    border-color: var(--warning);
  }
  .rec {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--danger);
  }
</style>
