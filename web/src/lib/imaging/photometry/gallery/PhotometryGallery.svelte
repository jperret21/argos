<!--
  Component gallery, wave 5, live photometry (development only, part of /?gallery=1): the
  Photometry card, TargetSetList, the Ensemble table, the Variables tab, the Light curve tab,
  the Recommend popover and the live status, each in its states, on deterministic synthetic
  data (fixtures.ts). Sections are [data-gallery="w5-<name>"] for element screenshots.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import type { Theme } from '../../../app/theme';
  import LightCurvePlot from '../../../charts/lightcurve/LightCurvePlot.svelte';
  import { LiveCurveStore, type LiveSnapshot as CurveSnapshot } from '../../../charts/lightcurve/store';
  import { formatDec, formatRA } from '../../../format/astro';
  import EnsembleTable from '../EnsembleTable.svelte';
  import EnsembleVerdict from '../EnsembleVerdict.svelte';
  import LightCurveTab from '../LightCurveTab.svelte';
  import LiveStatus from '../LiveStatus.svelte';
  import PhotometryCard from '../PhotometryCard.svelte';
  import { countLine, ensembleRows, ensembleTsv, minPoints, statusLine, verdict } from '../present';
  import RecommendPopover from '../RecommendPopover.svelte';
  import TargetSetList from '../TargetSetList.svelte';
  import VariablesTab from '../VariablesTab.svelte';
  import { curves, GEOMETRY, REPORT_NOT_READY, REPORT_OK, REPORT_WAITING, STARS, STATUS_MEASURED, STATUS_SKIPPED, VARIABLES } from './fixtures';

  let theme = $state<Theme>('observatory');
  onMount(() => {
    const read = () => (theme = (document.documentElement.dataset.theme as Theme) || 'observatory');
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  });

  const noop = () => undefined;
  const C40 = curves(40);
  const C6 = curves(6);
  const flagsOf = (s: { key: string }) => (s.key === 'auid:000-BCG-702' ? ['variable?'] : s.key === 'auid:000-BCG-661' ? ['Δ(B−V) > 0.3'] : []);
  const base = { connected: true, solved: true, hasTarget: true, comparisons: 5 };
  const lineOk = statusLine({ ...base, status: STATUS_MEASURED, points: 40 });
  const lineFew = statusLine({ ...base, status: STATUS_MEASURED, points: 6 });
  const lineSkipped = statusLine({ ...base, status: STATUS_SKIPPED, points: 6 });
  const lineNoTarget = statusLine({ ...base, status: null, hasTarget: false, points: 0 });
  const lineUnsolved = statusLine({ ...base, status: null, solved: false, points: 0 });
  const lineNoComp = statusLine({ ...base, status: null, comparisons: 0, points: 0 });
  const recommend = { count: 5, gate: { snr: 10, dmag: 1.5, sepArcmin: 25 }, reason: null, running: false, busy: null };
  const rowsOk = ensembleRows(STARS, REPORT_OK, { flagsOf, lastJd: REPORT_OK.comparison_stars[0].last?.jd_utc ?? null });
  const rowsWaiting = ensembleRows(STARS, REPORT_WAITING, { flagsOf });

  const store = new LiveCurveStore();
  store.load({ object_name: 'XX Cyg', object: 'XX Cyg', band: 'TG', revision: 1, seq: 280, curves: C40.map((c) => ({ ...c, auid: c.auid ?? undefined })) } as unknown as CurveSnapshot);
  store.applyTargets(STARS.map((s) => ({ ...s, auid: s.auid ?? undefined, mags: s.mags as Record<string, number | null> })), 'TG');
  const clock = () => (2461282.395 + 41 * (30 / 86400) - 2440587.5) * 86400;
  const tsv = ensembleTsv(rowsOk, { ra: formatRA, dec: (d) => formatDec(d) });
</script>

<section data-gallery="w5-card" id="w5-card">
  <h2>Photometry card <span>the set as shapes (comparisons folded), the target's newest Δmag ± error, check σ over 15 points and its offset from V (D10), the verdict in Qt's words (never "calibrated"), the live status</span></h2>
  <div class="row top">
    <figure class="rail"><PhotometryCard stars={STARS} curves={C40} report={REPORT_OK} line={lineOk} geometry={GEOMETRY} seriesFwhm={3.1} band="TG" {recommend} onrecommend={noop} onremove={noop} /><figcaption>measuring, consistent (4 of 5 stable is the ensemble's, not a certification)</figcaption></figure>
    <figure class="rail"><PhotometryCard stars={STARS} curves={C6} report={REPORT_WAITING} line={lineFew} geometry={GEOMETRY} band="TG" {recommend} onrecommend={noop} onremove={noop} hotKey="auid:000-BCG-688" /><figcaption>first points: waiting for 10, check hovered on the image</figcaption></figure>
    <figure class="rail"><PhotometryCard stars={STARS} curves={C40} report={REPORT_NOT_READY} line={lineSkipped} geometry={GEOMETRY} band="TG" {recommend} onrecommend={noop} onremove={noop} drawerTab="ensemble" /><figcaption>not ready; last frame skipped (the server's words)</figcaption></figure>
    <figure class="rail"><PhotometryCard stars={[]} curves={[]} report={null} line={lineNoTarget} geometry={null} recommend={{ ...recommend, reason: 'choose a target star first' }} onrecommend={noop} /><figcaption>no target</figcaption></figure>
  </div>
</section>

<section data-gallery="w5-set" id="w5-set">
  <h2>TargetSetList <span>one view of the set (D24): shape, name, AUID when it differs, a value, Remove (hover or focus; Delete) with Undo; rows ring their star on the image</span></h2>
  <div class="row top">
    <figure class="list"><TargetSetList stars={STARS} value={(s) => (s.role === 'target' ? '11.482 ± 0.012' : null)} onremove={noop} /><figcaption>expanded (Plan card)</figcaption></figure>
    <figure class="list"><TargetSetList stars={STARS} foldComparisons onremove={noop} removing="auid:000-BBC-123" /><figcaption>comparisons folded (rail), a removal in progress</figcaption></figure>
    <figure class="list"><TargetSetList stars={STARS.slice(0, 2)} onremove={noop} removeReason="the sequence owns the target set" hotKey="auid:000-BCG-653" /><figcaption>Remove unavailable (reason), hovered from the image</figcaption></figure>
    <figure class="list"><TargetSetList stars={[]} /><figcaption>empty</figcaption></figure>
  </div>
</section>

<section data-gallery="w5-ensemble" id="w5-ensemble">
  <h2>Ensemble (drawer tab) <span>verdict + scientific note verbatim; per comparison: Qt's status, samples, scatter and formal error (4 decimals), newest leave-one-out mag and its residual from V, the field's flags in words; check last; Qt's count line</span></h2>
  <div class="row top">
    <figure class="wide"><div class="drawer-demo"><EnsembleTable rows={rowsOk} verdict={verdict(REPORT_OK)} minPoints={minPoints(REPORT_OK)} countText={countLine(STARS)} onremove={noop} hotKey="auid:000-BCG-670" /></div><figcaption>consistent; a VSX-listed comparison stays eligible, flagged "variable?" (owner decision 2), and is unstable here</figcaption></figure>
    <figure class="wide"><div class="drawer-demo"><EnsembleTable rows={rowsWaiting} verdict={verdict(REPORT_WAITING)} minPoints={10} countText={countLine(STARS)} onremove={noop} removing="auid:000-BCG-653" /></div><figcaption>waiting for 10 points</figcaption></figure>
    <figure class="wide"><div class="drawer-demo short"><EnsembleTable rows={[]} verdict={null} minPoints={10} countText={countLine([])} /></div><figcaption>no comparison</figcaption></figure>
  </div>
  <details class="tsv"><summary>Copy TSV (Qt's columns first)</summary><pre>{tsv}</pre></details>
</section>

<section data-gallery="w5-variables" id="w5-variables">
  <h2>Variables (drawer tab) <span>Qt's filter (normalised designation or type, brightest mag), "n of N stars", role as its shape, suspected muted; the filter also filters the image's variable markers (D7)</span></h2>
  <div class="row top">
    <figure class="wide"><div class="drawer-demo"><VariablesTab rows={VARIABLES} query="" magLimit={null} ontarget={noop} /></div><figcaption>every variable (catalogue order)</figcaption></figure>
    <figure class="wide"><div class="drawer-demo"><VariablesTab rows={VARIABLES} query="cyg" magLimit={12.5} ontarget={noop} /></div><figcaption>filtered: "cyg", brightest ≤ 12.5</figcaption></figure>
    <figure class="wide"><div class="drawer-demo short"><VariablesTab rows={null} query="" magLimit={null} targetReason="identify the field first (S)" /></div><figcaption>field not identified</figcaption></figure>
  </div>
</section>

<section data-gallery="w5-curve" id="w5-curve">
  <h2>Light curve (drawer tab) <span>target, check (check − V with its trailing band) and ensemble facets on one time axis (LightCurvePlot); the facts in one row above</span></h2>
  <div class="row top">
    <figure class="wide"><div class="drawer-demo tall">
      <LightCurveTab stars={STARS} curves={C40} line={lineOk}>
        {#snippet plot()}<LightCurvePlot {store} facets={['target', 'check', 'ensemble']} variant="drawer" {theme} {clock} label="Live light curve (gallery)" />{/snippet}
      </LightCurveTab>
    </div><figcaption>measuring</figcaption></figure>
    <figure class="wide"><div class="drawer-demo short"><LightCurveTab stars={STARS} curves={[]} line={lineUnsolved} /></div><figcaption>no point yet: the sub-state in words</figcaption></figure>
    <figure class="wide"><div class="drawer-demo short"><LightCurveTab stars={[]} curves={[]} line={lineNoTarget} /></div><figcaption>no target</figcaption></figure>
  </div>
</section>

<section data-gallery="w5-status" id="w5-status">
  <h2>Live status and verdict <span>the Field band's slot and summary row (08 2.3 C); the ensemble verdict of the drawer's tab row; words, never the tone alone</span></h2>
  <div class="col">
    <LiveStatus line={lineOk} status={STATUS_MEASURED} onopen={noop} />
    <LiveStatus line={lineFew} status={STATUS_MEASURED} onopen={noop} />
    <LiveStatus line={lineSkipped} status={STATUS_SKIPPED} onopen={noop} />
    <LiveStatus line={lineNoComp} onopen={noop} />
    <LiveStatus line={lineUnsolved} onopen={noop} />
    <LiveStatus line={lineNoTarget} compact />
    <EnsembleVerdict verdict={verdict(REPORT_OK)} />
    <EnsembleVerdict verdict={verdict(REPORT_NOT_READY)} />
    <EnsembleVerdict verdict={null} />
  </div>
</section>

<section data-gallery="w5-recommend" id="w5-recommend">
  <h2>Recommend comparison stars <span>340 px; the count is sent with the action (no re-selection on change, 08 P11); the pilot gate in words; Replace asks first during a run</span></h2>
  <div class="row top">
    <figure><RecommendPopover preview count={5} gate={{ snr: 10, dmag: 1.5, sepArcmin: 25 }} onrecommend={noop} /><figcaption>ready</figcaption></figure>
    <figure><RecommendPopover preview count={5} gate={{ snr: 10, dmag: 1.5, sepArcmin: 25 }} reason="identify the field first (S)" onrecommend={noop} /><figcaption>unavailable, with the reason</figcaption></figure>
  </div>
</section>

<style>
  section {
    padding: var(--space-5) 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  h2 {
    margin: 0 0 var(--space-4);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  h2 span {
    margin-left: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-regular);
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-5);
  }
  .row.top {
    align-items: flex-start;
  }
  figure {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
  }
  figcaption {
    color: var(--text-muted);
    font-size: var(--text-xs);
    max-width: 400px;
  }
  .rail {
    width: 400px;
    background: var(--bg);
  }
  .list {
    width: 340px;
    padding: var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m, 6px);
    background: var(--surface);
  }
  .wide {
    width: 940px;
  }
  .drawer-demo {
    height: 216px;
    border: var(--border-w) solid var(--border-soft);
    background: var(--bg);
  }
  .drawer-demo.short {
    height: 140px;
  }
  .drawer-demo.tall {
    height: 320px;
  }
  .col {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
    max-width: 640px;
  }
  .tsv {
    margin-top: var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .tsv pre {
    overflow: auto;
    max-width: 100%;
    color: var(--fg);
    font-family: var(--font-mono);
  }
</style>
