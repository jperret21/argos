<!--
  A mode the app proposes, as a chip over the image (owner decision D1: the observer chooses
  the task mode, the app never switches; promoted from the suggestion chip of
  src/lab/workspace/observe/Viewer.svelte). "Run started · [Run ⌥4] [×]": the button
  switches, × dismisses; switching to that mode in any other way dismisses it too.
  Positions itself at the bottom centre of its positioned container (the viewer cell): the
  host only mounts it there. Polite live region, so a screen reader hears it once.
-->
<script lang="ts">
  import Icon from '../../components/Icon.svelte';
  import { formatShortcut } from '../../app/shortcuts';
  import { tooltip } from '../../components/tooltip';
  import { modeDef } from './layout';
  import type { ObserveWorkspace } from './workspace.svelte';

  interface Props {
    ws: ObserveWorkspace;
    /** Shortcut spec of a mode, from the registry ("Alt+4"). */
    keyFor?: (id: string) => string | undefined;
  }

  let { ws, keyFor = () => undefined }: Props = $props();
  const s = $derived(ws.suggestion);
  const def = $derived(s ? modeDef(s.mode) : null);
  const key = $derived(def ? keyFor(def.shortcut) : undefined);
</script>

<div class="slot" aria-live="polite">
  {#if s && def}
    <div class="chip" role="group" aria-label="Suggestion: {s.text}" data-suggestion={s.mode}>
      <span class="t">{s.text}</span>
      <button type="button" class="go" use:tooltip={{ text: `${def.label} mode: ${def.task}`, shortcut: key, placement: 'top' }} onclick={() => ws.setMode(s.mode)}>
        <Icon name={def.icon} size={14} />{def.label}{#if key}<kbd>{formatShortcut(key)}</kbd>{/if}
      </button>
      <button type="button" class="x" aria-label="Dismiss the suggestion" use:tooltip={{ text: 'Dismiss: the mode stays as it is', placement: 'top' }} onclick={() => ws.dismissSuggestion()}>
        <Icon name="close" size={14} />
      </button>
    </div>
  {/if}
</div>

<style>
  .slot {
    position: absolute;
    z-index: 3;
    left: 50%;
    bottom: var(--space-6);
    transform: translateX(-50%);
    pointer-events: none;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 30px;
    padding: 0 var(--space-1) 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg-2);
    box-shadow: var(--elev-hud);
    color: var(--fg);
    font-size: var(--text-s);
    pointer-events: auto;
  }
  .t {
    white-space: nowrap;
  }
  button {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 24px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--surface);
    color: var(--fg);
    font-size: var(--text-s);
    cursor: pointer;
  }
  button:hover {
    background: var(--hover-bg);
  }
  button:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .x {
    padding: 0 var(--space-1);
    border-color: transparent;
    background: transparent;
  }
  kbd {
    margin-left: 2px;
    padding: 0 3px;
    border: var(--border-w) solid var(--border);
    border-radius: 3px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    line-height: 14px;
  }
</style>
