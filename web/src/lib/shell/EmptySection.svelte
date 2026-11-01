<!--
  Placeholder for the sections this spike does not build yet: a quiet,
  centred statement of what the section will hold, and a way back.
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import Icon from '../components/Icon.svelte';
  import IconButton from '../components/IconButton.svelte';

  interface Props {
    icon: string;
    title: string;
    text: string;
    items: readonly string[];
  }

  let { icon, title, text, items }: Props = $props();
  const app = useApp();
</script>

<section class="empty" aria-labelledby="empty-title">
  <div class="inner">
    <span class="glyph"><Icon name={icon} size={48} /></span>
    <p class="eyebrow">Not in this preview</p>
    <h1 id="empty-title">{title}</h1>
    <p class="text">{text}</p>
    <ul>
      {#each items as item (item)}<li>{item}</li>{/each}
    </ul>
    <IconButton
      icon="nav-imaging"
      label="Back to Observe"
      showLabel
      shortcut="F2"
      onclick={() => (app.section = 'imaging')}
    />
  </div>
</section>

<style>
  .empty {
    display: grid;
    place-items: center;
    height: 100%;
    padding: var(--space-6);
    background: var(--bg);
    overflow: auto;
  }

  .inner {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    max-width: 440px;
  }

  .glyph {
    display: inline-flex;
    margin-bottom: var(--space-5);
    color: var(--fg-muted);
  }

  .eyebrow {
    margin: 0 0 var(--space-2);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }

  h1 {
    margin: 0 0 var(--space-3);
    color: var(--fg);
    font-size: var(--text-2xl);
    font-weight: var(--weight-semibold);
    letter-spacing: -0.02em;
    line-height: var(--leading-tight);
  }

  .text {
    margin: 0 0 var(--space-4);
    color: var(--text-muted);
    line-height: var(--leading-relaxed);
  }

  ul {
    margin: 0 0 var(--space-5);
    padding: 0;
    list-style: none;
    border-top: var(--border-w) solid var(--border-soft);
    width: 100%;
  }

  li {
    padding: var(--space-2) 0;
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg);
    font-size: var(--text-s);
  }
</style>
