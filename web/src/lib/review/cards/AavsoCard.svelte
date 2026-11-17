<!--
  Rail card "AAVSO export" (07 E13, WF-B; README M92; fixes 07 P8: the card now leads to the
  action). The pre-checks before the dialog: OBSCODE (required, Q-R2: a link to Settings),
  the target rows (target-role curves only, S11), one filter per file (S53), FILT against
  the frames' filter, CHART, the check star (KNAME / KMAG), the points left out (saturated,
  suspect: Q-R3). The dialog (front-end B, A77 preview, A78 export) is the final word; this
  card opens it through `onexport` (the same request as the toolbar's Export AAVSO…).
-->
<script lang="ts">
  import Card from '../../components/Card.svelte';
  import Control from '../../components/Control.svelte';
  import Icon from '../../components/Icon.svelte';
  import { int } from '../../format/number';
  import type { AavsoCheck } from '../rail';

  interface Props {
    checks: readonly AavsoCheck[];
    rows: number;
    blocked: string | null;
    onexport?: () => void;
    /** Settings › Observer & site (OBSCODE). */
    onsettings?: () => void;
  }
  let { checks, rows, blocked, onexport, onsettings }: Props = $props();
  const warn = $derived(checks.filter((c) => c.level !== 'ok').length);
</script>

<Card title="AAVSO export" icon="export-aavso" collapsible persist="review.aavso">
  {#snippet summary()}{blocked ? 'blocked' : `${int(rows)} rows`}{/snippet}
  <dl class="kv">
    {#each checks as c (c.id)}
      <dt>{c.label}</dt>
      <dd class:warn={c.level === 'warn'} class:block={c.level === 'block'} title={c.detail}>
        {#if c.level !== 'ok'}<span class="mark" aria-label={c.level === 'block' ? 'Blocks the export' : 'Check this'}><Icon name="attention" size={12} /></span>{/if}
        <span class="num">{c.value}</span>
        {#if c.id === 'obscode' && c.level === 'block' && onsettings}<button type="button" class="link" onclick={onsettings}>Settings ›</button>{/if}
      </dd>
    {/each}
  </dl>
  <div class="act">
    <span class="sum">{warn ? `${warn} to check` : 'Ready'}</span>
    <Control icon="export-aavso" label="Export AAVSO…" showLabel size="s" disabledReason={blocked} onclick={() => onexport?.()} />
  </div>
</Card>

<style>
  .kv {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 3px var(--space-3);
    margin: 0;
    font-size: var(--text-xs);
  }
  .kv dt {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    line-height: 18px;
  }
  .kv dd {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    margin: 0;
    min-width: 0;
    color: var(--fg);
    line-height: 18px;
  }
  .kv dd .num {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .mark {
    display: inline-flex;
    flex: none;
    color: var(--warning);
  }
  dd.block .mark {
    color: var(--danger);
  }
  .link {
    flex: none;
    padding: 0;
    border: none;
    background: none;
    color: var(--fg);
    font: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;
    cursor: pointer;
  }
  .link:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
  .act {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    margin-top: var(--space-3);
  }
  .sum {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
