<!--
  Watch: the run read from 2 m (functional-spaces P3, W5). A full-window view
  inside the one window (D27), opened by W, the toolbar or the palette; W or
  Esc returns. Fixed positions teach meaning from afar: state, frames, last
  frame age; target magnitude, check star, end; the curve; stars, HFD,
  altitude. Sizes: primary values 88 px, secondary 66 px, labels 30 px (2 m
  on a 13-inch 1440 x 900 laptop, Plex Mono digits 0.71 em).

  Truthful: values change when a frame arrives, instantly; the age ticks
  once a second (it is a clock); the newest point is a static ring. An
  attention item replaces the first row (outline + word, never a large red
  fill, the brightest thing in the room), but keeps the run's pulse at its
  right end (frames n/N and the last-frame age): the one signal that tells a
  frozen run from a healthy one must not disappear when an alert shows (lab
  synthesis). Dim multiplies the whole view's
  luminance with a CSS brightness filter: hue is kept, red stays red.
  Only W, Esc, ? and Mod+K act here; Pause is hold-to-confirm; no Stop, no
  mount action (they need the observer at the table).
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import LightCurve from '../charts/LightCurve.svelte';
  import Spark from '../charts/Spark.svelte';
  import { sim, ws } from '../model/app.svelte';
  import { NAMED_STARS } from '../model/field';
  import { fixed, int, PM, utc } from '../model/format';
  import { median, RUN } from '../model/night';
  import { RULES } from '../model/rules';
  import HoldButton from '../ui/HoldButton.svelte';
  import LabIcon from '../ui/LabIcon.svelte';

  const noCheck = new URLSearchParams(location.search).has('nocheck');
  const check = noCheck ? null : NAMED_STARS.find((s) => s.role === 'check');
  const l = $derived(sim.latest);
  const recs = $derived(sim.records);
  const top = $derived(sim.unacked[0] ?? null);
  const late = $derived(Number.isFinite(sim.cadence) && sim.lastAge > sim.cadence * 1.5);
  const state = $derived(
    sim.runState === 'running' ? 'RUNNING' : sim.runState === 'pausing' ? 'PAUSING' : sim.runState === 'paused' ? 'PAUSED' : sim.runState === 'complete' ? 'COMPLETE' : sim.runState === 'stopped' ? 'STOPPED' : 'IDLE',
  );
  const checkSd = $derived.by(() => {
    const r = recs.slice(-15);
    if (r.length < 3) return NaN;
    const m = median(r.map((x) => x.check));
    return Math.sqrt(r.reduce((s, x) => s + (x.check - m) ** 2, 0) / (r.length - 1));
  });
  const hfd0 = $derived(recs.length >= RULES.baselineFrames ? median(recs.slice(0, RULES.baselineFrames).map((r) => r.hfd)) : NaN);
  const hfdRule = $derived(sim.attention.find((a) => a.rule === 'HFD rise'));
  const flagged = $derived.by((): [number, number][] => {
    if (!hfdRule?.frame) return [];
    const first = sim.night[hfdRule.frame - 3];
    return first ? [[first.t - 20, sim.now]] : [];
  });
  const events = $derived(hfdRule ? [{ x: hfdRule.since, label: `HFD rule ${utc(hfdRule.since, false)}` }] : []);
  const end = $derived(Number.isFinite(sim.endsAt) ? Math.max(sim.endsAt, sim.now) : RUN.start + 3 * 3600);
  const DIMS = [100, 60, 30] as const;
</script>

<div class="watch" style:filter={ws.watchDim < 100 ? `brightness(${ws.watchDim / 100})` : undefined} role="dialog" aria-modal="true" aria-label="Watch: {RUN.object} run, {state.toLowerCase()}">
  {#if top}
    <section class="row1 alert level-{top.level}" role="alert">
      <span class="alert-head"><LabIcon name="lab-attention" size={44} /><span class="w-l strong">{top.level === 'critical' ? 'CRITICAL' : 'ATTENTION'}</span></span>
      <span class="alert-text">
        <span class="w-m num">{top.short}</span>
        <span class="w-s muted">{top.rule} · since {utc(top.since, false)} UTC{top.frame ? ` · frame ${top.frame}` : ''}</span>
      </span>
      <span class="pulse" class:late>
        <span class="w-m num">{sim.lastAge} s</span>
        <span class="w-xs muted">last frame · {sim.delivered} / {RUN.frames}</span>
      </span>
      <button type="button" class="ack" onclick={() => sim.ack(top.id)}>Acknowledge</button>
    </section>
  {:else}
    <section class="row1">
      <div class="tile">
        <span class="w-xl strong">{state}</span>
        <span class="w-s muted">{RUN.object} · step 1 of 1</span>
      </div>
      <div class="tile">
        <span class="w-l num">{sim.delivered} / {RUN.frames}</span>
        <span class="w-s muted">frames</span>
      </div>
      <div class="tile" class:late>
        <span class="w-l num">{sim.lastAge} s</span>
        <span class="w-s muted">last frame{late ? ` · as of ${utc(l?.t ?? sim.now, false)}` : ''} · every {fixed(sim.cadence, 0)} s</span>
      </div>
    </section>
  {/if}

  <section class="row2">
    <div class="tile">
      <span class="w-s muted">TARGET · {RUN.object}</span>
      <span class="w-xl num">{l ? fixed(l.target, 3) : '—'}</span>
      <span class="w-m num muted">{PM} {l ? fixed(l.targetErr, 3) : '—'} {RUN.band}</span>
    </div>
    <div class="tile">
      {#if check}
        <span class="w-s muted">CHECK STAR · σ of 15</span>
        <span class="w-l num">{fixed(checkSd, 3)}</span>
        <span class="w-s muted one">comps {l?.compsUsed ?? '—'} / {RUN.comparisons} · consistent</span>
      {:else}
        <span class="w-s muted">CHECK STAR</span>
        <span class="w-m">No check star</span>
        <span class="w-s muted">add one in Field · comps {l?.compsUsed ?? '—'} / {RUN.comparisons}</span>
      {/if}
    </div>
    <div class="tile">
      <span class="w-s muted">ENDS</span>
      <span class="w-xl num">{Number.isFinite(sim.endsAt) ? utc(sim.endsAt, false) : '—'}</span>
      <span class="w-m muted">UTC · in {Math.max(0, Math.round((sim.endsAt - sim.now) / 60))} min</span>
    </div>
  </section>

  <section class="row3">
    <LightCurve records={recs} start={RUN.start} {end} now={sim.running ? sim.now : null} {events} {flagged} variant="watch" header={false} targetName={RUN.object} checkName={check?.name?.slice(-3) ?? null} />
  </section>

  <section class="row4">
    <div class="tile cond">
      <span class="pair"><span class="w-s muted">STARS</span><span class="w-cond num">{l ? int(l.stars) : '—'}</span></span>
      <Spark values={recs.map((r) => r.stars)} height={56} bold label="Stars over the run" />
    </div>
    <div class="tile cond" class:flagged={!!hfdRule}>
      <span class="pair"><span class="w-s muted">HFD</span><span class="w-cond num">{l ? fixed(l.hfd, 1) : '—'}<span class="w-s muted"> px</span></span>{#if hfdRule}<span class="flag w-s">rule</span>{/if}</span>
      <Spark values={recs.map((r) => r.hfd)} threshold={Number.isFinite(hfd0) ? RULES.hfdFactor * hfd0 : null} height={56} bold label="HFD over the run" />
    </div>
    <div class="tile cond">
      <span class="pair"><span class="w-s muted">ALT</span><span class="w-cond num">{l ? fixed(l.alt, 0) : '—'}°</span></span>
      <span class="pair"><span class="w-s muted">limit 30°</span><span class="w-s">until 01:10</span></span>
    </div>
  </section>

  <footer class="row5">
    <span class="links"><span class="dot"></span>Seestar <span class="dot"></span>Net <span class="dot"></span>Server</span>
    <span class="dim" role="radiogroup" aria-label="Dim the view">
      <span class="w-xs muted">Dim</span>
      {#each DIMS as d (d)}
        <button type="button" role="radio" aria-checked={ws.watchDim === d} class:on={ws.watchDim === d} onclick={() => (ws.watchDim = d)}>{d} %</button>
      {/each}
    </span>
    {#if sim.running}
      <HoldButton icon="pause" label="Pause" size="l" tone="secondary" question="Pause the run?" consequence="It holds at the end of this frame; Resume continues." onconfirm={() => sim.pause()} />
    {:else if sim.runState === 'paused'}
      <span class="w-xs">Paused · resume at the table</span>
    {/if}
    <button type="button" class="back" onclick={() => (ws.overlay = 'none')}><Icon name="close" size={20} /> W or Esc: back</button>
  </footer>
</div>

<style>
  .watch {
    position: fixed;
    inset: 0;
    z-index: var(--z-modal);
    display: grid;
    grid-template-rows: 124px 214px minmax(0, 1fr) 128px 52px;
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
    background: var(--bg-2);
    color: var(--fg);
    visibility: visible;
  }
  section {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    border-bottom: var(--border-w) solid var(--border-soft);
    min-height: 0;
  }
  .tile {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 2px;
    min-width: 0;
    padding: 0 var(--space-6);
    border-right: var(--border-w) solid var(--border-soft);
    overflow: hidden;
  }
  .tile:last-child {
    border-right: none;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .w-xl {
    font-size: var(--lab-watch-xl);
    font-weight: var(--weight-medium);
    line-height: 1;
    letter-spacing: -0.01em;
  }
  .w-l {
    font-size: var(--lab-watch-l);
    font-weight: var(--weight-medium);
    line-height: 1.05;
  }
  .w-m {
    font-size: var(--lab-watch-m);
    line-height: 1.15;
  }
  .w-s {
    font-size: var(--lab-watch-s);
    line-height: 1.2;
  }
  .w-xs {
    font-size: 20px;
  }
  .w-cond {
    font-size: 48px;
    font-weight: var(--weight-medium);
    line-height: 1;
  }
  .strong {
    font-family: var(--font-ui);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.02em;
  }
  .row1 .w-xl.strong {
    font-size: 72px;
  }
  .muted {
    color: var(--text-muted);
  }
  .late .w-l {
    color: var(--text-muted);
  }
  .row1.alert {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    padding: 0 var(--space-6);
    box-shadow: inset 0 0 0 2px var(--warning);
  }
  .row1.alert.level-critical {
    box-shadow: inset 0 0 0 4px var(--danger);
  }
  .alert-head {
    display: inline-flex;
    align-items: center;
    gap: var(--space-4);
    color: var(--warning);
  }
  .level-critical .alert-head {
    color: var(--danger);
  }
  .alert-head .strong {
    color: var(--fg);
    font-size: 40px;
  }
  .pulse {
    flex: none;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    padding-left: var(--space-5);
    border-left: var(--border-w) solid var(--border-soft);
    line-height: 1.1;
  }
  .pulse.late .w-m {
    color: var(--text-muted);
  }
  .alert-text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .alert-text .w-m {
    font-size: clamp(26px, 2.5vw, 40px);
  }
  .one {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .alert-text > span {
    display: block;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .ack {
    height: 64px;
    padding: 0 var(--space-6);
    border: 2px solid var(--fg-muted);
    border-radius: var(--radius-m);
    background: var(--surface);
    color: var(--fg);
    font-size: 26px;
    font-weight: var(--weight-medium);
    cursor: pointer;
  }
  .row3 {
    display: block;
    padding: var(--space-2) 0 0;
    background: var(--chart-surface);
  }
  .row4 .cond {
    flex-direction: row;
    align-items: center;
    gap: var(--space-5);
  }
  .pair {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: none;
  }
  .cond :global(.wrap) {
    flex: 1;
  }
  .flag {
    align-self: flex-start;
    padding: 0 var(--space-2);
    border: 2px solid var(--warning);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: 20px;
  }
  .row5 {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    padding: 0 var(--space-6);
    font-size: 20px;
  }
  .links {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--fg);
  }
  .links .dot {
    width: 10px;
    height: 10px;
    margin-left: var(--space-3);
    border-radius: var(--radius-round);
    background: var(--status-ok);
  }
  .links .dot:first-child {
    margin-left: 0;
  }
  .dim {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .dim button {
    height: 36px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 18px;
    cursor: pointer;
  }
  .dim button.on {
    background: var(--toggled-bg);
    color: var(--fg);
    border-color: var(--fg-muted);
  }
  .back {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 40px;
    padding: 0 var(--space-4);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: 18px;
    cursor: pointer;
  }

  @media (max-height: 820px) {
    .watch {
      grid-template-rows: 112px 192px minmax(0, 1fr) 116px 48px;
    }
  }
  /* 1280 px: the alert row keeps the whole headline (level word, rule
     numbers, pulse and Acknowledge) without ellipsis. */
  @media (max-width: 1380px) {
    .row1.alert {
      gap: var(--space-5);
    }
    .alert-head .strong {
      font-size: 32px;
    }
    .alert-text .w-m {
      font-size: 28px;
    }
    .alert-text .w-s {
      font-size: 22px;
    }
    .pulse .w-m {
      font-size: 32px;
    }
    .ack {
      height: 56px;
      padding: 0 var(--space-5);
      font-size: 22px;
    }
  }
</style>
