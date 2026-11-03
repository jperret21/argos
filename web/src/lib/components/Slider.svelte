<!--
  Slider with ticks, promoted from src/lab/controls/components/Slider.svelte
  (web/lab/PROPOSAL.md 3.3, W2). Token-drawn (a native range input is grey in
  Night Red), role="slider" on the thumb, one tab stop plus the readout field.

  Pointer: the thumb sits exactly under the pointer (no easing: a value never
  lags its picture). Shift snaps to the minor ticks; Alt (Option) switches to
  FINE: the value moves at 1/10 of the pointer from where fine began, so a
  precise value is reachable on a 300 px track. While dragging, a dashed mark
  stays at the start value and Esc returns to it.
  Keyboard: arrows one step (Shift ×10, Alt ×0.1), PageUp / PageDown one major
  tick, Home / End. Wheel only while focused. The readout is a field: type a
  value, Enter (parseNumber: point or comma decimal).
  Detents: recommended values (aperture = 3 × FWHM) are marked above the track
  and catch the thumb within 5 px; when caught, the value IS the detent and its
  name lights up.
  `oninput` follows the drag (display values); `oncommit` gets ONE value on
  release, Enter, or 400 ms after keys settle (device values, README 3.4).
-->
<script lang="ts">
  import { fixed, parseNumber } from '../format/number';
  import { tooltip } from './tooltip';
  import {
    applyDetent,
    clamp,
    decimalsOf,
    dragValue,
    precisionOf,
    ratioOf,
    stepValue,
    ticks as makeTicks,
    type Precision,
  } from './values';

  interface Detent {
    value: number;
    label: string;
  }

  interface Props {
    label: string;
    value: number;
    min: number;
    max: number;
    step: number;
    minor: number;
    major: number;
    unit?: string;
    detents?: readonly Detent[];
    /** Live while dragging (display values). */
    oninput?: (v: number) => void;
    /** Once on release / Enter / after keys settle. */
    oncommit?: (v: number) => void;
    format?: (v: number) => string;
    tickFormat?: (v: number) => string;
    disabledReason?: string | null;
    /** What the detent labels count ("× FWHM 2.9 px"). */
    detentLegend?: string;
    /** Readout width in px (wider for "≤ 14.5"). */
    readoutWidth?: number;
    pin?: { dragging?: boolean; fine?: boolean; start?: number; focus?: boolean } | null;
  }

  let {
    label,
    value = $bindable(),
    min,
    max,
    step,
    minor,
    major,
    unit,
    detents = [],
    oninput,
    oncommit,
    format,
    tickFormat,
    disabledReason = null,
    detentLegend,
    readoutWidth = 76,
    pin = null,
  }: Props = $props();

  const id = `sl-${Math.random().toString(36).slice(2, 9)}`;
  let track: HTMLDivElement | undefined = $state();
  let thumb: HTMLDivElement | undefined = $state();
  let dragging = $state(false);
  let precision = $state<Precision>('normal');
  let start: number | null = $state(null);
  let fineFrom: { x: number; value: number } | null = null;
  let editing = $state(false);
  let text = $state('');
  let commitTimer: ReturnType<typeof setTimeout> | null = null;

  const dec = $derived(decimalsOf(step));
  const fmt = (v: number) => (format ? format(v) : fixed(v, dec));
  const tickList = $derived(makeTicks(min, max, minor, major));
  const inert = $derived(!!disabledReason);
  const showDragging = $derived(pin?.dragging ?? dragging);
  const showFine = $derived(pin?.fine ?? (dragging && precision === 'fine'));
  const startMark = $derived(pin?.start ?? (dragging ? start : null));
  const caught = $derived(detents.find((d) => d.value === value) ?? null);

  function pct(v: number): string {
    return `${ratioOf(v, min, max) * 100}%`;
  }

  function set(v: number): void {
    if (v === value) return;
    value = v;
    oninput?.(v);
  }

  function commitSoon(): void {
    if (commitTimer) clearTimeout(commitTimer);
    commitTimer = setTimeout(() => oncommit?.(value), 400);
  }

  function detentRadius(): number {
    const w = track?.getBoundingClientRect().width ?? 300;
    return ((max - min) / w) * 5; // 5 px of catch
  }

  function fromPointer(e: PointerEvent): void {
    if (!track) return;
    const r = track.getBoundingClientRect();
    const p = precisionOf(e);
    if (p === 'fine' && precision !== 'fine') fineFrom = { x: e.clientX - r.left, value };
    precision = p;
    let v = dragValue({
      x: e.clientX - r.left,
      width: r.width,
      min,
      max,
      step,
      precision: p,
      snap: minor,
      fineFrom: fineFrom ?? undefined,
    });
    if (p === 'normal') v = applyDetent(v, detents.map((d) => d.value), detentRadius());
    set(v);
  }

  function down(e: PointerEvent): void {
    if (inert || pin || e.button !== 0) return;
    e.preventDefault();
    thumb?.focus();
    track?.setPointerCapture(e.pointerId);
    dragging = true;
    start = value;
    precision = 'normal';
    fineFrom = null;
    // Alt at press: fine from the current value, no jump to the pointer.
    if (e.altKey && track) {
      fineFrom = { x: e.clientX - track.getBoundingClientRect().left, value };
      precision = 'fine';
      return;
    }
    fromPointer(e);
  }

  function move(e: PointerEvent): void {
    if (!dragging) return;
    fromPointer(e);
  }

  function up(): void {
    if (!dragging) return;
    dragging = false;
    fineFrom = null;
    start = null;
    oncommit?.(value);
  }

  function onKey(e: KeyboardEvent): void {
    if (inert) return;
    if (e.key === 'Escape' && dragging && start !== null) {
      e.preventDefault();
      set(start);
      dragging = false;
      start = null;
      return;
    }
    let v: number | null = null;
    const p = precisionOf(e);
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') v = stepValue(value, 1, step, p, min, max);
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') v = stepValue(value, -1, step, p, min, max);
    else if (e.key === 'PageUp') v = clamp(value + major, min, max);
    else if (e.key === 'PageDown') v = clamp(value - major, min, max);
    else if (e.key === 'Home') v = min;
    else if (e.key === 'End') v = max;
    if (v === null) return;
    e.preventDefault();
    set(v);
    commitSoon();
  }

  function onWheel(e: WheelEvent): void {
    if (inert || document.activeElement !== thumb) return;
    e.preventDefault();
    if (Math.abs(e.deltaY) < 1) return;
    set(stepValue(value, e.deltaY < 0 ? 1 : -1, step, precisionOf(e), min, max));
    commitSoon();
  }

  $effect(() => {
    if (!track) return;
    const el = track;
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  });

  function readoutKey(e: KeyboardEvent): void {
    if (e.key === 'Enter') {
      const v = parseNumber(text);
      if (v !== null && v >= min && v <= max) {
        set(Number(v.toFixed(dec)));
        oncommit?.(value);
        editing = false;
        (e.currentTarget as HTMLInputElement).blur();
      }
    } else if (e.key === 'Escape') {
      editing = false;
      (e.currentTarget as HTMLInputElement).blur();
    }
  }

  const readoutBad = $derived.by(() => {
    if (!editing) return false;
    const v = parseNumber(text);
    return v === null || v < min || v > max;
  });
</script>

<div class="slider" class:inert class:dragging={showDragging}>
  <div class="head">
    <span class="label" id="{id}-label">{label}</span>
    {#if showFine}<span class="chip num">fine ×0.1</span>{/if}
    {#if detents.length && detentLegend && !showFine}<span class="legend num">detents {detentLegend}</span>{/if}
    <span class="spacer"></span>
    <span class="readout" class:bad={readoutBad} style:--ro-w="{readoutWidth}px">
      <input
        class="num"
        type="text"
        inputmode="decimal"
        autocomplete="off"
        spellcheck="false"
        aria-label="{label} value"
        value={editing ? text : fmt(value)}
        readonly={inert}
        onfocus={(e) => {
          editing = true;
          text = fmt(value);
          e.currentTarget.select();
        }}
        onblur={() => (editing = false)}
        oninput={(e) => (text = e.currentTarget.value)}
        onkeydown={readoutKey}
      />
      {#if unit}<span class="unit">{unit}</span>{/if}
    </span>
  </div>

  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="track"
    class:has-detents={detents.length > 0}
    bind:this={track}
    onpointerdown={down}
    onpointermove={move}
    onpointerup={up}
    onpointercancel={up}
    use:tooltip={{ text: label, reason: disabledReason, disabled: !inert, placement: 'top' }}
  >
    <div class="rail"></div>
    <div class="fill" style:width={pct(value)}></div>

    {#each detents as d (d.value)}
      <div class="detent" class:on={caught === d} style:left={pct(d.value)} aria-hidden="true">
        <span class="dlabel num">{d.label}</span>
      </div>
    {/each}

    {#if startMark !== null}
      <div class="start" style:left={pct(startMark)} aria-hidden="true"></div>
    {/if}

    <div
      class="thumb"
      class:focus={pin?.focus}
      bind:this={thumb}
      role="slider"
      tabindex={inert ? -1 : 0}
      aria-labelledby="{id}-label"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-valuetext="{fmt(value)}{unit ? ` ${unit}` : ''}{caught ? `, ${caught.label}` : ''}"
      aria-disabled={inert || undefined}
      style:left={pct(value)}
      onkeydown={onKey}
      onblur={() => {
        if (commitTimer) {
          clearTimeout(commitTimer);
          commitTimer = null;
          oncommit?.(value);
        }
      }}
    ></div>
  </div>

  <div class="scale" aria-hidden="true">
    {#each tickList as t (t.value)}
      <span class="tick" class:major={t.major} style:left={pct(t.value)}>
        {#if t.major}<span class="tl num">{tickFormat ? tickFormat(t.value) : fixed(t.value, 0)}</span>{/if}
      </span>
    {/each}
  </div>
  {#if showDragging && startMark !== null}
    <p class="aside"><kbd class="cap">Esc</kbd> returns to <span class="num">{fmt(startMark)}</span></p>
  {:else if disabledReason}
    <p class="aside reason">{disabledReason}</p>
  {/if}
</div>

<style>
  .slider {
    --thumb-w: 4px;
    --thumb-h: 18px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    user-select: none;
    -webkit-user-select: none;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: 24px;
  }
  .label {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .spacer {
    flex: 1;
  }
  .chip {
    padding: 0 4px;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-2xs);
    line-height: 14px;
  }
  .readout {
    position: relative;
    display: inline-flex;
    align-items: center;
  }
  .readout input {
    width: var(--ro-w, 76px);
    height: 22px;
    padding: 0 calc(var(--space-2) + 3.4ch) 0 var(--space-2);
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-m);
    text-align: right;
    caret-color: var(--accent);
    transition: border-color var(--duration-fast) var(--ease-standard);
  }
  .readout input:hover {
    border-color: var(--border);
  }
  .readout input:focus {
    border-color: var(--border);
    background: var(--bg-2);
  }
  .readout input:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .readout.bad input {
    border-color: var(--danger);
  }
  .readout .unit {
    position: absolute;
    right: var(--space-2);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    pointer-events: none;
  }

  .legend {
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }
  .track {
    position: relative;
    height: 26px;
    margin: 0 calc(var(--thumb-w) / 2);
    cursor: pointer;
    touch-action: none;
  }
  .rail,
  .fill {
    position: absolute;
    top: 50%;
    left: 0;
    height: var(--track-h);
    margin-top: calc(var(--track-h) / -2);
    border-radius: 1px;
  }
  .rail {
    right: 0;
    background: var(--bg-2);
    box-shadow: inset 0 0 0 1px var(--border-soft);
  }
  .fill {
    background: var(--fg-muted);
  }

  .thumb {
    position: absolute;
    top: 50%;
    width: var(--thumb-w);
    height: var(--thumb-h);
    margin: calc(var(--thumb-h) / -2) 0 0 calc(var(--thumb-w) / -2);
    border-radius: 1px;
    background: var(--fg);
    box-shadow: 0 0 0 2px var(--bg);
    cursor: grab;
    transition: background-color var(--duration-fast) var(--ease-standard);
  }
  .track:hover .thumb {
    box-shadow:
      0 0 0 2px var(--bg),
      0 0 0 3px var(--border);
  }
  /* Dragging: the thumb turns brass (the active, deliberate manipulation). */
  .dragging .thumb,
  .dragging .track:hover .thumb {
    background: var(--accent);
    cursor: grabbing;
  }
  .thumb:focus-visible,
  .thumb.focus {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 3px;
  }

  .track.has-detents {
    margin-top: 8px;
  }
  /* A detent is a short upright tick above the track (never a triangle: the
     triangle is the check star, BRAND 2.6); --fg once the thumb is caught. */
  .detent {
    position: absolute;
    top: 0;
    width: 2px;
    height: 6px;
    margin-left: -1px;
    border-radius: 1px;
    background: var(--fg-muted);
    pointer-events: none;
  }
  .detent.on {
    background: var(--fg);
  }
  .dlabel {
    position: absolute;
    bottom: 6px;
    left: 0;
    transform: translateX(-50%);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    white-space: nowrap;
  }
  .detent.on .dlabel {
    color: var(--fg);
  }

  .start {
    position: absolute;
    top: 50%;
    width: 6px;
    height: 12px;
    margin: -6px 0 0 -3px;
    border: var(--border-w) dashed var(--fg-muted);
    border-radius: 1px;
    pointer-events: none;
  }

  .scale {
    position: relative;
    height: 22px;
    margin: 0 calc(var(--thumb-w) / 2);
  }
  .tick {
    position: absolute;
    top: 0;
    width: 1px;
    height: var(--tick-minor);
    background: var(--border);
  }
  .tick.major {
    height: var(--tick-major);
    background: var(--fg-muted);
  }
  .tl {
    position: absolute;
    top: 10px;
    left: 0;
    transform: translateX(-50%);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    white-space: nowrap;
  }

  .aside {
    display: flex;
    align-items: center;
    gap: 4px;
    margin: 0;
    height: 16px;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .cap {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 14px;
    height: 14px;
    padding: 0 3px;
    border: var(--border-w) solid var(--border);
    border-bottom-width: 2px;
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    line-height: 1;
  }
  .reason::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: 2px;
    border-radius: var(--radius-round);
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }

  .inert .fill {
    background: var(--border);
  }
  .inert .thumb {
    background: var(--fg-disabled);
    cursor: not-allowed;
  }
  .inert .track {
    cursor: not-allowed;
  }
</style>
