<!--
  Panels popover (D1, D16; 01 section 2.3.10): opened by the `arrange`
  button at the right end of a section toolbar. Lists the section's rail
  cards, drawer tabs and plot facets with a checkbox each (changes apply at
  once), and ends with [layout-reset Reset layout], which restores the
  section's defaults live (no confirmation: it is a reversible preference;
  a toast says it, 01 2.4.3).

  Bring your own state, or pass a SectionLayout:
    <PanelsPopover {groups} layout={observeLayout} onreset={() => app.toast('info', 'Layout restored')} />
-->
<script lang="ts" module>
  export interface PanelItem {
    id: string;
    label: string;
    /** Why it cannot be hidden or shown now. */
    disabledReason?: string | null;
  }

  export interface PanelGroup {
    title: string;
    panels: readonly PanelItem[];
  }
</script>

<script lang="ts">
  import type { SectionLayout } from '../app/layout.svelte';
  import Checkbox from './Checkbox.svelte';
  import IconButton from './IconButton.svelte';
  import Popover from './Popover.svelte';

  interface Props {
    groups: readonly PanelGroup[];
    layout?: SectionLayout;
    /** Without a layout: the visibility of a panel, and its change. */
    visible?: (id: string) => boolean;
    onchange?: (id: string, visible: boolean) => void;
    onreset?: () => void;
    /** Draw the open popover in place (gallery). */
    preview?: boolean;
    /** Section name for the button's label ("Observe panels"). */
    section?: string;
  }

  let { groups, layout, visible, onchange, onreset, preview = false, section }: Props = $props();

  let open = $state(false);
  let button: HTMLElement | undefined = $state();
  const id = `panels-${Math.random().toString(36).slice(2, 9)}`;

  function isOn(panel: string): boolean {
    return layout ? layout.visible(panel) : (visible?.(panel) ?? true);
  }

  function set(panel: string, on: boolean): void {
    layout?.setVisible(panel, on);
    onchange?.(panel, on);
  }

  function reset(): void {
    layout?.reset();
    onreset?.();
  }
</script>

{#snippet body()}
  {#each groups as g (g.title)}
    <div class="group" role="group" aria-label={g.title}>
      <h3>{g.title}</h3>
      {#each g.panels as p (p.id)}
        <Checkbox
          label={p.label}
          checked={isOn(p.id)}
          disabledReason={p.disabledReason}
          onchange={(on) => set(p.id, on)}
        />
      {/each}
    </div>
  {/each}
{/snippet}

{#snippet footer()}
  <IconButton icon="layout-reset" label="Reset layout" showLabel size="s" variant="ghost" tooltip="none" onclick={reset} />
{/snippet}

{#if preview}
  <Popover open title="Panels" preview width={260} {footer}>
    {@render body()}
  </Popover>
{:else}
  <span bind:this={button} class="anchor">
    <IconButton
      icon="arrange"
      label={section ? `${section} panels` : 'Panels'}
      variant="ghost"
      tooltip="bottom"
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-controls={id}
      onclick={() => (open = !open)}
    />
  </span>
  <Popover bind:open anchor={button} title="Panels" {id} width={260} placement="bottom-end" {footer}>
    {@render body()}
  </Popover>
{/if}

<style>
  .anchor {
    display: inline-flex;
  }

  .group + .group {
    margin-top: var(--space-2);
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }

  h3 {
    margin: 0 0 var(--space-1);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }

  .group :global(.checkbox) {
    display: flex;
  }
</style>
