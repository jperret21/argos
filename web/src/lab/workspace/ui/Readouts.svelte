<!--
  Readout grid for rail cards: micro label (10 px mono caps, --text-muted),
  value in Plex Mono with tabular figures (--lab-readout: 17 px compact,
  20 px comfortable), unit muted and smaller. `key` values use
  --lab-readout-key (17 / 26 px): what the observer reads from a step away.
  Reflows by the card's own width (container query): 2 columns in a 340-420
  px rail, 4 above 460 px.
-->
<script lang="ts" module>
  export interface ReadoutItem {
    k: string;
    v: string;
    unit?: string;
    note?: string;
    key?: boolean;
    /** Marked: an icon-free word next to the value carries the state. */
    flag?: string;
    muted?: boolean;
  }
</script>

<script lang="ts">
  interface Props {
    items: readonly ReadoutItem[];
    cols?: 2 | 3 | 4;
  }

  let { items, cols = 2 }: Props = $props();
</script>

<div class="wrap">
  <dl class="grid cols-{cols}">
    {#each items as it (it.k)}
      <div class="cell" class:key={it.key} class:muted={it.muted}>
        <dt>{it.k}</dt>
        <dd>
          <span class="v">{it.v}</span>{#if it.unit}<span class="u">{it.unit}</span>{/if}
          {#if it.flag}<span class="flag">{it.flag}</span>{/if}
        </dd>
        {#if it.note}<span class="note">{it.note}</span>{/if}
      </div>
    {/each}
  </dl>
</div>

<style>
  .wrap {
    container-type: inline-size;
  }
  .grid {
    display: grid;
    gap: var(--space-3) var(--space-4);
    margin: 0;
  }
  .cols-2 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .cols-3 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .cols-4 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  @container (min-width: 460px) {
    .cols-4 {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
  }
  .cell {
    min-width: 0;
  }
  dt {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  dd {
    display: flex;
    align-items: baseline;
    gap: var(--space-1);
    margin: 2px 0 0;
    color: var(--fg);
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
    font-size: var(--lab-readout);
    font-weight: var(--weight-medium);
    line-height: var(--leading-tight);
    white-space: nowrap;
  }
  .key dd {
    font-size: var(--lab-readout-key);
  }
  .muted dd {
    color: var(--text-muted);
  }
  .u {
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-regular);
  }
  .flag {
    align-self: center;
    margin-left: var(--space-1);
    padding: 0 var(--space-1);
    border: var(--border-w) solid var(--warning);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-family: var(--font-ui);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    line-height: 16px;
  }
  .note {
    display: block;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
