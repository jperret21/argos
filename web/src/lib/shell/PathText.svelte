<!--
  A file path that wraps only after a '/' (never at a hyphen inside a folder name, which
  would read as a hyphenated word): each segment is kept whole, a break opportunity
  follows each slash. The home folder shows as '~' (the full path stays in Copy details).
-->
<script lang="ts">
  import { pathSegments } from './pathText';

  interface Props {
    path: string;
    /** The home folder to show as '~' (when the path does not already start with it). */
    home?: string | null;
  }

  let { path, home = null }: Props = $props();

  const parts = $derived(pathSegments(path, home));
</script>

<span class="path num">{#each parts as part, i (i)}<span class="seg">{part}</span>{#if i < parts.length - 1}<wbr />{/if}{/each}</span>

<style>
  .path {
    overflow-wrap: normal;
  }
  .seg {
    white-space: nowrap;
  }
</style>
