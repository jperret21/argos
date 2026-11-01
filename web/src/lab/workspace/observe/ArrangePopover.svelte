<!--
  Arrange (the Panels popover of D1/D16), for the CURRENT mode: each rail
  card Open / Folded / Hidden, the band and the drawer, the rail width, and
  the two resets. What differs from the mode's preset is marked, so the
  observer knows what "Reset" will undo. Changes apply at once (no OK).
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import { ws } from '../model/app.svelte';
  import { CARD_LABELS, CARD_ORDER, changedKeys, DRAWER_TABS, MODES, PRESETS, type CardId, type CardState } from '../model/layout';

  const STATES: { id: CardState; label: string }[] = [
    { id: 'open', label: 'Open' },
    { id: 'folded', label: 'Folded' },
    { id: 'hidden', label: 'Hidden' },
  ];

  const mode = $derived(MODES.find((m) => m.id === ws.mode)!);
  const changed = $derived(new Set(changedKeys(ws.mode, ws.layout)));
  const isChanged = (id: CardId) => changed.has(`card.${id}`);
</script>

<div class="pop" role="dialog" aria-label="Layout of {mode.label}">
  <header>
    <Icon name={mode.icon} size={16} />
    <h2>{mode.label} layout</h2>
    <span class="hint">remembered for this mode</span>
  </header>
  <section>
    <h3 class="lab-caps">Right panel · {ws.layout.railOpen ? `${ws.layout.railW} px` : 'closed'}</h3>
    <ul>
      {#each CARD_ORDER[ws.mode] as id (id)}
        <li class:changed={isChanged(id)}>
          <span class="name">{CARD_LABELS[id].title}</span>
          {#if isChanged(id)}<span class="was">preset: {PRESETS[ws.mode].cards[id]}</span>{/if}
          <span class="tri" role="radiogroup" aria-label="{CARD_LABELS[id].title} card">
            {#each STATES as s (s.id)}
              <button
                type="button"
                role="radio"
                aria-checked={ws.layout.cards[id] === s.id}
                class:on={ws.layout.cards[id] === s.id}
                onclick={() => ws.setCard(id, s.id)}>{s.label}</button
              >
            {/each}
          </span>
        </li>
      {/each}
    </ul>
  </section>
  <section class="pair">
    <div>
      <h3 class="lab-caps">Band under the image</h3>
      <button type="button" class="toggle" aria-pressed={ws.layout.bandOpen} onclick={() => ws.toggleBand()}>
        {ws.layout.bandOpen ? 'Shown' : 'Hidden'} <kbd class="key">H</kbd>
      </button>
      <p class="sub">{mode.band}{ws.layout.bandH === null ? ' · fits the image' : ` · ${ws.layout.bandH} px`}</p>
    </div>
    <div>
      <h3 class="lab-caps">Drawer</h3>
      <button type="button" class="toggle" aria-pressed={ws.layout.drawerOpen} onclick={() => ws.toggleDrawer()}>
        {ws.layout.drawerOpen ? 'Open' : 'Closed'} <kbd class="key">D</kbd>
      </button>
      <p class="sub">tab: {DRAWER_TABS.find((t) => t.id === ws.layout.drawerTab)?.label}</p>
    </div>
  </section>
  <footer>
    <button type="button" class="reset" disabled={!ws.modified} onclick={() => ws.resetMode()}>
      <Icon name="layout-reset" size={16} /> Reset {mode.label} layout
    </button>
    <button type="button" class="reset quiet" onclick={() => ws.resetAll()}>Reset all four modes</button>
  </footer>
</div>

<style>
  .pop {
    position: absolute;
    right: 0;
    top: calc(100% + 6px);
    width: 380px;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--lab-elev-float);
    z-index: var(--z-popover);
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-3) var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg-muted);
  }
  h2 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .hint {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  section {
    padding: var(--space-3) var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  h3 {
    margin: 0 0 var(--space-2);
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  li {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: 28px;
    padding-left: var(--space-2);
    border-left: 2px solid transparent;
  }
  li.changed {
    border-left-color: var(--fg-muted);
  }
  .name {
    color: var(--fg);
    font-size: var(--text-s);
  }
  .was {
    color: var(--text-muted);
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
  }
  .tri {
    margin-left: auto;
    display: inline-flex;
    gap: 2px;
    padding: 2px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .tri button,
  .toggle {
    height: 20px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-xs);
    cursor: pointer;
  }
  .tri button:hover,
  .toggle:hover {
    color: var(--fg);
  }
  .tri button.on {
    background: var(--toggled-bg);
    border-color: var(--border);
    color: var(--fg);
  }
  .pair {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-4);
  }
  .toggle {
    height: 26px;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    border-color: var(--border-soft);
    color: var(--fg);
  }
  .sub {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--space-3) var(--space-4);
  }
  .reset {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 28px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    cursor: pointer;
  }
  .reset:disabled {
    color: var(--fg-disabled);
    border-color: var(--border-soft);
    cursor: not-allowed;
  }
  .reset.quiet {
    border-color: transparent;
    color: var(--text-muted);
  }
  .reset:hover:not(:disabled) {
    background: var(--hover-bg);
  }
</style>
