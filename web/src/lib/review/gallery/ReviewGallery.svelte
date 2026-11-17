<!--
  Component gallery, wave 7, Review R1 (development only, part of /?gallery=1): the session
  review screen (SessionReview: toolbar, plot wall, rail, drawer) on synthetic sessions in the
  server's A68 / A69 shapes (fixtures.ts: no real data, no personal metadata, the fake
  observer code "XYZ"), in every state: a session with a selected point, a wrong Settings site
  (header airmass, the readiness popover), two filters ("Name [IR]"), the rail collapsed
  (three columns), an expanded cell, the drawer's Ensemble tab, opening, no curve, the live
  run, an imported CSV; then the rail cards, the cell and metric menus and the health strip
  alone; then the large-session check (on its button, or at load with ?rvstress=1).
  Sections are [data-gallery="w7-review-<name>"] for element screenshots.
  A real session through the server's A68 / A69 (development check, nothing kept):
  ?gallery=1&rvapi=http://127.0.0.1:8742&rvtoken=dev&rvpath=<session folder> adds a section.
-->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import type { Theme } from '../../app/theme';
  import Button from '../../components/Button.svelte';
  import Menu from '../../components/Menu.svelte';
  import { fixed, int } from '../../format/number';
  import { CurveLink } from '../../charts/lightcurve/link.svelte';
  import AavsoCard from '../cards/AavsoCard.svelte';
  import EnsembleCard from '../cards/EnsembleCard.svelte';
  import PointCard from '../cards/PointCard.svelte';
  import SessionCard from '../cards/SessionCard.svelte';
  import HealthStrip from '../HealthStrip.svelte';
  import type { ReviewIntent } from '../intents';
  import { WallLayoutState } from '../layout.svelte';
  import { aavsoChecks, ensembleRows, pointInfo } from '../rail';
  import { httpLoader, ReviewSource } from '../session.svelte';
  import SessionReview from '../SessionReview.svelte';
  import { parseCurves, storeFromCurves } from '../source';
  import { cellMenu, healthOf, metricMenu, wallExtent } from '../wall';
  import { fixtureLoader, makeSession, type SessionFixture } from './fixtures';

  let theme = $state<Theme>('observatory');
  onMount(() => {
    const read = () => (theme = (document.documentElement.dataset.theme as Theme) || 'observatory');
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  });

  const WHEEL = ['IR', 'LP'];
  let lastIntent = $state('');
  const onintent = (i: ReviewIntent) => (lastIntent = describe(i));
  function describe(i: ReviewIntent): string {
    if (i.kind === 'export-aavso' || i.kind === 'export-csv') return `${i.kind} · ${i.source.kind}${'path' in i.source ? ` ${i.source.path}` : ''} · filter ${i.filter ?? '—'} · keys ${i.keys.join(', ') || 'every curve'} · ${i.curves.length} curves listed`;
    if (i.kind === 'open-frame') return `open-frame · ${i.filename}`;
    if (i.kind === 'rerun') return `rerun · ${i.path ?? 'live run'}`;
    if (i.kind === 'settings') return `settings · ${i.category}`;
    return i.kind;
  }

  /** A source opened on a fixture, its layout not kept (no storage). */
  function opened(f: SessionFixture, after?: (s: ReviewSource) => void): ReviewSource {
    const s = new ReviewSource();
    void s.open(fixtureLoader(f), f.path).then(() => after?.(s));
    return s;
  }
  const layout = () => new WallLayoutState(null);
  const selectAt = (row: number) => (s: ReviewSource) => {
    const t = s.store.primary('target')?.cols.t[row];
    if (t !== undefined) s.link.select(t);
  };

  // -- R1 states -------------------------------------------------------------------------------
  const plain = makeSession({ n: 240, comps: 5, zpOutlier: [150] });
  const main = opened(plain, selectAt(118));
  const mainLayout = layout();

  const site = makeSession({ n: 180, comps: 4, headerAirmass: true, seed: 21, missing: [] });
  const siteSrc = opened(site, selectAt(60));
  const siteLayout = layout();
  siteLayout.setMetric('airmass');
  let siteIssues = $state(false);

  const two = makeSession({ n: 320, comps: 3, filters: ['ir', 'lp'], seed: 5 });
  const twoSrc = opened(two);

  const wide = opened(makeSession({ n: 240, comps: 6, seed: 9 }));

  const expLayout = layout();
  // Expanded once the session is in (a new source restores the grid).
  const expSrc = opened(makeSession({ n: 240, comps: 3, seed: 13 }), (s) => {
    selectAt(40)(s);
    requestAnimationFrame(() => expLayout.toggleExpand('target:000-AAA-001'));
  });

  const drawerSrc = opened(makeSession({ n: 200, comps: 5, seed: 17 }));

  const loading = new ReviewSource();
  void loading.open({ session: () => new Promise(() => undefined), curves: () => new Promise(() => undefined) }, '/sessions/20261101T200000Z_SW_And').catch(() => undefined);

  const emptyFix = makeSession({ n: 60, comps: 2, seed: 4 });
  const empty = opened({ ...emptyFix, curves: { ...emptyFix.curves, curves: [] } });

  const liveFix = makeSession({ n: 140, comps: 4, seed: 33, missing: [] });
  const live = new ReviewSource();
  live.openLive(storeFromCurves({ curves: parseCurves(liveFix.curves).curves, object: 'SW And' }).store, { object: 'SW And' });

  const impFix = makeSession({ n: 120, comps: 0, check: false, seed: 41 });
  const imp = new ReviewSource();
  imp.openImport({ ...impFix.curves, object: 'SW And' }, '/sessions/exports/target_SW_And_IR_000-AAA-001.csv');

  // -- A real session through the server (development check: ?rvapi=&rvtoken=&rvpath=) -------------------
  const params = new URLSearchParams(location.search);
  const rvApi = params.get('rvapi');
  const rvPath = params.get('rvpath');
  let realError = $state('');
  const real = rvApi && rvPath ? new ReviewSource() : null;
  if (real && rvApi && rvPath) {
    const token = params.get('rvtoken') ?? 'dev';
    const request = async <T,>(method: string, path: string, _body?: unknown, o?: { signal?: AbortSignal }): Promise<T> => {
      const r = await fetch(`${rvApi}${path}`, { method, headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' }, signal: o?.signal });
      if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
      return (await r.json()) as T;
    };
    void real.open(httpLoader({ request }), rvPath).catch((e: unknown) => (realError = e instanceof Error ? e.message : String(e)));
  }

  // -- Cards, menus, health strip --------------------------------------------------------------------
  const cardSrc = opened(makeSession({ n: 160, comps: 4, seed: 51, zpOutlier: [70] }));
  const cards = $derived.by(() => {
    void cardSrc.version;
    const filter = cardSrc.shownFilter();
    const st = cardSrc.store;
    const tgt = st.primary('target', null, filter);
    const info = cardSrc.info;
    const point = tgt && tgt.n ? pointInfo(st, tgt.cols.t[70], { filter, frames: cardSrc.frames, tol: 15, extras: cardSrc.extras, airmassSource: cardSrc.airmassSource() }) : null;
    const base = { store: st, filter, filters: cardSrc.filters, band: 'TG', frameFilters: info?.filters ?? {}, chartId: info?.chartId ?? null };
    return {
      point,
      ready: aavsoChecks({ ...base, obscode: 'XYZ' }),
      blocked: aavsoChecks({ ...base, obscode: null }),
      ensemble: ensembleRows(st, filter, cardSrc.report(), info?.targets ?? [], 'TG'),
      ensembleNoReport: ensembleRows(st, filter, null, info?.targets ?? [], 'TG'),
      report: cardSrc.report(),
      health: healthOf(cardSrc.wallFrames(), tgt, st.comparisons(filter).length, 1.5, tgt ? (cardSrc.extras.get(tgt.key) ?? null) : null),
      times: tgt ? tgt.cols.view('t') : new Float64Array(0),
      info,
      lights: cardSrc.frames.filter((f) => f.light).length,
      missing: cardSrc.frames.filter((f) => f.light && f.missing).length,
    };
  });
  const healthLink = new CurveLink({ extent: () => wallExtent(cardSrc.store, cardSrc.shownFilter(), cardSrc.wallFrames()), minSpan: 300, reducedMotion: () => true });
  const noop = () => undefined;

  // -- Large-session check ------------------------------------------------------------------------------
  interface StressResult {
    frames: number;
    stars: number;
    points: number;
    wireKb: number;
    /** JSON.parse of the A68 + A69 answers (what the client's fetch does). */
    jsonMs: number;
    /** Columns into the store, frames, vetting (ReviewSource.open after the answers). */
    parseMs: number;
    paintMs: number;
    pushMs: number;
    pushes: number;
    zoomMs: number;
    /** JS heap after a GC (Chrome with --js-flags=--expose-gc), and its growth over the page before. */
    heapMb: number | null;
    heapDeltaMb: number | null;
  }
  let stress = $state<ReviewSource | null>(null);
  const stressLayout = layout();
  let results = $state<StressResult[]>([]);
  let running = $state(false);
  let pushSum = 0;
  let pushes = 0;
  const frame = () => new Promise<void>((r) => requestAnimationFrame(() => r()));
  const heap = () => {
    (window as Window & { gc?: () => void }).gc?.();
    const m = (performance as Performance & { memory?: { usedJSHeapSize: number } }).memory;
    return m ? m.usedJSHeapSize / 1048576 : null;
  };

  async function runStress(): Promise<void> {
    if (running) return;
    running = true;
    results = [];
    for (const [n, comps] of [
      [2000, 8],
      [6000, 12],
    ] as const) {
      const f = makeSession({ n, comps, cadence: 12, exposure: 10, seed: 77, missing: [], gapAt: null, hfdEpisodeAt: Math.floor(n / 3) });
      const wire = [JSON.stringify(f.session), JSON.stringify(f.curves)];
      const wireKb = Math.round((wire[0].length + wire[1].length) / 1024);
      stress = null;
      await frame();
      await frame();
      const h0 = heap();
      const tj = performance.now();
      const answers = { session: JSON.parse(wire[0]), curves: JSON.parse(wire[1]) };
      const jsonMs = performance.now() - tj;
      const s = new ReviewSource();
      pushSum = 0;
      pushes = 0;
      const t0 = performance.now();
      await s.open({ session: async () => answers.session, curves: async () => answers.curves }, f.path);
      const t1 = performance.now();
      stress = s;
      // Two frames: the cells mount, their first push draws.
      await frame();
      await frame();
      const t2 = performance.now();
      const pushBefore = pushSum;
      s.link.zoom.setUser(s.store.primary('target')!.cols.t[Math.floor(n / 3)], s.store.primary('target')!.cols.t[Math.floor(n / 2)]);
      await frame();
      await frame();
      const t3 = performance.now();
      results.push({
        frames: n,
        stars: s.store.stars.size,
        points: s.store.points,
        wireKb,
        jsonMs,
        parseMs: t1 - t0,
        paintMs: t2 - t1,
        pushMs: pushBefore,
        pushes,
        zoomMs: t3 - t2,
        ...((): { heapMb: number | null; heapDeltaMb: number | null } => {
          const h = heap();
          return { heapMb: h, heapDeltaMb: h !== null && h0 !== null ? h - h0 : null };
        })(),
      });
      results = [...results];
    }
    running = false;
  }
  onMount(() => {
    if (new URLSearchParams(location.search).has('rvstress')) untrack(() => void runStress());
  });
</script>

{#if real}
  <section data-gallery="w7-review-real" id="w7-review-real">
    <h2>A session from the server <span>A68 + A69 of {rvPath} (development check)</span></h2>
    {#if realError}<p class="intent">{realError}</p>{/if}
    <div class="frame"><SessionReview source={real} layout={layout()} {theme} obscode="TEST" band="TG" prefs={null} {onintent} /></div>
  </section>
{/if}

<section data-gallery="w7-review-r1" id="w7-review-r1">
  <h2>Review R1 <span>a session under review: toolbar (identity, readiness, time axis, U / M / F, the zoom state, Re-run, Export CSV, Export AAVSO, Plots, drawer, rail), the plot wall (health strip; target, check, five comparisons and Conditions on one time axis; suspect hollow, saturated ×; a selected frame ringed on every cell), the rail (Selected point, Ensemble, Session, AAVSO export)</span></h2>
  <div class="frame"><SessionReview source={main} layout={mainLayout} {theme} obscode="XYZ" band="TG" wheel={WHEEL} prefs={null} {onintent} /></div>
  <p class="intent num" aria-live="polite">Last intent: {lastIntent || '— (press Export AAVSO…, Export CSV…, Re-run, Open frame)'}</p>
</section>

<section data-gallery="w7-review-r1-site" id="w7-review-r1-site">
  <h2>Wrong Settings site <span>A68 says the curves' airmass is wrong (header site check: mismatch): Conditions on the FITS header AIRMASS, the Selected point's airmass from the header with the CSV's beside it, the readiness popover with the issues</span></h2>
  <div class="frame"><SessionReview source={siteSrc} layout={siteLayout} {theme} obscode="XYZ" band="TG" wheel={WHEEL} prefs={null} bind:issuesOpen={siteIssues} {onintent} /></div>
</section>

<section data-gallery="w7-review-r1-filters" id="w7-review-r1-filters">
  <h2>Two filters <span>S49 curves of IR and LP: the filter shown in the toolbar, each series labelled "Name [IR]"; the AAVSO card says one filter per file (S53)</span></h2>
  <div class="frame"><SessionReview source={twoSrc} layout={layout()} {theme} obscode="XYZ" band="TG" wheel={WHEEL} prefs={null} {onintent} /></div>
</section>

<section data-gallery="w7-review-r1-wide" id="w7-review-r1-wide">
  <h2>Rail collapsed <span>three columns from 1200 px (07 E6)</span></h2>
  <div class="frame"><SessionReview source={wide} layout={layout()} {theme} obscode="XYZ" band="TG" railOpen={false} prefs={null} {onintent} /></div>
</section>

<section data-gallery="w7-review-r1-expanded" id="w7-review-r1-expanded">
  <h2>Expanded cell <span>one cell fills the wall (Expand, again to restore); the zoom and the selection stay the wall's</span></h2>
  <div class="frame"><SessionReview source={expSrc} layout={expLayout} {theme} obscode="XYZ" band="TG" prefs={null} {onintent} /></div>
</section>

<section data-gallery="w7-review-r1-drawer" id="w7-review-r1-drawer">
  <h2>Drawer, Ensemble tab <span>every column of the comparisons (the Frames tab is front-end B's table, wired by the integrator)</span></h2>
  <div class="frame"><SessionReview source={drawerSrc} layout={layout()} {theme} obscode="XYZ" band="TG" prefs={null} drawerAt="ensemble" {onintent} /></div>
</section>

<section data-gallery="w7-review-states" id="w7-review-states">
  <h2>Sources and states <span>opening (skeleton cells, "Opening {'{folder}'}…"), a session without curves, the live run (read-only, Preview), an imported CSV (no frames, no Conditions)</span></h2>
  <div class="row">
    <figure>
      <div class="frame small"><SessionReview source={loading} layout={layout()} {theme} obscode="XYZ" railOpen={false} prefs={null} {onintent} /></div>
      <figcaption>opening</figcaption>
    </figure>
    <figure>
      <div class="frame small"><SessionReview source={empty} layout={layout()} {theme} obscode="XYZ" railOpen={false} prefs={null} {onintent} /></div>
      <figcaption>no photometry CSV</figcaption>
    </figure>
  </div>
  <div class="row">
    <figure>
      <div class="frame small"><SessionReview source={live} layout={layout()} {theme} obscode="XYZ" railOpen={false} prefs={null} {onintent} /></div>
      <figcaption>the live run (D3)</figcaption>
    </figure>
    <figure>
      <div class="frame small"><SessionReview source={imp} layout={layout()} {theme} obscode="XYZ" railOpen={false} prefs={null} {onintent} /></div>
      <figcaption>an imported curve CSV</figcaption>
    </figure>
  </div>
</section>

<section data-gallery="w7-review-cards" id="w7-review-cards">
  <h2>Rail cards <span>Selected point (a ZP-outlier frame: the flag in words), Ensemble with and without a vetting report, Session, AAVSO export ready and blocked (no observer code: Settings ›)</span></h2>
  <div class="row top">
    <div class="rail">
      <PointCard info={cards.point} airmassNote="Photometry CSV airmass (computed for the Settings site; the AAVSO AMASS)" onopenframe={noop} onstar={noop} onclear={noop} />
      <PointCard info={null} />
    </div>
    <div class="rail">
      <EnsembleCard rows={cards.ensemble} report={cards.report} />
      <EnsembleCard rows={cards.ensembleNoReport} report={null} />
    </div>
    <div class="rail">
      <AavsoCard checks={cards.ready.checks} rows={cards.ready.rows} blocked={cards.ready.blocked} onexport={noop} />
      <AavsoCard checks={cards.blocked.checks} rows={cards.blocked.rows} blocked={cards.blocked.blocked} onexport={noop} onsettings={noop} />
      <SessionCard info={cards.info} kind="session" lights={cards.lights} missing={cards.missing} curves={{ target: 1, check: 1, comparison: 4 }} filters={['ir']} problems={[]} />
    </div>
  </div>
</section>

<section data-gallery="w7-review-menus" id="w7-review-menus">
  <h2>Cell menu and frame metric <span>Copy data (TSV), Save as PNG, Expand, Move earlier / later (disabled with the reason), Hide plot, Reset layout; the Conditions cell's metric</span></h2>
  <div class="row top">
    <figure><Menu preview open label="Plot SW And" items={cellMenu({ kind: 'target' }, 0, 7, false)} onselect={noop} onclose={noop} /><figcaption>the first cell</figcaption></figure>
    <figure><Menu preview open label="Plot Conditions" items={cellMenu({ kind: 'conditions' }, 6, 7, true)} onselect={noop} onclose={noop} /><figcaption>Conditions, expanded</figcaption></figure>
    <figure><Menu preview open label="Frame metric" items={metricMenu('airmass')} onselect={noop} onclose={noop} /><figcaption>frame metric</figcaption></figure>
  </div>
</section>

<section data-gallery="w7-review-health" id="w7-review-health">
  <h2>Health strip <span>frames (a gap left empty, missing FITS hollow), HFD episodes (warning), fewer comparisons than the run's best frame (as tall as the shortfall), flags (suspect hollow, saturated ×, recorder flags filled)</span></h2>
  <div class="strip"><HealthStrip lanes={cards.health} times={cards.times} link={healthLink} {theme} /></div>
</section>

<section data-gallery="w7-review-stress" id="w7-review-stress">
  <h2>Large session <span>A68 + A69 of 2 000 and 6 000 frames (8 and 12 comparisons, a check, the target): parse into the store, first paint of every cell, one linked zoom, the JS heap (Chrome)</span></h2>
  <div class="row">
    <Button label={running ? 'Measuring…' : 'Run the large-session check'} disabled={running} onclick={() => void runStress()} />
  </div>
  {#if results.length}
    <table class="num" data-stress-results={JSON.stringify(results)}>
      <thead><tr><th>frames</th><th>stars</th><th>points</th><th>wire kB</th><th>JSON ms</th><th>open ms</th><th>first paint ms</th><th>cell pushes</th><th>zoom ms</th><th>heap MB (+ this session)</th></tr></thead>
      <tbody>
        {#each results as r (r.frames)}
          <tr><td>{int(r.frames)}</td><td>{r.stars}</td><td>{int(r.points)}</td><td>{int(r.wireKb)}</td><td>{fixed(r.jsonMs, 0)}</td><td>{fixed(r.parseMs, 0)}</td><td>{fixed(r.paintMs, 0)}</td><td>{r.pushes} · {fixed(r.pushMs, 1)} ms</td><td>{fixed(r.zoomMs, 0)}</td><td>{r.heapMb === null ? '—' : `${fixed(r.heapMb, 0)} (+${fixed(r.heapDeltaMb, 0)})`}</td></tr>
        {/each}
      </tbody>
    </table>
  {/if}
  {#if stress}
    <div class="frame"><SessionReview source={stress} layout={stressLayout} {theme} obscode="XYZ" band="TG" prefs={null} onperf={(ms) => ((pushSum += ms), pushes++)} /></div>
  {/if}
</section>

<style>
  section {
    padding: var(--space-5) var(--space-6);
    border-bottom: var(--border-w) solid var(--border);
  }
  h2 {
    margin: 0 0 var(--space-4);
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  h2 span {
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-regular);
  }
  .frame {
    width: 1440px;
    max-width: 100%;
    height: 860px;
    border: var(--border-w) solid var(--border);
    overflow: hidden;
  }
  .frame.small {
    width: 700px;
    height: 460px;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-5);
  }
  .row + .row {
    margin-top: var(--space-5);
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
  figcaption,
  .intent {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .rail {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    width: 340px;
    padding: var(--space-3);
    background: var(--bg-2);
  }
  .strip {
    width: 900px;
    height: 52px;
    background: var(--chart-surface);
  }
  table {
    margin: var(--space-3) 0;
    border-collapse: collapse;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  th,
  td {
    padding: 2px var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    text-align: right;
  }
  th {
    color: var(--text-muted);
    font-weight: var(--weight-regular);
  }
</style>
