<!--
  The task band under the image (owner decision D1; promoted from
  src/lab/workspace/observe/Band.svelte, web/lab/PROPOSAL.md 3.1 and 6, W3): one region
  whose content follows the mode, sized by bandLayout() (BRAND 11.1: by default exactly
  the space a fitted frame leaves, so the image keeps its size and no dead band appears).

  A 28 px header (--band-header-h) names it and says how it is sized ("fits the image" or
  "set by you" with [Fit to image]); H hides it in every mode. Below 150 px it becomes one
  summary row of the same facts (the drawer took the space). Field (wave 4) shows the
  comparison candidates (imaging/field); Run never reaches here in this version.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import Icon from '../../components/Icon.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import { modeDef, type Mode } from './layout';

  interface Props {
    mode: Mode;
    /** Band height, CSS px (its top separator excluded). */
    height: number;
    compact: boolean;
    /** The observer dragged the height (null: it fits the image). */
    userHeight: number | null;
    /** Shortcut of the hide action (registry "view.levels", H). */
    hideKey?: string;
    onhide: () => void;
    onfit: () => void;
    /** The band's content for the current mode, at this content height. */
    children: Snippet<[{ height: number; compact: boolean }]>;
    /** Tools of the mode in the header (right of the title). */
    tools?: Snippet;
  }

  let { mode, height, compact, userHeight, hideKey, onhide, onfit, children, tools }: Props = $props();
  const def = $derived(modeDef(mode));
  const HEADER = 28;
</script>

<section class="band" class:compact aria-label="{def.band} ({def.label})" data-band-height={height} data-band-mode={mode}>
  {#if !compact}
    <header>
      <Icon name={def.icon} size={16} />
      <h2>{def.band}</h2>
      {#if tools}<span class="tools">{@render tools()}</span>{/if}
      <span class="size num">{userHeight === null ? 'fits the image' : 'set by you'} · {height} px</span>
      {#if userHeight !== null}
        <button type="button" class="fit" onclick={onfit}>Fit to image</button>
      {/if}
      <IconButton icon="close" label="Hide the band" shortcut={hideKey} size="s" variant="ghost" tooltip="top" onclick={onhide} />
    </header>
  {/if}
  <div class="content">
    {@render children({ height: compact ? height : Math.max(0, height - HEADER), compact })}
  </div>
</section>

<style>
  .band {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    min-width: 0;
    background: var(--bg-2);
    overflow: hidden;
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: var(--band-header-h);
    padding: 0 var(--space-1) 0 var(--space-3);
    flex: none;
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg-muted);
  }
  h2 {
    margin: 0;
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
    white-space: nowrap;
  }
  .tools {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    margin-left: var(--space-2);
    min-width: 0;
  }
  .size {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-2xs);
    white-space: nowrap;
  }
  .fit {
    height: 22px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-xs);
    cursor: pointer;
  }
  .fit:hover {
    background: var(--hover-bg);
  }
  .fit:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .content {
    position: relative;
    flex: 1;
    min-height: 0;
    min-width: 0;
  }
</style>
