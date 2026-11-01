<!--
  Conditions card: numbers first, each with a sparkline of the run. A rule
  that holds marks its row with a word ("rule") and its dashed threshold on
  the sparkline: never colour alone. Altitude says until when the target
  stays above the limit.
-->
<script lang="ts">
  import Spark from '../../charts/Spark.svelte';
  import { sim } from '../../model/app.svelte';
  import { fixed, int, utc } from '../../model/format';
  import { median } from '../../model/night';
  import { RULES } from '../../model/rules';

  const recs = $derived(sim.records);
  const l = $derived(sim.latest);
  const base = $derived(recs.length >= RULES.baselineFrames ? recs.slice(0, RULES.baselineFrames) : null);
  const hfd0 = $derived(base ? median(base.map((r) => r.hfd)) : NaN);
  const stars0 = $derived(base ? median(base.map((r) => r.stars)) : NaN);
  const hfdRule = $derived(sim.attention.find((a) => a.rule === 'HFD rise'));

  const rows = $derived(
    l
      ? [
          {
            k: 'HFD',
            v: fixed(l.hfd, 1),
            u: 'px',
            vals: recs.map((r) => r.hfd),
            thr: Number.isFinite(hfd0) ? RULES.hfdFactor * hfd0 : null,
            note: Number.isFinite(hfd0) ? `baseline ${fixed(hfd0, 2)} · rule at ${fixed(RULES.hfdFactor * hfd0, 1)}` : '',
            flag: hfdRule ? `rule since ${utc(hfdRule.since, false)}` : null,
          },
          {
            k: 'Stars',
            v: int(l.stars),
            u: '',
            vals: recs.map((r) => r.stars),
            thr: Number.isFinite(stars0) ? RULES.starFactor * stars0 : null,
            note: Number.isFinite(stars0) ? `baseline ${int(stars0)} · rule below ${int(RULES.starFactor * stars0)}` : '',
            flag: null,
          },
          { k: 'Sky', v: int(l.sky), u: 'ADU', vals: recs.map((r) => r.sky), thr: null, note: 'median of the frame', flag: null },
          {
            k: 'Altitude',
            v: fixed(l.alt, 1),
            u: '°',
            vals: recs.map((r) => r.alt),
            thr: null,
            note: 'above 30° until 01:10 UTC',
            flag: null,
          },
        ]
      : [],
  );
</script>

{#if rows.length}
  <ul class="cond">
    {#each rows as r (r.k)}
      <li class:flagged={!!r.flag}>
        <span class="k lab-caps">{r.k}</span>
        <span class="v num">{r.v}<span class="u">{r.u}</span></span>
        <span class="spark"><Spark values={r.vals} threshold={r.thr} label="{r.k} over the run, latest {r.v} {r.u}" height={26} /></span>
        <span class="note">{r.note}</span>
        {#if r.flag}<span class="flag">{r.flag}</span>{/if}
      </li>
    {/each}
  </ul>
{:else}
  <p class="empty">Conditions appear with the first frame of a run.</p>
{/if}

<style>
  .cond {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }
  li {
    display: grid;
    grid-template-columns: 74px 96px 1fr;
    grid-template-rows: auto auto;
    align-items: center;
    column-gap: var(--space-3);
    padding: var(--space-2) 0;
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  li:last-child {
    border-bottom: none;
  }
  .k {
    grid-row: 1;
  }
  .v {
    grid-row: 1;
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--lab-readout);
    font-weight: var(--weight-medium);
    text-align: right;
  }
  .u {
    margin-left: 3px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-regular);
  }
  .spark {
    grid-row: 1;
    min-width: 0;
  }
  .note {
    grid-column: 1 / 3;
    grid-row: 2;
    color: var(--text-muted);
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .flag {
    grid-column: 3;
    grid-row: 2;
    justify-self: end;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--warning);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    line-height: 16px;
  }
  .empty {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>
