<!--
  Field band: choosing comparisons is a comparison BETWEEN stars, so it is a
  table linked to the image (functional-spaces P5). Columns follow the
  guide's rules: V, B−V and Δ(B−V) against the target (keep within 0.3 mag),
  separation (within 25′), the peak measured on the frame on screen
  ("clipped" at 65 535, never "saturated"), SNR, Nbr = catalogue stars
  inside the 31″ aperture brighter than V + 3 (blend risk), and the live
  status. Hover a row: its star is ringed on the image; click: Inspector.
  Sorting re-orders rows with a 120 ms flip (orientation only; zero under
  reduced motion); values never animate.
-->
<script lang="ts">
  import { flip } from 'svelte/animate';
  import { reducedMotion } from '../../model/env.svelte';
  import { sim, ws } from '../../model/app.svelte';
  import { APERTURE_PX, NAMED_STARS, neighboursInAperture, sepArcmin, TARGET_PX, type Star } from '../../model/field';
  import { fixed, int, signed } from '../../model/format';
  import { shapePath } from '../../charts/plugins';

  interface Props {
    compact: boolean;
  }
  let { compact }: Props = $props();

  type Key = 'role' | 'name' | 'v' | 'bv' | 'dbv' | 'sep' | 'peak' | 'snr' | 'nbr' | 'status';
  const COLS: { key: Key; label: string; num: boolean; title: string }[] = [
    { key: 'role', label: 'Role', num: false, title: 'Role in the set (shape as on the image)' },
    { key: 'name', label: 'Star', num: false, title: 'VSP label (synthetic: 000-LAB-…)' },
    { key: 'v', label: 'V', num: true, title: 'V magnitude (VSP)' },
    { key: 'bv', label: 'B−V', num: true, title: 'Colour index (VSP)' },
    { key: 'dbv', label: 'Δ(B−V)', num: true, title: 'Colour difference with the target (keep within 0.3 mag)' },
    { key: 'sep', label: 'Sep ′', num: true, title: 'Separation from the target, arcmin (keep within 25′)' },
    { key: 'peak', label: 'Peak ADU', num: true, title: 'Brightest pixel on the frame on screen (full scale 65 535)' },
    { key: 'snr', label: 'SNR', num: true, title: 'Signal-to-noise in the aperture' },
    { key: 'nbr', label: 'Nbr', num: true, title: 'Catalogue stars inside the aperture brighter than V + 3 (blend risk)' },
    { key: 'status', label: 'Status', num: false, title: 'Leave-one-out check (needs 10 points)' },
  ];

  const target = NAMED_STARS.find((s) => s.role === 'target')!;
  let sortKey: Key = $state('dbv');
  let asc = $state(true);
  let tab: 'candidates' | 'ensemble' = $state('candidates');

  interface Row {
    s: Star;
    role: string;
    v: number;
    bv: number;
    dbv: number;
    sep: number;
    peak: number;
    snr: number;
    nbr: number;
    status: string;
    flag: boolean;
  }

  const rows: Row[] = $derived.by(() => {
    const out: Row[] = NAMED_STARS.filter((s) => s.role !== 'target').map((s) => {
      const peak = sim.measured.peaks[s.id] ?? NaN;
      const nbr = neighboursInAperture(s, APERTURE_PX).length;
      const dbv = (s.bv ?? NaN) - (target.bv ?? NaN);
      const clipped = peak >= 65535;
      const status = clipped ? 'clipped' : nbr > 0 ? 'blend risk' : s.role === 'comparison' ? 'waiting 7/10' : s.role === 'check' ? 'check' : '—';
      return {
        s,
        role: s.role ?? '',
        v: s.v,
        bv: s.bv ?? NaN,
        dbv,
        sep: sepArcmin(s, TARGET_PX),
        peak,
        snr: clipped ? NaN : 410 * Math.pow(10, -0.2 * (s.v - 7.95)),
        nbr,
        status,
        flag: clipped || nbr > 0 || Math.abs(dbv) > 0.3,
      };
    });
    return out.filter((r) => tab === 'candidates' || r.role === 'comparison' || r.role === 'check');
  });

  const sorted = $derived.by(() => {
    const k = sortKey;
    const dir = asc ? 1 : -1;
    const val = (r: Row) => (k === 'dbv' ? Math.abs(r.dbv) : k === 'name' ? (r.s.name ?? '') : k === 'role' ? r.role || 'z' : r[k]);
    return [...rows].sort((a, b) => {
      const x = val(a);
      const y = val(b);
      if (typeof x === 'string' || typeof y === 'string') return String(x).localeCompare(String(y)) * dir;
      if (!Number.isFinite(x)) return 1;
      if (!Number.isFinite(y)) return -1;
      return (x - y) * dir;
    });
  });

  function sortBy(k: Key): void {
    if (sortKey === k) asc = !asc;
    else {
      sortKey = k;
      asc = true;
    }
  }

  const ensembleCount = NAMED_STARS.filter((s) => s.role === 'comparison').length;
  const dur = $derived(reducedMotion() ? 0 : 120);
</script>

{#if compact}
  <div class="row-compact">
    <span class="k">ENSEMBLE</span><span class="num">{ensembleCount} of 5 aimed · check 000-LAB-523</span>
  </div>
{:else}
  <div class="wrap">
    <div class="tabs" role="tablist" aria-label="Field lists">
      <button type="button" role="tab" aria-selected={tab === 'candidates'} class:on={tab === 'candidates'} onclick={() => (tab = 'candidates')}>
        Candidates <span class="n num">{NAMED_STARS.length - 1}</span>
      </button>
      <button type="button" role="tab" aria-selected={tab === 'ensemble'} class:on={tab === 'ensemble'} onclick={() => (tab = 'ensemble')}>
        Ensemble <span class="n num">{ensembleCount + 1}</span>
      </button>
      <span class="note">Target RR Lyr · B−V {fixed(target.bv ?? NaN, 2)} · aperture {APERTURE_PX} px (31″) · rows flagged when Δ(B−V) &gt; 0.3, clipped or blended</span>
    </div>
    <div class="scroll">
      <table>
        <thead>
          <tr>
            {#each COLS as c (c.key)}
              <th class:num={c.num} aria-sort={sortKey === c.key ? (asc ? 'ascending' : 'descending') : 'none'}>
                <button type="button" onclick={() => sortBy(c.key)} aria-label="{c.label}: {c.title}">
                  {c.label}{#if sortKey === c.key}<svg class="arrow" class:up={asc} viewBox="0 0 10 10" aria-hidden="true"><path d="M2.5 3.75 5 6.25 7.5 3.75" /></svg>{/if}
                </button>
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each sorted as r (r.s.id)}
            <tr
              animate:flip={{ duration: dur }}
              class:hov={ws.hovered === r.s.id}
              class:sel={ws.selected === r.s.id}
              class:flag={r.flag}
              onmouseenter={() => (ws.hovered = r.s.id)}
              onmouseleave={() => (ws.hovered = null)}
              onclick={() => ws.select(r.s.id)}
            >
              <td class="role">
                {#if r.role}
                  <svg viewBox="0 0 20 20" class={r.role} aria-label={r.role}><path d={shapePath(r.role === 'check' ? 'triangle' : 'square')} /></svg>
                {:else}
                  <svg viewBox="0 0 20 20" class="cand" aria-label="candidate"><path d={shapePath('square')} /></svg>
                {/if}
              </td>
              <td class="name">{r.s.name}</td>
              <td class="num">{fixed(r.v, 2)}</td>
              <td class="num">{fixed(r.bv, 2)}</td>
              <td class="num" class:warn={Math.abs(r.dbv) > 0.3}>{signed(r.dbv, 2)}</td>
              <td class="num">{fixed(r.sep, 1)}</td>
              <td class="num">{r.peak >= 65535 ? 'clipped' : int(r.peak)}</td>
              <td class="num">{Number.isFinite(r.snr) ? int(r.snr) : '—'}</td>
              <td class="num" class:warn={r.nbr > 0}>{r.nbr}</td>
              <td class="status">{r.status}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
{/if}

<style>
  .wrap {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  .tabs {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    height: 30px;
    padding: 0 var(--space-2);
    flex: none;
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .tabs button {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 24px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-s);
    cursor: pointer;
  }
  .tabs button.on {
    background: var(--toggled-bg);
    border-color: var(--border);
    color: var(--fg);
  }
  .n {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .note {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .scroll {
    flex: 1;
    min-height: 0;
    overflow: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-s);
  }
  th {
    position: sticky;
    top: 0;
    z-index: 1;
    height: 26px;
    padding: 0;
    border-bottom: var(--border-w) solid var(--border-soft);
    background: var(--bg);
    text-align: left;
  }
  th button {
    width: 100%;
    height: 100%;
    padding: 0 var(--space-3);
    border: none;
    background: transparent;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-align: inherit;
    text-transform: uppercase;
    cursor: pointer;
  }
  th button:hover {
    color: var(--fg);
  }
  th.num {
    text-align: right;
  }
  th[aria-sort='ascending'] button,
  th[aria-sort='descending'] button {
    color: var(--fg);
  }
  .arrow {
    width: 10px;
    height: 10px;
    margin-left: 2px;
    vertical-align: -1px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.25;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .arrow.up {
    transform: rotate(180deg);
  }
  td {
    height: var(--lab-row-h);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg);
    white-space: nowrap;
  }
  td.num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
    text-align: right;
  }
  td.name {
    font-family: var(--font-mono);
  }
  td.status {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  td.warn {
    text-decoration: underline;
    text-decoration-color: var(--warning);
    text-decoration-thickness: 2px;
    text-underline-offset: 3px;
  }
  tr {
    cursor: pointer;
  }
  tbody tr:hover,
  tr.hov {
    background: var(--hover-bg);
  }
  tr.sel {
    background: var(--selection-bg);
  }
  tr.flag td.status {
    color: var(--fg);
  }
  .role svg {
    width: 14px;
    height: 14px;
    display: block;
  }
  .role path {
    fill: none;
    stroke-width: 1.6;
  }
  .comparison path {
    stroke: var(--role-comparison);
  }
  .check path {
    stroke: var(--role-check);
  }
  .cand path {
    stroke: var(--overlay-other);
    stroke-dasharray: 2 2;
  }
  .row-compact {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 100%;
    padding: 0 var(--space-3);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
  }
</style>
