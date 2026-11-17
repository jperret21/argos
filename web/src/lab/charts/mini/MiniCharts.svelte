<!--
  Mini-charts for glanceable places: status-bar chips (32 px), rail rows
  (Run card), and the glance view read from 2 m (functional-spaces 2.5:
  88 px primary digits, 66 px secondary). Every chip states its value in
  text; the chart adds the trend or the time, never information found
  nowhere else. States: normal, attention (warning outline + word), stale
  (muted + "as of"), no data ("—").
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import { clock, observedCadence } from '../sim/stream.svelte';
  import { AUTOFOCUS, COMPS, hfdBaseline, hfdEpisodes, RUN_END, RUN_START, SITE, TARGET } from '../sim/night';
  import { crossings, horizontal } from '../sim/astro';
  import { clockUtc, duration, fixed, grouped } from '../core/format';
  import { rms } from '../core/stats';
  import type { ChartInks } from '../core/palette';
  import Sparkline from './Sparkline.svelte';
  import AgeMeter from './AgeMeter.svelte';
  import RunProgress from './RunProgress.svelte';
  import type { SparkSpec } from './spark';

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
  const limitAt = $derived(crossings((t) => horizontal(TARGET.pos, SITE, t).alt, 30, clock.now, RUN_END + 7200).find((x) => !x.rising)?.t ?? null);
  const altNow = $derived(horizontal(TARGET.pos, SITE, clock.now).alt);

  // Altitude curve of the night for the mini arc.
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

  const hfdSpec = (attention: boolean) => (ink: ChartInks): SparkSpec => ({
    ...lastHour(c.hfd)(ink),
    color: attention ? ink.fg.a() : ink.fgMuted.a(),
    ref: thr ?? undefined,
    markOut: true,
  });
  const magSpec = (ink: ChartInks): SparkSpec => ({ ...lastHour(c.target)(ink), invert: true, dots: true, color: ink.target.a() });
  const altSpec = (ink: ChartInks): SparkSpec => ({
    xs: ALT_T,
    ys: ALT_V,
    n: ALT_T.length,
    y0: 0,
    y1: 90,
    ref: 30,
    refBelow: true,
    now: clock.now,
    area: true,
    color: ink.fg.a(), // altitude is geometry, not a photometric role: neutral (lab synthesis)
  });

  const stateRows = [
    { id: 'age', label: 'Frame age' },
    { id: 'hfd', label: 'HFD' },
    { id: 'mag', label: 'Target' },
    { id: 'alt', label: 'Altitude' },
  ] as const;
  const STATES = ['Normal', 'Attention', 'Stale', 'No data'] as const;
</script>

<div class="mini">
  <section class="sb-wrap">
    <p class="lab-eyebrow">Status bar · 32 px · chips with a chart carry the value in text first</p>
    <div class="statusbar" role="group" aria-label="Status bar mock">
      <span class="seg"><Icon name="nav-connection" size={16} /> Seestar <i class="d ok"></i></span>
      <span class="seg">Mount <b>Tracking</b></span>
      <span class="sep"></span>
      <span class="chip run">
        <i class="rec"></i><b>REC</b> {TARGET.label}
        <RunProgress start={RUN_START} end={RUN_END} now={clock.now} times={c.t} {n} marks={AUTOFOCUS} width={84} />
        <span class="num"><b>{grouped(n)}</b>/{grouped(s.total)}</span>
        <span class="num">ends {clockUtc(RUN_END, false)}</span>
      </span>
      <span class="chip">
        <AgeMeter {age} {cadence} width={44} />
      </span>
      <span class="chip" class:attention={episode !== null}>
        <span class="k">HFD</span><b class="num">{n ? fixed(c.hfd[last], 2) : '—'}</b>
        <Sparkline width={56} height={14} version={`${n}`} spec={hfdSpec(episode !== null)} label="HFD, last hour" />
        {#if episode}<span class="word">Attention</span>{/if}
      </span>
      <span class="chip">
        <span class="k">V</span><b class="num">{n ? fixed(c.target[last], 3) : '—'}</b>
        <Sparkline width={56} height={14} version={`${n}`} spec={magSpec} label="Target magnitude, last hour" />
      </span>
      <span class="chip">
        <span class="k">Alt</span><b class="num">{fixed(altNow, 0)}°</b>
        <Sparkline width={56} height={14} version={`${tick >> 6}`} spec={altSpec} label="Altitude over the night, now marked" />
        <span class="num">{limitAt ? `30° at ${clockUtc(limitAt, false)}` : ''}</span>
      </span>
      <span class="grow"></span>
      <span class="seg">Log</span>
    </div>
  </section>

  <div class="cols">
    <section class="rail">
      <p class="lab-eyebrow">Rail · 420 px</p>
      <article class="card">
        <header>
          <Icon name="nav-sequencer" size={16} />
          <h3>Run</h3>
          <span class="grow"></span>
          <span class="lab-chip"><span class="lab-dot busy"></span>Running</span>
        </header>
        <div class="line"><span>{TARGET.label} · step 1 / 1</span><span class="num"><b>{grouped(n)}</b> / {grouped(s.total)} frames</span></div>
        <RunProgress start={RUN_START} end={RUN_END} now={clock.now} times={c.t} {n} marks={AUTOFOCUS} width={388} height={10} />
        <div class="line"><span>Last frame</span><AgeMeter {age} {cadence} width={150} /></div>
        <div class="line"><span>Cadence</span><span class="num">every {cadence ? duration(cadence) : '—'} · median of 15</span></div>
        <div class="line"><span>Ends</span><span class="num"><b>{clockUtc(RUN_END, false)}</b> UTC · in {duration(RUN_END - clock.now)}</span></div>
        <div class="line"><span>Next autofocus</span><span class="num">{AUTOFOCUS.find((t) => t > clock.now) ? clockUtc(AUTOFOCUS.find((t) => t > clock.now)!, false) : 'none'}</span></div>
      </article>
      <article class="card">
        <header>
          <Icon name="photometry" size={16} />
          <h3>Photometry</h3>
          <span class="grow"></span>
          <span class="lab-chip"><span class="lab-dot ok"></span>Consistent</span>
        </header>
        <div class="phot">
          <div>
            <p class="lab-eyebrow">{TARGET.label} · V</p>
            <p class="big num">{n ? fixed(c.target[last], 3) : '—'}<small>± {n ? fixed(c.targetErr[last], 3) : '—'}</small></p>
          </div>
          <Sparkline width={170} height={40} version={`${n}`} spec={magSpec} label="Target magnitude, last hour, brighter up" />
        </div>
        <div class="line"><span>Check rms (60)</span><span class="num"><b>{fixed(checkRms, 3)}</b> mag</span></div>
        <div class="line"><span>Comparisons used</span><span class="num"><b>{n ? c.nUsed[last] : '—'}</b> / {COMPS.length}</span></div>
      </article>
    </section>

    <section class="right">
      <p class="lab-eyebrow">Chip states (status-bar scale)</p>
      <div class="states" role="table" aria-label="Chip states">
        <div class="hrow" role="row">
          <span role="columnheader"></span>
          {#each STATES as st (st)}<span role="columnheader" class="lab-eyebrow">{st}</span>{/each}
        </div>
        {#each stateRows as r (r.id)}
          <div class="srow" role="row">
            <span role="rowheader" class="rh">{r.label}</span>
            {#each STATES as st (st)}
              <span role="cell">
                {#if r.id === 'age'}
                  <span class="chip" class:attention={st === 'Attention'} class:stale={st === 'Stale'}>
                    {#if st === 'No data'}<span class="num">no frame yet</span>{:else if st === 'Stale'}<span class="num">link lost · as of 22:41</span>{:else}<AgeMeter age={st === 'Normal' ? 31 : 212} cadence={52} width={44} />{/if}
                  </span>
                {:else if r.id === 'hfd'}
                  <span class="chip" class:attention={st === 'Attention'} class:stale={st === 'Stale'}>
                    <span class="k">HFD</span><b class="num">{st === 'No data' ? '—' : st === 'Normal' ? '2.31' : '6.78'}</b>
                    {#if st !== 'No data'}<Sparkline width={56} height={14} version={st} spec={(ink) => ({ ...hfdSpec(st === 'Attention')(ink), n: st === 'Normal' ? Math.min(n, 200) : n, x0: st === 'Normal' ? c.t[Math.max(0, Math.min(n, 200) - 70)] : undefined, x1: st === 'Normal' ? c.t[Math.min(n, 200) - 1] : undefined })} label="HFD sparkline" />{/if}
                    {#if st === 'Attention'}<span class="word">Attention</span>{/if}
                    {#if st === 'Stale'}<span class="num">as of 22:41</span>{/if}
                  </span>
                {:else if r.id === 'mag'}
                  <span class="chip" class:attention={st === 'Attention'} class:stale={st === 'Stale'}>
                    <span class="k">V</span><b class="num">{st === 'No data' ? '—' : fixed(c.target[last], 3)}</b>
                    {#if st !== 'No data'}<Sparkline width={56} height={14} version={st} spec={magSpec} label="Magnitude sparkline" />{/if}
                    {#if st === 'Attention'}<span class="word">Saturated</span>{/if}
                    {#if st === 'Stale'}<span class="num">as of 22:41</span>{/if}
                  </span>
                {:else}
                  <span class="chip" class:attention={st === 'Attention'} class:stale={st === 'Stale'}>
                    <span class="k">Alt</span><b class="num">{st === 'No data' ? '—' : st === 'Attention' ? '31°' : `${fixed(altNow, 0)}°`}</b>
                    {#if st !== 'No data'}<Sparkline width={56} height={14} version={st} spec={altSpec} label="Altitude sparkline" />{/if}
                    {#if st === 'Attention'}<span class="word">Limit in 9m</span>{/if}
                    {#if st === 'Stale'}<span class="num">no site</span>{/if}
                  </span>
                {/if}
              </span>
            {/each}
          </div>
        {/each}
      </div>

      <p class="lab-eyebrow">Glance view · read from 2 m (88 px primary, 66 px secondary)</p>
      <div class="glance">
        <div class="tile">
          <p class="gl-label">TARGET <span>{TARGET.label}</span></p>
          <p class="gl-big num">{n ? fixed(c.target[last], 3) : '—'}</p>
          <p class="gl-sub num">± {n ? fixed(c.targetErr[last], 3) : '—'} · V</p>
          <Sparkline width={300} height={72} version={`${n}`} spec={(ink) => ({ ...magSpec(ink), dots: true })} label="Target, last hour" />
        </div>
        <div class="tile" class:attn={episode !== null}>
          <p class="gl-label">HFD <span>{episode ? 'above 1.5× baseline' : 'steady'}</span></p>
          <p class="gl-mid num">{n ? fixed(c.hfd[last], 1) : '—'}<small>px</small></p>
          <p class="gl-sub num">{episode ? `since ${clockUtc(c.t[episode.fired], false)}` : `baseline ${fixed(base ?? NaN, 2)} px`}</p>
          <Sparkline width={300} height={72} version={`${n}`} spec={(ink) => ({ ...hfdSpec(true)(ink), width: 2 })} label="HFD, last hour" />
        </div>
        <div class="tile">
          <p class="gl-label">LAST FRAME</p>
          <p class="gl-mid num">{age !== null ? duration(age) : '—'}</p>
          <p class="gl-sub num">every {cadence ? duration(cadence) : '—'}</p>
          <AgeMeter {age} {cadence} width={300} showText={false} />
        </div>
      </div>
    </section>
  </div>
</div>

<style>
  .mini {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    height: 100%;
    padding: var(--space-4) var(--space-5);
    overflow: auto;
    background: var(--bg);
  }
  .sb-wrap {
    display: grid;
    gap: var(--space-2);
  }
  .statusbar {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: var(--statusbar-h);
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    background: var(--bg);
    color: var(--text-muted);
    font-size: var(--text-s);
    white-space: nowrap;
  }
  .seg {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--fg-muted);
  }
  .seg b {
    color: var(--fg);
    font-weight: var(--weight-regular);
  }
  .d {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--status-ok);
  }
  .sep {
    width: 1px;
    height: 16px;
    background: var(--border-soft);
  }
  .grow {
    flex: 1;
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
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .chip b {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .chip .k {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
  }
  .chip.attention {
    border-color: var(--warning);
  }
  .chip .word {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .chip.stale {
    border-style: dashed;
  }
  .chip.stale b {
    color: var(--text-muted);
  }
  .chip.run .rec {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--danger);
  }
  .cols {
    display: grid;
    grid-template-columns: 420px minmax(0, 1fr);
    gap: var(--space-6);
    min-height: 0;
  }
  .rail {
    display: grid;
    align-content: start;
    gap: var(--space-3);
  }
  .card {
    display: grid;
    gap: var(--space-2);
    padding: 12px 14px 12px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--bg);
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
  .line b {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .line .num {
    font-size: var(--text-xs);
  }
  .phot {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--space-4);
  }
  .big {
    margin: 2px 0 0;
    font-size: var(--text-xl);
    font-weight: var(--weight-medium);
  }
  .big small {
    margin-left: 6px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-regular);
  }
  .right {
    display: grid;
    align-content: start;
    gap: var(--space-3);
    min-width: 0;
  }
  .states {
    display: grid;
    gap: 6px;
    padding: var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
  }
  .hrow,
  .srow {
    display: grid;
    grid-template-columns: 90px repeat(4, minmax(0, 1fr));
    align-items: center;
    gap: var(--space-3);
  }
  .rh {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .srow > [role='cell'] {
    min-width: 0;
  }
  .srow .chip {
    max-width: 100%;
    overflow: hidden;
  }
  .glance {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-3);
  }
  .tile {
    container-type: inline-size;
    display: grid;
    align-content: start;
    gap: 6px;
    padding: var(--space-3) var(--space-4) var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--bg-2);
    overflow: hidden;
  }
  .tile.attn {
    border: 2px solid var(--warning);
  }
  .tile p {
    margin: 0;
  }
  .gl-label {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 15px;
    letter-spacing: var(--tracking-caps);
  }
  .gl-label span {
    margin-left: 8px;
    color: var(--fg);
    letter-spacing: 0;
    font-family: var(--font-ui);
  }
  .gl-big {
    /* 88 px when the tile allows it (full-window glance view), never overflowing. */
    font-size: min(var(--lab-glance-l), 29cqi);
    font-weight: var(--weight-medium);
    line-height: 1;
    letter-spacing: -0.02em;
  }
  .gl-mid {
    font-size: min(var(--lab-glance-m), 22cqi);
    font-weight: var(--weight-medium);
    line-height: 1.1;
  }
  .gl-mid small {
    margin-left: 8px;
    color: var(--text-muted);
    font-size: 24px;
  }
  .gl-sub {
    color: var(--text-muted);
    font-size: 18px;
  }
</style>
