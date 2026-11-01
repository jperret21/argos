<!--
  Demo 4: functional space on the Observe layout (spec 1.1, BRAND 11.1).

  - Right rail 420-580 px and bottom drawer 160 px - 50 %: separators as
    attachments (pointer capture + keyboard, snaps, double-click reset).
  - The image box is fitted live and its black bands are measured, so a
    layout change shows its cost in pixels immediately.
  - Cards are size containers: the Mount readouts reflow from 2x2 to one row,
    and the very same Conditions component becomes a strip in the drawer.
  - Camera form: one label column for every group via subgrid; an invalid
    field marks its row through :has(:invalid), with no script; the Object
    field grows with its text (field-sizing: content, where supported).
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import { airmass, altitudeAt, curvePoint, frameRows, NIGHT_START, prng } from '../synth';
  import ConditionsCard, { type Metric } from './ConditionsCard.svelte';
  import LabCard from './LabCard.svelte';
  import { splitter } from './splitter';

  const RAIL = { min: 420, max: 580, reset: 420, snaps: [420, 500, 580] };
  const DRAWER = { min: 160, reset: 216 };

  let rail = $state(420);
  let railOpen = $state(true);
  let drawer = $state(216);
  let drawerOpen = $state(true);
  let section = $state({ w: 0, h: 0 });
  let centre = $state({ w: 0, h: 0 });
  let dragging = $state(false);
  let drawerTab = $state<'conditions' | 'log'>('conditions');

  const drawerMax = () => Math.max(DRAWER.min, Math.round(section.h * 0.5));

  // Image box: a 1920 x 1080 frame fitted in the centre; bands measured.
  const FRAME = { w: 1920, h: 1080 };
  const fit = $derived.by(() => {
    const s = Math.min(centre.w / FRAME.w, centre.h / FRAME.h) || 0;
    const w = FRAME.w * s;
    const h = FRAME.h * s;
    return { w, h, bandX: (centre.w - w) / 2, bandY: (centre.h - h) / 2, scale: s };
  });

  // Synthetic conditions, last 120 frames.
  const metrics: Metric[] = (() => {
    const r = prng(9);
    const pts = Array.from({ length: 120 }, (_, i) => curvePoint(400 + i, r));
    const rows = frameRows(120, 21);
    return [
      { id: 'hfd', label: 'HFD', unit: 'px', values: pts.map((p) => p.hfd), digits: 2 },
      { id: 'stars', label: 'Stars', unit: '', values: rows.map((x) => x.stars), digits: 0 },
      { id: 'sky', label: 'Sky', unit: 'ADU', values: rows.map((x) => x.sky), digits: 0 },
      { id: 'airmass', label: 'Airmass', unit: '', values: pts.map((p) => airmass(altitudeAt(p.t))), digits: 3 },
    ];
  })();

  const stars = (() => {
    const r = prng(77);
    return Array.from({ length: 260 }, () => ({ x: r() * 100, y: r() * 100, s: 0.5 + 2.4 * Math.pow(r(), 7) }));
  })();

  let exposure = $state('0.0004');
  let gain = $state('80');
  let object = $state('SW And');
  let mountOpen = $state(true);
  let cameraOpen = $state(true);
  let condOpen = $state(true);

  const utc = new Date((NIGHT_START + 3 * 3600) * 1000).toISOString().slice(11, 19);
</script>

<div class="space" class:dragging>
  <div class="toolbar">
    <span class="lab-eyebrow">Rail</span>
    <div class="lab-seg" role="group" aria-label="Rail width presets">
      <button aria-pressed={railOpen && rail === 420} onclick={() => ((railOpen = true), (rail = 420))}>420</button>
      <button aria-pressed={railOpen && rail === 500} onclick={() => ((railOpen = true), (rail = 500))}>500</button>
      <button data-shot="rail-580" aria-pressed={railOpen && rail === 580} onclick={() => ((railOpen = true), (rail = 580))}>580</button>
      <button aria-pressed={!railOpen} onclick={() => (railOpen = !railOpen)}>Closed</button>
    </div>
    <span class="lab-eyebrow">Drawer</span>
    <div class="lab-seg" role="group" aria-label="Drawer height presets">
      <button aria-pressed={drawerOpen && drawer === 160} onclick={() => ((drawerOpen = true), (drawer = 160))}>160</button>
      <button aria-pressed={drawerOpen && drawer === 216} onclick={() => ((drawerOpen = true), (drawer = 216))}>216</button>
      <button data-shot="drawer-tall" aria-pressed={drawerOpen && drawer === drawerMax()} onclick={() => ((drawerOpen = true), (drawer = drawerMax()))}>50 %</button>
      <button aria-pressed={!drawerOpen} onclick={() => (drawerOpen = !drawerOpen)}>Closed</button>
    </div>
    <span class="grow"></span>
    <span class="lab-chip">rail <b>{railOpen ? rail : 0}</b> px</span>
    <span class="lab-chip">drawer <b>{drawerOpen ? drawer : 0}</b> px</span>
    <span class="lab-chip">image <b>{Math.round(fit.w)}×{Math.round(fit.h)}</b> · bands <b>{Math.round(Math.max(fit.bandX, fit.bandY))}</b> px</span>
  </div>

  <div
    class="section"
    bind:clientWidth={section.w}
    bind:clientHeight={section.h}
    style:--rail="{railOpen ? rail : 0}px"
    style:--drawer="{drawerOpen ? drawer : 0}px"
  >
    <div class="centre" bind:clientWidth={centre.w} bind:clientHeight={centre.h}>
      <div class="frame" style:width="{fit.w}px" style:height="{fit.h}px">
        <svg viewBox="0 0 100 56.25" preserveAspectRatio="none" aria-hidden="true">
          {#each stars as s, i (i)}
            <circle cx={s.x} cy={s.y * 0.5625} r={s.s * 0.1} />
          {/each}
        </svg>
        <div class="chips">
          <span class="lab-chip"><span class="lab-dot accent"></span><b>LIVE</b></span>
          <span class="lab-chip">#<b>1 284</b></span>
          <span class="lab-chip"><b>{utc}</b> UTC</span>
        </div>
      </div>
      {#if fit.bandY > 1}
        <span class="band top" style:height="{fit.bandY}px"><span class="num">{Math.round(fit.bandY)} px</span></span>
      {/if}
      {#if fit.bandX > 1}
        <span class="band left" style:width="{fit.bandX}px"><span class="num">{Math.round(fit.bandX)} px</span></span>
      {/if}
    </div>

    {#if drawerOpen}
      <!-- A focusable separator is the WAI-ARIA window-splitter pattern (an interactive role). -->
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div
        class="sep h"
        role="separator"
        aria-orientation="horizontal"
        aria-label="Drawer height"
        aria-valuenow={drawer}
        aria-valuemin={DRAWER.min}
        aria-valuemax={drawerMax()}
        tabindex="0"
        {@attach splitter({
          axis: 'y',
          invert: true,
          get: () => drawer,
          set: (v) => (drawer = v),
          min: DRAWER.min,
          max: drawerMax,
          reset: DRAWER.reset,
          snaps: [DRAWER.reset],
          ondrag: (a) => (dragging = a),
        })}
      ></div>
      <div class="drawer">
        <div class="tabs" role="tablist" aria-label="Drawer">
          <button role="tab" aria-selected={drawerTab === 'conditions'} onclick={() => (drawerTab = 'conditions')}>Conditions</button>
          <button role="tab" aria-selected={drawerTab === 'log'} onclick={() => (drawerTab = 'log')}>Log</button>
          <span class="grow"></span>
          <span class="hint">same component as the rail card · reflowed by @container</span>
        </div>
        <div class="pane">
          {#if drawerTab === 'conditions'}
            <ConditionsCard {metrics} />
          {:else}
            <pre class="log num">21:30:02 UTC  OK    Frame 1 284 saved (10.0 s, gain 80)
21:30:03 UTC  INFO  Field solved · 3.67″/px · rotation 12.4°
21:30:13 UTC  OK    Frame 1 285 saved (10.0 s, gain 80)</pre>
          {/if}
        </div>
      </div>
    {/if}

    {#if railOpen}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div
        class="sep v"
        role="separator"
        aria-orientation="vertical"
        aria-label="Right panel width"
        aria-valuenow={rail}
        aria-valuemin={RAIL.min}
        aria-valuemax={RAIL.max}
        tabindex="0"
        {@attach splitter({
          axis: 'x',
          invert: true,
          get: () => rail,
          set: (v) => (rail = v),
          min: RAIL.min,
          max: () => RAIL.max,
          reset: RAIL.reset,
          snaps: RAIL.snaps,
          ondrag: (a) => (dragging = a),
        })}
      ></div>
      <aside class="rail">
        <LabCard title="Camera" icon="camera" bind:open={cameraOpen}>
          {#snippet badge()}<span class="lab-chip"><span class="lab-dot ok"></span>Live</span>{/snippet}
          {#snippet summary()}10.0 s · gain 80{/snippet}
          <div class="form">
            <div class="group" role="group" aria-labelledby="lab-g-exp">
              <p class="lab-eyebrow legend" id="lab-g-exp">Exposure</p>
              <label for="lab-exp">Exposure</label>
              <input id="lab-exp" class="num" type="number" min="0.001" max="3600" step="any" bind:value={exposure} />
              <span class="unit">s</span>
              <span class="err">0.001 to 3600 s · not clamped, not sent</span>
              <label for="lab-gain">Gain</label>
              <input id="lab-gain" class="num" type="number" min="0" max="300" step="1" bind:value={gain} />
              <span class="unit"></span>
            </div>
            <div class="group" role="group" aria-labelledby="lab-g-sensor">
              <p class="lab-eyebrow legend" id="lab-g-sensor">Sensor</p>
              <span class="k">Size</span><span class="v num">1080 × 1920 · mono</span><span></span>
              <span class="k">Temperature</span><span class="v num">−2.4 °C</span><span></span>
            </div>
          </div>
        </LabCard>

        <LabCard title="Mount" icon="mount" bind:open={mountOpen}>
          {#snippet badge()}<span class="lab-chip"><span class="lab-dot ok"></span>Tracking</span>{/snippet}
          {#snippet summary()}23h 17m 44.6s · +29° 00′ 46″{/snippet}
          <div class="readouts num">
            <div><span>RA</span><b>23h 17m 44.6s</b></div>
            <div><span>Dec</span><b>+29° 00′ 46″</b></div>
            <div><span>Alt</span><b>71.42°</b></div>
            <div><span>Az</span><b>203.15°</b></div>
          </div>
          <div class="object">
            <label for="lab-object" class="lab-eyebrow">Object</label>
            <input id="lab-object" class="grow-input" bind:value={object} />
            <button class="lab-btn"><Icon name="goto" size={16} /> Slew</button>
          </div>
        </LabCard>

        <LabCard title="Conditions" icon="focus-metrics" bind:open={condOpen}>
          {#snippet summary()}HFD 2.31 px · 398 stars{/snippet}
          <ConditionsCard {metrics} />
        </LabCard>
      </aside>
    {/if}
  </div>
</div>

<style>
  .space {
    display: flex;
    flex-direction: column;
    height: 100%;
    border-top: var(--border-w) solid var(--border);
  }
  .space.dragging {
    cursor: grabbing;
    user-select: none;
    -webkit-user-select: none;
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: 40px;
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border);
    flex: none;
  }
  .toolbar .lab-eyebrow {
    margin-left: var(--space-2);
  }
  .grow {
    flex: 1;
  }

  .section {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto var(--rail);
    grid-template-rows: minmax(0, 1fr) auto var(--drawer);
    grid-template-areas:
      'centre vsep rail'
      'hsep   vsep rail'
      'drawer vsep rail';
  }

  .centre {
    grid-area: centre;
    position: relative;
    display: grid;
    place-items: center;
    min-height: 0;
    background: var(--viewer-bg);
    overflow: hidden;
  }
  .frame {
    position: relative;
    border: 1px solid var(--border-soft);
  }
  .frame svg {
    display: block;
    width: 100%;
    height: 100%;
    fill: var(--fg-muted);
  }
  .chips {
    position: absolute;
    top: var(--space-2);
    left: var(--space-2);
    display: flex;
    gap: var(--space-1);
  }
  .band {
    position: absolute;
    display: grid;
    place-items: center;
    color: var(--fg-disabled);
    font-size: var(--text-2xs);
    pointer-events: none;
    background: repeating-linear-gradient(135deg, transparent 0 6px, color-mix(in srgb, var(--border-soft) 40%, transparent) 6px 7px);
  }
  .band.top {
    top: 0;
    left: 0;
    right: 0;
  }
  .band.left {
    top: 0;
    bottom: 0;
    left: 0;
  }

  .sep {
    background: var(--border);
    position: relative;
    touch-action: none;
    z-index: 1;
  }
  .sep.v {
    grid-area: vsep;
    width: 1px;
    cursor: col-resize;
  }
  .sep.h {
    grid-area: hsep;
    height: 1px;
    cursor: row-resize;
  }
  /* A 9 px hit area around the 1 px line. */
  .sep::before {
    content: '';
    position: absolute;
    inset: -4px;
  }
  .sep:hover,
  .sep:focus-visible,
  .space.dragging .sep {
    background: var(--accent);
  }
  .sep:focus-visible {
    outline: none;
  }

  .drawer {
    grid-area: drawer;
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--bg);
  }
  .tabs {
    display: flex;
    align-items: stretch;
    gap: var(--space-1);
    height: 32px;
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .tabs button {
    position: relative;
    padding: 0 var(--space-3);
    border: 0;
    background: none;
    color: var(--text-muted);
    font-size: var(--text-s);
    cursor: pointer;
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
    background: var(--fg-muted);
  }
  .hint {
    align-self: center;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
  }
  .pane {
    flex: 1;
    min-height: 0;
    padding: var(--space-3) var(--space-4);
    overflow: auto;
    container-type: inline-size;
  }
  .log {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
    line-height: 1.6;
  }

  .rail {
    grid-area: rail;
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-height: 0;
    padding: var(--space-3);
    overflow: auto;
    background: var(--bg);
  }

  /* Camera form: subgrid aligns labels of every fieldset on one column. */
  .form {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr) 24px;
    gap: var(--space-2) var(--space-3);
    align-items: center;
  }
  /* A <fieldset> cannot be a subgrid (its anonymous content box is the
     grid), so groups are role="group" divs. */
  .group {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: subgrid;
    row-gap: var(--space-2);
    align-items: center;
    min-width: 0;
  }
  .legend {
    grid-column: 1 / -1;
    margin: var(--space-1) 0 0;
  }
  .group label,
  .k {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .v {
    color: var(--fg);
    font-size: var(--text-s);
  }
  input {
    height: var(--input-h);
    min-width: 0;
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    text-align: right;
  }
  .unit {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .err {
    display: none;
    grid-column: 2 / -1;
    margin-top: calc(-1 * var(--space-1));
    color: var(--fg);
    font-size: var(--text-xs);
  }
  /* :has(): the invalid field marks its own row, no script. */
  .group:has(#lab-exp:invalid) .err {
    display: block;
  }
  .group:has(#lab-exp:invalid) label[for='lab-exp'] {
    color: var(--fg);
  }
  #lab-exp:invalid {
    border-color: var(--danger);
  }
  input[type='number'] {
    appearance: textfield;
    -moz-appearance: textfield;
  }
  input::-webkit-inner-spin-button {
    -webkit-appearance: none;
  }

  /* Mount readouts: 2 x 2 in a narrow card, one row when there is room. */
  .readouts {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-3) var(--space-4);
    padding: var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .readouts div {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .readouts span {
    color: var(--text-muted);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .readouts b {
    color: var(--fg);
    font-size: var(--text-xl);
    font-weight: var(--weight-medium);
    white-space: nowrap;
  }
  @container (min-width: 520px) {
    .readouts {
      grid-template-columns: 1.25fr 1.15fr 0.8fr 0.8fr;
    }
    .readouts b {
      font-size: var(--text-l);
    }
  }
  .object {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-top: var(--space-3);
  }
  .grow-input {
    text-align: left;
    min-width: 8ch;
    max-width: 100%;
    /* Grows with its text (WebKit 26.2+, WebKitGTK 2.52+, Chromium 123+). */
    field-sizing: content;
  }
  @supports not (field-sizing: content) {
    .grow-input {
      width: 14ch;
    }
  }
</style>
