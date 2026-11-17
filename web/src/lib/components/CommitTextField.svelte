<!--
  Text field with the one commit model (commit.svelte.ts; README 3.4): a
  name, a host, an observer code or a path is sent ONCE, on Enter or when the
  field loses focus, never per keystroke (fixes the Qt host-per-keystroke
  write, 02 A). The same visible states as NumberField: not sent (dashed
  edge), sending (spinner), applied, refused (the server's words; the field
  keeps the text until Esc reverts it), unavailable (reason), changed
  elsewhere (Reload), plus the server's warnings after an applied value
  ("does not exist, it will be created"), marked by the upright attention
  mark and the word.

  `browse` adds an icon button (`browse`) after the field: the caller opens
  the FilePicker and calls `set(path)` with the choice, which commits it.
  `upper` upper-cases as typed (AAVSO codes); `nullable` sends null for an
  empty field (an override that falls back to the profile's value).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { CommitModel } from './commit.svelte';
  import Control from './Control.svelte';
  import { reducedMotion } from './motion.svelte';
  import { middlePath } from './pathfield';

  type V = string | null;

  interface Props {
    label: string;
    value: V;
    send?: (v: V) => Promise<unknown> | unknown;
    onchange?: (v: V) => void;
    mono?: boolean;
    upper?: boolean;
    nullable?: boolean;
    placeholder?: string;
    maxlength?: number;
    disabledReason?: string | null;
    hint?: string | null;
    appliedNote?: string;
    hideLabel?: boolean;
    reserve?: boolean;
    /** Width of the input (CSS); default the full width. */
    width?: string;
    /** A path: shown with the middle cut and the last segment whole while not focused (02 2.2). */
    path?: boolean;
    /** The uncommitted state (default "Not saved"; device fields say "Not sent"). */
    dirtyWord?: string;
    /** What Enter does (default "saves"). */
    commitVerb?: string;
    /** An icon button after the field (a FilePicker); it receives `set` to commit a choice. */
    browse?: { label: string; onclick: (set: (v: string) => void) => void } | null;
    /** Specimen only: freeze a state. */
    pin?: { phase?: 'dirty' | 'sending' | 'applied' | 'refused' | 'elsewhere'; text?: string; message?: string } | null;
    id?: string;
  }

  let {
    label,
    value = $bindable(),
    send,
    onchange,
    mono = false,
    upper = false,
    nullable = false,
    placeholder,
    maxlength,
    disabledReason = null,
    hint = null,
    appliedNote,
    hideLabel = false,
    reserve = false,
    browse = null,
    path = false,
    width,
    dirtyWord = 'Not saved',
    commitVerb = 'saves',
    pin = null,
    id = `ctf-${Math.random().toString(36).slice(2, 9)}`,
  }: Props = $props();

  let warnings: string[] = $state([]);

  function warningsOf(r: unknown): string[] {
    if (r && typeof r === 'object' && 'warnings' in r && Array.isArray((r as { warnings: unknown }).warnings)) {
      return ((r as { warnings: unknown[] }).warnings as unknown[]).map((w) =>
        typeof w === 'string' ? w : w && typeof w === 'object' && 'message' in w ? String((w as { message: unknown }).message) : '',
      ).filter(Boolean);
    }
    return [];
  }

  const model = new CommitModel<V>(
    untrack(() => value),
    {
      get send() {
        return send
          ? async (v: V) => {
              const r = await send!(v);
              warnings = warningsOf(r);
            }
          : undefined;
      },
      onapplied: (v) => {
        value = v;
        onchange?.(v);
      },
    },
  );
  $effect(() => {
    const v = value;
    untrack(() => model.sync(v));
  });
  $effect(() => () => model.dispose());
  // A new applied value (normalised by the server: upper-cased, ~ expanded)
  // replaces the text even while the field has focus, unless it holds a draft.
  $effect(() => {
    const v = model.value;
    untrack(() => {
      if (editing && !model.hasDraft && model.phase !== 'refused') text = v ?? '';
    });
  });

  let editing = $state(false);
  let text = $state('');

  const soft = $derived(!!disabledReason);
  const phase = $derived(pin?.phase ?? (model.phase === 'idle' && model.elsewhere ? 'elsewhere' : model.phase));
  const shown = $derived(pin?.text ?? (editing || model.phase === 'refused' ? text : (model.current ?? '')));
  const bad = $derived(phase === 'refused');
  const escapeLocal = $derived(!soft && (phase === 'dirty' || bad || !!model.elsewhere));

  function toValue(t: string): V {
    const s = upper ? t.toUpperCase() : t;
    return nullable && !s.trim() ? null : s;
  }

  function onInput(e: Event & { currentTarget: HTMLInputElement }): void {
    if (soft) return;
    let t = e.currentTarget.value;
    if (upper && t !== t.toUpperCase()) {
      const pos = e.currentTarget.selectionStart;
      t = t.toUpperCase();
      e.currentTarget.value = t;
      if (pos !== null) e.currentTarget.setSelectionRange(pos, pos);
    }
    text = t;
    warnings = [];
    model.edit(toValue(t));
  }

  function commitText(): void {
    if (soft) return;
    void model.commit(toValue(text));
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitText();
    } else if (e.key === 'Escape' && escapeLocal) {
      e.preventDefault(); // the registry still sees it (abort motion, D21)
      model.revert();
      text = model.current ?? '';
    }
  }

  /** Commit a value chosen elsewhere (the FilePicker). */
  function set(v: string): void {
    text = v;
    warnings = [];
    void model.commit(toValue(v));
  }

  const message = $derived.by((): { kind: string; text: string } | null => {
    if (soft) return { kind: 'reason', text: disabledReason ?? '' };
    if (phase === 'refused') return { kind: 'bad', text: pin?.message ?? model.refused ?? '' };
    if (phase === 'elsewhere' || model.elsewhere) return { kind: 'elsewhere', text: 'Changed elsewhere' };
    if (phase === 'sending') return { kind: 'plain', text: 'Saving…' };
    if (warnings.length) return { kind: 'warn', text: warnings.join(' · ') };
    if (phase === 'applied') return { kind: 'ok', text: appliedNote ? `Saved · ${appliedNote}` : 'Saved' };
    if (phase === 'dirty') return { kind: 'dirty', text: dirtyWord };
    if (hint) return { kind: 'hint', text: hint };
    return null;
  });
  const lineShown = $derived(reserve || (!!message && ['reason', 'bad', 'elsewhere', 'hint', 'warn'].includes(message.kind)));
</script>

<div class="field" class:is-dirty={phase === 'dirty'} class:is-bad={bad} class:is-locked={soft}>
  <label for={id} class:visually-hidden={hideLabel}>{label}</label>
  <div class="row">
    <div class="box" style:--ctf-w={width}>
      <input
        {id}
        type="text"
        class:mono
        autocomplete="off"
        spellcheck="false"
        value={shown}
        use:middlePath={{ value: shown, enabled: path && !pin }}
        {placeholder}
        {maxlength}
        readonly={soft}
        aria-disabled={soft || undefined}
        aria-invalid={bad || undefined}
        aria-busy={phase === 'sending' || undefined}
        aria-describedby="{id}-help"
        data-escape={escapeLocal ? 'local' : undefined}
        oninput={onInput}
        onkeydown={onKey}
        onfocus={() => {
          editing = true;
          if (model.phase !== 'refused') text = model.current ?? '';
        }}
        onblur={() => {
          editing = false;
          if (model.phase === 'dirty') commitText();
        }}
      />
      {#if phase === 'sending'}
        <svg class="spinner" class:still={reducedMotion()} viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
          <path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" />
        </svg>
      {/if}
    </div>
    {#if browse}
      <Control
        icon="browse"
        label={browse.label}
        size="s"
        disabledReason={soft ? disabledReason : null}
        onclick={() => browse?.onclick(set)}
      />
    {/if}
  </div>
  {#if lineShown}
    <div class="help" class:reserve id="{id}-help">
      {#if message}
        <span class="msg {message.kind}">{message.text}</span>
        {#if message.kind === 'bad'}
          <span class="aside"><kbd class="cap">Esc</kbd> reverts</span>
        {:else if message.kind === 'elsewhere'}
          <button type="button" class="link" onclick={() => model.reload()}>Reload</button>
        {:else if message.kind === 'dirty'}
          <span class="aside"><kbd class="cap">↵</kbd> {commitVerb} · <kbd class="cap">Esc</kbd></span>
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
  label {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .box {
    position: relative;
    display: flex;
    flex: 1;
    align-items: center;
    min-width: 0;
    max-width: var(--ctf-w, none);
  }
  input {
    width: 100%;
    height: var(--input-h);
    padding: 0 calc(var(--space-3) + 14px) 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-family: var(--font-ui);
    font-size: var(--text-m);
    caret-color: var(--accent);
    text-overflow: ellipsis;
    transition: border-color var(--duration-fast) var(--ease-standard);
  }
  input.mono {
    font-family: var(--font-mono);
    font-size: var(--text-s);
  }
  input::placeholder {
    color: var(--text-muted);
    opacity: 1;
  }
  .box:hover input {
    border-color: var(--fg-muted);
  }
  input:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
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
    cursor: not-allowed;
  }
  .spinner {
    position: absolute;
    right: var(--space-2);
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
  .help {
    align-items: flex-start;
  }
  .msg {
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  /* A refusal, a reason or a warning is never cut (BRAND 8): up to three lines. */
  .msg.bad,
  .msg.reason,
  .msg.warn {
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
  .msg.warn,
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
  .msg.elsewhere::before {
    border: 1.5px dashed var(--fg-muted);
    box-sizing: border-box;
  }
  /* A warning: the upright attention mark (a bar over a dot), never a triangle. */
  .msg.warn::before {
    content: '';
    display: inline-block;
    width: 2px;
    height: 9px;
    margin: 0 8px 0 2px;
    vertical-align: -1px;
    background: linear-gradient(var(--warning) 0 6px, transparent 6px 7px, var(--warning) 7px 9px);
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
</style>
