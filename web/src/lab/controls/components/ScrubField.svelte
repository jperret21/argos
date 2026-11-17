<!--
  Numeric field with scrubbing (proposal over lib NumberField, same parser
  rules: text input, inputmode decimal, comma or point, U+2212).

  Ways to change the value, all with the same modifiers (values.ts):
  - type, Enter (or leave the field) sends;
  - drag the label, or drag across the field before clicking into it
    (a click without movement edits the text); Shift x10, Alt fine;
  - ArrowUp / ArrowDown (Shift x10, Alt x0.1), wheel while focused only
    (never on hover: a rail that scrolls must not change an exposure);
  - ladder fields (exposure) step through preferred values, Alt leaves the
    ladder for fine linear steps.
  While scrubbing or stepping, a dial tape under the field shows the
  neighbouring values; the number itself never animates.

  Commit model for device values (README 3.4): nothing is sent per
  keystroke or per pixel of drag. Released drag, Enter, blur or a 600 ms
  pause after arrow / wheel steps send ONE value. States, each double-coded:
    dirty     dashed outline + "Enter sends" (the field is not what the device has)
    sending   spinner in the unit slot, aria-busy
    applied   "Applied · <note>" for 2 s
    refused   danger outline + the server's words; Esc returns to the device value
    invalid   danger outline + the range; never clamped silently
    unavailable  muted, reason in words (aria-disabled, still focusable)
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import { exposure, fixed, grouped, parseNumber } from '../format';
  import { tip } from '../tip';
  import { clamp, decimalsOf, ladderStep, nearestRung, precisionOf, scrubValue, stepValue, type Precision } from '../values';

  type Phase = 'idle' | 'dirty' | 'sending' | 'applied' | 'refused';

  interface Props {
    label: string;
    value: number;
    unit?: string;
    min: number;
    max: number;
    step?: number;
    ladder?: readonly number[];
    integer?: boolean;
    /** "0.01–600 s · driver" */
    range?: string;
    /** Shown after a successful send ("from the next frame"). */
    appliedNote?: string;
    /** Send to the device; reject with the device's words. */
    oncommit?: (v: number) => Promise<void> | void;
    disabledReason?: string | null;
    format?: (v: number) => string;
    /** Specimen: freeze a state. */
    pin?: { phase?: Phase | 'invalid' | 'scrub'; text?: string; message?: string; precision?: Precision } | null;
    /** Pixels per step when scrubbing a linear value. */
    pxPerStep?: number;
    /**
     * An ACTION field (focuser Go to): nothing is sent on blur, on a released
     * drag or after arrow steps; only Enter or the action button send.
     */
    action?: { icon: string; label: string } | null;
    /** One row: key on the left (eyebrow), field, then the help (rails). */
    inline?: boolean;
  }

  let {
    label,
    value = $bindable(),
    unit,
    min,
    max,
    step = 1,
    ladder,
    integer = false,
    range,
    appliedNote,
    oncommit,
    disabledReason = null,
    format,
    pin = null,
    pxPerStep = 4,
    action = null,
    inline = false,
  }: Props = $props();

  const id = `sf-${Math.random().toString(36).slice(2, 9)}`;
  let input: HTMLInputElement | undefined = $state();
  let field: HTMLDivElement | undefined = $state();

  let phase = $state<Phase>('idle');
  let draft: number | null = $state(null);
  let text = $state('');
  let editing = $state(false);
  let invalid: string | null = $state(null);
  let refused: string | null = $state(null);
  let scrubbing = $state<'no' | 'pending' | 'active'>('no');
  let precision = $state<Precision>('normal');
  let stepping = $state(false);

  let startX = 0;
  let startVal = 0;
  let fromLabel = false;
  let settle: ReturnType<typeof setTimeout> | null = null;
  let appliedTimer: ReturnType<typeof setTimeout> | null = null;
  let steppingTimer: ReturnType<typeof setTimeout> | null = null;

  function fmt(v: number): string {
    if (format) return format(v);
    if (ladder) return exposure(v);
    if (integer) return Math.abs(v) >= 10_000 ? grouped(v) : String(Math.round(v));
    return fixed(v, decimalsOf(step));
  }

  const current = $derived(draft ?? value);
  const shownPhase = $derived(pin?.phase ?? (invalid ? 'invalid' : phase));
  const shownText = $derived(pin?.text ?? (editing || invalid || refused ? text : fmt(current)));
  const inert = $derived(!!disabledReason);
  const showTape = $derived(pin?.phase === 'scrub' || scrubbing === 'active' || stepping);
  const shownPrecision = $derived(pin?.precision ?? precision);

  // -- Commit ---------------------------------------------------------------------

  function clearSettle(): void {
    if (settle) clearTimeout(settle);
    settle = null;
  }

  async function commit(v: number): Promise<void> {
    clearSettle();
    if (v === value) {
      draft = null;
      phase = 'idle';
      return;
    }
    phase = 'sending';
    refused = null;
    try {
      await oncommit?.(v);
      value = v;
      draft = null;
      phase = 'applied';
      if (appliedTimer) clearTimeout(appliedTimer);
      appliedTimer = setTimeout(() => {
        if (phase === 'applied') phase = 'idle';
      }, 2000);
    } catch (err) {
      refused = err instanceof Error ? err.message : String(err);
      text = fmt(v);
      phase = 'refused';
    }
  }

  function offer(v: number, settleMs: number | null): void {
    draft = v;
    invalid = null;
    refused = null;
    phase = 'dirty';
    text = fmt(v);
    clearSettle();
    if (settleMs !== null && !action) settle = setTimeout(() => void commit(v), settleMs);
  }

  function revert(): void {
    clearSettle();
    draft = null;
    invalid = null;
    refused = null;
    phase = 'idle';
    text = fmt(value);
  }

  function markStepping(): void {
    stepping = true;
    if (steppingTimer) clearTimeout(steppingTimer);
    steppingTimer = setTimeout(() => (stepping = false), 900);
  }

  // -- Typing ---------------------------------------------------------------------

  function validate(t: string): number | null {
    const v = parseNumber(t);
    if (v === null) {
      invalid = 'Enter a number';
      return null;
    }
    if (integer && !Number.isInteger(v)) {
      invalid = 'Whole numbers only';
      return null;
    }
    if (v < min || v > max) {
      invalid = range ? `Range ${range}` : `Range ${fmt(min)}–${fmt(max)}`;
      return null;
    }
    invalid = null;
    return v;
  }

  function onInput(e: Event & { currentTarget: HTMLInputElement }): void {
    text = e.currentTarget.value;
    const v = validate(text);
    refused = null;
    if (v !== null) {
      draft = v;
      phase = v === value ? 'idle' : 'dirty';
    } else {
      phase = 'dirty';
    }
  }

  function stepBy(dir: 1 | -1, p: Precision): void {
    const base = draft ?? value;
    let v: number;
    if (ladder && p !== 'fine') v = clamp(ladderStep(ladder, base, dir, p === 'coarse' ? 3 : 1), min, max);
    else v = stepValue(base, dir, step, p, min, max);
    if (integer) v = Math.round(v);
    precision = p;
    markStepping();
    offer(v, 600);
  }

  function onKey(e: KeyboardEvent): void {
    if (inert) return;
    if (e.key === 'Enter') {
      e.preventDefault();
      const v = validate(text);
      if (v !== null) void commit(v);
      return;
    }
    if (e.key === 'Escape') {
      if (phase !== 'idle' || invalid) {
        e.preventDefault();
        e.stopPropagation();
        revert();
        input?.select();
      }
      return;
    }
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      stepBy(e.key === 'ArrowUp' ? 1 : -1, precisionOf(e));
    }
  }

  function onWheel(e: WheelEvent): void {
    if (inert || document.activeElement !== input) return; // focused only
    e.preventDefault();
    if (Math.abs(e.deltaY) < 1) return;
    stepBy(e.deltaY < 0 ? 1 : -1, precisionOf(e));
  }

  $effect(() => {
    if (!field) return;
    const el = field;
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  });

  // -- Scrubbing --------------------------------------------------------------------

  function scrubDown(e: PointerEvent, label: boolean): void {
    if (inert || pin || e.button !== 0 || phase === 'sending') return;
    if (!label && document.activeElement === input) return; // editing text: let the caret work
    e.preventDefault();
    fromLabel = label;
    startX = e.clientX;
    startVal = draft ?? value;
    precision = precisionOf(e);
    scrubbing = 'pending';
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  }

  function scrubMove(e: PointerEvent): void {
    if (scrubbing === 'no') return;
    const dx = e.clientX - startX;
    if (scrubbing === 'pending') {
      if (Math.abs(dx) < 3) return;
      scrubbing = 'active';
    }
    const p = precisionOf(e);
    if (p !== precision) {
      // Rebase on a modifier change: the value never jumps.
      startVal = draft ?? value;
      startX = e.clientX;
      precision = p;
      return;
    }
    let v = scrubValue({ start: startVal, dx, step, min, max, precision: p, pxPerStep, ladder });
    if (integer) v = Math.round(v);
    if (v !== (draft ?? value)) {
      draft = v;
      text = fmt(v);
      invalid = null;
      refused = null;
      phase = 'dirty';
    }
  }

  function scrubUp(): void {
    if (scrubbing === 'pending' && !fromLabel) {
      scrubbing = 'no';
      input?.focus();
      input?.select();
      return;
    }
    if (scrubbing === 'active' && draft !== null && !action) void commit(draft);
    scrubbing = 'no';
  }

  // -- Tape -------------------------------------------------------------------------

  const tape = $derived.by(() => {
    const v = current;
    if (ladder) {
      const i = nearestRung(ladder, v);
      const out: { v: number; here: boolean }[] = [];
      for (let k = i - 3; k <= i + 3; k++) {
        if (k < 0 || k >= ladder.length) out.push({ v: Number.NaN, here: false });
        else out.push({ v: k === i ? v : ladder[k], here: k === i });
      }
      return out;
    }
    const span = step * 10;
    const base = Math.round(v / span) * span;
    return [-3, -2, -1, 0, 1, 2, 3].map((k) => {
      const t = k === 0 ? v : base + k * span;
      return { v: t < min || t > max ? Number.NaN : t, here: k === 0 };
    });
  });

  $effect(() => () => {
    clearSettle();
    if (appliedTimer) clearTimeout(appliedTimer);
    if (steppingTimer) clearTimeout(steppingTimer);
  });
</script>

<div
  class="sf"
  class:inline
  class:inert
  class:is-dirty={shownPhase === 'dirty'}
  class:is-bad={shownPhase === 'refused' || shownPhase === 'invalid'}
  class:is-scrub={scrubbing === 'active' || pin?.phase === 'scrub'}
>
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="key"
    onpointerdown={(e) => scrubDown(e, true)}
    onpointermove={scrubMove}
    onpointerup={scrubUp}
    onpointercancel={scrubUp}
    use:tip={{ text: `Drag to change ${label.toLowerCase()}`, hint: 'Shift ×10 · Alt fine · ↑ ↓ step', placement: 'top', disabled: inert }}
  >
    <label for={id}>{label}</label>
    {#if !inert}<span class="grip" aria-hidden="true"></span>{/if}
  </div>

  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="box"
    class:has-act={!!action}
    bind:this={field}
    onpointerdown={(e) => scrubDown(e, false)}
    onpointermove={scrubMove}
    onpointerup={scrubUp}
    onpointercancel={scrubUp}
    use:tip={{ text: label, reason: disabledReason, disabled: !inert, placement: 'top' }}
  >
    <input
      {id}
      bind:this={input}
      type="text"
      inputmode="decimal"
      autocomplete="off"
      spellcheck="false"
      value={shownText}
      readonly={inert}
      aria-disabled={inert || undefined}
      aria-invalid={shownPhase === 'invalid' || shownPhase === 'refused' || undefined}
      aria-busy={shownPhase === 'sending' || undefined}
      aria-describedby="{id}-help"
      oninput={onInput}
      onkeydown={onKey}
      onfocus={() => {
        editing = true;
        if (!invalid && !refused) text = fmt(current);
      }}
      onblur={() => {
        editing = false;
        if (inert) return;
        const v = validate(text);
        if (v !== null && v !== value && phase === 'dirty' && !action) void commit(v);
      }}
    />
    <span class="unit" aria-hidden="true">
      {#if shownPhase === 'sending'}
        <svg class="spinner" viewBox="0 0 24 24" width="12" height="12"><path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" /></svg>
      {:else}{unit ?? ''}{/if}
    </span>
    {#if action}
      <button
        type="button"
        class="act"
        class:ready={shownPhase === 'dirty' && !invalid}
        aria-label={action.label}
        aria-disabled={inert || undefined}
        onpointerdown={(e) => e.stopPropagation()}
        onclick={() => {
          if (inert) return;
          const v = editing ? validate(text) : (draft ?? null);
          if (v !== null) void commit(v);
        }}
        use:tip={{ text: action.label, reason: disabledReason, shortcut: inert ? undefined : 'Enter' }}
      >
        <Icon name={action.icon} size={16} />
      </button>
    {/if}
  </div>

  <div class="help" id="{id}-help">
    {#if showTape}
      <div class="tape num" aria-hidden="true">
        {#each tape as t, i (i)}
          <span class:here={t.here}>{Number.isNaN(t.v) ? '' : fmt(t.v)}</span>
        {/each}
      </div>
      {#if shownPrecision !== 'normal'}
        <span class="prec num">{shownPrecision === 'coarse' ? '×10' : 'fine'}</span>
      {/if}
    {:else if inert}
      <span class="msg reason">{disabledReason}</span>
    {:else if shownPhase === 'invalid'}
      <span class="msg bad">{pin?.message ?? invalid}</span>
    {:else if shownPhase === 'refused'}
      <span class="msg bad">{pin?.message ?? refused}</span><span class="aside"><kbd class="cap">Esc</kbd> reverts</span>
    {:else if shownPhase === 'sending'}
      <span class="msg">Sending…</span>
    {:else if shownPhase === 'applied'}
      <span class="msg ok">Applied{appliedNote ? ` · ${appliedNote}` : ''}</span>
    {:else if shownPhase === 'dirty'}
      <span class="msg">Not sent</span><span class="aside"><kbd class="cap">↵</kbd> {action ? 'moves' : 'sends'} · <kbd class="cap">Esc</kbd></span>
    {:else}
      <span class="range num">{range ?? ''}</span>
    {/if}
  </div>
</div>

<style>
  .sf {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }
  .sf.inline {
    display: grid;
    grid-template-columns: auto minmax(0, 168px) minmax(0, 1fr);
    align-items: center;
    gap: var(--space-3);
  }
  .inline label {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .inline .help {
    justify-content: flex-start;
    gap: var(--space-2);
  }

  .key {
    display: flex;
    align-items: center;
    gap: 6px;
    width: max-content;
    max-width: 100%;
    cursor: ew-resize;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
  }
  label {
    color: var(--text-muted);
    font-size: var(--text-s);
    cursor: inherit;
    transition: color var(--duration-fast) var(--ease-standard);
  }
  .key:hover label,
  .is-scrub label {
    color: var(--fg);
  }
  /* Knurl: three hairlines that say "drag me" without a word. */
  .grip {
    width: 1px;
    height: 7px;
    margin-right: 6px;
    background: var(--fg-muted);
    box-shadow:
      3px 0 0 var(--fg-muted),
      6px 0 0 var(--fg-muted);
    opacity: 0;
    transition: opacity var(--duration-fast) var(--ease-standard);
  }
  .key:hover .grip,
  .is-scrub .grip {
    opacity: 1;
  }
  .inert .key {
    cursor: default;
  }

  .box {
    position: relative;
    display: flex;
    align-items: center;
    cursor: ew-resize;
    touch-action: none;
  }
  .box:focus-within {
    cursor: auto;
  }
  input {
    width: 100%;
    height: var(--input-h);
    padding: 0 calc(var(--space-2) + 3ch) 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-m);
    font-variant-numeric: var(--numeric);
    text-align: right;
    cursor: inherit;
    caret-color: var(--accent);
    transition: border-color var(--duration-fast) var(--ease-standard);
  }
  input:focus {
    cursor: text;
  }
  .box:hover input {
    border-color: var(--fg-muted);
  }
  input:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
  .is-scrub input {
    border-color: var(--fg);
  }
  /* Dashed = what the field shows is not what the device has (as a stale frame). */
  .is-dirty input,
  .is-dirty .box:hover input {
    border-style: dashed;
    border-color: var(--fg-muted);
  }
  .is-bad input,
  .is-bad .box:hover input {
    border-style: solid;
    border-color: var(--danger);
  }
  .inert input,
  .inert .box:hover input {
    border-color: var(--border-soft);
    background: transparent;
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  .inert .box {
    cursor: not-allowed;
  }

  .act {
    display: inline-flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: var(--input-h);
    height: var(--input-h);
    margin-left: var(--space-1);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg-muted);
    cursor: pointer;
    transition:
      background-color var(--duration-instant) var(--ease-standard),
      color var(--duration-fast) var(--ease-standard);
  }
  .act:hover:not([aria-disabled='true']) {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .act:active:not([aria-disabled='true']) {
    background: var(--pressed-bg);
    box-shadow: var(--lab-pressed-inset);
  }
  .act.ready {
    border-color: var(--fg-muted);
    color: var(--fg);
  }
  .act:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }
  .act[aria-disabled='true'] {
    border-color: var(--border-soft);
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  .unit {
    position: absolute;
    right: var(--space-2);
    display: inline-flex;
    align-items: center;
    justify-content: flex-end;
    min-width: 2ch;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    pointer-events: none;
  }
  .inert .unit {
    color: var(--fg-disabled);
  }
  .has-act .unit {
    right: calc(var(--space-2) + var(--input-h) + var(--space-1));
  }

  .help {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    height: 18px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
  }
  .range {
    font-size: var(--text-xs);
  }
  .msg {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .msg.bad,
  .msg.ok {
    color: var(--fg);
  }
  .msg.bad::before,
  .msg.ok::before,
  .msg.reason::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: 6px;
    border-radius: var(--radius-round);
    vertical-align: 1px;
  }
  .msg.bad::before {
    background: var(--danger);
  }
  .msg.ok::before {
    background: var(--success);
  }
  .msg.reason::before {
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .aside {
    display: inline-flex;
    align-items: center;
    gap: 3px;
  }
  .aside :global(kbd.cap) {
    height: 14px;
    min-width: 14px;
  }

  /* Dial tape: the neighbouring values; the centre is the value. */
  .tape {
    position: relative;
    display: grid;
    flex: 1;
    grid-template-columns: repeat(7, 1fr);
    align-items: center;
    height: 18px;
    border-top: var(--border-w) solid var(--border-soft);
    color: var(--fg-disabled);
    font-size: var(--text-2xs);
    text-align: center;
  }
  .tape span {
    position: relative;
  }
  .tape span:not(:empty)::before {
    content: '';
    position: absolute;
    top: -4px;
    left: 50%;
    width: 1px;
    height: 3px;
    background: var(--border);
  }
  .tape .here {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .tape .here::before {
    top: -4px !important;
    height: 5px !important;
    width: 2px !important;
    margin-left: -0.5px;
    background: var(--accent) !important;
  }
  .prec {
    flex: none;
    padding: 0 4px;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-2xs);
    line-height: 14px;
  }

  .spinner {
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spinner {
      animation: none;
    }
  }
  :global(html[data-motion='reduced']) .spinner {
    animation: none;
  }
</style>
