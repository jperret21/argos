<!--
  Numeric field, v2 (web/lab/PROPOSAL.md 3.3 "ScrubField", BRAND 8 "Device
  value fields", README 3.4; promoted from src/lab/controls). Plex Mono,
  tabular figures, right-aligned, unit inside the field. A text input with
  inputmode="decimal", never type=number (a native spinner is grey in Night
  Red and Chrome localises "0,0004"); text is read by format/number.ts
  parseNumber (point or comma decimal, any minus, spaces as grouping).

  ONE commit model (commit.svelte.ts): nothing is sent per keystroke. Enter,
  leaving the field, a released label drag (`scrub`) or a pause after
  arrow / wheel steps send ONE value. States, each double-coded:
    not sent     dashed edge, "Not sent · ↵ sends · Esc"
    sending      spinner in the unit slot, aria-busy
    applied      "Applied · <appliedNote>" for 2 s
    refused      danger edge + the server's words; the field keeps the value
                 until Esc reverts it
    invalid      danger edge + the reason ("Search radius must be between 0°
                 and 180°"; "60,000" in a decimal field is refused as
                 ambiguous); never clamped silently, nothing is sent
    unavailable  `disabledReason`: muted, read-only, still focusable, the
                 reason in words
    elsewhere    the value changed in another client while this one held a
                 draft: "Changed elsewhere · Reload"
  Modifiers on every step (values.ts): plain one step, Shift ×10, Alt ×0.1
  (an integer never takes a fractional step); the wheel acts only while the
  field has focus; `ladder` steps through preferred values (exposure).

  `send(v)` commits to the server (reject with its words to refuse); without
  it the value is applied locally at once and `onchange` reports it (the
  wave-1 API: `bind:value`, `onchange`, `settleMs`, `bind:invalid`, `lazy`
  still work; `lazy` is now the default behaviour).

  `action` (W3, the focuser's Go to; PROPOSAL 3.3 "action mode"): an ACTION
  field. Nothing is sent on blur, on a released drag or after arrow steps;
  only Enter or the action button (its icon at the field's right end) send.
  While the field has focus a value from outside never rewrites it (Qt P5:
  autofocus steps overwrote a typed Go to).

  `reserve` keeps a status line of fixed height under the field (forms: the
  layout never jumps); without it the line appears only for an error, a
  refusal, a reason or a hint, and "not sent" / "applied" live in the edge,
  the unit slot and the accessible description (compact rows).
-->
<script lang="ts" generics="T extends number | null = number">
  import NumText from './NumText.svelte';
  import { untrack } from 'svelte';
  import {
    ambiguousComma,
    betweenText,
    DASH,
    fixed,
    formatLimit,
    formatRange,
    MINUS,
    parseNumber,
    signed as signedText,
  } from '../format/number';
  import { CommitModel, type CommitPhase } from './commit.svelte';
  import Icon from './Icon.svelte';
  import { reducedMotion } from './motion.svelte';
  import { tooltip } from './tooltip';
  import { clamp, ladderStep, precisionOf, scrubValue, stepValue, type Precision } from './values';

  type PinPhase = CommitPhase | 'invalid' | 'elsewhere';

  interface Props {
    label: string;
    value: T;
    unit?: string;
    min?: number;
    max?: number;
    step?: number;
    /** Digits shown (default: the value as it is, trimmed). */
    decimals?: number;
    integer?: boolean;
    /** Always show the sign ("+48.85000", latitudes). */
    signed?: boolean;
    /** Group thousands with U+202F ("65 535", default, BRAND 5 / D5); pass false for identifiers (ports). */
    group?: boolean;
    /** Empty text means null (an override that falls back to a default). */
    nullable?: boolean;
    /** Shown in an empty nullable field ("Profile: 60 000"). */
    placeholder?: string;
    /** Preferred values the steps walk through (exposure); Alt leaves them. */
    ladder?: readonly number[];
    /** Custom display format (the text is still parsed by parseNumber). */
    format?: (v: number) => string;
    /** Hard-disabled (no reason to give). Prefer `disabledReason`. */
    disabled?: boolean;
    /** Why it cannot be changed now: read-only, still focusable, the reason in words. */
    disabledReason?: string | null;
    /** Help line (also the accessible description). */
    hint?: string | null;
    /** "0.01–600 s · driver": shown at rest in a reserved line, and in range errors. */
    range?: string;
    /** When an applied value takes effect ("from the next frame"). */
    appliedNote?: string;
    /** The word once applied: "Applied" (devices), "Saved" (configuration, README 3.4). */
    appliedWord?: string;
    /** The uncommitted state: "Not sent" (devices), "Not saved" (configuration). */
    dirtyWord?: string;
    /** What Enter does: "sends" (devices), "saves" (configuration). */
    commitVerb?: string;
    /** Visible label above the field (default) or only for screen readers. */
    hideLabel?: boolean;
    /** True while the text in the field is not a valid value (bindable, read-only). */
    invalid?: boolean;
    /** Also commit after this pause in typing (the wave-1 live exposure). */
    settleMs?: number;
    /** Pause after arrow / wheel steps before the one value is sent. */
    stepSettleMs?: number;
    /** Wave 1: commit only on Enter or blur. Now the default; kept for callers. */
    lazy?: boolean;
    /** Send one value; reject (or throw) with the server's words to refuse it. */
    send?: (v: T) => Promise<unknown> | unknown;
    /** Called with each applied value (after `send` resolved). */
    onchange?: (value: T) => void;
    /** A fixed-height status line under the field (forms). */
    reserve?: boolean;
    /** Drag the label to change the value (W3 instruments); one value on release. */
    scrub?: boolean;
    pxPerStep?: number;
    /** Width of the input (CSS); default 100 % of the container. */
    width?: string;
    /** Specimen only: freeze a state. */
    pin?: { phase?: PinPhase; text?: string; message?: string } | null;
    id?: string;
    /** An action field: only Enter or this button send (focuser Go to). */
    action?: { icon: string; label: string } | null;
  }

  let {
    label,
    value = $bindable(),
    unit,
    min = -Infinity,
    max = Infinity,
    step = 1,
    decimals,
    integer = false,
    signed = false,
    group = true,
    nullable = false,
    placeholder,
    ladder,
    format,
    disabled = false,
    disabledReason = null,
    hint = null,
    range,
    appliedNote,
    appliedWord = 'Applied',
    dirtyWord = 'Not sent',
    commitVerb = 'sends',
    hideLabel = false,
    invalid = $bindable(false),
    settleMs,
    stepSettleMs = 600,
    // `lazy` (wave 1) is accepted and ignored: commit on Enter / blur is the default now.
    send,
    onchange,
    reserve = false,
    scrub = false,
    pxPerStep = 4,
    width,
    pin = null,
    id = `nf-${Math.random().toString(36).slice(2, 9)}`,
    action = null,
  }: Props = $props();


  const model = new CommitModel<T>(
    untrack(() => value),
    {
      // Read at each commit, so a caller may pass or swap `send` later.
      get send() {
        return send ? (v: T) => send!(v) : undefined;
      },
      equals: (a, b) => a === b || (a !== null && b !== null && Math.abs((a as number) - (b as number)) < 1e-12),
      onapplied: (v) => {
        value = v;
        onchange?.(v);
      },
    },
  );

  // A value from outside (bound prop, config event, device echo).
  $effect(() => {
    const v = value;
    untrack(() => model.sync(v));
  });
  $effect(() => () => model.dispose());

  let input: HTMLInputElement | undefined = $state();
  let box: HTMLDivElement | undefined = $state();
  let editing = $state(false);
  let text = $state('');
  let invalidMsg: string | null = $state(null);
  let precision = $state<Precision>('normal');

  const soft = $derived(!disabled && !!disabledReason);
  const locked = $derived(disabled || soft);

  function trimmed(v: number): string {
    const s = String(Number(v.toPrecision(12)));
    return s.startsWith('-') ? MINUS + s.slice(1) : s;
  }

  function fmt(v: T | number | null): string {
    if (v === null || v === undefined) return '';
    const n = v as number;
    if (!Number.isFinite(n)) return '';
    if (format) return format(n);
    const digits = integer ? 0 : decimals;
    if (digits === undefined) {
      const t = trimmed(n);
      return signed && !t.startsWith(MINUS) ? `+${t}` : t;
    }
    const s = signed ? signedText(n, digits, { group }) : fixed(n, digits, { group });
    return s === DASH ? '' : s;
  }

  /** One range notation everywhere (format/number.ts formatRange): "−90° … +90°", limits at their natural precision. */
  const rangeOpts = $derived({ signed, unit: unit ?? null, digits: integer ? 0 : undefined });
  const rangeText = $derived.by(() => {
    if (range) return range;
    return formatRange(min, max, rangeOpts);
  });
  /** An angle unit sits against the number (BRAND 5: "41.27°"), any other after a space. */
  const tightUnit = $derived(!!unit && /^(°|′|″)/.test(unit) && !/^°C/.test(unit));

  /** Typed text -> a value, or the reason it is not one (never clamped). */
  function validate(t: string): { ok: true; v: T } | { ok: false; msg: string } {
    if (!t.trim()) {
      if (nullable) return { ok: true, v: null as T };
      return { ok: false, msg: 'Enter a number' };
    }
    // "60,000": 60 000 in a whole-number field; both readings are possible in a
    // decimal one, so it is refused instead of guessed (a factor of 1 000 either way).
    const both = integer ? null : ambiguousComma(t);
    if (both) return { ok: false, msg: `Write ${both.grouped} or ${both.decimal}: a comma before three digits reads both ways` };
    const v = parseNumber(t, { integer });
    if (v === null) return { ok: false, msg: 'Enter a number' };
    if (integer && !Number.isInteger(v)) return { ok: false, msg: 'Whole numbers only' };
    if (v < min || v > max) {
      if (range) return { ok: false, msg: `Range ${range}` };
      const between = Number.isFinite(min) && Number.isFinite(max) ? betweenText(min, max, rangeOpts) : '';
      const bound = between
        ? `must be between ${between}`
        : v < min
          ? `must be at least ${formatLimit(min, rangeOpts)}`
          : `must be at most ${formatLimit(max, rangeOpts)}`;
      return { ok: false, msg: `${label} ${bound}` };
    }
    return { ok: true, v: v as T };
  }

  // -- Shown state ------------------------------------------------------------------

  const phase = $derived<PinPhase>(
    pin?.phase ?? (invalidMsg ? 'invalid' : model.phase === 'idle' && model.elsewhere ? 'elsewhere' : model.phase),
  );
  const shownText = $derived(
    pin?.text ?? (editing || invalidMsg || model.phase === 'refused' ? text : fmt(model.current)),
  );
  const bad = $derived(phase === 'invalid' || phase === 'refused');
  const dirty = $derived(phase === 'dirty');
  const message = $derived.by((): { kind: string; text: string } | null => {
    if (soft) return { kind: 'reason', text: disabledReason ?? '' };
    if (phase === 'invalid') return { kind: 'bad', text: pin?.message ?? invalidMsg ?? '' };
    if (phase === 'refused') return { kind: 'bad', text: pin?.message ?? model.refused ?? '' };
    if (model.elsewhere || phase === 'elsewhere') return { kind: 'elsewhere', text: 'Changed elsewhere' };
    if (phase === 'sending') return { kind: 'plain', text: 'Sending…' };
    if (phase === 'applied') return { kind: 'ok', text: appliedNote ? `${appliedWord} · ${appliedNote}` : appliedWord };
    if (phase === 'dirty') return { kind: 'dirty', text: dirtyWord };
    if (hint) return { kind: 'hint', text: hint };
    if (reserve && rangeText) return { kind: 'range', text: rangeText };
    return null;
  });
  /** Compact rows show only what the observer must read now. */
  const lineShown = $derived(
    reserve || (!!message && ['reason', 'bad', 'elsewhere', 'hint'].includes(message.kind)),
  );
  /** The edge says "not what the device has" for the screen reader too. */
  const srState = $derived(
    dirty ? `${dirtyWord}. Enter ${commitVerb}, Escape reverts.` : phase === 'sending' ? 'Sending.' : '',
  );
  const escapeLocal = $derived(
    !locked && (dirty || bad || phase === 'sending' || !!model.elsewhere),
  );

  $effect(() => {
    invalid = !!invalidMsg;
  });

  // A new applied value (our commit, or a sync while the field holds nothing
  // of its own) is echoed in canonical form even while the field has focus
  // ("44,5" -> "+44.50000"); text being typed is never rewritten.
  $effect(() => {
    const v = model.value;
    untrack(() => {
      if (action) return; // an action field is never rewritten while it has focus
      if (editing && !model.hasDraft && !invalidMsg && model.phase !== 'refused') text = fmt(v);
    });
  });

  // -- Commit paths -------------------------------------------------------------------

  async function commit(v: T): Promise<void> {
    invalidMsg = null;
    const ok = await model.commit(v);
    if (!ok && model.phase === 'refused') text = fmt(v);
  }

  function onInput(e: Event & { currentTarget: HTMLInputElement }): void {
    if (locked) return;
    text = e.currentTarget.value;
    const r = validate(text);
    if (r.ok) {
      invalidMsg = null;
      if (settleMs !== undefined) model.offer(r.v, settleMs);
      else model.edit(r.v);
    } else {
      invalidMsg = r.msg;
      model.markDirty();
    }
  }

  function stepBy(dir: 1 | -1, p: Precision): void {
    const base = (model.current ?? (Number.isFinite(min) ? min : 0)) as number;
    let v: number;
    if (ladder && p !== 'fine') v = clamp(ladderStep(ladder, base, dir, p === 'coarse' ? 3 : 1), min, max);
    else v = stepValue(base, dir, step, p, min, max, integer);
    precision = p;
    invalidMsg = null;
    text = fmt(v);
    if (action) model.edit(v as T);
    else model.offer(v as T, stepSettleMs);
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      if (escapeLocal || invalidMsg) {
        e.preventDefault(); // the registry still sees it: Escape aborts motion (D21)
        invalidMsg = null;
        model.revert();
        text = fmt(model.current);
        input?.select();
      }
      return;
    }
    if (locked) return;
    if (e.key === 'Enter') {
      e.preventDefault();
      const r = validate(text);
      if (r.ok) void commit(r.v);
      else invalidMsg = r.msg;
      return;
    }
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      stepBy(e.key === 'ArrowUp' ? 1 : -1, precisionOf(e));
    }
  }

  function onWheel(e: WheelEvent): void {
    // Only while focused: a rail that scrolls must never change a value.
    if (locked || !input || document.activeElement !== input) return;
    e.preventDefault();
    if (Math.abs(e.deltaY) < 1) return;
    stepBy(e.deltaY < 0 ? 1 : -1, precisionOf(e));
  }

  $effect(() => {
    if (!box) return;
    const el = box;
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  });

  function onFocus(): void {
    editing = true;
    if (!invalidMsg && model.phase !== 'refused') text = fmt(model.current);
  }

  function onBlur(): void {
    editing = false;
    if (locked || invalidMsg || action) return; // invalid text stays; an action field waits for Enter
    const r = validate(text);
    if (r.ok && model.phase === 'dirty') void commit(r.v);
  }

  // -- Scrubbing (drag the label) -------------------------------------------------------

  let scrubStart: { x: number; v: number } | null = null;
  let scrubbing = $state(false);

  function scrubDown(e: PointerEvent): void {
    if (!scrub || locked || pin || e.button !== 0 || model.busy) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    scrubStart = { x: e.clientX, v: (model.current ?? 0) as number };
    precision = precisionOf(e);
  }

  function scrubMove(e: PointerEvent): void {
    if (!scrubStart) return;
    const dx = e.clientX - scrubStart.x;
    if (!scrubbing && Math.abs(dx) < 3) return;
    scrubbing = true;
    const p = precisionOf(e);
    if (p !== precision) {
      // Rebase on a modifier change: the value never jumps.
      scrubStart = { x: e.clientX, v: (model.current ?? 0) as number };
      precision = p;
      return;
    }
    let v = scrubValue({ start: scrubStart.v, dx, step, min, max, precision: p, pxPerStep, ladder });
    if (integer) v = Math.round(v);
    invalidMsg = null;
    text = fmt(v);
    model.edit(v as T);
  }

  function scrubUp(): void {
    if (scrubStart && scrubbing && model.hasDraft && !action) void commit(model.current);
    scrubStart = null;
    scrubbing = false;
  }

  /** The action button: send what the field holds (typed text or a stepped draft). */
  function runAction(): void {
    if (locked || pin) return;
    const r = validate(editing || invalidMsg ? text : fmt(model.current));
    if (!r.ok) {
      invalidMsg = r.msg;
      return;
    }
    void commit(r.v);
  }

  const fieldTip = $derived({
    text: label,
    reason: soft ? disabledReason : null,
    disabled: !soft,
    placement: 'top' as const,
  });
</script>

<div
  class="field"
  class:is-dirty={dirty}
  class:is-bad={bad}
  class:is-locked={locked}
  class:hard-disabled={disabled}
  class:is-scrub={scrubbing}
  class:tight-unit={tightUnit}
  class:has-action={!!action}
  style:--nf-w={width}
  style:--nf-unit={tightUnit ? `${(unit ?? '').length}ch` : `${Math.max(2, (unit ?? '').length) + 1.2}ch`}
>
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="key"
    class:scrubbable={scrub && !locked}
    class:visually-hidden={hideLabel}
    onpointerdown={scrubDown}
    onpointermove={scrubMove}
    onpointerup={scrubUp}
    onpointercancel={scrubUp}
  >
    <label for={id}>{label}</label>
    {#if scrub && !locked}<span class="grip" aria-hidden="true"></span>{/if}
  </div>
  <div class="box" bind:this={box} use:tooltip={fieldTip}>
    <input
      {id}
      bind:this={input}
      type="text"
      inputmode="decimal"
      autocomplete="off"
      spellcheck="false"
      role="spinbutton"
      value={shownText}
      {placeholder}
      {disabled}
      readonly={soft}
      aria-valuemin={Number.isFinite(min) ? min : undefined}
      aria-valuemax={Number.isFinite(max) ? max : undefined}
      aria-valuenow={model.current === null || !Number.isFinite(model.current as number) ? undefined : (model.current as number)}
      aria-valuetext={model.current === null ? (placeholder ?? 'empty') : `${fmt(model.current)}${unit ? ` ${unit}` : ''}`}
      aria-invalid={bad || undefined}
      aria-busy={phase === 'sending' || undefined}
      aria-disabled={soft || undefined}
      aria-describedby="{id}-help {id}-state"
      data-escape={escapeLocal || invalidMsg ? 'local' : undefined}
      oninput={onInput}
      onkeydown={onKey}
      onfocus={onFocus}
      onblur={onBlur}
    />
    <span class="unit" aria-hidden="true">
      {#if phase === 'sending'}
        <svg class="spinner" class:still={reducedMotion()} viewBox="0 0 24 24" width="12" height="12">
          <path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" />
        </svg>
      {:else if unit && shownText !== ''}{unit}{/if}
    </span>
    {#if action}
      <button
        type="button"
        class="act"
        class:ready={dirty && !invalidMsg}
        aria-label={action.label}
        aria-disabled={soft || undefined}
        {disabled}
        onclick={runAction}
        use:tooltip={{ text: action.label, reason: soft ? disabledReason : null, shortcut: locked ? undefined : 'Enter' }}
      >
        <Icon name={action.icon} size={16} />
      </button>
    {/if}
  </div>
  <span id="{id}-state" class="visually-hidden">{srState}</span>
  {#if lineShown}
    <div class="help" class:reserve id="{id}-help">
      {#if message}
        <span class="msg {message.kind}"><NumText text={message.text} /></span>
        {#if message.kind === 'bad' && phase === 'refused'}
          <span class="aside"><kbd class="cap">Esc</kbd> reverts</span>
        {:else if message.kind === 'elsewhere'}
          <button type="button" class="link" onclick={() => model.reload()}>Reload</button>
        {:else if message.kind === 'dirty'}
          <span class="aside"><kbd class="cap">↵</kbd> {commitVerb} · <kbd class="cap">Esc</kbd></span>
        {:else if message.kind === 'plain' && precision !== 'normal'}
          <span class="aside num">{precision === 'coarse' ? '×10' : '×0.1'}</span>
        {/if}
      {/if}
    </div>
  {:else}
    <span id="{id}-help" hidden></span>
  {/if}
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .key {
    display: flex;
    align-items: center;
    gap: 6px;
    width: max-content;
    max-width: 100%;
  }
  .key.scrubbable {
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
  .key.scrubbable:hover label,
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

  .box {
    position: relative;
    display: flex;
    align-items: center;
    width: var(--nf-w, auto);
  }

  input {
    width: 100%;
    height: var(--input-h);
    /* Room for the unit on the right: its length, at least 2 characters ("× FWHM" is 6). */
    padding: 0 calc(var(--space-2) + var(--nf-unit, 3.2ch)) 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-m);
    font-variant-numeric: var(--numeric);
    text-align: right;
    caret-color: var(--accent);
    transition: border-color var(--duration-fast) var(--ease-standard);
  }
  input::placeholder {
    color: var(--text-muted);
    opacity: 1;
  }
  .box:hover input:not(:disabled) {
    border-color: var(--fg-muted);
  }
  /* Ring outside the border (as on buttons), so the state edge stays readable. */
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
  .is-locked input,
  .is-locked .box:hover input {
    border-color: var(--border-soft);
    background: transparent;
    color: var(--fg-disabled);
  }
  .is-locked input {
    cursor: not-allowed;
  }

  .unit {
    position: absolute;
    right: var(--nf-unit-right, var(--space-2));
    display: inline-flex;
    align-items: center;
    justify-content: flex-end;
    min-width: 2ch;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    pointer-events: none;
  }
  .is-locked .unit {
    color: var(--fg-disabled);
  }
  /* ° ′ ″ against the number ("30°", BRAND 5): the slot is only as wide as the sign. */
  .tight-unit .unit {
    min-width: 0;
    justify-content: flex-start;
  }

  /* Action field: the button sits at the right end of the box; the unit moves left of it. */
  .has-action {
    --nf-unit-right: calc(var(--input-h) + var(--space-1));
  }
  .has-action input {
    padding-right: calc(var(--input-h) + var(--space-2) + var(--nf-unit, 3.2ch));
  }
  .act {
    position: absolute;
    top: 2px;
    right: 2px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: calc(var(--input-h) - 4px);
    height: calc(var(--input-h) - 4px);
    padding: 0;
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg-muted);
    cursor: pointer;
    transition:
      background-color var(--duration-instant) var(--ease-standard),
      color var(--duration-fast) var(--ease-standard);
  }
  .act:hover:not([aria-disabled='true']):not(:disabled) {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .act:active:not([aria-disabled='true']):not(:disabled) {
    background: var(--pressed-bg);
    box-shadow: var(--pressed-inset);
  }
  /* A value waits to be sent: the button that sends it reads as the next step (no brass: a field state). */
  .act.ready {
    border-color: var(--border);
    color: var(--fg);
  }
  .act:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .act[aria-disabled='true'],
  .act:disabled {
    color: var(--fg-disabled);
    cursor: not-allowed;
  }

  .help {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    min-height: 16px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: 16px;
  }
  /* The reserved line is one line high; a refusal or a reason may take up to
     three (the device's or server's words are the text that matters: never
     cut with an ellipsis, BRAND 8). The line grows only in those states. */
  .help.reserve {
    min-height: 16px;
  }
  .help {
    align-items: flex-start;
  }
  .msg {
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .msg.bad,
  .msg.reason {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    white-space: normal;
    text-overflow: clip;
    overflow-wrap: anywhere;
  }
  .msg.bad,
  .msg.ok,
  .msg.elsewhere {
    color: var(--fg);
  }
  .msg.bad::before,
  .msg.ok::before,
  .msg.reason::before,
  .msg.elsewhere::before {
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
  /* Changed elsewhere: a dashed ring (not current), the word carries it. */
  .msg.elsewhere::before {
    border: 1.5px dashed var(--fg-muted);
    box-sizing: border-box;
  }
  .range {
    font-variant-numeric: var(--numeric);
  }
  .aside {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: 3px;
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
  .link {
    flex: none;
    padding: 0 2px;
    border: none;
    border-radius: var(--radius-s);
    background: none;
    color: var(--fg);
    font: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;
    cursor: pointer;
  }
  .link:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }

  .spinner {
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    animation: spin 0.9s linear infinite;
  }
  .spinner.still {
    animation: none;
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
</style>
