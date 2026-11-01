<!--
  Demo 7: support matrix. "Live" is measured now, in the engine that opens
  the page (open it in a Tauri dev build on Linux to fill the WebKitGTK gap).
  Chromium and WebKit columns are the recorded runs of the same probes
  (support/recorded.json): headless Chrome 156 and a WKWebView of macOS 26.5
  driven by demos/webkit-probe.swift. The GTK column is read from the WebKit
  sources of each WebKitGTK branch, not tested.

  window.__labSupport() returns the probes and benchmarks as JSON, for the
  recording scripts.
-->
<script lang="ts">
  import { detectEngine } from '../env.svelte';
  import { runBench, type BenchResult } from './bench.svelte';
  import { PROBES, runProbes, type Group, type Probe } from './features';
  import recordedJson from './recorded.json';

  interface Recorded {
    engine: string;
    date: string;
    probes: Record<string, boolean | string>;
    bench: Record<string, number>;
  }
  const recorded = recordedJson as unknown as Partial<Record<'chromium' | 'webkit' | 'webkitOldSdk', Recorded>>;

  const engine = detectEngine();
  let live = $state.raw<Record<string, boolean | string>>({});
  let bench = $state.raw<BenchResult[]>([]);
  let benchRunning = $state(false);
  let selected = $state<string>('popover');

  const GROUPS: Group[] = ['Layout', 'Colour', 'Motion', 'Overlays and forms', 'Input', 'Graphics', 'Workers and scheduling', 'Formatting'];

  async function run(): Promise<void> {
    const r = await runProbes();
    live = Object.fromEntries(r.map((x) => [x.id, x.value]));
  }
  async function runAllBench(): Promise<BenchResult[]> {
    benchRunning = true;
    const r = await runBench((partial) => (bench = partial));
    benchRunning = false;
    return r;
  }

  $effect(() => {
    void run().then(() => setTimeout(() => void runAllBench(), 300));
    (window as unknown as { __labSupport: () => Promise<string> }).__labSupport = async () => {
      const probes = Object.fromEntries((await runProbes()).map((x) => [x.id, x.value]));
      const b = await runAllBench();
      return JSON.stringify({ engine: `${engine.family} ${engine.version}`, ua: navigator.userAgent, probes, bench: Object.fromEntries(b.map((x) => [x.id, x.ms])) });
    };
  });

  function cell(v: boolean | string | undefined): { text: string; tone: 'yes' | 'no' | 'info' | 'na' } {
    if (v === undefined) return { text: '·', tone: 'na' };
    if (v === true) return { text: 'yes', tone: 'yes' };
    if (v === false) return { text: 'no', tone: 'no' };
    if (v.startsWith('error')) return { text: 'err', tone: 'no' };
    return { text: v.length > 7 ? 'info' : v, tone: 'info' };
  }
  function gtk(p: Probe): { text: string; tone: 'yes' | 'no' | 'info' | 'na' } {
    if (!p.gtk) return { text: '·', tone: 'na' };
    const m = /^(\d\.\d+)/.exec(p.gtk);
    if (m) return { text: `${m[1]}+`, tone: 'info' };
    if (p.gtk.startsWith('pretty')) return { text: '2.50+', tone: 'info' };
    return { text: 'off', tone: 'no' };
  }
  const sel = $derived(PROBES.find((p) => p.id === selected));
  const facts = $derived(JSON.stringify({ engine: `${engine.family} ${engine.version}`, probes: Object.keys(live).length, bench: bench.length }));
  const show = (v: boolean | string | undefined) => (v === undefined ? 'not recorded' : v === true ? 'yes' : v === false ? 'no' : v);
</script>

<div class="matrix" data-lab-facts={facts}>
  <div class="features">
    <div class="legend">
      <span class="lab-eyebrow">Columns</span>
      <span><b>Live</b> this engine, now</span>
      <span><b>Cr</b> Chromium 156 (recorded)</span>
      <span><b>WK</b> WebKit, WKWebView of macOS 26.5, app linked on SDK 26 (recorded)</span>
      <span><b>GTK</b> WebKitGTK release where it is on by default (from source); · = not flag-gated, untested on Linux</span>
    </div>
    <div class="groups">
      {#each GROUPS as g (g)}
        <section class="group">
          <h3 class="lab-eyebrow">{g}</h3>
          <table>
            <thead>
              <tr><th></th><th>Live</th><th>Cr</th><th>WK</th><th>GTK</th></tr>
            </thead>
            <tbody>
              {#each PROBES.filter((p) => p.group === g) as p (p.id)}
                {@const l = cell(live[p.id])}
                {@const c = cell(recorded.chromium?.probes[p.id])}
                {@const w = cell(recorded.webkit?.probes[p.id])}
                {@const k = gtk(p)}
                <tr class:sel={selected === p.id} onclick={() => (selected = p.id)}>
                  <td class="name"><button onclick={() => (selected = p.id)}>{p.name}</button></td>
                  <td class="v {l.tone}">{l.text}</td>
                  <td class="v {c.tone}">{c.text}</td>
                  <td class="v {w.tone}">{w.text}</td>
                  <td class="v {k.tone}">{k.text}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </section>
      {/each}
    </div>
  </div>

  <aside class="side">
    {#if sel}
      <section class="card">
        <p class="lab-eyebrow">{sel.group}</p>
        <h3>{sel.name}</h3>
        <p class="use">{sel.use}</p>
        <dl class="num">
          <dt>Live</dt><dd>{show(live[sel.id])}</dd>
          <dt>Chromium</dt><dd>{show(recorded.chromium?.probes[sel.id])}</dd>
          <dt>WebKit</dt><dd>{show(recorded.webkit?.probes[sel.id])}</dd>
          {#if recorded.webkitOldSdk?.probes[sel.id] !== undefined}
            <dt>WebKit, SDK 13.3</dt><dd>{show(recorded.webkitOldSdk?.probes[sel.id])}</dd>
          {/if}
          <dt>WebKitGTK</dt><dd>{sel.gtk ?? 'not flag-gated: follows WebCore (untested)'}</dd>
        </dl>
      </section>
    {/if}
    <section class="card bench">
      <header>
        <p class="lab-eyebrow">Benchmarks · median of 5 · this engine</p>
        <button class="lab-btn" disabled={benchRunning} onclick={() => void runAllBench()}>{benchRunning ? 'Running…' : 'Run again'}</button>
      </header>
      <table class="num">
        <thead><tr><th></th><th>Live</th><th>Cr</th><th>WK</th></tr></thead>
        <tbody>
          {#each bench as b (b.id)}
            <tr>
              <td class="name">{b.label}{#if b.detail}<small> · {b.detail}</small>{/if}</td>
              <td class="ms">{Number.isFinite(b.ms) ? b.ms.toFixed(b.ms < 1 ? 3 : 1) : '—'}</td>
              <td class="ms rec">{recorded.chromium?.bench[b.id]?.toFixed((recorded.chromium?.bench[b.id] ?? 2) < 1 ? 3 : 1) ?? '·'}</td>
              <td class="ms rec">{recorded.webkit?.bench[b.id]?.toFixed((recorded.webkit?.bench[b.id] ?? 2) < 1 ? 3 : 1) ?? '·'}</td>
            </tr>
          {:else}
            <tr><td class="name" colspan="4">Running…</td></tr>
          {/each}
        </tbody>
      </table>
      <p class="note">ms, Apple M2 Pro. Cr: headless Chrome on the Metal GPU. WK: WKWebView on the Apple GPU; WebKit clamps performance.now() to 1 ms, so its small timings read 0, 1, 2 or 3. Not a contest between engines: each line compares approaches inside one engine.</p>
    </section>
  </aside>
</div>

<style>
  .matrix {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 400px;
    height: 100%;
    border-top: var(--border-w) solid var(--border);
  }
  .features {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: auto;
    padding: var(--space-3) var(--space-4);
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1) var(--space-4);
    margin-bottom: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .legend b {
    color: var(--fg);
    font-family: var(--font-mono);
    font-weight: var(--weight-medium);
  }
  .groups {
    columns: 3 300px;
    column-gap: var(--space-5);
  }
  .group {
    break-inside: avoid;
    margin-bottom: var(--space-4);
  }
  h3.lab-eyebrow {
    margin: 0 0 var(--space-1);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-s);
  }
  /* Fixed layout: a long value never pushes the GTK column out of the group. */
  .groups table {
    table-layout: fixed;
  }
  .groups th:not(:first-child) {
    width: 46px;
  }
  th {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    text-align: right;
    padding: 0 0 2px var(--space-2);
  }
  td {
    height: 21px;
    border-top: 1px solid var(--border-soft);
  }
  tr.sel td {
    background: var(--selection-bg);
  }
  tbody tr {
    cursor: pointer;
  }
  tbody tr:hover td {
    background: var(--hover-bg);
  }
  .name button {
    padding: 0;
    border: 0;
    background: none;
    color: var(--fg);
    font-size: var(--text-s);
    text-align: left;
    overflow-wrap: anywhere;
    cursor: pointer;
  }
  .v {
    overflow: hidden;
    padding-left: var(--space-1);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    text-align: right;
    white-space: nowrap;
  }
  .v.yes {
    color: var(--fg);
  }
  .v.no {
    color: var(--text-muted);
  }
  .v.no::before {
    content: '';
    display: inline-block;
    width: 5px;
    height: 5px;
    margin-right: 4px;
    border-radius: var(--radius-round);
    background: var(--status-busy);
    vertical-align: 1px;
  }
  .v.info {
    color: var(--text-muted);
  }
  .v.na {
    color: var(--fg-disabled);
  }

  .side {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-height: 0;
    padding: var(--space-3);
    overflow: auto;
    border-left: var(--border-w) solid var(--border);
  }
  .card {
    padding: var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
  }
  .card h3 {
    margin: 2px 0 var(--space-2);
    font-size: var(--text-l);
  }
  .use {
    margin: 0 0 var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: var(--space-1) var(--space-3);
    margin: 0;
    font-size: var(--text-xs);
  }
  dt {
    color: var(--text-muted);
  }
  dd {
    margin: 0;
    color: var(--fg);
    overflow-wrap: anywhere;
  }
  .bench header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--space-2);
  }
  .bench td {
    height: auto;
    padding: 3px 0;
    vertical-align: top;
  }
  .bench .name {
    font-family: var(--font-ui);
    font-size: var(--text-xs);
    color: var(--fg);
  }
  .bench small {
    color: var(--text-muted);
  }
  .ms {
    width: 52px;
    text-align: right;
    font-size: var(--text-xs);
    color: var(--fg);
  }
  .ms.rec {
    color: var(--text-muted);
  }
  .note {
    margin: var(--space-2) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
