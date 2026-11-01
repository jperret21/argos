<!--
  Numeric input in the instrument style: Plex Mono, tabular figures,
  right-aligned, unit inside the field. A text input (inputmode decimal), not
  type=number, so no native spinner is drawn (it would be grey in Night Red).
  The bound value only changes for valid input; ArrowUp / ArrowDown step it
  (Shift x10). Invalid text is outlined in --danger and explained in words,
  and stays (with its message) after the field loses focus: the layout never
  jumps under the pointer, and `invalid` lets the caller refuse an action
  while the field does not hold what the observer typed.

  With `settleMs`, a valid value is committed on Enter, on blur, or after
  that pause in typing (arrow steps too), never on each keystroke: a value
  that drives hardware (live-view exposure) is sent once, not for every
  digit typed on the way to it.
-->
<script lang="ts">
  interface Props {
    label: string;
    value: number;
    unit?: string;
    min?: number;
    max?: number;
    step?: number;
    /** Digits shown after blur (undefined: as typed, trimmed). */
    decimals?: number;
    integer?: boolean;
    disabled?: boolean;
    /** Accessible description / help line. */
    hint?: string;
    /** Visible label above the field (default) or only for screen readers. */
    hideLabel?: boolean;
    /** True while the text in the field is not a valid value (bindable, read-only). */
    invalid?: boolean;
    /** Commit after this pause in typing (and on Enter / blur) instead of per keystroke. */
    settleMs?: number;
    onchange?: (value: number) => void;
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
    disabled = false,
    hint,
    hideLabel = false,
    invalid = $bindable(false),
    settleMs,
    onchange,
  }: Props = $props();

  const id = `nf-${Math.random().toString(36).slice(2, 9)}`;
  let focused = $state(false);
  let draft = $state('');
  let error: string | null = $state(null);

  function format(v: number): string {
    if (!Number.isFinite(v)) return '';
    if (integer) return String(Math.round(v));
    return decimals === undefined ? String(Number(v.toPrecision(12))) : v.toFixed(decimals);
  }

  const shown = $derived(focused || error ? draft : format(value));

  $effect(() => {
    invalid = !!error;
  });

  function parse(text: string): { ok: true; v: number } | { ok: false; msg: string } {
    const t = text.trim().replace(',', '.').replace('−', '-');
    if (!/^[-+]?(\d+\.?\d*|\.\d+)$/.test(t)) return { ok: false, msg: 'Enter a number' };
    const v = Number(t);
    if (integer && !Number.isInteger(v)) return { ok: false, msg: 'Whole numbers only' };
    if (v < min || v > max) return { ok: false, msg: `Range ${format(min)}–${format(max)}` };
    return { ok: true, v };
  }

  /** Valid value typed but not committed yet (settle mode). */
  let pending: number | null = null;
  let settleTimer: ReturnType<typeof setTimeout> | null = null;

  function clearSettle(): void {
    if (settleTimer !== null) clearTimeout(settleTimer);
    settleTimer = null;
  }

  function commit(v: number): void {
    clearSettle();
    pending = null;
    if (v === value) return;
    value = v;
    onchange?.(v);
  }

  /** Commit now, or after the settle pause. */
  function offer(v: number): void {
    if (settleMs === undefined) return commit(v);
    pending = v;
    clearSettle();
    settleTimer = setTimeout(() => {
      if (pending !== null) commit(pending);
    }, settleMs);
  }

  function flush(): void {
    if (pending !== null) commit(pending);
  }

  $effect(() => clearSettle); // unmount: drop a timer still running

  function onInput(e: Event & { currentTarget: HTMLInputElement }): void {
    draft = e.currentTarget.value;
    const r = parse(draft);
    error = r.ok ? null : r.msg;
    if (r.ok) offer(r.v);
    else {
      pending = null;
      clearSettle();
    }
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === 'Enter') {
      flush();
      return;
    }
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
    e.preventDefault();
    const dir = e.key === 'ArrowUp' ? 1 : -1;
    const current = pending ?? value;
    const base = Number.isFinite(current) ? current : 0;
    let next = base + dir * step * (e.shiftKey ? 10 : 1);
    next = Math.min(max, Math.max(min, Number(next.toPrecision(12))));
    if (integer) next = Math.round(next);
    draft = format(next);
    error = null;
    offer(next);
  }
</script>

<div class="field" class:invalid={!!error} class:disabled>
  <label for={id} class:visually-hidden={hideLabel}>{label}</label>
  <div class="box" style:--unit-w={unit ? `${unit.length}ch` : undefined}>
    <input
      {id}
      type="text"
      inputmode="decimal"
      autocomplete="off"
      spellcheck="false"
      value={shown}
      {disabled}
      aria-invalid={!!error || undefined}
      aria-describedby={error || hint ? `${id}-help` : undefined}
      oninput={onInput}
      onkeydown={onKey}
      onfocus={() => {
        if (!error) draft = format(value);
        focused = true;
      }}
      onblur={() => {
        flush();
        focused = false;
      }}
    />
    {#if unit}<span class="unit" aria-hidden="true">{unit}</span>{/if}
  </div>
  {#if error}
    <span class="help error" id="{id}-help">{error}</span>
  {:else if hint}
    <span class="help" id="{id}-help">{hint}</span>
  {/if}
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  label {
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  .box {
    position: relative;
    display: flex;
    align-items: center;
  }

  input {
    width: 100%;
    height: var(--input-h);
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-m);
    font-variant-numeric: var(--numeric);
    text-align: right;
    transition: border-color var(--duration-fast) var(--ease-standard);
  }
  /* The unit sits right after the number, inside the field. */
  .box:has(.unit) input {
    padding-right: calc(var(--space-2) + var(--unit-w, 1ch) + 4px);
  }
  input:hover:not(:disabled) {
    border-color: var(--fg-muted);
  }
  /* Ring outside the border (as on buttons), so an invalid field keeps its red edge. */
  input:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
  input:disabled {
    color: var(--fg-disabled);
    border-color: var(--border-soft);
    background: transparent;
  }

  .unit {
    position: absolute;
    right: var(--space-2);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    pointer-events: none;
  }

  .invalid input,
  .invalid input:hover:not(:disabled) {
    border-color: var(--danger);
  }

  .help {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .help.error {
    color: var(--fg);
  }
  .help.error::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: var(--space-1);
    border-radius: var(--radius-round);
    background: var(--danger);
    vertical-align: 1px;
  }
</style>
