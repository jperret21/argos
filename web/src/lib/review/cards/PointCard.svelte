<!--
  Rail card "Selected point" (spec 07 §2.4 "Selection model", E7 point row; 08 1.10 #23-#24;
  fixes 07 P7: one place for every plot). The wall's selected time: every star at that time
  as its cell draws it, the target's details (UTC, JD and BJD_TDB to 5 decimals, formal
  error, σ_sys, comparisons, airmass, flags), the frame it was measured on (Δt from the
  frame's start: the point is dated at mid-exposure; its FWHM, HFD, sky) and Open frame
  (Enter), disabled with its reason when the FITS is missing (07 1.9 #5).
-->
<script lang="ts">
  import Card from '../../components/Card.svelte';
  import Control from '../../components/Control.svelte';
  import CurveKey from '../../charts/lightcurve/CurveKey.svelte';
  import { FACET_SHAPE } from '../../charts/lightcurve/facets';
  import { DASH, fixed, int, signed } from '../../format/number';
  import { tooltip } from '../../components/tooltip';
  import type { PointInfo } from '../rail';

  interface Props {
    info: PointInfo | null;
    /** The airmass's source in words (RR Lyr 2026-09-25: the Settings site was wrong, the CSV's is wrong). */
    airmassNote?: string | null;
    onopenframe?: (info: PointInfo) => void;
    /** A star row was pressed: show its cell. */
    onstar?: (cellId: string) => void;
    /** Clear the selection. */
    onclear?: () => void;
  }
  let { info, airmassNote = null, onopenframe, onstar, onclear }: Props = $props();

  const TOKEN = { target: '--chart-1', check: '--chart-3', comparison: '--chart-2' } as const;
</script>

<Card title="Selected point" icon="crosshair" collapsible persist="review.point">
  {#snippet status()}
    {#if info}
      <Control icon="close" label="Clear the selection" size="xs" variant="ghost" tooltip="bottom" onclick={() => onclear?.()} />
    {/if}
  {/snippet}
  {#if info}
    <dl class="kv num">
      <dt>UTC</dt><dd>{info.utc}</dd>
      <dt>JD</dt><dd>{info.jd}</dd>
      <dt>BJD<sub>TDB</sub></dt><dd>{info.bjd ?? '— (no site)'}</dd>
    </dl>
    {#snippet starRow(s: PointInfo['stars'][number])}
      <li>
        <button type="button" class="srow" onclick={() => onstar?.(s.cellId)} title="Show its plot">
          <CurveKey shape={FACET_SHAPE[s.role]} color="var({TOKEN[s.role]})" variant={s.flags.includes('saturated') ? 'cross' : s.flags.includes('suspect') ? 'hollow' : 'filled'} size={11} />
          <span class="name">{s.name}</span>
          <b class="num">{s.value}</b>
        </button>
      </li>
    {/snippet}
    <!-- The target and check here; the comparisons fold (their cells show them): the card
         stays short enough for the AAVSO card to sit in the first screen (design review). -->
    <ul class="stars" aria-label="Target and check at this time">
      {#each info.stars.filter((s) => s.role !== 'comparison') as s (s.cellId)}{@render starRow(s)}{/each}
    </ul>
    {#if info.stars.some((s) => s.role === 'comparison')}
      <details class="comps">
        <summary>{info.stars.filter((s) => s.role === 'comparison').length} comparisons</summary>
        <ul class="stars" aria-label="Comparisons at this time">
          {#each info.stars.filter((s) => s.role === 'comparison') as s (s.cellId)}{@render starRow(s)}{/each}
        </ul>
      </details>
    {/if}
    <dl class="kv num">
      <dt>formal · σ<sub>sys</sub></dt><dd>{info.formal ?? DASH} · {info.syst ?? DASH}</dd>
      <dt>comparisons</dt><dd>{info.comps ?? DASH}</dd>
      <dt>airmass</dt>
      <dd>
        {info.airmass ?? DASH}{#if info.airmassFrom}<span class="note" use:tooltip={{ text: airmassNote ?? '' }}>{info.airmassFrom === 'header' ? 'header' : 'CSV'}</span>{/if}{#if info.airmassOther}<span class="note" use:tooltip={{ text: airmassNote ?? '' }}>· {info.airmassFrom === 'header' ? 'CSV' : 'header'} {info.airmassOther}</span>{/if}
      </dd>
      <dt>flags</dt><dd>{info.flags}</dd>
    </dl>
    {#if info.frame}
      <p class="file num" title={info.frame.filename}>{info.frame.filename}</p>
      <dl class="kv num">
        <dt>Δt</dt><dd>{info.dt !== null ? `${signed(info.dt, 1)} s from the start` : DASH}</dd>
        <dt>FWHM · HFD</dt><dd>{fixed(info.frame.fwhm, 2)} · {fixed(info.frame.hfd, 2)} px</dd>
        <dt>sky</dt><dd>{int(info.frame.sky_adu)} ADU</dd>
      </dl>
    {/if}
    <div class="act">
      <Control icon="open-image" label="Open frame" showLabel size="s" shortcut="Enter" disabledReason={info.frameReason} onclick={() => info && onopenframe?.(info)} />
    </div>
  {:else}
    <p class="empty">Click a point on any plot to read every star at that time. ← → step frame by frame, Enter opens the frame.</p>
  {/if}
</Card>

<style>
  .kv {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px var(--space-3);
    margin: 0;
    font-size: var(--text-xs);
  }
  .kv dt {
    color: var(--text-muted);
    font-family: var(--font-ui);
  }
  .kv dd {
    margin: 0;
    text-align: right;
    color: var(--fg);
  }
  .note {
    margin-left: 4px;
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }
  .stars {
    display: grid;
    gap: 1px;
    margin: var(--space-2) 0;
    padding: var(--space-1) 0;
    list-style: none;
    border-top: var(--border-w) solid var(--border-soft);
    border-bottom: var(--border-w) solid var(--border-soft);
    max-height: 196px;
    overflow-y: auto;
  }
  .comps summary {
    color: var(--text-muted);
    font-size: var(--text-xs);
    cursor: pointer;
  }
  .comps .stars {
    margin-top: var(--space-1);
  }
  .srow {
    display: grid;
    grid-template-columns: 14px minmax(0, 1fr) auto;
    align-items: center;
    gap: 6px;
    width: 100%;
    height: 22px;
    padding: 0 var(--space-1);
    border: 0;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-align: left;
    cursor: pointer;
  }
  .srow:hover {
    background: var(--hover-bg);
  }
  .srow:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .srow b {
    color: var(--fg);
    font-weight: var(--weight-regular);
  }
  .file {
    margin: var(--space-2) 0 var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .act {
    margin-top: var(--space-2);
  }
  .empty {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
    line-height: var(--leading-relaxed);
  }
</style>
