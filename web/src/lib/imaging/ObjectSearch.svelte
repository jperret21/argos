<!--
  Object field of the Mount card's Target block (README D11, spec 05 §2.3 C,
  rows A40-A41): the observation's name merged with the catalogue search.

  - Typing lists names the server knows offline (bundled catalogue and
    earlier lookups, GET /api/catalog/suggest, 150 ms after the last key):
    a token-drawn listbox (Night Red), ↑ ↓ choose, Enter takes the
    highlighted name, Esc closes the list (and, as everywhere, still aborts
    a slew: the key is not swallowed, D21).
  - Enter (or the search button) resolves the text (GET /api/catalog/resolve:
    bundled catalogue, cache, then CDS Sesame online, up to 8 s): the field is
    read-only meanwhile, the search glyph spins. The result goes to the card
    (`onresolved`), which fills the GoTo fields; the observation's name is
    never changed by typing alone (D11: "typing never overwrites silently").
  - A refusal stays under the field in the resolver's own words ("No ICRS
    coordinates found for 'xyz'.", "Catalogue unavailable…"); `onnotfound`
    lets the card offer the text as a plain object name.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import type { Resolved } from '../api/types';
  import { ApiError } from '../api/client';
  import Icon from '../components/Icon.svelte';
  import { tooltip } from '../components/tooltip';

  interface Props {
    /** The observation's object name (shown at rest, restored by Esc). */
    current: string;
    /** Offline names for the typed text. */
    suggest: (q: string, signal: AbortSignal) => Promise<string[]>;
    resolve: (q: string, signal: AbortSignal) => Promise<Resolved>;
    onresolved: (r: Resolved, typed: string) => void;
    onnotfound?: (typed: string, message: string) => void;
    /** The field text changed from the name in use (the card hides an older result). */
    ontyping?: (text: string) => void;
    disabledReason?: string | null;
  }

  let { current, suggest, resolve, onresolved, onnotfound, ontyping, disabledReason = null }: Props = $props();

  const uid = `obj-${Math.random().toString(36).slice(2, 9)}`;
  let text = $state(untrack(() => current));
  let focused = $state(false);
  let edited = $state(false);
  let names: string[] = $state.raw([]);
  let active = $state(-1);
  let listOpen = $state(false);
  let looking = $state(false);
  let error: string | null = $state(null);
  let timer: ReturnType<typeof setTimeout> | null = null;
  let suggestCtl: AbortController | null = null;
  let resolveCtl: AbortController | null = null;

  // The name in use replaces the text while the observer is not editing it.
  $effect(() => {
    const c = current;
    untrack(() => {
      if (!edited && !focused) text = c;
    });
  });

  function onInput(): void {
    edited = true;
    error = null;
    ontyping?.(text);
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
      // The exact text alone is no suggestion.
      names = got.filter((n) => n.toLowerCase() !== q.toLowerCase() || got.length > 1);
      active = -1;
      listOpen = focused && names.length > 0;
    } catch {
      // Offline names are a convenience: a failure only hides the list.
      names = [];
      listOpen = false;
    }
  }

  async function lookUp(q: string = text.trim()): Promise<void> {
    if (!q || looking || disabledReason) return;
    if (timer) clearTimeout(timer);
    suggestCtl?.abort();
    listOpen = false;
    looking = true;
    error = null;
    resolveCtl?.abort();
    const ctl = new AbortController();
    resolveCtl = ctl;
    try {
      const r = await resolve(q, ctl.signal);
      if (ctl.signal.aborted) return;
      onresolved(r, q);
    } catch (err) {
      if (ctl.signal.aborted) return;
      const msg = err instanceof Error ? err.message : String(err);
      error = msg;
      if (err instanceof ApiError && err.code === 'not_found') onnotfound?.(q, msg);
    } finally {
      if (resolveCtl === ctl) looking = false;
    }
  }

  function take(i: number): void {
    const n = names[i];
    if (!n) return;
    text = n;
    edited = true;
    ontyping?.(text);
    void lookUp(n);
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
      else void lookUp();
    } else if (e.key === 'Escape') {
      // Not stopped: the registry still aborts a slew (D21).
      if (listOpen) listOpen = false;
      else if (edited) {
        text = current;
        edited = false;
        error = null;
        ontyping?.(text);
      }
    }
  }

  function onBlur(): void {
    focused = false;
    // Let a click on a suggestion land first.
    setTimeout(() => {
      if (!focused) listOpen = false;
    }, 120);
    if (!text.trim()) {
      text = current;
      edited = false;
    }
  }

  /** The text went back to the name in use (after a target was set). */
  export function settle(): void {
    edited = false;
    text = current;
  }
</script>

<div class="field" class:invalid={!!error}>
  <label for={uid} class="label">Object</label>
  <div class="box" class:disabled={!!disabledReason}>
    <input
      id={uid}
      type="text"
      role="combobox"
      aria-expanded={listOpen}
      aria-controls="{uid}-list"
      aria-autocomplete="list"
      aria-activedescendant={listOpen && active >= 0 ? `${uid}-o${active}` : undefined}
      aria-describedby="{uid}-msg"
      aria-busy={looking}
      autocomplete="off"
      spellcheck="false"
      placeholder="Name: M 42, SS Cyg, RR Lyr…"
      readonly={looking || !!disabledReason}
      bind:value={text}
      oninput={onInput}
      onkeydown={onKey}
      onfocus={() => {
        focused = true;
        if (names.length && edited) listOpen = true;
      }}
      onblur={onBlur}
    />
    <button
      type="button"
      class="go"
      class:spin={looking}
      aria-label="Look up this name in the catalogues"
      aria-disabled={!text.trim() || !!disabledReason || looking}
      onclick={() => void lookUp()}
      use:tooltip={{ text: 'Look up this name', hint: disabledReason ?? 'Bundled catalogue, earlier lookups, then CDS Sesame online (8 s)', shortcut: 'Enter' }}
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
    {#if error}{error}{:else if looking}Looking up “{text.trim()}”…{:else if edited && text.trim() && text.trim() !== current}Enter looks it up{:else}&nbsp;{/if}
  </p>
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }
  .label {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .box {
    position: relative;
    display: flex;
    align-items: center;
    height: var(--control-h-m);
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
  input {
    flex: 1;
    min-width: 0;
    height: 100%;
    padding: 0 var(--space-3);
    border: 0;
    outline: none;
    background: transparent;
    color: var(--fg);
    font-family: var(--font-sans);
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
    width: 30px;
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
