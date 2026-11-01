<!--
  The same Conditions content in a 420-580 px rail and in a 1000 px drawer:
  @container rules on the nearest size container (LabCard or the drawer
  pane) switch it from rows (label | sparkline | value) to a strip of tiles.
  No JavaScript measures anything; no prop says "compact".
-->
<script lang="ts" module>
  export interface Metric {
    id: string;
    label: string;
    unit: string;
    values: number[];
    digits: number;
    tone?: '--fg-muted' | '--chart-1' | '--chart-2' | '--chart-3';
  }
</script>

<script lang="ts">
  import Sparkline from '../frame/Sparkline.svelte';

  let { metrics }: { metrics: Metric[] } = $props();
  const last = (m: Metric) => m.values[m.values.length - 1];
  const range = (m: Metric) => {
    const lo = Math.min(...m.values);
    const hi = Math.max(...m.values);
    return `${lo.toFixed(m.digits)}–${hi.toFixed(m.digits)}`;
  };
</script>

<div class="conditions">
  {#each metrics as m (m.id)}
    <div class="metric">
      <span class="label">{m.label}</span>
      <span class="spark"><Sparkline values={m.values} label="{m.label}, last {m.values.length} frames" tone={m.tone} /></span>
      <span class="value num">{last(m).toFixed(m.digits)}<small> {m.unit}</small></span>
      <span class="range num">{range(m)}</span>
    </div>
  {/each}
</div>

<style>
  .conditions {
    display: grid;
    gap: var(--space-2);
  }
  .metric {
    display: grid;
    grid-template-columns: 64px minmax(0, 1fr) 84px;
    align-items: center;
    gap: var(--space-3);
  }
  .label {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .value {
    color: var(--fg);
    font-size: var(--text-s);
    text-align: right;
  }
  .value small {
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }
  .range {
    display: none;
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }

  /* Wide (drawer): a strip of tiles, sparkline under a big readout. */
  @container (min-width: 720px) {
    .conditions {
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: var(--space-3);
    }
    .metric {
      grid-template-columns: 1fr auto;
      grid-template-areas:
        'label value'
        'spark spark'
        'range range';
      gap: var(--space-1) var(--space-3);
      padding: var(--space-3);
      border: var(--border-w) solid var(--border-soft);
      border-radius: var(--radius-m);
    }
    .label {
      grid-area: label;
      align-self: end;
    }
    .value {
      grid-area: value;
      font-size: var(--text-xl);
    }
    .spark {
      grid-area: spark;
    }
    .range {
      grid-area: range;
      display: block;
    }
  }
</style>
