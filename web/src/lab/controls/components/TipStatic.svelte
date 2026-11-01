<!--
  A tooltip drawn in place (specimen only): the same look as tip.ts, so a
  screenshot shows what hover or focus would show.
-->
<script lang="ts">
  import { formatShortcut } from '../../../lib/app/shortcuts';

  interface Props {
    text: string;
    shortcut?: string | readonly string[];
    reason?: string | null;
    error?: string | null;
    hint?: string | null;
  }

  let { text, shortcut, reason = null, error = null, hint = null }: Props = $props();
  const keys = $derived(shortcut === undefined ? [] : typeof shortcut === 'string' ? [shortcut] : shortcut);
</script>

<span class="ctl-tip" aria-hidden="true">
  <span class="row">
    <span>{text}</span>
    {#if keys.length && !reason}
      <span class="keys">{#each keys as k (k)}<kbd class="cap">{formatShortcut(k)}</kbd>{/each}</span>
    {/if}
  </span>
  {#if error}
    <span class="reason error">{error}</span>
  {:else if reason}
    <span class="reason">{reason}</span>
  {:else if hint}
    <span class="reason hint">{hint}</span>
  {/if}
</span>
