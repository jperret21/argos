<!--
  Component gallery, wave 7, Review files (development only, part of /?gallery=1): R0 the
  landing, the drawer's Frames tab, R2 the frame inspector, the Re-run, Export AAVSO and
  Export CSV dialogs, and the job strip, each in its states, on synthetic fixtures
  (files-fixtures.ts). Sections are [data-gallery="w7-<name>"] for element screenshots.
  Nothing here talks to a server: the routes are fakes answering the fixtures.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import type { Theme } from '../../app/theme';
  import { fakeList } from '../../components/gallery/fixtures2';
  import IconButton from '../../components/IconButton.svelte';
  import JobStrip from '../../components/JobStrip.svelte';
  import type { JobEntry, Job } from '../../app/jobs';
  import { LAYERS, syntheticFrame } from '../../imaging/field/gallery/fixtures';
  import type { RotationMode } from '../../viewer/rotation';
  import { ViewerTools } from '../../viewer/tools/tools.svelte';
  import type { AavsoBody, AavsoPreview, JobStart, RerunBody, RerunPlan } from '../dialogs/api';
  import ExportAavsoDialog from '../dialogs/ExportAavsoDialog.svelte';
  import ExportCsvDialog from '../dialogs/ExportCsvDialog.svelte';
  import RerunDialog from '../dialogs/RerunDialog.svelte';
  import { trackingText } from '../dialogs/rerun';
  import FramesTable from '../frames/FramesTable.svelte';
  import FramesTools from '../frames/FramesTools.svelte';
  import { FramesView } from '../frames/frames.svelte';
  import { fileFrameInfo, type InspectorApi } from '../inspector/api';
  import FrameInspector from '../inspector/FrameInspector.svelte';
  import { InspectorStore, type JobsLike } from '../inspector/inspector.svelte';
  import SessionsLanding from '../landing/SessionsLanding.svelte';
  import {
    CARDS,
    CURVES_LP,
    CURVES_ONE,
    CURVES_TWO,
    CURVES_UNIDENTIFIED,
    FILE,
    framesRaw,
    JOBS,
    KEYWORDS,
    LIVE,
    MEASURE,
    NOW,
    PAGE,
    PAGE_EMPTY,
    PAGE_MISSING,
    PAGE_PAGED,
    PLAN,
    PLAN_LIVE,
    PLAN_NO_COMPS,
    PLAN_NO_FRAMES,
    PREVIEW,
    PREVIEW_MISMATCH,
    PREVIEW_NO_OBSCODE,
    PREVIEW_UNIDENTIFIED,
    R2_FRAMES,
    R2_LABEL,
    RECENT,
    ROOT,
    SOLUTION,
    SOURCE,
  } from './files-fixtures';

  let theme = $state<Theme>('observatory');
  onMount(() => {
    const read = () => (theme = (document.documentElement.dataset.theme as Theme) || 'observatory');
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  });
  const TINTS: Record<Theme, [number, number, number]> = { observatory: [1, 1, 1], charcoal: [1, 1, 1], 'night-red': [0.847, 0, 0] };
  const SATURATED: Record<Theme, [number, number, number]> = { observatory: [1, 0.2, 0.33], charcoal: [1, 0.2, 0.33], 'night-red': [0, 0, 0] };
  const memory = () => {
    const d = new Map<string, string>();
    return { getItem: (k: string) => d.get(k) ?? null, setItem: (k: string, v: string) => void d.set(k, v) };
  };
  const noop = () => undefined;
  const never = <T,>() => new Promise<T>(noop);

  // -- R0 --------------------------------------------------------------------------------------
  const landingProps = { list: fakeList, onopen: noop, onrefresh: noop, onforget: noop };

  // -- Frames ----------------------------------------------------------------------------------
  const RAW = framesRaw();
  const frames = new FramesView(false);
  frames.setFrames(RAW);
  frames.selected = 'f6';
  const framesFiltered = new FramesView(false);
  framesFiltered.setFrames(RAW);
  framesFiltered.query = 'dark';
  const framesEmpty = new FramesView(false);

  // -- R2 --------------------------------------------------------------------------------------
  const fakeApi = { frame: never, header: never, solution: never, measure: never, solve: never, catalogue: never } as unknown as InspectorApi;
  const runningSolve: JobEntry = { ...JOBS.open, id: 's1', kind: 'file_solve', stage: 'ASTAP', message: 'ASTAP (hinted by OBJCTRA / OBJCTDEC)', total: null, started_utc: new Date(NOW - 6e3).toISOString() };
  const jobs: JobsLike = { get: (id) => (id === 's1' ? runningSolve : null), ingest: (raw) => raw as Job, cancel: () => Promise.resolve() };
  const r2Frames = new FramesView(false);
  r2Frames.setFrames(R2_FRAMES);
  const info = fileFrameInfo({ path: FILE, file_name: FILE.slice(FILE.lastIndexOf('/') + 1), date_obs: '2026-11-08T22:40:00.000', bayer: 'GRBG', filter: 'IR', image_type: 'Light Frame', object: 'RR Lyr', raw: true });
  const header = { path: FILE, file_name: info.file_name ?? '', text: '', cards: CARDS, keywords: KEYWORDS };

  function loaded(): InspectorStore {
    const s = new InspectorStore(fakeApi, jobs, false);
    s.setSession(r2Frames.lights, R2_LABEL);
    s.path = FILE;
    s.frame = syntheticFrame();
    s.info = info;
    s.header = header;
    return s;
  }
  const r2Full = loaded();
  r2Full.solution = SOLUTION;
  r2Full.layers = { path: FILE, frame_shape: LAYERS.frame_shape ?? null, display_mag_limit: LAYERS.display_mag_limit ?? null, layers: LAYERS.layers, counts: LAYERS.counts, warnings: [] };
  r2Full.gLimit = LAYERS.display_mag_limit ?? null;
  r2Full.measure = MEASURE;
  r2Full.visibility = { ...r2Full.visibility, grid: true };

  const r2Error = loaded();
  r2Error.loading = FILE.replace('00007', '00009');
  r2Error.error = 'Could not open RR_Lyr_ir_light_e010000ms_g080_00008.fit: not a FITS image (no image HDU)';
  r2Error.measure = { ...MEASURE, found: false, message: 'No star near (130, 610).' };

  const r2Solving = loaded();
  r2Solving.solveJobId = 's1';
  r2Solving.wantField = true;
  r2Solving.measuring = true;
  r2Solving.measureAt_ = { x: 292, y: 452 };
  r2Solving.railOpen = true;

  const r2Empty = new InspectorStore(fakeApi, jobs, false);
  const toolsA = new ViewerTools(memory());
  const toolsB = new ViewerTools(memory());
  const toolsC = new ViewerTools(memory());
  const toolsD = new ViewerTools(memory());
  let rotation = $state<RotationMode>('auto');

  // -- Dialogs ----------------------------------------------------------------------------------
  const preview = (pv: AavsoPreview) => (b: AavsoBody) => Promise.resolve({ ...pv, filter: b.filter ?? pv.filter });
  const twoFilters = (b: AavsoBody) => Promise.resolve({ ...PREVIEW, filter: b.filter, filters: ['ir', 'lp'], head: PREVIEW.head.replace(/TG/g, b.filter === 'lp' ? 'na' : 'TG') });
  const startJob = (): Promise<JobStart> => Promise.resolve({ job_id: 'g', job: null });
  const plan = (p: RerunPlan) => (_b: RerunBody) => Promise.resolve(p);
  const planFails = () => Promise.reject(new Error('Cannot reach the ARGOS server at http://127.0.0.1:8742 (fetch failed)'));
  const label = 'SW And · 20261114T201210Z_SW_And · session photometry';

  // -- Job strip -------------------------------------------------------------------------------
  const TITLES: Record<string, string> = { rerun: 'Re-running photometry', export: 'Exporting', session_open: 'Opening the session', file_solve: 'Identifying field', file_catalogue: 'Catalogue sources' };
  const title = (j: JobEntry) => TITLES[j.kind] ?? j.kind;
  const unit = (j: JobEntry) => (j.kind === 'rerun' ? 'frames' : '');
  const detail = (j: JobEntry) => (j.kind === 'rerun' && j.done > 100 ? trackingText({ rotation_deg: 0.42, shift_px: 3.1 }) : null);
  const resultText = (j: JobEntry) => (j.kind === 'rerun' ? '195 of 195 frames · 7 curves · 4 unverified (suspect) → photometry_rerun_20261115T213000Z/' : j.message);
</script>

<section data-gallery="w7-r0" id="w7-r0">
  <h2>R0 Review landing <span>sessions list (A67) with scope and search, the live run (D3), Recent (per viewer), Open folder… / Import CSV… / Open FITS through the FilePicker; issues as a count that opens the server's lines</span></h2>
  <figure class="screen tall"><SessionsLanding page={PAGE} recent={RECENT} live={LIVE} opening={`${ROOT}/20261102T190455Z_DY_Peg`} {...landingProps} /><figcaption>ready: the live run, Recent, newest first; DY Peg is opening (spinner)</figcaption></figure>
  <div class="grid two">
    <figure class="screen"><SessionsLanding page={PAGE} query="cyg" scope="issues" {...landingProps} /><figcaption>filtered: scope Issues + “cyg”, “1 of 8”</figcaption></figure>
    <figure class="screen"><SessionsLanding page={PAGE} previewIssues={`${ROOT}/20261020T183320Z_AH_Cep`} {...landingProps} /><figcaption>the issues popover: the server's lines verbatim</figcaption></figure>
    <figure class="screen"><SessionsLanding page={null} loading {...landingProps} /><figcaption>loading: skeleton rows, aria-busy</figcaption></figure>
    <figure class="screen"><SessionsLanding page={PAGE_PAGED} error="GET /api/sessions: 500 Internal Server Error" openError={{ path: `${ROOT}/20261003T201500Z_V1143_Cyg`, message: 'session.json has no frame list' }} ondismisserror={noop} {...landingProps} /><figcaption>list error (the last list stays, Retry), open error banner, paged list</figcaption></figure>
    <figure class="screen"><SessionsLanding page={PAGE_EMPTY} {...landingProps} /><figcaption>empty: no sessions in the folder</figcaption></figure>
    <figure class="screen"><SessionsLanding page={PAGE_MISSING} linkDown {...landingProps} /><figcaption>link down over a missing sessions folder: every action says why</figcaption></figure>
  </div>
</section>

<section data-gallery="w7-frames" id="w7-frames">
  <h2>Frames tab (drawer) <span>the virtual table, read-only: mono numbers, fixed decimals, missing frames dimmed and tagged; ↑ ↓ select (the plots' cursor follows), Enter / double click opens R2; ⌘/Ctrl+C copies TSV</span></h2>
  <figure class="drawer"><div class="tabrow"><span class="tab">FRAMES</span><FramesTools view={frames} /></div><FramesTable view={frames} height="300px" /><figcaption>195 lights, 2 missing (rows 42, 43), 2 darks; frame 7 selected</figcaption></figure>
  <div class="grid two">
    <figure class="drawer"><div class="tabrow"><span class="tab">FRAMES</span><FramesTools view={framesFiltered} /></div><FramesTable view={framesFiltered} height="200px" /><figcaption>filter “dark”: 2 of 197</figcaption></figure>
    <figure class="drawer"><div class="tabrow"><span class="tab">FRAMES</span><FramesTools view={framesEmpty} /></div><FramesTable view={framesEmpty} height="200px" empty="An imported curve CSV has no frames: open its session to see them." /><figcaption>an imported CSV: no frames</figcaption></figure>
  </div>
</section>

<section data-gallery="w7-r2" id="w7-r2">
  <h2>R2 Frame inspector <span>the image the hero; previous / next light frame (PageUp / PageDown); a click measures (A73), never a role; Identify (S) then the catalogue; FITS header filter and copy; the context menu has no role items (M102)</span></h2>
  <figure class="screen r2"><FrameInspector store={r2Full} tools={toolsA} {theme} tint={TINTS[theme]} saturatedColour={SATURATED[theme]} {rotation} onrotation={(r) => (rotation = r)} fullWell={60000} onback={noop} onopenfits={noop} /><figcaption>identified: grid, catalogue layers, the measured star (FWHM, HFD in px and ″, SNR), 7 / 193</figcaption></figure>
  <div class="grid two">
    <figure class="screen r2s"><FrameInspector store={r2Error} tools={toolsB} {theme} tint={TINTS[theme]} saturatedColour={SATURATED[theme]} {rotation} onrotation={(r) => (rotation = r)} onback={noop} /><figcaption>a failed open keeps the previous frame (P28), the next one loading; no star at the click</figcaption></figure>
    <figure class="screen r2s"><FrameInspector store={r2Solving} tools={toolsC} {theme} tint={TINTS[theme]} saturatedColour={SATURATED[theme]} {rotation} onrotation={(r) => (rotation = r)} onback={noop} /><figcaption>identifying (ASTAP, Cancel in place), measuring</figcaption></figure>
    <figure class="screen r2s"><FrameInspector store={r2Empty} tools={toolsD} {theme} tint={TINTS[theme]} saturatedColour={SATURATED[theme]} {rotation} onrotation={(r) => (rotation = r)} onopenfits={noop} /><figcaption>no frame: open one from the session or any FITS</figcaption></figure>
  </div>
</section>

<section data-gallery="w7-aavso" id="w7-aavso">
  <h2>Export AAVSO <span>the server's preview is the file's head (the fixed core writer); one filter at a time (S53); saturated and suspect points left out with counts; refusals in the server's words before any job (A77)</span></h2>
  <div class="grid dialogs">
    <figure><ExportAavsoDialog open preview source={SOURCE} sourceLabel={label} curves={CURVES_ONE} getPreview={preview(PREVIEW)} start={startJob} list={fakeList} filterNames={['IR', 'LP']} /><figcaption>ready: one filter, the check gives KNAME / KMAG, 190 rows, 5 left out</figcaption></figure>
    <figure><ExportAavsoDialog open preview source={SOURCE} sourceLabel={label} curves={CURVES_TWO} getPreview={twoFilters} start={startJob} list={fakeList} filterNames={['IR', 'LP']} /><figcaption>two filters: the observer chooses one (S53)</figcaption></figure>
    <figure><ExportAavsoDialog open preview source={SOURCE} sourceLabel={label} curves={CURVES_ONE} getPreview={preview(PREVIEW_NO_OBSCODE)} start={startJob} onsettings={noop} list={fakeList} /><figcaption>refused: no observer code (Q-R2), Open Settings</figcaption></figure>
    <figure><ExportAavsoDialog open preview source={SOURCE} sourceLabel={label} curves={CURVES_LP} getPreview={preview(PREVIEW_MISMATCH)} start={startJob} list={fakeList} /><figcaption>an LP run: FILT does not fit (allowed, said); the run's Settings site was wrong (airmass); flight-recorder flags</figcaption></figure>
    <figure><ExportAavsoDialog open preview source={{ kind: 'import', path: '/Users/observer/Desktop/mystery.csv' }} sourceLabel="mystery.csv · imported curve" curves={CURVES_UNIDENTIFIED} getPreview={preview(PREVIEW_UNIDENTIFIED)} start={startJob} list={fakeList} /><figcaption>a curve whose star or role is unknown: no AAVSO export (S10)</figcaption></figure>
  </div>
</section>

<section data-gallery="w7-csv" id="w7-csv">
  <h2>Export CSV <span>the lossless measurements file (write_curves_csv), one filter per file (the file has no filter column); every role, ticked by default</span></h2>
  <div class="grid dialogs">
    <figure><ExportCsvDialog open preview source={SOURCE} sourceLabel={label} object="SW And" curves={CURVES_ONE} folder={SOURCE.path} start={startJob} list={fakeList} filterNames={['IR', 'LP']} /><figcaption>one filter: 7 curves, the default file in the session</figcaption></figure>
    <figure><ExportCsvDialog open preview source={{ kind: 'live' }} sourceLabel="SW And · live run" object="SW And" curves={CURVES_TWO} folder={null} start={startJob} list={fakeList} filterNames={['IR', 'LP']} /><figcaption>the live run in two filters: choose one; a download by default</figcaption></figure>
  </div>
</section>

<section data-gallery="w7-rerun" id="w7-rerun">
  <h2>Re-run photometry <span>the server's plan (never writes): frames found and left out, the stars, the reference, the parameters, the NEW folder; Start disabled with the server's reason (M50)</span></h2>
  <div class="grid dialogs">
    <figure><RerunDialog open preview session={SOURCE.path} sessionLabel={label} getPlan={plan(PLAN)} start={startJob} onsettings={noop} list={fakeList} /><figcaption>ready: identify the first frame (ASTAP), a new folder</figcaption></figure>
    <figure><RerunDialog open preview session={SOURCE.path} sessionLabel={label} liveTargets getPlan={plan(PLAN_LIVE)} start={startJob} list={fakeList} /><figcaption>the live solution offered (D2); no site: no airmass, no BJD</figcaption></figure>
    <figure><RerunDialog open preview session={SOURCE.path} sessionLabel={label} getPlan={plan(PLAN_NO_FRAMES)} start={startJob} list={fakeList} /><figcaption>no frames in the folder</figcaption></figure>
    <figure><RerunDialog open preview session={SOURCE.path} sessionLabel={label} getPlan={plan(PLAN_NO_COMPS)} start={startJob} list={fakeList} /><figcaption>no comparison star: refused in the server's words</figcaption></figure>
    <figure><RerunDialog open preview session={SOURCE.path} sessionLabel={label} getPlan={planFails} start={startJob} list={fakeList} /><figcaption>the plan failed: the reason, Start disabled</figcaption></figure>
    <figure><RerunDialog open preview session={SOURCE.path} sessionLabel={label} getPlan={plan(PLAN)} start={startJob} onsettings={noop} list={fakeList} siteWarning="The site in Settings was not where the telescope was during this run" /><figcaption>the session's site check said mismatch: the re-run's airmass would be wrong (RR Lyr 2026-09-25)</figcaption></figure>
  </div>
</section>

<section data-gallery="w7-jobstrip" id="w7-jobstrip">
  <h2>Job strip <span>one line in the toolbar while a long job runs: count, ETA from the observed rate, stage, Cancel (icon + label); the outcome stays in words until dismissed</span></h2>
  <div class="col strips">
    <figure><div class="bar"><JobStrip jobs={[JOBS.rerun]} {title} {unit} {detail} oncancel={noop} now={NOW} label="Review jobs" /></div><figcaption>re-run measuring: 37 / 195 frames, ETA</figcaption></figure>
    <figure><div class="bar"><JobStrip jobs={[JOBS.queued, JOBS.resolving]} {title} {unit} {detail} oncancel={noop} now={NOW} /></div><figcaption>re-solving (ASTAP) with the tracking detail; another job waits (+1)</figcaption></figure>
    <figure><div class="bar"><JobStrip jobs={[JOBS.cancelling]} {title} {unit} oncancel={noop} now={NOW} /></div><figcaption>cancelling: stops at the next frame</figcaption></figure>
    <figure><div class="bar"><JobStrip jobs={[JOBS.open]} {title} oncancel={noop} now={NOW} /></div><figcaption>indeterminate (opening a session: no count, no ETA)</figcaption></figure>
    <figure>
      <div class="bar">
        <JobStrip jobs={[JOBS.done]} {title} {unit} {resultText} ondismiss={noop} now={NOW}>
          {#snippet actions(_job: JobEntry)}<IconButton icon="open-session" label="Open the new run" showLabel size="s" variant="secondary" onclick={noop} />{/snippet}
        </JobStrip>
      </div>
      <figcaption>done: the result and Open</figcaption>
    </figure>
    <figure><div class="bar"><JobStrip jobs={[JOBS.failed]} {title} {unit} ondismiss={noop} now={NOW} /></div><figcaption>failed: the server's exact message (role alert)</figcaption></figure>
    <figure><div class="bar"><JobStrip jobs={[JOBS.cancelled]} {title} {unit} ondismiss={noop} now={NOW} /></div><figcaption>cancelled: nothing saved</figcaption></figure>
    <figure><div class="bar"><JobStrip jobs={[JOBS.exported]} {title} {resultText} ondismiss={noop} now={NOW} /></div><figcaption>an export done: the log line</figcaption></figure>
  </div>
</section>

<style>
  section {
    padding: var(--space-5) var(--space-6);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  h2 {
    margin: 0 0 var(--space-4);
    font-size: var(--text-l);
    color: var(--fg);
  }
  h2 span {
    display: block;
    margin-top: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-regular, 400);
  }
  .grid {
    display: grid;
    gap: var(--space-5);
    margin-top: var(--space-5);
  }
  .grid.two {
    grid-template-columns: repeat(auto-fill, minmax(560px, 1fr));
  }
  .grid.dialogs {
    grid-template-columns: repeat(auto-fill, minmax(680px, 1fr));
    align-items: start;
  }
  .col {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  figure {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }
  figcaption {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .screen {
    height: 400px;
  }
  .screen.tall {
    height: 460px;
  }
  .screen.r2 {
    height: 640px;
  }
  .screen.r2s {
    height: 520px;
  }
  .screen > :global(:first-child) {
    flex: 1;
    min-height: 0;
    border: var(--border-w) solid var(--border-soft);
  }
  .drawer {
    border: var(--border-w) solid var(--border-soft);
    background: var(--bg);
  }
  .drawer > figcaption {
    padding: var(--space-2) var(--space-3);
  }
  .tabrow {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: var(--toolbar-h);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .tab {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    color: var(--fg);
  }
  .bar > :global(.strip) {
    flex: 1 1 0;
  }
  .bar {
    display: flex;
    align-items: center;
    height: var(--toolbar-h);
    max-width: 1100px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    background: var(--bg);
  }
  .strips figure {
    max-width: 1100px;
  }
</style>
