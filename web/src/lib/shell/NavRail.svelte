<!--
  Left navigation rail (Qt sidebar.py): the ARGOS mark, then one entry per
  workflow phase, Settings pushed to the bottom. 24 px icon above an 11 px
  label, plus a state mark whose SHAPE says the state (BRAND 4.3, README
  3.12: every status double-coded; brass and amber are close hues, and all
  three are red in Night Red): ready = filled disc (--success), running =
  half disc (--accent), needs attention = ring (--warning), the same
  grammar as the device marks. The state word is in the tooltip and the
  accessible name. Selected entry: --toggled-fg on --surface with the 3 px
  brass bar on the left (BRAND section 8).

  Footer (README 1.1, D14, D15): [help] and [theme] above Settings; the Help
  menu opens the keyboard shortcuts sheet, which lives here so that "?"
  works from every section.
-->
<script lang="ts" module>
  import type { Section } from '../app/state.svelte';

  export interface NavEntry {
    id: Section;
    icon: string;
    label: string;
    hint: string;
    shortcut: string;
  }
</script>

<script lang="ts">
  import { ariaShortcut } from '../app/shortcuts';
  import { useApp } from '../app/state.svelte';
  import Icon from '../components/Icon.svelte';
  import { tooltip } from '../components/tooltip';
  import { firstRunChecklist } from '../connection/model';
  import RailFooter from './RailFooter.svelte';
  import ShortcutSheet from './ShortcutSheet.svelte';

  interface Props {
    entries: readonly NavEntry[];
  }

  let { entries }: Props = $props();
  const app = useApp();

  type Dot = 'ready' | 'active' | 'blocked' | null;

  /**
   * Rail state dots (01 2.4.4, README 3.10.1):
   * - Connection: ready = mount and camera connected; active = discovering or
   *   connecting; attention = a device in error, or the server link lost /
   *   token rejected.
   * - Observe: ready = camera connected; active = live view, an exposure or
   *   a slew (no amber when nothing is connected: that is the normal start).
   * - Settings: attention while the observer code or the site is missing
   *   (Q-G11): FITS and AAVSO metadata would be wrong.
   * - Plan, Review: nothing to report until their waves ship.
   */
  function dotFor(id: Section): Dot {
    // Link down: the records are stale, claim nothing but the problem.
    if (app.stale && app.events.link !== 'idle' && app.events.link !== 'connecting') {
      return id === 'connection' ? 'blocked' : null;
    }
    const devices = app.devices;
    const ready = (d: 'mount' | 'camera') => devices?.[d]?.state === 'connected' || devices?.[d]?.state === 'busy';
    if (id === 'connection') {
      if (app.equipment.anyError) return 'blocked';
      if (app.discovering || app.equipment.anyConnecting) return 'active';
      if (ready('mount') && ready('camera')) return 'ready';
      return null;
    }
    if (id === 'imaging') {
      if (app.cameraBusy || app.slewing) return 'active';
      if (ready('camera')) return 'ready';
      return null;
    }
    if (id === 'configuration' && app.configValues) {
      const missing = firstRunChecklist(app.configValues, true).some((c) => c.id !== 'astap' && !c.done);
      return missing ? 'blocked' : null;
    }
    return null;
  }

  const DOT_WORDS: Record<Exclude<Dot, null>, string> = {
    ready: 'ready',
    active: 'running',
    blocked: 'needs attention',
  };

  const main = $derived(entries.filter((e) => e.id !== 'configuration'));
  const footer = $derived(entries.filter((e) => e.id === 'configuration'));
</script>

{#snippet entry(e: NavEntry)}
  {@const dot = dotFor(e.id)}
  <button
    type="button"
    class="entry"
    class:selected={app.section === e.id}
    aria-current={app.section === e.id ? 'page' : undefined}
    aria-label={dot ? `${e.label}, ${DOT_WORDS[dot]}` : e.label}
    aria-keyshortcuts={ariaShortcut(e.shortcut)}
    onclick={() => app.go(e.id)}
    use:tooltip={{ text: dot ? `${e.hint} · ${DOT_WORDS[dot]}` : e.hint, shortcut: e.shortcut, placement: 'right' }}
  >
    <span class="glyph">
      <Icon name={e.icon} size="l" />
      {#if dot}<span class="dot {dot}" aria-hidden="true"></span>{/if}
    </span>
    <span class="label" aria-hidden="true">{e.label}</span>
  </button>
{/snippet}

<nav class="rail" aria-label="Workspace">
  <div class="mark">
    <Icon name="about" size="l" />
    <span class="wordmark">ARGOS</span>
  </div>
  <div class="entries">
    {#each main as e (e.id)}{@render entry(e)}{/each}
  </div>
  <div class="entries footer">
    <RailFooter
      theme={app.theme}
      ontheme={(t) => app.setTheme(t)}
      version={app.serverVersion}
      api={app.serverApi}
      onshortcuts={() => (app.shortcutSheetOpen = true)}
    />
    {#each footer as e (e.id)}{@render entry(e)}{/each}
  </div>
</nav>
<ShortcutSheet bind:open={app.shortcutSheetOpen} registry={app.shortcuts} />

<style>
  .rail {
    display: flex;
    flex-direction: column;
    width: var(--sidebar-w);
    height: 100%;
    border-right: var(--border-w) solid var(--border);
    background: var(--bg-2);
  }

  /* Brand lockup (BRAND 5): the brass mark, "ARGOS" beside it in Plex Sans 600
     with -0.065em tracking, as on the website. */
  .mark {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    height: calc(var(--control-h-m) + 2 * var(--space-2) + var(--border-w));
    margin-bottom: var(--space-2);
    border-bottom: var(--border-w) solid var(--border); /* continues the toolbar's edge */
    color: var(--accent);
  }

  .wordmark {
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
    letter-spacing: -0.065em;
  }

  .entries {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-1) 0;
  }

  .footer {
    margin-top: auto;
    padding-bottom: var(--space-3);
  }

  .entry {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-1);
    width: 100%;
    padding: var(--space-3) var(--space-1) var(--space-2);
    border: none;
    background: transparent;
    color: var(--fg-muted);
    cursor: pointer;
    transition:
      background-color var(--duration-fast) var(--ease-standard),
      color var(--duration-fast) var(--ease-standard);
  }

  .entry:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }

  .entry:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: calc(-1 * var(--focus-ring-w) - 2px);
  }

  .entry.selected {
    background: var(--surface);
    color: var(--toggled-fg);
  }

  .entry.selected::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: var(--accent);
  }

  .glyph {
    position: relative;
    display: inline-flex;
  }

  .label {
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    line-height: var(--leading-tight);
  }
  .entry:hover .label {
    color: var(--fg);
  }
  .entry.selected .label {
    color: var(--toggled-fg);
  }

  .dot {
    --c: var(--success);
    --halo: var(--bg-2);
    position: absolute;
    top: -2px;
    right: -5px;
    width: 8px;
    height: 8px;
    border-radius: var(--radius-round);
    overflow: hidden;
    /* A halo in the rail's colour keeps the mark off the glyph's strokes. */
    outline: 1.5px solid var(--halo);
  }
  .selected .dot {
    --halo: var(--surface);
  }
  /* Ready: a filled disc. */
  .dot.ready {
    background: var(--c);
  }
  /* Running: a ring, its left half filled. */
  .dot.active {
    --c: var(--accent);
    box-shadow: inset 0 0 0 1.5px var(--c);
  }
  .dot.active::before {
    content: '';
    position: absolute;
    inset: 0 50% 0 0;
    background: var(--c);
  }
  /* Needs attention: a ring. */
  .dot.blocked {
    --c: var(--warning);
    box-shadow: inset 0 0 0 1.5px var(--c);
  }
</style>
