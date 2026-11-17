<!--
  Navigation rail of the prototype: the same look and grammar as the app's
  NavRail (mark + wordmark, 24 px icon above an 11 px label, state dot,
  selected entry --toggled-fg on --surface with the 3 px brass bar), fed by
  the lab's state instead of the app's. Footer: overview of the sections,
  theme quick toggle.
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import { tooltip } from '../../../lib/components/tooltip';
  import { nextTheme, THEME_LABELS } from '../../../lib/app/theme';
  import { env, setTheme } from '../model/env.svelte';
  import { sim, ws } from '../model/app.svelte';
  import type { Section } from '../model/workspace.svelte';

  const ENTRIES: { id: Section; icon: string; label: string; key: string }[] = [
    { id: 'connection', icon: 'nav-connection', label: 'Connection', key: 'F1' },
    { id: 'observe', icon: 'nav-imaging', label: 'Observe', key: 'F2' },
    { id: 'plan', icon: 'nav-sequencer', label: 'Plan', key: 'F3' },
    { id: 'review', icon: 'nav-analyze', label: 'Review', key: 'F4' },
  ];

  type Dot = 'ready' | 'active' | 'blocked' | null;
  function dot(id: Section): Dot {
    if (id === 'connection') return 'ready';
    if (id === 'observe') return sim.live || sim.afRunning ? 'active' : 'ready';
    if (id === 'plan') return sim.running ? 'active' : null;
    return null;
  }

  function go(id: Section): void {
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
    if (doc.startViewTransition && env.motion !== 'reduced') doc.startViewTransition(() => (ws.section = id));
    else ws.section = id;
  }
</script>

<nav class="rail" aria-label="Sections">
  <div class="mark">
    <Icon name="about" size={24} />
    <span class="wordmark">ARGOS</span>
  </div>
  <div class="entries">
    {#each ENTRIES as e (e.id)}
      {@const d = dot(e.id)}
      <button
        type="button"
        class="entry"
        class:selected={ws.section === e.id}
        aria-current={ws.section === e.id ? 'page' : undefined}
        onclick={() => go(e.id)}
        use:tooltip={{ text: e.label, shortcut: e.key, placement: 'right' }}
      >
        <span class="glyph">
          <Icon name={e.icon} size={24} />
          {#if d}<span class="dot {d}" aria-hidden="true"></span>{/if}
        </span>
        <span class="label">{e.label}</span>
      </button>
    {/each}
  </div>
  <div class="footer">
    <button
      type="button"
      class="foot"
      aria-label="Sections overview"
      onclick={() => (ws.overlay = ws.overlay === 'overview' ? 'none' : 'overview')}
      use:tooltip={{ text: 'Sections overview: how every section shares the regions', placement: 'right' }}
    >
      <Icon name="layout-tile" size={20} />
    </button>
    <button
      type="button"
      class="foot"
      aria-label="Theme: {THEME_LABELS[env.theme]} (switch)"
      onclick={() => setTheme(nextTheme(env.theme))}
      use:tooltip={{ text: `Theme: ${THEME_LABELS[env.theme]}`, placement: 'right' }}
    >
      <Icon name="theme" size={20} />
    </button>
    <button
      type="button"
      class="entry settings"
      class:selected={ws.section === 'settings'}
      onclick={() => go('settings')}
      use:tooltip={{ text: 'Settings', shortcut: 'F5', placement: 'right' }}
    >
      <span class="glyph"><Icon name="nav-configuration" size={24} /></span>
      <span class="label">Settings</span>
    </button>
  </div>
</nav>

<style>
  .rail {
    grid-area: rail;
    display: flex;
    flex-direction: column;
    width: var(--sidebar-w);
    min-height: 0;
    border-right: var(--border-w) solid var(--border);
    background: var(--bg-2);
  }
  .mark {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    height: var(--lab-toolbar-h);
    margin-bottom: var(--space-2);
    border-bottom: var(--border-w) solid var(--border);
    color: var(--accent);
    flex: none;
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
  .entry:focus-visible,
  .foot:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: calc(-1 * var(--focus-ring-w) - 2px);
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
    position: absolute;
    top: -2px;
    right: -5px;
    width: 7px;
    height: 7px;
    border: 1.5px solid var(--bg-2);
    border-radius: var(--radius-round);
    box-sizing: content-box;
  }
  .selected .dot {
    border-color: var(--surface);
  }
  .dot.ready {
    background: var(--success);
  }
  .dot.active {
    background: var(--accent);
  }
  .dot.blocked {
    background: var(--warning);
  }
  .footer {
    margin-top: auto;
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: var(--space-1);
    padding-bottom: var(--space-2);
  }
  .foot {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg-muted);
    cursor: pointer;
  }
  .foot:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .settings {
    margin-top: var(--space-1);
  }
</style>
