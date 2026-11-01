<!--
  Keyboard shortcuts sheet (01 section 2.3.11), opened by "?" or the Help
  popover. Generated from the one shortcut registry, so the sheet, the
  tooltips and aria-keyshortcuts never disagree; rows that are planned but
  not built yet are not listed (registry.sheet()).
-->
<script lang="ts">
  import { SCOPE_TITLES } from '../app/keymap';
  import { formatShortcut, type ShortcutRegistry } from '../app/shortcuts';
  import Dialog from '../components/Dialog.svelte';

  interface Props {
    open?: boolean;
    registry: ShortcutRegistry;
    preview?: boolean;
  }

  let { open = $bindable(false), registry, preview = false }: Props = $props();

  const groups = $derived(open ? registry.sheet(SCOPE_TITLES) : []);
  const keyText = (k: string) => formatShortcut(k, registry.mac);
</script>

<Dialog bind:open title="Keyboard shortcuts" size="l" {preview}>
  <p class="lead">
    Single keys work when the cursor is not in a text field. Keys never move the mount, except
    <kbd class="key">{keyText('Escape')}</kbd> (abort a slew).
  </p>
  <div class="grid">
    {#each groups as g (g.title)}
      <section aria-label={g.title}>
        <h3>{g.title}</h3>
        <dl>
          {#each g.rows as row (row.id)}
            <dt>
              {#each row.keys as k, i (k)}{#if i > 0}<span class="or">/</span>{/if}<kbd class="key">{keyText(k)}</kbd>{/each}
            </dt>
            <dd>{row.label}</dd>
          {/each}
        </dl>
      </section>
    {/each}
  </div>
</Dialog>

<style>
  .lead {
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4) var(--space-6);
  }

  h3 {
    margin: 0 0 var(--space-2);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }

  dl {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: var(--space-1) var(--space-3);
    margin: 0;
    font-size: var(--text-s);
  }
  dt {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 2px;
    justify-content: flex-end;
  }
  dd {
    margin: 0;
    color: var(--fg);
    line-height: 18px;
  }
  .or {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
