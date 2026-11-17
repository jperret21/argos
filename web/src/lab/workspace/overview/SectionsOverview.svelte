<!--
  One grammar, five sections: the five sections as blueprints at the same
  scale, with what every one of them shares and what each adds. Opened from
  the rail foot, the palette or ?view=overview; Esc closes; a click on a
  miniature opens that section.
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import IconButton from '../../../lib/components/IconButton.svelte';
  import { ws } from '../model/app.svelte';
  import Blueprint from './Blueprint.svelte';
  import { COMMON, SECTIONS } from './sections';
</script>

<div class="overview" role="dialog" aria-modal="true" aria-label="Sections overview">
  <header>
    <div>
      <h1>One workspace grammar, five sections</h1>
      <p>Every section is the same frame: rail, one toolbar row, a hero region, an optional band, a right panel of cards, a drawer with the Log, the status bar. Only the content changes.</p>
    </div>
    <IconButton icon="close" label="Close the overview" shortcut="Escape" variant="ghost" onclick={() => (ws.overlay = 'none')} />
  </header>
  <div class="grid">
    {#each SECTIONS as s (s.id)}
      <button
        type="button"
        class="cell"
        class:current={s.id === 'observe'}
        onclick={() => {
          ws.overlay = 'none';
          ws.section = s.id;
        }}
      >
        <span class="head">
          <Icon name={s.icon} size={20} />
          <span class="name">{s.label}</span>
          <kbd class="key">{s.key}</kbd>
          <span class="role">{s.role}</span>
        </span>
        <span class="mini"><Blueprint section={s.id} mini /></span>
        <span class="notes">
          {#each s.notes as n, i (i)}<span>{n}</span>{/each}
        </span>
      </button>
    {/each}
    <div class="cell legend">
      <span class="head"><span class="name">Shared by every section</span></span>
      <dl>
        {#each COMMON as c (c.title)}
          <dt>{c.title}</dt>
          <dd>{c.text}</dd>
        {/each}
      </dl>
      <p class="key-line">
        <span class="sw hero"></span>hero <span class="sw band"></span>band <span class="sw drawer"></span>drawer
        <span class="sw new"></span>new in this proposal
      </p>
    </div>
  </div>
</div>

<style>
  .overview {
    position: fixed;
    inset: 0;
    z-index: var(--z-modal);
    display: flex;
    flex-direction: column;
    padding: var(--space-5) var(--space-6);
    background: var(--bg);
    overflow: auto;
  }
  header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-5);
    margin-bottom: var(--space-4);
  }
  h1 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-2xl);
    font-weight: var(--weight-semibold);
    letter-spacing: -0.02em;
  }
  header p {
    margin: var(--space-1) 0 0;
    max-width: 980px;
    color: var(--text-muted);
    font-size: var(--text-m);
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-4);
  }
  .cell {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--bg-2);
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .cell:hover {
    border-color: var(--border);
  }
  .cell.current {
    border-color: var(--fg-muted);
  }
  .cell.legend {
    cursor: default;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--fg-muted);
    min-width: 0;
  }
  .name {
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .role {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .mini {
    display: block;
    aspect-ratio: 1440 / 900;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    overflow: hidden;
  }
  .notes {
    display: flex;
    flex-direction: column;
    gap: 2px;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  dl {
    margin: var(--space-1) 0 0;
    display: grid;
    grid-template-columns: 112px 1fr;
    gap: var(--space-2) var(--space-3);
    font-size: var(--text-xs);
  }
  dt {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  dd {
    margin: 0;
    color: var(--text-muted);
  }
  .key-line {
    margin: auto 0 0;
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .sw {
    display: inline-block;
    width: 18px;
    height: 12px;
    margin-left: var(--space-2);
    border: 1px solid var(--border);
    background: var(--bg-2);
  }
  .sw.hero {
    border: 1.5px solid var(--fg-muted);
  }
  .sw.band {
    background: repeating-linear-gradient(45deg, var(--bg), var(--bg) 3px, var(--border-soft) 3px, var(--border-soft) 4px);
  }
  .sw.drawer {
    border-style: dashed;
    background: var(--bg);
  }
  .sw.new {
    border: none;
    border-top: 2px solid var(--fg);
    border-right: 2px solid var(--fg);
    background: transparent;
  }
</style>
