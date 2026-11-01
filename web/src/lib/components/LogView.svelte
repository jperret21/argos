<!--
  The activity log list (README 3.8, D17): one line per message, UTC time
  (local time in the tooltip, Q-G18), level tag (CMD INFO OK WARN ERROR, and
  DEBUG when shown), the source when the server names one, the message.

  - Follows the newest line; once the observer scrolls up to read (wheel,
    touch, keys or the scrollbar), it stops following and counts the new
    lines: "Paused · 12 new · Jump to latest" (fixes the Qt log that jumped
    on every line, 01 P28-P30). A scroll the observer did not make (a card
    above grows, a drawer opens, the browser's scroll anchoring) never
    pauses it: a following view is pinned back to the newest line.
  - Windowed (README 3.5, more than 500 rows): only the newest
    `WINDOW` lines are in the page; scrolling to the top (or the "earlier
    lines" row) brings `CHUNK` more, keeping the line under the eyes in
    place. A paused view keeps its first line while new ones arrive.
  - Reads one LogStore through one LogFilter (level, debug, search, topics),
    so the drawer's Log tab and the Connection log show the same store.
  - `markSeen`: while it is on screen and following, its lines count as
    seen (the status-bar badge clears).
  - Level is double-coded (word + colour token), so Night Red holds.
-->
<script lang="ts">
  import { tick } from 'svelte';
  import type { LogFilter, LogStore } from '../app/log.svelte';
  import { FollowState, isAtBottom, LEVEL_NAMES, LEVEL_TAGS, localClock, utcClock, utcFull } from '../app/log';
  import { tooltip } from './tooltip';

  interface Props {
    store: LogStore;
    filter: LogFilter;
    /** What appears here and how, when nothing does yet. */
    empty?: string;
    markSeen?: boolean;
    /** Show the source column (server v2 lines carry one). */
    sources?: boolean;
    /** Gallery: start paused with this many new lines. */
    previewPaused?: number;
    /** Accessible name of the list. */
    label?: string;
  }

  let {
    store,
    filter,
    empty = 'No messages yet. Server events, warnings and failed commands appear here.',
    markSeen = false,
    sources = true,
    previewPaused,
    label = 'Activity log',
  }: Props = $props();

  /** Lines in the page while following the newest one. */
  const WINDOW = 300;
  /** Lines added above when the observer reaches the top. */
  const CHUNK = 300;
  /** A scroll within this long after a wheel, touch or key is the observer's. */
  const INTENT_MS = 400;
  /** Within this many px of the top, earlier lines are brought in. */
  const EARLIER_PX = 40;

  const lines = $derived(store.filtered(filter.spec));
  const searching = $derived(filter.query.trim().length > 0);

  let list: HTMLOListElement | undefined = $state();
  const follow = new FollowState();
  let following = $state(true);
  let unseen = $state(0);
  /** Newest line counted at the last render: newer lines are "new". */
  let lastUid = 0;

  // -- Window -----------------------------------------------------------------
  /** First line shown while paused (stays put as lines arrive). */
  let anchor: number | null = $state(null);
  /** Earlier lines brought in above the window while following. */
  let extra = $state(0);
  const start = $derived.by(() => {
    if (anchor !== null) {
      const i = lines.findIndex((r) => r.uid === anchor);
      if (i >= 0) return i;
      // The anchor line left the store (oldest lines dropped): the top.
      if (lines.length && lines[0].uid > anchor) return 0;
    }
    return Math.max(0, lines.length - WINDOW - extra);
  });
  const shown = $derived(start > 0 ? lines.slice(start) : lines);
  const hasSource = $derived(sources && shown.some((r) => r.source));
  const fmt = (n: number) => n.toLocaleString('en-GB').replace(/,/g, ' ');

  // A new filter shows the newest matching lines again.
  let filterKey = '';
  $effect(() => {
    const key = `${filter.level}|${filter.debug}|${filter.query}`;
    if (key === filterKey) return;
    const first = filterKey === '';
    filterKey = key;
    if (first || previewPaused !== undefined) return;
    anchor = null;
    extra = 0;
    jump();
  });

  $effect.pre(() => {
    if (previewPaused !== undefined) {
      follow.following = false;
      follow.unseen = previewPaused;
      following = false;
      unseen = previewPaused;
    }
  });

  $effect(() => {
    const current = lines;
    if (previewPaused !== undefined) return;
    // A filter change shows old lines: only lines newer than the last render count.
    let added = 0;
    let newest = lastUid;
    for (const r of current) {
      if (r.uid > lastUid) added++;
      if (r.uid > newest) newest = r.uid;
    }
    lastUid = newest;
    const scroll = added > 0 ? follow.appended(added) : follow.following;
    following = follow.following;
    unseen = follow.unseen;
    if (scroll) void tick().then(toBottom);
    if (markSeen && follow.following) store.markSeen();
  });

  function toBottom(): void {
    if (list) list.scrollTop = list.scrollHeight;
  }

  // The region is resized (a card above grows, a drawer opens under it, the
  // window shrinks): a view that follows the newest line keeps it in sight.
  $effect(() => {
    const el = list;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => {
      if (follow.following) toBottom();
    });
    ro.observe(el);
    return () => ro.disconnect();
  });

  // -- What the observer does -------------------------------------------------
  let intentUntil = 0;
  let pointerHeld = false;
  const intent = () => (intentUntil = performance.now() + INTENT_MS);
  const SCROLL_KEYS = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']);

  function onKey(e: KeyboardEvent): void {
    if (SCROLL_KEYS.has(e.key)) intent();
  }
  function onPointerDown(e: PointerEvent): void {
    // The scrollbar (or a drag that scrolls): a click on a line's text is not a scroll.
    if (e.target === list) pointerHeld = true;
  }
  function onPointerUp(): void {
    if (!pointerHeld) return;
    pointerHeld = false;
    intent();
  }

  // Passive listeners: they only note that the observer is scrolling.
  $effect(() => {
    const el = list;
    if (!el) return;
    const opts = { passive: true } as const;
    el.addEventListener('wheel', intent, opts);
    el.addEventListener('touchmove', intent, opts);
    el.addEventListener('keydown', onKey, opts);
    el.addEventListener('pointerdown', onPointerDown, opts);
    return () => {
      el.removeEventListener('wheel', intent);
      el.removeEventListener('touchmove', intent);
      el.removeEventListener('keydown', onKey);
      el.removeEventListener('pointerdown', onPointerDown);
    };
  });

  function onScroll(): void {
    if (!list) return;
    const atBottom = isAtBottom(list.scrollTop, list.scrollHeight, list.clientHeight);
    const byObserver = pointerHeld || performance.now() < intentUntil;
    if (!byObserver) {
      // Layout moved the list (not the observer): a following view stays on
      // the newest line, a paused one stays paused.
      if (follow.following && !atBottom) toBottom();
      return;
    }
    follow.scrolled(atBottom);
    following = follow.following;
    unseen = follow.unseen;
    if (following) {
      anchor = null;
      extra = 0;
    } else if (anchor === null) {
      anchor = shown[0]?.uid ?? null;
    }
    if (markSeen && following) store.markSeen();
    if (list.scrollTop < EARLIER_PX && start > 0) void earlier();
  }

  /** Bring CHUNK earlier lines in above, keeping the line under the eyes in place. */
  async function earlier(): Promise<void> {
    if (!list || start <= 0) return;
    const fromBottom = list.scrollHeight - list.scrollTop;
    const next = Math.max(0, start - CHUNK);
    if (follow.following) extra += start - next;
    else anchor = lines[next]?.uid ?? null;
    await tick();
    if (list) list.scrollTop = list.scrollHeight - fromBottom;
  }

  function jump(): void {
    follow.jump();
    following = true;
    unseen = 0;
    anchor = null;
    extra = 0;
    void tick().then(toBottom);
    if (markSeen) store.markSeen();
  }
</script>

<svelte:window onpointerup={onPointerUp} onpointercancel={onPointerUp} />

<div class="log" class:has-source={hasSource}>
  {#if lines.length === 0}
    <p class="empty">
      {#if store.length === 0}{empty}{:else if searching}No line matches "{filter.query.trim()}".{:else}No line at this level.{/if}
    </p>
  {:else}
    <!-- svelte-ignore a11y_no_noninteractive_tabindex: a scrollable log is read with the keyboard too -->
    <ol
      bind:this={list}
      onscroll={onScroll}
      role="log"
      aria-label={label}
      tabindex="0"
    >
      {#if start > 0}
        <li class="earlier">
          <button type="button" class="more" onclick={() => void earlier()}>
            {fmt(start)} earlier {start === 1 ? 'line' : 'lines'} · show {fmt(Math.min(CHUNK, start))} more
          </button>
        </li>
      {/if}
      {#each shown as r (r.uid)}
        <li class="level-{r.level}">
          <time
            class="num"
            datetime={r.t}
            use:tooltip={{ text: `${utcFull(r.t)} · ${localClock(r.t)}`, placement: 'top' }}
          >{utcClock(r.t)}</time>
          <span class="tag"><span class="visually-hidden">{LEVEL_NAMES[r.level]}: </span><span aria-hidden="true">{LEVEL_TAGS[r.level]}</span></span>
          {#if hasSource}<span class="source">{r.source ?? ''}</span>{/if}
          <span class="msg">{r.message}</span>
        </li>
      {/each}
    </ol>
  {/if}
  {#if !following}
    <div class="paused" role="status">
      <span class="dot" aria-hidden="true"></span>
      <span>{unseen > 0 ? `Paused · ${unseen} new` : 'Paused'}</span>
      <button type="button" class="jump" onclick={jump}>Jump to latest</button>
    </div>
  {/if}
</div>

<style>
  .log {
    position: relative;
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  ol {
    flex: 1;
    min-height: 0;
    margin: 0;
    padding: var(--space-1) 0;
    overflow-y: auto;
    list-style: none;
    /* Follow and pause are decided here, not by the browser's scroll anchoring. */
    overflow-anchor: none;
    font-family: var(--font-mono);
    font-size: var(--text-s);
    line-height: 20px;
  }

  li {
    display: grid;
    grid-template-columns: 64px 44px minmax(0, 1fr);
    gap: var(--space-3);
    padding: 0 var(--space-4);
  }
  .has-source li {
    grid-template-columns: 64px 44px 80px minmax(0, 1fr);
  }
  li:hover {
    background: var(--bg);
  }
  ol:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }

  li.earlier {
    display: block;
  }
  li.earlier:hover {
    background: none;
  }
  .more {
    height: 20px;
    padding: 0;
    border: 0;
    background: none;
    color: var(--text-muted);
    font: inherit;
    font-size: var(--text-xs);
    cursor: pointer;
  }
  .more:hover {
    color: var(--fg);
    text-decoration: underline;
  }
  .more:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }

  time {
    color: var(--text-muted);
  }

  .tag {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    line-height: 20px;
  }
  .level-debug .tag {
    color: var(--log-debug);
  }
  .level-cmd .tag {
    color: var(--log-cmd);
  }
  .level-info .tag {
    color: var(--log-info);
  }
  .level-ok .tag {
    color: var(--log-ok);
  }
  .level-warning .tag {
    color: var(--log-warning);
  }
  .level-error .tag {
    color: var(--log-error);
  }

  .source {
    overflow: hidden;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .msg {
    color: var(--fg);
    overflow-wrap: anywhere;
  }
  .level-debug .msg {
    color: var(--text-muted);
  }

  .empty {
    margin: 0;
    padding: var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  .paused {
    position: absolute;
    right: var(--space-4);
    bottom: var(--space-2);
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 24px;
    padding: 0 var(--space-1) 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--surface);
    box-shadow: var(--shadow-1);
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .dot {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .jump {
    height: 20px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg);
    color: var(--fg);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    cursor: pointer;
  }
  .jump:hover {
    background: var(--hover-bg);
  }
  .jump:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
</style>
