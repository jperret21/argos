<!--
  Target-name suggestion after a Stellarium GoTo (row A20; Qt shell.py:346-353,
  imaging_page.py:2733-2765; spec 05 §2.3 C, mapping M25 / M60): an inline
  notice, dismissible, shown on the Planetarium card (Connection) and in the
  Mount card's Target block (Observe).

  The server looks up names near the GoTo coordinates (online only when
  "Look up target names online after a GoTo" is on) and only OFFERS them:
  nothing changes until the observer chooses one and presses "Use as target
  name", which sets the observation's name and target (A39; the FITS OBJECT
  of the next saves). The candidate list is token-drawn (Select, Night Red),
  nearest first, with its type and separation.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import type { Candidate, TargetSuggestions } from '../api/types';
  import Control from '../components/Control.svelte';
  import Icon from '../components/Icon.svelte';
  import Select from '../components/Select.svelte';
  import { formatDec, formatRA } from '../format/astro';
  import { fixed } from '../format/number';

  interface Props {
    suggestion: TargetSuggestions;
    /** The observation's current name: a candidate already in use says so. */
    current?: string;
    busy?: boolean;
    onuse: (c: Candidate) => void;
    ondismiss: () => void;
  }

  let { suggestion, current = '', busy = false, onuse, ondismiss }: Props = $props();

  let chosen: string | null = $state(untrack(() => suggestion.candidates[0]?.name ?? null));
  $effect(() => {
    const first = suggestion.candidates[0]?.name ?? null;
    untrack(() => {
      if (!suggestion.candidates.some((c) => c.name === chosen)) chosen = first;
    });
  });

  const sep = (c: Candidate) => (c.separation_arcsec < 60 ? `${fixed(c.separation_arcsec, 1)}″` : `${fixed(c.separation_arcsec / 60, 1)}′`);
  const options = $derived(
    suggestion.candidates.map((c) => ({ value: c.name, label: `${c.name} · ${c.type_label || c.object_type} · ${sep(c)} away` })),
  );
  const pick = $derived(suggestion.candidates.find((c) => c.name === chosen) ?? null);
  const n = $derived(suggestion.candidates.length);
  const head = $derived(
    suggestion.state === 'checking'
      ? 'Looking up names near the Stellarium GoTo…'
      : suggestion.state === 'failed'
        ? 'Target-name suggestion failed'
        : n
          ? `${n} catalogue name${n > 1 ? 's' : ''} near the Stellarium GoTo`
          : 'No catalogue name near the Stellarium GoTo',
  );
</script>

<div class="notice" role="group" aria-label="Target-name suggestion">
  <div class="top">
    <Icon name="planetarium" size="s" />
    <span class="head">{head}</span>
    <button type="button" class="x" aria-label="Dismiss the suggestion" onclick={ondismiss}><Icon name="close" size={14} /></button>
  </div>
  <p class="where num">GoTo {formatRA(suggestion.ra_hours)} {formatDec(suggestion.dec_deg)}</p>
  {#if suggestion.state === 'failed'}
    <p class="text">{suggestion.message ?? 'The lookup did not answer.'}</p>
  {:else if suggestion.state === 'ready' && n}
    <p class="text">Choose one only if it is the intended target: it becomes the FITS OBJECT of the next frames.</p>
    <Select label="Candidate" hideLabel options={options} bind:value={chosen} />
    <div class="act">
      <Control
        icon="labels"
        label={pick && pick.name === current ? 'In use' : 'Use as target name'}
        showLabel
        size="s"
        {busy}
        disabledReason={!pick ? 'choose a candidate' : pick.name === current ? `${pick.name} is the object name already` : null}
        onclick={() => pick && onuse(pick)}
      />
    </div>
  {:else if suggestion.state === 'ready'}
    <p class="text">{suggestion.message ?? 'Type the object name in the Mount card if you know it.'}</p>
  {/if}
</div>

<style>
  .notice {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3) var(--space-3);
    border: var(--border-w) solid var(--border);
    border-left: 2px solid var(--fg-muted);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .top {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--fg);
  }
  .head {
    flex: 1;
    min-width: 0;
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
  }
  .x {
    display: inline-flex;
    padding: 2px;
    border: 0;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg-muted);
    cursor: pointer;
  }
  .x:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .x:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
  }
  .where {
    margin: calc(-1 * var(--space-1)) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .text {
    margin: 0;
    color: var(--fg-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-relaxed);
  }
  .act {
    display: flex;
    justify-content: flex-end;
  }
</style>
