<!--
  Photometry rail card (D8, D10, 03 2.3 W6, M8 live parts; promoted from
  src/lab/workspace/observe/cards/PhotometryCard.svelte). The dissolved Qt "Field
  photometry" window's acquisition side, next to the image it acts on:

  - the target set (TargetSetList: roles as shapes, AUIDs, Remove with Undo, the
    comparisons folded into one row);
  - the readouts: the target's newest differential magnitude ± error (band named), the
    check star's scatter over its trailing 15 points and its mean offset from catalogue V
    (D10), the comparisons in the set and used on the newest point, the effective
    geometry in green px with where the FWHM comes from (08 1.7 #9, P36);
  - the ensemble verdict in Qt's words with "n of m stable" (never a tick that reads as
    "calibrated"), and the live status in one line;
  - actions: Recommend… (A58), and the drawer's Light curve, Variables and Ensemble tabs.

  Folded, the header says target · comparisons · verdict (W6).
-->
<script lang="ts">
  import Card from '../../components/Card.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import NumText from '../../components/NumText.svelte';
  import Readouts, { type ReadoutItem } from '../../components/Readouts.svelte';
  import StatusBadge from '../../components/StatusBadge.svelte';
  import { fixed, mag } from '../../format/number';
  import type { TargetStar } from '../field/types';
  import { catalogV, comparisonSplit, curveFor, entryFor, latestMag, measuredCount, minPoints, offsetText, statusLabel, trailingStats, verdict as verdictOf, type StatusLine } from './present';
  import RecommendPopover from './RecommendPopover.svelte';
  import TargetSetList from './TargetSetList.svelte';
  import type { Curve, PhotGeometry, QualityReport, RecommendMode } from './types';

  interface Props {
    open?: boolean;
    stars: readonly TargetStar[];
    curves: readonly Curve[];
    report: QualityReport | null;
    /** The live status line (statusLine). */
    line: StatusLine;
    /** Say the live status here (false while the Field band says it: once on screen). */
    showLine?: boolean;
    geometry: PhotGeometry | null;
    /** The series FWHM the apertures use (green px), from the live snapshot. */
    seriesFwhm?: number | null;
    band?: string | null;
    hotKey?: string | null;
    removeReason?: string | null;
    removing?: string | null;
    recommend: {
      count: number;
      gate: { snr: number | null; dmag: number | null; sepArcmin: number | null };
      reason: string | null;
      running: boolean;
      busy: RecommendMode | null;
    };
    /** The drawer tab on screen (its button is pressed). */
    drawerTab?: string | null;
    onrecommend: (mode: RecommendMode, count: number) => Promise<unknown> | void;
    onremove?: (s: TargetStar) => void;
    onhover?: (s: TargetStar | null) => void;
    onpick?: (s: TargetStar) => void;
    ondrawer?: (tab: 'light-curve' | 'variables' | 'ensemble') => void;
  }

  let {
    open = $bindable(true),
    stars,
    curves,
    report,
    line,
    showLine = true,
    geometry,
    seriesFwhm = null,
    band = null,
    hotKey = null,
    removeReason = null,
    removing = null,
    recommend,
    drawerTab = null,
    onrecommend,
    onremove,
    onhover,
    onpick,
    ondrawer,
  }: Props = $props();

  const target = $derived(stars.find((s) => s.role === 'target') ?? null);
  const check = $derived(stars.find((s) => s.role === 'check') ?? null);
  const tCurve = $derived(target ? curveFor(curves, target) : null);
  const cCurve = $derived(check ? curveFor(curves, check) : null);
  const tLast = $derived(latestMag(tCurve));
  const cV = $derived(check ? catalogV(check, cCurve) : null);
  const cStats = $derived(trailingStats(cCurve, cV ?? 0));
  const split = $derived(comparisonSplit(stars));
  /** Calibrated comparisons (a band or V magnitude) and VSP picks: the Recommend buttons' numbers. */
  const calibrated = $derived(stars.filter((s) => s.role === 'comparison' && Object.values(s.mags ?? {}).some((m) => typeof m === 'number')).length);
  const vspN = $derived(stars.filter((s) => s.role === 'comparison' && (s.source === 'vsp' || s.source === 'vsp_auto')).length);
  const v = $derived(verdictOf(report));
  const min = $derived(minPoints(report));
  const nameOf = (s: TargetStar | null) => (s ? s.display_name || s.name || s.auid || s.key : '');
  const bandText = $derived(band || 'TG');

  const fwhm = $derived(seriesFwhm ?? geometry?.fwhm_px ?? null);
  const fwhmSource = $derived(seriesFwhm !== null ? 'series' : geometry?.fwhm_source === 'frame' ? 'frame' : 'default');
  const vspText = $derived(split.text.includes('(') ? split.text.slice(split.text.indexOf('(') + 1, -1) : '');
  // Readout keys are set in capitals by Readouts: no σ there (it would read Σ). The unit sits
  // in the key, so a value that gains a digit never reflows the grid.
  const items = $derived.by((): ReadoutItem[] => [
    {
      k: `Target · ${bandText} · mag`,
      v: tLast ? mag(tLast.mag, tLast.mag_err) : '—',
      note: tLast ? `newest point · frame #${tLast.frame_seq ?? '—'}` : 'no point yet',
      key: true,
    },
    {
      k: 'Check scatter · mag',
      // σ to 3 decimals, as the plot's readout (one precision per quantity).
      v: check && cStats.sd !== null ? fixed(cStats.sd, 3) : '—',
      note: !check ? 'no check star' : cStats.n ? `last ${cStats.n} · check − V ${offsetText(cStats.mean)}` : 'no point yet',
      key: true,
    },
    {
      k: 'Comparisons',
      // Used in the newest zero point / in the set (the lab's "Comps used 4 / 7").
      v: tLast ? `${tLast.comps_used} / ${split.n}` : String(split.n),
      note: split.n ? `${tLast ? 'in the newest zero point' : 'in the set'}${vspText ? ` · ${vspText}` : ''}` : 'none: Recommend, or a role on the image',
      flag: split.n === 0 ? 'none' : tLast && tLast.comps_used < 2 ? 'low' : undefined,
    },
    {
      k: 'Aperture',
      v: geometry?.aperture_px != null ? `${fixed(geometry.aperture_px, 1)} px` : '—',
      unit: geometry?.aperture_px != null ? 'green' : undefined,
      note:
        geometry?.annulus_in_px != null && geometry?.annulus_out_px != null
          ? `sky ${fixed(geometry.annulus_in_px, 1)}–${fixed(geometry.annulus_out_px, 1)} · FWHM ${fwhm === null ? '—' : fixed(fwhm, 1)} (${fwhmSource})`
          : undefined,
    },
  ]);

  const badge = $derived.by((): { tone: 'idle' | 'ok' | 'busy' | 'error'; label: string } => {
    if (!target) return { tone: 'idle', label: 'No target' };
    if (!v) return { tone: 'idle', label: measuredCount(tCurve) ? 'Measuring' : 'Waiting' };
    if (v.tone === 'ok') return { tone: 'ok', label: 'Consistent' };
    if (v.tone === 'warn') return { tone: 'busy', label: 'Not ready' };
    const n = Math.min(...(report?.comparison_stars ?? []).map((e) => e.n_valid ?? 0), measuredCount(tCurve));
    return { tone: 'idle', label: `Waiting · ${Number.isFinite(n) ? n : 0} of ${min} pts` };
  });

  /**
   * The right of a set row: a comparison's status. The target's value and the check's
   * scatter are in the readouts below (never twice on screen).
   */
  function rowValue(s: TargetStar): string | null {
    if (s.role === 'target' || s.role === 'check') return null;
    const e = entryFor(report, s);
    if (!e) return null;
    return e.status === 'insufficient_data' ? `${e.n_valid} of ${min} pts` : statusLabel(e.status, min);
  }
</script>

<Card title="Photometry" icon="photometry" collapsible bind:open>
  {#snippet status()}
    <StatusBadge tone={badge.tone} label={badge.label} plain live={false} />
  {/snippet}
  {#snippet summary()}
    {#if target}{nameOf(target)} · {split.n} comp{split.n === 1 ? '' : 's'}{check ? ' · check' : ''}{v?.counts ? ` · ${v.counts}` : ''}{:else}No target{/if}
  {/snippet}
  <div class="phot">
    <TargetSetList
      {stars}
      value={rowValue}
      {hotKey}
      foldComparisons
      {removeReason}
      {removing}
      {onremove}
      {onhover}
      {onpick}
    />
    {#if target}
      <Readouts {items} cols={2} />
    {/if}
    {#if target}
      <p class="verdict" class:ok={v?.tone === 'ok'} class:warn={v?.tone === 'warn'} title={v?.line ?? undefined}>
        <span class="k">Ensemble</span>
        <span class="w"><NumText text={v ? `${v.counts ? `${v.counts} · ` : ''}${v.words}` : `waiting for ${min} points per comparison`} /></span>
      </p>
    {/if}
    {#if showLine && target}<p class="live {line.tone}" title={line.text}><NumText text={line.text} /></p>{/if}
    <div class="actions">
      <RecommendPopover count={recommend.count} gate={recommend.gate} reason={recommend.reason} running={recommend.running} busy={recommend.busy} inSet={calibrated} vspPicks={vspN} {onrecommend} />
      <span class="grow"></span>
      <IconButton icon="light-curve" label="Light curve (drawer)" size="s" variant="ghost" layoutToggle pressed={drawerTab === 'light-curve'} onclick={() => ondrawer?.('light-curve')} />
      <IconButton icon="variable-star" label="Variables of the field (drawer)" size="s" variant="ghost" layoutToggle pressed={drawerTab === 'variables'} onclick={() => ondrawer?.('variables')} />
      <IconButton icon="comparison-quality" label="Ensemble (drawer)" size="s" variant="ghost" layoutToggle pressed={drawerTab === 'ensemble'} onclick={() => ondrawer?.('ensemble')} />
    </div>
  </div>
</Card>

<style>
  .phot {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  p {
    margin: 0;
    font-size: var(--text-s);
  }
  .verdict {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    color: var(--fg);
  }
  .verdict .k {
    color: var(--text-muted);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  /* Wraps rather than cut the verdict's word. */
  .verdict .w {
    min-width: 0;
  }
  .live {
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .live.warn {
    color: var(--fg);
  }
  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-1);
  }
  .grow {
    flex: 1;
  }
</style>
