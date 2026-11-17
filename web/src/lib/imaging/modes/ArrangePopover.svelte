<!--
  Arrange (the Panels popover of D1 / D16, extended for the task modes; promoted from
  src/lab/workspace/observe/ArrangePopover.svelte, web/lab/PROPOSAL.md 3.1 and 6, W3). It
  arranges the CURRENT mode: each rail card Open / Folded / Hidden, the band under the
  image, the drawer and its tab, the right panel; what differs from the mode's preset is
  marked, so the observer knows what "Reset" will undo. Changes apply at once (no OK, README
  3.2); Reset is live and offers Undo (no confirmation: a reversible preference).

  Same trigger and Popover as the shared PanelsPopover (the `arrange` icon at the right end
  of the toolbar), so every section's layout menu looks and behaves alike.
-->
<script lang="ts">
  import IconButton from '../../components/IconButton.svelte';
  import Popover from '../../components/Popover.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import { CARD_IDS, CARD_LABELS, CARD_STATES, DRAWER_TABS, modeDef, PRESETS, type CardId, type CardState } from './layout';
  import type { ObserveWorkspace } from './workspace.svelte';

  interface Props {
    ws: ObserveWorkspace;
    /** Draw the open popover in place (gallery). */
    preview?: boolean;
  }

  let { ws, preview = false }: Props = $props();

  let open = $state(false);
  let button: HTMLElement | undefined = $state();
  const id = `arrange-${Math.random().toString(36).slice(2, 9)}`;
  const mode = $derived(modeDef(ws.mode));
  const changed = $derived(new Set(ws.changed));
  const STATE_WORDS: Record<CardState, string> = { open: 'Open', folded: 'Folded', hidden: 'Hidden' };
  const STATE_OPTIONS = CARD_STATES.map((s) => ({ value: s, label: STATE_WORDS[s] }));
  const tabLabel = $derived(DRAWER_TABS.find((t) => t.id === ws.layout.drawerTab)?.label ?? '');
</script>

{#snippet body()}
  <p class="sub">Remembered for {mode.label}; the other modes keep their own.</p>
  <section aria-label="Right panel">
    <h3>
      Right panel <span class="num">· {ws.layout.railOpen ? `${ws.layout.railW} px` : 'closed'}</span>
      {#if changed.has('railOpen') || changed.has('railW')}<span class="mark" aria-label="changed"></span>{/if}
    </h3>
    <ul>
      {#each CARD_IDS as cid (cid)}
        {@const isChanged = changed.has(`card.${cid}`)}
        <li class:changed={isChanged}>
          <span class="name">{CARD_LABELS[cid as CardId].title}</span>
          {#if isChanged}<span class="was">preset {STATE_WORDS[PRESETS[ws.mode].cards[cid as CardId]].toLowerCase()}</span>{/if}
          <span class="seg">
            <Segmented
              label="{CARD_LABELS[cid as CardId].title} card"
              options={STATE_OPTIONS}
              value={ws.layout.cards[cid as CardId]}
              size="s"
              onchange={(v) => ws.setCard(cid as CardId, v as CardState)}
            />
          </span>
        </li>
      {/each}
    </ul>
  </section>
  <section class="pair" aria-label="Band and drawer">
    <div>
      <h3>
        Band <kbd class="key">H</kbd>
        {#if changed.has('bandOpen') || changed.has('bandH')}<span class="mark" aria-label="changed"></span>{/if}
      </h3>
      <button type="button" class="toggle" aria-pressed={ws.layout.bandOpen} onclick={() => ws.toggleBand()}>
        {ws.layout.bandOpen ? 'Shown' : 'Hidden'}
      </button>
      <p class="hint">{mode.band}{ws.layout.bandH === null ? ' · fits the image' : ` · ${ws.layout.bandH} px, set by you`}</p>
    </div>
    <div>
      <h3>
        Drawer <kbd class="key">D</kbd>
        {#if changed.has('drawerOpen') || changed.has('drawerTab') || changed.has('drawerH')}<span class="mark" aria-label="changed"></span>{/if}
      </h3>
      <button type="button" class="toggle" aria-pressed={ws.layout.drawerOpen} onclick={() => ws.toggleDrawer()}>
        {ws.layout.drawerOpen ? 'Open' : 'Closed'}
      </button>
      <p class="hint">tab {tabLabel} · {ws.layout.drawerH} px</p>
    </div>
  </section>
{/snippet}

{#snippet footer()}
  <div class="foot">
    <IconButton
      icon="layout-reset"
      label="Reset {mode.label}"
      showLabel
      size="s"
      variant="ghost"
      tooltip="none"
      disabledReason={ws.modified ? null : `${mode.label} already has its preset layout`}
      onclick={() => ws.resetMode()}
    />
    <button type="button" class="quiet" onclick={() => ws.resetAll()}>Reset every mode</button>
  </div>
{/snippet}

{#if preview}
  <Popover open title="{mode.label} layout" preview width={340} {footer}>
    {@render body()}
  </Popover>
{:else}
  <span bind:this={button} class="anchor">
    <IconButton
      icon="arrange"
      label="Arrange {mode.label}: panels, band, drawer"
      variant="ghost"
      tooltip="bottom"
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-controls={id}
      onclick={() => (open = !open)}
    />
    {#if ws.modified}<span class="dot" aria-hidden="true"></span>{/if}
  </span>
  <Popover bind:open anchor={button} title="{mode.label} layout" {id} width={340} placement="bottom-end" {footer}>
    {@render body()}
  </Popover>
{/if}

<style>
  .anchor {
    position: relative;
    display: inline-flex;
  }
  .dot {
    position: absolute;
    top: 5px;
    right: 5px;
    width: 4px;
    height: 4px;
    border-radius: var(--radius-round);
    background: var(--fg-muted);
    pointer-events: none;
  }
  .sub {
    margin: 0 0 var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  section + section {
    margin-top: var(--space-2);
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }
  h3 {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    margin: 0 0 var(--space-1);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  h3 .num {
    text-transform: none;
    letter-spacing: 0;
  }
  .mark {
    width: 4px;
    height: 4px;
    border-radius: var(--radius-round);
    background: var(--fg-muted);
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
    min-height: 28px;
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
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
  }
  .seg {
    margin-left: auto;
  }
  .pair {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-4);
  }
  .toggle {
    height: 24px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-xs);
    cursor: pointer;
  }
  .toggle[aria-pressed='true'] {
    background: var(--toggled-bg);
    border-color: var(--border);
  }
  .toggle:hover {
    background: var(--hover-bg);
  }
  .toggle:focus-visible,
  .quiet:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .hint {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
  }
  .quiet {
    height: 26px;
    padding: 0 var(--space-2);
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-s);
    cursor: pointer;
  }
  .quiet:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
</style>
