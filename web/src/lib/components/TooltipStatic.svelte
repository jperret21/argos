<!--
  A tooltip drawn in place (gallery and screenshots only): the same element
  and classes as tooltip.ts, so a screenshot shows exactly what hover, focus
  or a press on an unavailable control shows. Promoted from
  src/lab/controls/components/TipStatic.svelte.
-->
<script lang="ts">
  import { formatShortcut } from '../app/shortcuts';
  import { tipContent } from './tooltip';

  interface Props {
    text: string;
    shortcut?: string | readonly string[];
    reason?: string | null;
    error?: string | null;
    hint?: string | null;
  }

  let { text, shortcut, reason = null, error = null, hint = null }: Props = $props();
  const c = $derived(tipContent({ text, shortcut, reason, error, hint }));
</script>

<span class="argos-tip static" data-v2 data-open="true" aria-hidden="true">
  <span class="tip-row">
    <span>{c.text}</span>
    {#if c.keys.length}
      <span class="tip-keys">{#each c.keys as k (k)}<kbd>{formatShortcut(k)}</kbd>{/each}</span>
    {/if}
  </span>
  {#if c.second}
    <span class="tip-second {c.second.kind}">{c.second.text}</span>
  {/if}
</span>
