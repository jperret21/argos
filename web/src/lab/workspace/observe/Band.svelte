<!--
  The task band under the image (functional-spaces P2): one region, sized by
  bandLayout(), whose content follows the mode. A 28 px header names it and
  says how it is sized; H hides it in every mode. Below 120 px it becomes one
  summary row (the drawer took the space).
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import IconButton from '../../../lib/components/IconButton.svelte';
  import { MODES } from '../model/layout';
  import { ws } from '../model/app.svelte';
  import RunBand from './bands/RunBand.svelte';
  import FramingBand from './bands/FramingBand.svelte';
  import FocusBand from './bands/FocusBand.svelte';
  import FieldBand from './bands/FieldBand.svelte';

  interface Props {
    compact: boolean;
    height: number;
  }

  let { compact, height }: Props = $props();
  const mode = $derived(MODES.find((m) => m.id === ws.mode)!);
</script>

<section class="band" class:compact aria-label="{mode.band} ({mode.label})">
  {#if !compact}
    <header>
      <Icon name={mode.icon} size={16} />
      <h2 class="lab-caps">{mode.band}</h2>
      <span class="slot">
        {#if ws.mode === 'run'}
          <IconButton icon="error-bars" label="Error bars" shortcut="U" size="s" variant="ghost" pressed={ws.errorBars} onclick={() => (ws.errorBars = !ws.errorBars)} />
        {/if}
      </span>
      <span class="size num">{ws.layout.bandH === null ? 'fits the image' : 'set by you'} · {height} px</span>
      {#if ws.layout.bandH !== null}
        <button type="button" class="reset" onclick={() => ws.edit((l) => (l.bandH = null))}>Fit to image</button>
      {/if}
      <IconButton icon="disclosure" label="Hide the band" shortcut="H" size="s" variant="ghost" onclick={() => ws.toggleBand()} />
    </header>
  {/if}
  <div class="content">
    {#if ws.mode === 'run'}
      <RunBand {compact} />
    {:else if ws.mode === 'framing'}
      <FramingBand {compact} height={height - 29} />
    {:else if ws.mode === 'focus'}
      <FocusBand {compact} />
    {:else}
      <FieldBand {compact} />
    {/if}
  </div>
</section>

<style>
  .band {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--bg);
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: var(--lab-band-header-h);
    padding: 0 var(--space-1) 0 var(--space-3);
    flex: none;
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg-muted);
  }
  h2 {
    margin: 0;
    color: var(--fg);
  }
  .slot {
    display: inline-flex;
    margin-left: var(--space-2);
  }
  .size {
    margin-left: auto;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
  }
  .reset {
    height: 22px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-xs);
    cursor: pointer;
  }
  .content {
    flex: 1;
    min-height: 0;
    position: relative;
  }
</style>
