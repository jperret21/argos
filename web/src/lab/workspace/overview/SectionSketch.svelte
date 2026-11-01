<!--
  A section the lab does not build: its blueprint at full size in the real
  shell (rail and status bar are live), so the inheritance of the regions is
  seen where it would be used. A note says what is prototyped.
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import { ws } from '../model/app.svelte';
  import type { Section } from '../model/workspace.svelte';
  import Blueprint from './Blueprint.svelte';
  import { SECTIONS } from './sections';

  interface Props {
    section: Section;
  }
  let { section }: Props = $props();
  const def = $derived(SECTIONS.find((s) => s.id === section)!);
</script>

<div class="sketch">
  <Blueprint {section} crop="section" />
  <div class="note">
    <Icon name={def.icon} size={20} />
    <div>
      <p class="t">{def.label} · {def.role}</p>
      <p class="s">Blueprint: this lab builds Observe. {def.label} inherits the same regions: {def.notes.join(' · ')}.</p>
    </div>
    <button type="button" onclick={() => (ws.overlay = 'overview')}>All sections</button>
    <button type="button" onclick={() => (ws.section = 'observe')}>Back to Observe</button>
  </div>
</div>

<style>
  .sketch {
    position: relative;
    height: 100%;
    min-height: 0;
  }
  .note {
    position: absolute;
    left: 50%;
    bottom: var(--space-5);
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: var(--space-3);
    max-width: 920px;
    padding: var(--space-3) var(--space-4);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--shadow-2);
    color: var(--fg-muted);
  }
  .t {
    margin: 0;
    color: var(--fg);
    font-weight: var(--weight-semibold);
  }
  .s {
    margin: 2px 0 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  button {
    flex: none;
    height: 30px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-s);
    cursor: pointer;
  }
</style>
