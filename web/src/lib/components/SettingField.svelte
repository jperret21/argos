<!--
  One configuration key in a SettingsForm (settings.ts decides the control
  from the server's meta). Every kind commits ONE `PATCH /api/config` per
  commit (README 3.4): numbers, text and paths on Enter or blur (NumberField
  / CommitTextField), switches, segments and lists of options at once.

  - Label column: the label, the server's help (one line where the "About
    this setting" column shows it in full, Settings at 1 340 px and wider),
    and when the value differs from the default a small neutral dot after
    the label ("changed from the default", in words for screen readers).
    [Reset] (tooltip: the default) appears on row hover or focus, stays
    reachable by keyboard, and offers Undo when the form has an UndoQueue.
    Personal keys (meta.personal: observer name and code, the site) have no
    shipped default to go back to: no dot, no Reset (0°, 0° is not a site).
  - Control column: the control sized for its content (numbers about 12
    characters plus the unit, codes 8-10, names about 280 px, paths the full
    width), left-aligned, then its status line (not saved, saving, saved,
    refused with the server's words, warnings, changed elsewhere).
  - Read-only keys show the value as a fact with the reason (hollow ring);
    dependent keys are unavailable with the reason (never hidden).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { ConfigValue, KeyMeta } from '../api/types';
  import Checkbox from './Checkbox.svelte';
  import CommitTextField from './CommitTextField.svelte';
  import Control from './Control.svelte';
  import NumberField from './NumberField.svelte';
  import { reducedMotion } from './motion.svelte';
  import Segmented from './Segmented.svelte';
  import Select from './Select.svelte';
  import {
    commitKey,
    decimalsFor,
    fieldKind,
    formatValue,
    groupFor,
    isDefault,
    optionKey,
    refusalFor,
    type SettingsPatch,
    signedFor,
  } from './settings';
  import type { UndoQueue } from './undo.svelte';

  interface Props {
    key: string;
    meta: KeyMeta;
    value: ConfigValue | undefined;
    patch: SettingsPatch;
    /** Why it cannot be changed here (read-only keys, dependent keys). */
    reason?: string | null;
    /** Path keys: open the FilePicker, then call `set` with the choice. */
    browse?: ((key: string, current: string, set: (v: string) => void) => void) | null;
    undo?: UndoQueue | null;
    /** Text of an empty field (a nullable override: "Profile: 60 000"). */
    placeholder?: string | null;
    /** Rendered instead of the generated control (lists such as saved sites). */
    custom?: Snippet<[string, KeyMeta, ConfigValue | undefined]> | null;
    onsaved?: (key: string) => void;
    /** Specimen only: freeze the field's state. */
    pin?: { phase?: 'dirty' | 'sending' | 'applied' | 'refused' | 'elsewhere' | 'invalid'; text?: string; message?: string } | null;
  }

  let {
    key,
    meta,
    value,
    patch,
    reason = null,
    browse = null,
    undo = null,
    placeholder = null,
    custom = null,
    onsaved,
    pin = null,
  }: Props = $props();

  const instance = Math.random().toString(36).slice(2, 7);
  const id = $derived(`set-${key.replace(/[^a-z0-9]+/gi, '-')}-${instance}`);
  const kind = $derived(fieldKind(meta));
  const readOnly = $derived(meta.read_only);
  /** The observer's own value (name, AAVSO code, site): no default to reset to (wave 2 fix). */
  const personal = $derived(!!(meta as KeyMeta & { personal?: boolean }).personal);
  const changed = $derived(!personal && value !== undefined && !isDefault(value, meta));
  const defaultText = $derived(formatValue(meta.default, meta, key));
  /** The server says why a read-only key cannot be changed (KeyMeta.read_only_reason, wave 2). */
  const serverReason = $derived((meta as KeyMeta & { read_only_reason?: string | null }).read_only_reason ?? null);
  const unavailable = $derived(readOnly ? (reason ?? serverReason ?? 'Read-only here') : reason);
  /** An empty nullable field: the caller's words, else the default, else "Not set". */
  const emptyText = $derived(
    placeholder ?? (meta.nullable ? (meta.default === null ? 'Not set' : `Default: ${defaultText}`) : undefined),
  );

  async function send(v: ConfigValue): Promise<unknown> {
    const r = await commitKey(patch, key, v);
    onsaved?.(key);
    return r;
  }

  // -- Instant controls (switch, segmented, select): one PATCH per change ---------------

  let instantPhase: 'idle' | 'sending' | 'applied' | 'refused' = $state('idle');
  let instantMessage: string | null = $state(null);
  let instantShown: ConfigValue | undefined = $state(undefined);
  let appliedTimer: ReturnType<typeof setTimeout> | null = null;

  async function sendInstant(v: ConfigValue): Promise<void> {
    if (appliedTimer) clearTimeout(appliedTimer);
    instantShown = v;
    instantPhase = 'sending';
    instantMessage = null;
    try {
      await send(v);
      instantPhase = 'applied';
      appliedTimer = setTimeout(() => {
        if (instantPhase === 'applied') instantPhase = 'idle';
      }, 2000);
    } catch (err) {
      instantPhase = 'refused';
      instantMessage = refusalFor(err, key);
    } finally {
      instantShown = undefined; // the control follows the server's value again
    }
  }
  $effect(() => () => {
    if (appliedTimer) clearTimeout(appliedTimer);
  });

  const instantValue = $derived(instantShown !== undefined ? instantShown : value);
  const segOptions = $derived((meta.options ?? []).map((o) => ({ value: optionKey(o.value), label: o.label })));

  // -- Reset to the default (+ Undo) ---------------------------------------------------------

  let resetting = $state(false);
  let resetError: string | null = $state(null);

  async function reset(): Promise<void> {
    const before = value;
    resetting = true;
    resetError = null;
    try {
      await send(meta.default);
      undo?.push({
        title: `${meta.label} reset to the default`,
        detail: `Was ${formatValue(before ?? null, meta, key)}`,
        undo: () => send(before ?? null),
      });
    } catch (err) {
      resetError = refusalFor(err, key);
    } finally {
      resetting = false;
    }
  }

  /**
   * Width of the control by what it holds (design review: one 400 px input for
   * a 5-character code read as a database dump). Numbers: the widest limit,
   * its decimals and sign, plus the unit; codes and bands 8-10 characters;
   * names about 280 px; hosts 22 characters; paths and lists the full column.
   */
  const controlWidth = $derived.by((): string | undefined => {
    if (kind === 'number') {
      const lim = Math.max(Math.abs(meta.min ?? 0), Math.abs(meta.max ?? 0), Math.abs(typeof value === 'number' ? value : 0));
      const intDigits = Math.max(1, String(Math.floor(lim)).length);
      const groups = intDigits > 3 ? Math.floor((intDigits - 1) / 3) : 0;
      const dec = decimalsFor(meta) ?? 2;
      // An empty override shows its placeholder ("Profile: 60 000"): room for it too.
      const chars = Math.max(6, intDigits + groups + (dec > 0 ? dec + 1 : 0) + 1, (emptyText?.length ?? 0) - 1);
      const unitChars = meta.unit ? meta.unit.length + (/^(°|′|″)/.test(meta.unit) ? 0.4 : 1.2) : 0;
      return `calc(${(chars + unitChars).toFixed(1)}ch + 34px)`;
    }
    if (kind === 'text') {
      if (/obscode|band/.test(key)) return '12ch';
      if (meta.type === 'host') return '24ch';
      return '280px';
    }
    if (kind === 'select') return '280px';
    return undefined;
  });

  /** Number and text fields have an input the label points at; the others are named by aria. */
  const labelled = $derived(!readOnly && !custom && (kind === 'number' || kind === 'text' || kind === 'path'));
  const textPin = $derived(pin && pin.phase !== 'invalid' ? { phase: pin.phase as 'dirty' | 'sending' | 'applied' | 'refused' | 'elsewhere', text: pin.text, message: pin.message } : null);
</script>

<div class="setting" class:changed class:switch-row={kind === 'switch' && !readOnly} data-key={key} style:--ctl-w={controlWidth}>
  {#if kind === 'switch' && !readOnly && !custom}
    <div class="switch-cell">
      <Checkbox
        label={meta.label}
        checked={instantValue === true}
        disabledReason={unavailable}
        detail={meta.help}
        onchange={(c) => void sendInstant(c)}
      />
      <div class="status">
        {#if instantPhase === 'sending'}
          <span class="msg">Saving…</span>
        {:else if instantPhase === 'applied'}
          <span class="msg ok">Saved</span>
        {:else if instantPhase === 'refused'}
          <span class="msg bad">{instantMessage}</span>
        {/if}
      </div>
    </div>
  {:else}
    <div class="label-col">
      {#if labelled}
        <label class="label" for={id}>{meta.label}</label>
      {:else}
        <span class="label" id="{id}-label">{meta.label}</span>
      {/if}
      {#if changed && !readOnly && !custom}<span class="changed-dot" aria-hidden="true"></span>{/if}
      {#if meta.help}<p class="help">{meta.help}</p>{/if}
    </div>
    <div class="control-col">
      {#if custom}
        {@render custom(key, meta, value)}
      {:else if readOnly || kind === 'list' || kind === 'object'}
        <p class="fact" aria-labelledby="{id}-label">
          <!-- An empty override shows what is in effect ("12 bit · from the telescope profile"), never "not set". -->
          <span class="value" class:num={meta.type === 'int' || meta.type === 'float'}>{value === null && placeholder ? placeholder : formatValue(value, meta, key)}</span>
        </p>
        <p class="status"><span class="msg reason">{unavailable ?? 'Edited in its own panel'}</span></p>
      {:else if kind === 'number'}
        <NumberField
          {id}
          label={meta.label}
          hideLabel
          value={typeof value === 'number' ? value : null}
          unit={meta.unit ?? undefined}
          min={meta.min ?? -Infinity}
          max={meta.max ?? Infinity}
          step={meta.step ?? 1}
          decimals={decimalsFor(meta)}
          integer={meta.type === 'int'}
          signed={signedFor(key)}
          group={groupFor(key, meta)}
          nullable={meta.nullable}
          placeholder={emptyText}
          disabledReason={unavailable}
          send={(v) => send(v)}
          appliedWord="Saved"
          dirtyWord="Not saved"
          commitVerb="saves"
          width="min(100%, var(--ctl-w))"
          reserve
          {pin}
        />
      {:else if kind === 'segmented'}
        <div class="instant" class:off={!!unavailable}>
          <Segmented
            label={meta.label}
            options={segOptions}
            value={optionKey(instantValue ?? null)}
            disabled={!!unavailable}
            onchange={(k) => void sendInstant(JSON.parse(k) as ConfigValue)}
          />
          {#if instantPhase === 'sending'}
            <svg class="spinner" class:still={reducedMotion()} viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" /></svg>
          {/if}
        </div>
        <p class="status">
          {#if unavailable}<span class="msg reason">{unavailable}</span>
          {:else if instantPhase === 'applied'}<span class="msg ok">Saved</span>
          {:else if instantPhase === 'refused'}<span class="msg bad">{instantMessage}</span>{/if}
        </p>
      {:else if kind === 'select'}
        <Select
          label={meta.label}
          hideLabel
          width="min(100%, var(--ctl-w))"
          options={segOptions}
          value={optionKey(instantValue ?? null)}
          disabledReason={unavailable}
          onchange={(k) => void sendInstant(JSON.parse(k) as ConfigValue)}
        />
        <p class="status">
          {#if unavailable}<span class="msg reason">{unavailable}</span>
          {:else if instantPhase === 'sending'}<span class="msg">Saving…</span>
          {:else if instantPhase === 'applied'}<span class="msg ok">Saved</span>
          {:else if instantPhase === 'refused'}<span class="msg bad">{instantMessage}</span>{/if}
        </p>
      {:else}
        <CommitTextField
          {id}
          label={meta.label}
          hideLabel
          value={typeof value === 'string' ? value : value === null ? null : String(value ?? '')}
          mono={kind === 'path' || meta.type === 'host' || /obscode|band/.test(key)}
          path={kind === 'path'}
          width={controlWidth ? 'var(--ctl-w)' : undefined}
          upper={/obscode/.test(key)}
          nullable={meta.nullable}
          placeholder={emptyText ?? (kind === 'path' && meta.default === '' ? 'Auto-detect' : undefined)}
          disabledReason={unavailable}
          send={(v) => send(v)}
          reserve
          pin={textPin}
          browse={kind === 'path' && browse
            ? { label: `Choose ${meta.label.toLowerCase()}…`, onclick: (set) => browse?.(key, typeof value === 'string' ? value : '', set) }
            : null}
        />
      {/if}
    </div>
  {/if}
  {#if changed && !readOnly && !custom}
    <div class="reset">
      <span class="visually-hidden">Changed from the default ({defaultText}).</span>
      <Control
        label="Reset"
        size="xs"
        variant="ghost"
        tooltip="top"
        tooltipText="Reset to the default: {defaultText}"
        busy={resetting}
        error={resetError}
        disabledReason={unavailable}
        onclick={() => void reset()}
      />
    </div>
  {/if}
</div>

<style>
  .setting {
    position: relative;
    display: grid;
    grid-template-columns: minmax(0, 15fr) minmax(0, 17fr) 52px;
    grid-template-areas: 'label control reset';
    align-items: start;
    gap: var(--space-1) var(--space-5);
    /* No rule per row: rules separate groups (SettingsBlock), spacing separates rows. */
    padding: 6px 0 6px var(--space-4);
  }
  .setting.switch-row {
    grid-template-columns: minmax(0, 1fr) 52px;
    grid-template-areas: 'control reset';
  }
  @container settings (max-width: 520px) {
    .setting {
      grid-template-columns: minmax(0, 1fr) 52px;
      grid-template-areas:
        'label reset'
        'control control';
    }
  }

  .label-col {
    grid-area: label;
    min-width: 0;
    padding-top: 5px;
  }
  .label {
    color: var(--fg);
    font-size: var(--text-m);
    font-weight: var(--weight-medium);
    line-height: var(--leading-tight);
  }
  /* Changed from the default: a small neutral dot after the label (left bars
     are for selection and alerts; never brass: several rows can be changed). */
  .changed-dot {
    display: inline-block;
    width: 5px;
    height: 5px;
    margin-left: 6px;
    border-radius: var(--radius-round);
    background: var(--fg-muted);
    vertical-align: 2px;
  }
  .help {
    margin: 2px 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
    text-wrap: pretty;
  }
  /* Where the "About this setting" column shows the help in full (Settings
     at 1 340 px and wider), the row keeps one line of it (design review). */
  @container settings-screen (min-width: 1340px) {
    .help {
      display: -webkit-box;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 1;
      line-clamp: 1;
      overflow: hidden;
    }
  }
  .control-col,
  .switch-cell {
    grid-area: control;
    min-width: 0;
  }
  /* Reset: on row hover or focus only (Q-C6: text, no new icon); a keyboard
     user reaches it with Tab, which shows it. */
  .reset {
    grid-area: reset;
    padding-top: 2px;
    opacity: 0;
    transition: opacity var(--duration-fast) var(--ease-standard);
  }
  .setting:hover .reset,
  .setting:focus-within .reset {
    opacity: 1;
  }

  .fact {
    display: flex;
    align-items: center;
    min-height: var(--input-h);
    margin: 0;
  }
  .value {
    color: var(--fg);
    font-size: var(--text-m);
  }
  .value.num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }

  .instant {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--input-h);
  }
  .status {
    display: flex;
    align-items: center;
    min-height: 16px;
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: 16px;
  }
  /* A switch's status ("Saving…", "Saved", the refusal) sits at the right of
     its label instead of a reserved line under it: a switch row is one line
     plus its help (space first, BRAND 11.1). */
  .switch-cell {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: start;
    gap: var(--space-3);
  }
  .switch-cell .status {
    min-height: 0;
    margin-top: 3px;
  }
  .msg {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  /* A refusal or a reason is never cut (BRAND 8): up to three lines. */
  .msg.bad,
  .msg.reason {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    overflow-wrap: anywhere;
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
  .spinner {
    flex: none;
    fill: none;
    stroke: var(--fg-muted);
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
