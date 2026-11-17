<!--
  A sentence with its numbers in Plex Mono (BRAND 5), the words in the
  surrounding font. See numtext.ts.
-->
<script lang="ts">
  import { groupInteger, numberRuns } from './numtext';

  /** `group`: regroup the plain integers of a server sentence ("5000" -> "5 000"). */
  let { text, group = false }: { text: string; group?: boolean } = $props();
  const runs = $derived(numberRuns(text).map((r) => (group && r.num ? { ...r, text: groupInteger(r.text) } : r)));
</script>

{#each runs as r, i (i)}{#if r.num}<span class="num">{r.text}</span>{:else}{r.text}{/if}{/each}
