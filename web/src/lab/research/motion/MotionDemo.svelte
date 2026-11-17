<!--
  Demo 3: motion that orients without lying (BRAND 2 and 9: data never
  animates; motion is for state changes and orientation).

  1. Star card (svelte/motion Spring): follows the pointer exactly while
     dragged (set instant), then settles in the nearest corner on release.
  2. Levels (svelte/motion Tween): the handle and the number jump to the new
     value; only a ghost of the old value fades. A "spring the handle"
     switch shows the rejected alternative (the handle lags behind its number).
  3. Ensemble ranking (svelte/animate flip): rows travel to their new rank so
     the eye can follow a star; the numbers in them change instantly.
  4. Controls: hold-to-confirm (time shown truthfully, linear), and a
     segmented control whose selection fill is placed by CSS anchor
     positioning (no JavaScript measuring).

  Reduced motion (OS or the lab switch): every duration is 0, the ghost is
  not drawn, the spring is instant; nothing else changes.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { flip } from 'svelte/animate';
  import { Spring, Tween } from 'svelte/motion';
  import { cubicOut } from 'svelte/easing';
  import { fade } from 'svelte/transition';
  import Checkbox from '../../../lib/components/Checkbox.svelte';
  import Icon from '../../../lib/components/Icon.svelte';
  import { reducedMotion } from '../env.svelte';
  import { comparisonStars, prng, type CompStar } from '../synth';

  // -- 1. Star card -------------------------------------------------------------
  const CARD = { w: 276, h: 96 };
  const MARGIN = 12;
  let field = $state({ w: 640, h: 360 });
  let dragging = $state(false);
  let corner = $state(2); // 0 tl, 1 tr, 2 bl, 3 br
  const card = new Spring({ x: MARGIN, y: 240 }, { stiffness: 0.16, damping: 0.72 });
  let grab = { dx: 0, dy: 0 };

  function cornerPos(c: number): { x: number; y: number } {
    const x = c % 2 === 0 ? MARGIN : field.w - CARD.w - MARGIN;
    const y = c < 2 ? MARGIN : field.h - CARD.h - MARGIN;
    return { x, y };
  }
  function nearest(p: { x: number; y: number }): number {
    let best = 0;
    let d = Infinity;
    for (let c = 0; c < 4; c++) {
      const q = cornerPos(c);
      const dd = Math.hypot(q.x - p.x, q.y - p.y);
      if (dd < d) {
        d = dd;
        best = c;
      }
    }
    return best;
  }
  const preview = $derived(dragging ? nearest(card.target) : corner);

  $effect(() => {
    // Field resized: stay in the corner, without animation (corner and
    // dragging are read untracked, or a release would cancel the settle).
    void field.w;
    void field.h;
    untrack(() => {
      if (!dragging) card.set(cornerPos(corner), { instant: true });
    });
  });

  function down(e: PointerEvent): void {
    if (e.button !== 0) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragging = true;
    grab = { dx: e.clientX - card.current.x, dy: e.clientY - card.current.y };
  }
  function move(e: PointerEvent): void {
    if (!dragging) return;
    // While held, the card is exactly under the pointer: no spring lag.
    card.set({ x: e.clientX - grab.dx, y: e.clientY - grab.dy }, { instant: true });
  }
  function up(): void {
    if (!dragging) return;
    dragging = false;
    corner = nearest(card.current);
    card.set(cornerPos(corner), { instant: reducedMotion() });
  }
  function cardKey(e: KeyboardEvent): void {
    const map: Record<string, number> = {
      ArrowLeft: corner === 1 ? 0 : corner === 3 ? 2 : corner,
      ArrowRight: corner === 0 ? 1 : corner === 2 ? 3 : corner,
      ArrowUp: corner === 2 ? 0 : corner === 3 ? 1 : corner,
      ArrowDown: corner === 0 ? 2 : corner === 1 ? 3 : corner,
    };
    if (!(e.key in map)) return;
    e.preventDefault();
    corner = map[e.key];
    card.set(cornerPos(corner), { instant: reducedMotion() });
  }
  const CORNER_NAMES = ['top left', 'top right', 'bottom left', 'bottom right'];

  // Static star field for the mock viewer.
  const stars = (() => {
    const r = prng(3);
    return Array.from({ length: 140 }, () => ({ x: r() * 100, y: r() * 100, s: 0.6 + 2.2 * Math.pow(r(), 6) }));
  })();

  // -- 2. Levels ----------------------------------------------------------------
  const RANGE = { lo: 1600, hi: 2200 };
  let black = $state(1721);
  let white = $state(2077);
  let ghost = $state<{ black: number; white: number } | null>(null);
  const ghostAlpha = new Tween(0, { duration: 900, easing: cubicOut });
  let springHandles = $state(false);
  const handleSpring = new Spring({ black: 1721, white: 2077 }, { stiffness: 0.06, damping: 0.6 });
  let variant = 0;

  $effect(() => {
    handleSpring.set({ black, white }, { instant: !springHandles || reducedMotion() });
  });

  function autoStretch(): void {
    const presets = [
      { black: 1688, white: 2140 },
      { black: 1742, white: 1990 },
    ];
    const next = presets[variant++ % presets.length];
    const before = { black, white };
    black = next.black;
    white = next.white;
    if (reducedMotion()) {
      ghost = null;
      return;
    }
    ghost = before;
    ghostAlpha.set(1, { duration: 0 });
    ghostAlpha.set(0);
  }
  const pct = (v: number) => ((v - RANGE.lo) / (RANGE.hi - RANGE.lo)) * 100;
  const shownBlack = $derived(springHandles ? handleSpring.current.black : black);
  const shownWhite = $derived(springHandles ? handleSpring.current.white : white);
  const histPath = (() => {
    // A sky peak and a star tail, log-ish, on a 0..100 x 0..40 box.
    let d = 'M0 40';
    for (let i = 0; i <= 100; i++) {
      const v = RANGE.lo + (i / 100) * (RANGE.hi - RANGE.lo);
      const peak = Math.exp(-Math.pow((v - 1797) / 38, 2) / 2);
      const tail = 0.18 * Math.exp(-(v - 1797) / 260) * (v > 1797 ? 1 : 0);
      const y = 40 - 36 * Math.max(peak, tail, 0.02);
      d += ` L${i} ${y.toFixed(2)}`;
    }
    return `${d} L100 40 Z`;
  })();

  // -- 3. Ensemble ranking ------------------------------------------------------
  let comps = $state<CompStar[]>(comparisonStars().sort((a, b) => a.rms - b.rms));
  let round = 0;
  function newFrame(): void {
    const r = prng(100 + ++round);
    comps = comps
      .map((c) => ({ ...c, rms: Math.max(0.004, c.rms + 0.006 * (r() - 0.5) * 2) }))
      .sort((a, b) => a.rms - b.rms);
  }
  function remove(id: string): void {
    comps = comps.filter((c) => c.id !== id);
  }
  const maxRms = $derived(Math.max(0.02, ...comps.map((c) => c.rms)));
  const dur = (ms: number) => (reducedMotion() ? 0 : ms);

  // -- 4. Hold to confirm + anchored segments -----------------------------------
  const HOLD_MS = 900;
  let holding = $state(false);
  let parked = $state(false);
  let holdTimer: ReturnType<typeof setTimeout> | null = null;
  let holdStart = 0;
  let holdLeft = $state(HOLD_MS);
  let holdRaf = 0;
  function holdBegin(): void {
    if (holding || parked) return;
    holding = true;
    holdStart = performance.now();
    const tick = () => {
      holdLeft = Math.max(0, HOLD_MS - (performance.now() - holdStart));
      if (holding) holdRaf = requestAnimationFrame(tick);
    };
    tick();
    holdTimer = setTimeout(() => {
      holding = false;
      parked = true;
      cancelAnimationFrame(holdRaf);
    }, HOLD_MS);
  }
  function holdEnd(): void {
    if (!holding) return;
    holding = false;
    if (holdTimer) clearTimeout(holdTimer);
    cancelAnimationFrame(holdRaf);
    holdLeft = HOLD_MS;
  }
  function holdKey(e: KeyboardEvent, down: boolean): void {
    if (e.key !== ' ' && e.key !== 'Enter') return;
    e.preventDefault();
    if (down && !e.repeat) holdBegin();
    if (!down) holdEnd();
  }

  type Transfer = 'linear' | 'log' | 'asinh';
  const TRANSFERS: Transfer[] = ['linear', 'log', 'asinh'];
  let transfer = $state<Transfer>('asinh');
  const anchorSupported = typeof CSS !== 'undefined' && CSS.supports('anchor-name: --a');
</script>

<div class="motion">
  <!-- 1 ------------------------------------------------------------------- -->
  <section class="panel p-card">
    <header>
      <p class="lab-eyebrow">1 · Spring · star card</p>
      <p class="rule">Follows the pointer exactly while held; on release it settles in the nearest corner, never over the image centre.</p>
    </header>
    <div class="field" bind:clientWidth={field.w} bind:clientHeight={field.h}>
      <svg class="sky" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {#each stars as s, i (i)}
          <circle cx={s.x} cy={s.y} r={s.s * 0.18} />
        {/each}
      </svg>
      <svg class="target" style:left="58%" style:top="44%" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="1.8" class="dot" />
      </svg>
      {#if dragging}
        {@const q = cornerPos(preview)}
        <div class="dropzone" style:left="{q.x}px" style:top="{q.y}px" style:width="{CARD.w}px" style:height="{CARD.h}px"></div>
      {/if}
      <div
        class="starcard"
        class:dragging
        style:width="{CARD.w}px"
        style:height="{CARD.h}px"
        style:transform="translate({card.current.x}px, {card.current.y}px)"
      >
        <div
          class="grip"
          role="button"
          tabindex="0"
          aria-label="Move the star card (arrow keys: corner). Now {CORNER_NAMES[corner]}"
          onpointerdown={down}
          onpointermove={move}
          onpointerup={up}
          onpointercancel={up}
          onkeydown={cardKey}
        >
          <svg viewBox="0 0 20 20" class="role" aria-hidden="true"><path d="M10 5a5 5 0 1 0 0.001 0Z" /></svg>
          <b>SW And</b><span class="num muted">target</span>
          <span class="grow"></span>
          <Icon name="arrange" size={16} />
        </div>
        <dl class="num">
          <div><dt>V</dt><dd>9.553 ± 0.005</dd></div>
          <div><dt>HFD</dt><dd>2.08 px</dd></div>
          <div><dt>SNR</dt><dd>212</dd></div>
          <div><dt>Peak</dt><dd>31 207 ADU</dd></div>
        </dl>
      </div>
    </div>
  </section>

  <!-- 2 ------------------------------------------------------------------- -->
  <section class="panel p-levels">
    <header>
      <p class="lab-eyebrow">2 · Tween · levels</p>
      <p class="rule">The handle and the number jump to the new value at once; only a ghost of the old value fades (orientation).</p>
    </header>
    <div class="levels">
      <svg class="hist" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true">
        <path d={histPath} />
      </svg>
      {#if ghost && ghostAlpha.current > 0.01}
        <span class="handle ghost" style:left="{pct(ghost.black)}%" style:opacity={ghostAlpha.current}></span>
        <span class="handle ghost" style:left="{pct(ghost.white)}%" style:opacity={ghostAlpha.current}></span>
      {/if}
      <span class="handle" style:left="{pct(shownBlack)}%"><i>B</i></span>
      <span class="handle" style:left="{pct(shownWhite)}%"><i>W</i></span>
    </div>
    <div class="row">
      <button class="lab-btn" data-shot="auto-stretch" onclick={autoStretch}>
        <Icon name="stretch-auto" size={16} /> Auto stretch
      </button>
      <span class="lab-chip">Black <b>{black}</b> ADU</span>
      <span class="lab-chip">White <b>{white}</b> ADU</span>
    </div>
    <!-- The app's token-drawn checkbox: a native one draws a grey box in
         Night Red even with accent-color (measured: rgb(115, 113, 113)). -->
    <Checkbox size="s" label="Compare: spring the handles" detail="Rejected: the handle lags behind its number" bind:checked={springHandles} />
  </section>

  <!-- 3 ------------------------------------------------------------------- -->
  <section class="panel p-ranking">
    <header>
      <p class="lab-eyebrow">3 · animate:flip · ensemble ranking</p>
      <p class="rule">Rows travel to their new rank so a star can be followed; the values inside change instantly.</p>
    </header>
    <div class="row">
      <button class="lab-btn" onclick={newFrame}><Icon name="refresh" size={16} /> New frame</button>
      <span class="muted small">sorted by residual RMS, best first</span>
    </div>
    <ol class="ranking">
      {#each comps as c, i (c.id)}
        <li animate:flip={{ duration: dur(260) }} out:fade={{ duration: dur(120) }}>
          <span class="rank num">{i + 1}</span>
          <svg viewBox="0 0 20 20" class="role cmp" aria-hidden="true"><path d="M5.5 5.5h9v9h-9Z" /></svg>
          <span class="lbl">C {c.label}</span>
          <span class="id num">{c.id}</span>
          <span class="bar"><span style:width="{(c.rms / maxRms) * 100}%"></span></span>
          <span class="rms num">{c.rms.toFixed(4)}</span>
          <button class="lab-btn ghost x" aria-label="Remove C {c.label} from the ensemble" onclick={() => remove(c.id)}>
            <Icon name="remove" size={16} />
          </button>
        </li>
      {/each}
    </ol>
  </section>

  <!-- 4 ------------------------------------------------------------------- -->
  <section class="panel p-controls">
    <header>
      <p class="lab-eyebrow">4 · Controls</p>
      <p class="rule">Hold-to-confirm shows elapsed time linearly (it is information); the segment fill is placed by CSS anchor positioning.</p>
    </header>
    <div class="row">
      <button
        class="lab-btn hold"
        class:holding
        style:--hold-ms="{HOLD_MS}ms"
        aria-label={parked ? 'Parked' : 'Park: hold to confirm'}
        aria-disabled={parked}
        onpointerdown={holdBegin}
        onpointerup={holdEnd}
        onpointerleave={holdEnd}
        onpointercancel={holdEnd}
        onkeydown={(e) => holdKey(e, true)}
        onkeyup={(e) => holdKey(e, false)}
      >
        <span class="fill" aria-hidden="true"></span>
        <Icon name="park" size={16} />
        <span>{parked ? 'Parked' : holding ? `Hold ${(holdLeft / 1000).toFixed(1)} s` : 'Park · hold'}</span>
      </button>
      {#if parked}
        <button class="lab-btn" onclick={() => (parked = false)}><Icon name="unpark" size={16} /> Unpark</button>
      {/if}
    </div>
    <div class="row">
      <div class="seg-anchored" role="radiogroup" aria-label="Transfer function" data-active={transfer}>
        {#each TRANSFERS as t (t)}
          <button role="radio" aria-checked={transfer === t} class="seg-{t}" onclick={() => (transfer = t)}>{t === 'asinh' ? 'Asinh' : t === 'log' ? 'Log' : 'Linear'}</button>
        {/each}
        <span class="indicator" aria-hidden="true"></span>
      </div>
      <span class="lab-chip"><span class="lab-dot {anchorSupported ? 'ok' : 'busy'}"></span>anchor-name: <b>{anchorSupported ? 'supported' : 'fallback'}</b></span>
    </div>
  </section>
</div>

<style>
  .motion {
    display: grid;
    grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr) auto;
    grid-template-areas:
      'card levels'
      'card ranking'
      'controls ranking';
    gap: var(--space-3);
    height: 100%;
    padding: var(--space-3);
    border-top: var(--border-w) solid var(--border);
  }
  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-height: 0;
    padding: var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    overflow: hidden;
  }
  .p-card {
    grid-area: card;
  }
  .p-levels {
    grid-area: levels;
  }
  .p-ranking {
    grid-area: ranking;
  }
  .p-controls {
    grid-area: controls;
  }
  .panel header {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .rule {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .muted {
    color: var(--text-muted);
  }
  .small {
    font-size: var(--text-s);
  }
  .grow {
    flex: 1;
  }
  .row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  /* 1 ------------------------------------------------------------------- */
  .field {
    position: relative;
    flex: 1;
    min-height: 0;
    background: var(--viewer-bg);
    border: var(--border-w) solid var(--border-soft);
    overflow: hidden;
    touch-action: none;
  }
  .sky {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    fill: var(--fg-muted);
  }
  .target {
    position: absolute;
    width: 26px;
    height: 26px;
    margin: -13px 0 0 -13px;
    fill: none;
    stroke: var(--role-target);
    stroke-width: 1.5;
  }
  .target .dot {
    fill: var(--role-target);
    stroke: none;
  }
  .dropzone {
    position: absolute;
    border: 1px dashed var(--border);
    border-radius: var(--radius-m);
  }
  .starcard {
    position: absolute;
    left: 0;
    top: 0;
    display: flex;
    flex-direction: column;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--shadow-2);
    will-change: transform;
  }
  .starcard.dragging {
    border-color: var(--accent);
  }
  .grip {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: 30px;
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg-muted);
    font-size: var(--text-s);
    cursor: grab;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
  }
  .grip b {
    color: var(--fg);
    font-weight: var(--weight-semibold);
  }
  .starcard.dragging .grip {
    cursor: grabbing;
  }
  .role {
    width: 13px;
    height: 13px;
    fill: var(--role-target);
    flex: none;
  }
  .role.cmp {
    fill: var(--role-comparison);
  }
  .starcard dl {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-1) var(--space-4);
    margin: 0;
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-s);
  }
  .starcard dl div {
    display: flex;
    gap: var(--space-2);
  }
  .starcard dt {
    color: var(--text-muted);
    min-width: 30px;
  }
  .starcard dd {
    margin: 0;
    color: var(--fg);
    white-space: nowrap;
  }

  /* 2 ------------------------------------------------------------------- */
  .levels {
    position: relative;
    height: 84px;
    margin: 14px 8px 0;
    border-bottom: 1px solid var(--chart-axis);
    background: var(--chart-surface);
  }
  .hist {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    fill: color-mix(in srgb, var(--fg-muted) 22%, transparent);
    stroke: var(--fg-muted);
    stroke-width: 0.4;
    vector-effect: non-scaling-stroke;
  }
  .handle {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 0;
    border-left: 1.5px solid var(--accent);
  }
  .handle i {
    position: absolute;
    top: -15px;
    left: -4px;
    color: var(--chart-text);
    font: 600 var(--text-2xs) var(--font-mono);
    font-style: normal;
  }
  .handle::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: -6px;
    border: 5px solid transparent;
    border-bottom: 8px solid var(--accent);
    border-top: 0;
  }
  .handle.ghost {
    border-left: 1.5px dashed var(--fg-muted);
  }
  .handle.ghost::after {
    border-bottom-color: var(--fg-muted);
  }

  /* 3 ------------------------------------------------------------------- */
  .ranking {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
    min-height: 0;
    overflow: hidden;
  }
  .ranking li {
    display: grid;
    grid-template-columns: 18px 14px 52px 92px minmax(40px, 1fr) 56px 30px;
    align-items: center;
    gap: var(--space-2);
    height: 26px;
    border-bottom: 1px solid var(--border-soft);
    background: var(--bg);
    font-size: var(--text-s);
  }
  .rank {
    color: var(--text-muted);
    text-align: right;
  }
  .lbl {
    color: var(--fg);
  }
  .id {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .bar {
    height: 6px;
    background: var(--bg-2);
  }
  .bar span {
    display: block;
    height: 100%;
    background: var(--role-comparison);
  }
  .rms {
    text-align: right;
    color: var(--fg);
  }
  .x {
    width: 26px;
    min-width: 26px;
    height: 24px;
  }

  /* 4 ------------------------------------------------------------------- */
  @property --hold {
    syntax: '<number>';
    inherits: false;
    initial-value: 0;
  }
  .hold {
    position: relative;
    overflow: hidden;
    border-color: var(--danger);
    min-width: 150px;
    justify-content: flex-start;
  }
  .hold :global(.icon) {
    color: var(--danger);
    position: relative;
  }
  .hold span:not(.fill) {
    position: relative;
  }
  .hold .fill {
    position: absolute;
    inset: 0;
    background: color-mix(in srgb, var(--danger) 30%, transparent);
    transform-origin: left;
    transform: scaleX(var(--hold));
    --hold: 0;
  }
  /* Linear on purpose: the fill is the time held, not decoration. It keeps
     running with reduced motion (information), the label counts down too. */
  .hold.holding .fill {
    --hold: 1;
    transition: --hold var(--hold-ms) linear;
  }
  .hold[aria-disabled='true'] {
    border-color: var(--border-soft);
    color: var(--text-muted);
  }

  .seg-anchored {
    position: relative;
    display: inline-flex;
    padding: 1px;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .seg-anchored button {
    position: relative;
    z-index: 1;
    height: 26px;
    padding: 0 var(--space-4);
    border: 0;
    background: none;
    color: var(--text-muted);
    font-size: var(--text-s);
    cursor: pointer;
  }
  .seg-anchored button[aria-checked='true'] {
    color: var(--fg);
  }
  .seg-linear {
    anchor-name: --seg-linear;
  }
  .seg-log {
    anchor-name: --seg-log;
  }
  .seg-asinh {
    anchor-name: --seg-asinh;
  }
  .indicator {
    position: absolute;
    position-anchor: --seg-asinh;
    left: anchor(left);
    right: anchor(right);
    top: anchor(top);
    bottom: anchor(bottom);
    border: var(--border-w) solid var(--border);
    border-radius: 1px;
    background: var(--toggled-bg);
    transition:
      left var(--duration-base) var(--ease-out),
      right var(--duration-base) var(--ease-out);
  }
  .seg-anchored[data-active='linear'] .indicator {
    position-anchor: --seg-linear;
  }
  .seg-anchored[data-active='log'] .indicator {
    position-anchor: --seg-log;
  }
  /* No anchor positioning: the selected button carries the fill itself. */
  @supports not (anchor-name: --a) {
    .indicator {
      display: none;
    }
    .seg-anchored button[aria-checked='true'] {
      background: var(--toggled-bg);
      box-shadow: inset 0 0 0 1px var(--border);
    }
  }
</style>
