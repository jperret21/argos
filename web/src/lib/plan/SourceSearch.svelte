<!--
  Source search of the Plan's Source card (06 §2.2 rows 1.5 #2-#4, M72): one field for every
  programme; the programme decides the catalogue (variable stars and other objects:
  `GET /api/catalog/suggest` + `/resolve`, A40-A41; exoplanets: `GET /api/exoplanets/suggest`
  + `/lookup`, A42).

  - Typing lists names known offline (150 ms after the last key; the server caches the file,
    P28): a token-drawn listbox (Night Red), ↑ ↓ choose, Enter takes the highlighted name
    or looks the text up, Escape closes the list then reverts the text.
  - A lookup makes the field read-only and spins the search glyph (BRAND 8); a new lookup
    cancels the previous one. A refusal stays under the field in the server's own words
    (spec 2.4 "Lookup error"; no toast for "not found").
  - `/` focuses it from anywhere on the Plan screen (the screen binds the key).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import Icon from '../components/Icon.svelte';
  import { tooltip } from '../components/tooltip';

  interface Props {
    /** Accessible name ("Variable star"). */
    label: string;
    placeholder: string;
    /** The name in use (shown at rest, restored by Escape). */
    current: string;
    suggest: (q: string, signal: AbortSignal) => Promise<string[]>;
    /** Look the text up; reject with the server's words to refuse. */
    lookup: (q: string, signal: AbortSignal) => Promise<unknown>;
    /** Where a lookup goes, for the button's tooltip. */
    lookupHint?: string;
    disabledReason?: string | null;
    /** Gallery: a frozen state. */
    pin?: { text?: string; looking?: boolean; error?: string; names?: string[]; active?: number } | null;
    /** The input element (the screen's `/` key focuses it). */
    input?: HTMLInputElement | null;
  }

  let { label, placeholder, current, suggest, lookup, lookupHint = '', disabledReason = null, pin = null, input = $bindable(null) }: Props = $props();

  const uid = `src-${Math.random().toString(36).slice(2, 9)}`;
  let text = $state(untrack(() => pin?.text ?? current));
  let focused = $state(false);
  let edited = $state(false);
  let names: string[] = $state.raw(untrack(() => pin?.names ?? []));
  let active = $state(untrack(() => pin?.active ?? -1));
  let listOpen = $state(untrack(() => !!pin?.names?.length));
  let looking = $state(untrack(() => !!pin?.looking));
  let error: string | null = $state(untrack(() => pin?.error ?? null));
  let timer: ReturnType<typeof setTimeout> | null = null;
  let suggestCtl: AbortController | null = null;
  let lookupCtl: AbortController | null = null;

  // The name in use replaces the text while the observer is not editing it.
  $effect(() => {
    const c = current;
    untrack(() => {
      if (!edited && !focused && !pin) text = c;
    });
  });

  // A programme change (new catalogue) drops the open list and the last refusal.
  $effect(() => {
    void suggest;
    untrack(() => {
      if (pin) return;
      names = [];
      listOpen = false;
      error = null;
    });
  });

  function onInput(): void {
    edited = true;
    error = null;
    if (timer) clearTimeout(timer);
    const q = text.trim();
    if (!q) {
      names = [];
      listOpen = false;
      return;
    }
    timer = setTimeout(() => void fetchNames(q), 150);
  }

  async function fetchNames(q: string): Promise<void> {
    suggestCtl?.abort();
    const ctl = new AbortController();
    suggestCtl = ctl;
    try {
      const got = await suggest(q, ctl.signal);
      if (ctl.signal.aborted || text.trim() !== q) return;
      names = got.filter((n) => n.toLowerCase() !== q.toLowerCase() || got.length > 1);
      active = -1;
      listOpen = focused && names.length > 0;
    } catch {
      // Offline names are a convenience: a failure only hides the list.
      names = [];
      listOpen = false;
    }
  }

  async function run(q: string = text.trim()): Promise<void> {
    if (!q || looking || disabledReason) return;
    if (timer) clearTimeout(timer);
    suggestCtl?.abort();
    listOpen = false;
    looking = true;
    error = null;
    lookupCtl?.abort();
    const ctl = new AbortController();
    lookupCtl = ctl;
    try {
      await lookup(q, ctl.signal);
      if (ctl.signal.aborted) return;
      edited = false;
    } catch (err) {
      if (ctl.signal.aborted) return;
      error = err instanceof Error ? err.message : String(err);
    } finally {
      if (lookupCtl === ctl) looking = false;
    }
  }

  function take(i: number): void {
    const n = names[i];
    if (!n) return;
    text = n;
    edited = true;
    void run(n);
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === 'ArrowDown' && names.length) {
      e.preventDefault();
      listOpen = true;
      active = Math.min(names.length - 1, active + 1);
    } else if (e.key === 'ArrowUp' && listOpen) {
      e.preventDefault();
      active = Math.max(-1, active - 1);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (listOpen && active >= 0) take(active);
      else void run();
    } else if (e.key === 'Escape') {
      // Not stopped: the registry still aborts a slew (D21).
      if (listOpen) listOpen = false;
      else if (edited) {
        text = current;
        edited = false;
        error = null;
      }
    }
  }

  function onBlur(): void {
    focused = false;
    setTimeout(() => {
      if (!focused) listOpen = false;
    }, 120);
    if (!text.trim()) {
      text = current;
      edited = false;
    }
  }
</script>

<div class="field" class:invalid={!!error}>
  <div class="box" class:disabled={!!disabledReason}>
    <span class="glyph" aria-hidden="true"><Icon name="search" size="s" /></span>
    <input
      bind:this={input}
      id={uid}
      type="text"
      role="combobox"
      aria-label={label}
      aria-expanded={listOpen}
      aria-controls="{uid}-list"
      aria-autocomplete="list"
      aria-activedescendant={listOpen && active >= 0 ? `${uid}-o${active}` : undefined}
      aria-describedby="{uid}-msg"
      aria-busy={looking}
      aria-disabled={disabledReason ? true : undefined}
      autocomplete="off"
      spellcheck="false"
      {placeholder}
      readonly={looking || !!disabledReason}
      bind:value={text}
      oninput={onInput}
      onkeydown={onKey}
      onfocus={() => {
        focused = true;
        if (names.length && edited) listOpen = true;
      }}
      onblur={onBlur}
      use:tooltip={{ text: label, reason: disabledReason, placement: 'top', disabled: !disabledReason }}
    />
    <button
      type="button"
      class="go"
      class:spin={looking}
      aria-label="Find {text.trim() || 'this name'}"
      aria-disabled={!text.trim() || !!disabledReason || looking}
      onclick={() => void run()}
      use:tooltip={{ text: 'Find', hint: disabledReason ?? lookupHint, shortcut: 'Enter' }}
    >
      <Icon name={looking ? 'refresh' : 'search'} size="s" />
    </button>
    {#if listOpen}
      <div class="list" id="{uid}-list" role="listbox" aria-label="Known names">
        {#each names as n, i (n)}
          <!-- svelte-ignore a11y_click_events_have_key_events (the input owns the keys: aria-activedescendant) -->
          <div
            id="{uid}-o{i}"
            class="opt"
            class:active={i === active}
            role="option"
            aria-selected={i === active}
            tabindex="-1"
            onpointerdown={(e) => e.preventDefault()}
            onclick={() => take(i)}
            onpointerenter={() => (active = i)}
          >
            {n}
          </div>
        {/each}
      </div>
    {/if}
  </div>
  <p class="msg" id="{uid}-msg" class:bad={!!error} aria-live="polite">
    {#if error}{error}{:else if looking}Looking up “{text.trim()}”…{:else if disabledReason}{disabledReason}{:else if edited && text.trim() && text.trim() !== current}Enter finds it{:else}&nbsp;{/if}
  </p>
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }
  .box {
    position: relative;
    display: flex;
    align-items: center;
    height: var(--control-h-s);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg);
  }
  .box:focus-within {
    border-color: var(--focus-ring);
    box-shadow: 0 0 0 1px var(--focus-ring);
  }
  .invalid .box {
    border-color: var(--danger);
  }
  .box.disabled {
    border-color: var(--border-soft);
  }
  .glyph {
    display: inline-flex;
    padding-left: var(--space-3);
    color: var(--fg-muted);
  }
  input {
    flex: 1;
    min-width: 0;
    height: 100%;
    padding: 0 var(--space-2);
    border: 0;
    outline: none;
    background: transparent;
    color: var(--fg);
    font-family: var(--font-ui);
    font-size: var(--text-m);
  }
  input::placeholder {
    color: var(--text-muted);
  }
  input[readonly] {
    color: var(--fg-muted);
  }
  .go {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: calc(100% - 4px);
    margin-right: 2px;
    border: 0;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg-muted);
    cursor: pointer;
  }
  .go:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .go:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .go[aria-disabled='true'] {
    color: var(--fg-disabled);
    cursor: default;
  }
  .go.spin :global(svg) {
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .go.spin :global(svg) {
      animation: none;
    }
  }
  .list {
    position: absolute;
    top: calc(100% + 2px);
    left: -1px;
    right: -1px;
    z-index: 20;
    max-height: calc(6 * 26px + 8px);
    overflow-y: auto;
    padding: var(--space-1) 0;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    box-shadow: var(--shadow-2);
  }
  .opt {
    height: 26px;
    padding: 0 var(--space-3);
    color: var(--fg);
    font-size: var(--text-s);
    line-height: 26px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    cursor: pointer;
  }
  .opt.active {
    background: var(--hover-bg);
    box-shadow: inset 2px 0 0 var(--fg-muted);
  }
  .msg {
    min-height: 1.3em;
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-tight);
  }
  .msg.bad {
    color: var(--fg);
  }
</style>
