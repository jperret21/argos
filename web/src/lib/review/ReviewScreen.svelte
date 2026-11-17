<!--
  Review (wave 7; README R0-R2, M8, M50, M80-M103, D2, D3, D5, D6): the section's host. It
  holds no data of its own: the stores are the app's (state.svelte.ts), the screens the roles'
  components, and this file routes between them.

  - R0 (SessionsLanding) while nothing is open, and on Mod+Shift+O (M103): the sessions list
    (A67), the recent items, Open curve CSV (A70), Open FITS (R2) and the live run (D3) while a
    sequence is under way. A failed open stays on R0 with the server's words.
  - R1 (SessionReview): a session (A68 as its `session_open` job, then A69), an imported CSV or
    the live run; the drawer's Frames tab (FramesTable, double-click -> R2), Ensemble and Log
    tabs; every action outside R1 is an intent routed here (intents.ts).
  - R2 (FrameInspector): a frame of the session (previous / next through its lights) or a FITS
    opened alone; back goes to R1 when it came from a session.
  - The dialogs (Re-run M50, Export AAVSO M92, Export CSV), opened by R1's intents or the
    palette (M8 "Re-run subs…"); their jobs show in R1's job strip with Cancel, their outcome
    stays until dismissed, a download starts by itself, a toast says what was written.
  - L: R1's Log tab; on R0 and R2, the shared Log drawer under the screen.
-->
<script lang="ts">
  import { tick, untrack } from 'svelte';
  import { useApp } from '../app/state.svelte';
  import { isActive as jobActive, type JobEntry } from '../app/jobs';
  import { LogFilter } from '../app/log.svelte';
  import IconButton from '../components/IconButton.svelte';
  import JobStrip from '../components/JobStrip.svelte';
  import { stripJob } from '../components/jobstrip';
  import LogControls from '../components/LogControls.svelte';
  import LogView from '../components/LogView.svelte';
  import { profileLimits } from '../imaging/modes/exposure';
  import { isActive as seqActive } from '../run/run';
  import LogDrawer from '../shell/LogDrawer.svelte';
  import { parseExportResult, parseRerunResult, type JobStart } from './dialogs/api';
  import ExportAavsoDialog from './dialogs/ExportAavsoDialog.svelte';
  import ExportCsvDialog from './dialogs/ExportCsvDialog.svelte';
  import RerunDialog from './dialogs/RerunDialog.svelte';
  import { rerunResultText } from './dialogs/rerun';
  import FramesTable from './frames/FramesTable.svelte';
  import FramesTools from './frames/FramesTools.svelte';
  import type { FrameRow } from './frames/frames';
  import { FramesView } from './frames/frames.svelte';
  import FrameInspector from './inspector/FrameInspector.svelte';
  import FrameStrip, { type StripPoint } from './inspector/FrameStrip.svelte';
  import { FLAG_RECORDER, FLAG_SATURATED, FLAG_SUSPECT } from '../charts/uplot/markers';
  import type { ReviewIntent } from './intents';
  import { baseName, parentPath, type LiveSource, type ReviewSource as Opened } from './landing/landing';
  import SessionsLanding from './landing/SessionsLanding.svelte';
  import SessionReview from './SessionReview.svelte';

  const app = useApp();
  const review = app.review;

  // -- R0 ------------------------------------------------------------------------------------------
  let landingEl = $state<SessionsLanding | undefined>();
  let opening = $state<string | null>(null);
  let openError = $state<{ path: string; message: string } | null>(null);

  $effect(() => {
    if (app.reviewScreen === 'r0') untrack(() => void app.landing.load());
  });
  // Mod+O in Review (and R1 / R2's Open FITS): R0's FITS picker.
  let pickSeen = untrack(() => app.reviewPickFits);
  $effect(() => {
    const n = app.reviewPickFits;
    if (n === pickSeen) return;
    pickSeen = n;
    untrack(() => {
      app.reviewScreen = 'r0';
      void tick().then(() => landingEl?.pickFits());
    });
  });

  const liveSource: LiveSource | null = $derived.by(() => {
    const s = app.sequence.state;
    if (!s || !seqActive(s)) return null;
    return { object: s.object_name ?? '', started_utc: s.started_t ? new Date(s.started_t * 1000).toISOString() : null, frames: s.frames_done, state: s.state };
  });

  const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

  /** R0, the recent items, the Frames tab and R1's points open a source here. */
  async function openSource(src: Opened): Promise<string | null> {
    openError = null;
    if (src.kind === 'fits') {
      app.r2.setSession([], null);
      const why = await app.r2.open(src.path);
      if (why) return why;
      app.landing.opened(src);
      app.reviewScreen = 'r2';
      return null;
    }
    if (src.kind === 'live') {
      app.openReviewLive();
      app.reviewScreen = 'r1';
      return null;
    }
    opening = src.path;
    try {
      if (src.kind === 'session') await app.openReviewSession(src.path);
      else await app.openReviewCsv(src.path);
      app.landing.opened(src);
      app.reviewScreen = 'r1';
      return null;
    } catch (e) {
      const message = errText(e);
      openError = { path: src.path, message };
      return message;
    } finally {
      if (opening === src.path) opening = null;
    }
  }

  // -- R1: Frames tab, live targets, the log ---------------------------------------------------------
  const frames = new FramesView();
  $effect(() => {
    const rows = review.frames;
    untrack(() => {
      frames.rows = rows;
      if (frames.selected && !rows.some((r) => r.key === frames.selected)) frames.selected = null;
    });
  });
  // The plots' selected time rings its frame in the table (07 selection model).
  $effect(() => {
    const t = review.link.selection.t;
    untrack(() => frames.selectAt(t));
  });
  /** A frame's mid-exposure (where its points sit), unix s. */
  function midOf(row: FrameRow): number | null {
    const mid = row.header?.mid_utc ? Date.parse(row.header.mid_utc) / 1000 : NaN;
    if (Number.isFinite(mid)) return mid;
    return row.t === null ? null : row.t + (row.exposure_s ?? 0) / 2;
  }

  // -- R2's session strip: the target's curve under the frame (BRAND 11.1 band rule) ----------
  const stripData = $derived.by(() => {
    void review.version;
    if (review.kind !== 'session') return null;
    const star = review.store.primary('target', null, review.display.filter ?? null);
    if (!star) return null;
    const c = star.cols;
    // Each point's light frame (mid-exposure within 60 s), by bisection over the sorted mids.
    const lights = review.frames
      .filter((r) => r.light)
      .map((r) => ({ r, m: midOf(r) }))
      .filter((x): x is { r: FrameRow; m: number } => x.m !== null)
      .sort((a, b) => a.m - b.m);
    const points: StripPoint[] = [];
    for (let i = 0; i < c.n; i++) {
      const t = c.t[i];
      let lo = 0;
      let hi = lights.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (lights[mid].m < t) lo = mid + 1;
        else hi = mid;
      }
      let best: FrameRow | null = null;
      let bestD = 60;
      for (const k of [lo - 1, lo]) {
        const x = lights[k];
        if (x && Math.abs(x.m - t) < bestD) {
          bestD = Math.abs(x.m - t);
          best = x.r;
        }
      }
      points.push({ t, mag: c.mag[i], hollow: (c.flags[i] & (FLAG_SUSPECT | FLAG_SATURATED | FLAG_RECORDER)) !== 0, path: best && !best.missing ? best.path : null });
    }
    return { points, name: star.name };
  });
  const stripRow = $derived(app.r2.path ? (review.frames.find((r) => r.path === app.r2.path) ?? null) : null);
  const stripPrev = $derived.by(() => {
    const row = stripRow;
    if (!row) return null;
    const lights = review.frames.filter((r) => r.light && r.t !== null);
    const k = lights.findIndex((r) => r.key === row.key);
    return k > 0 ? lights[k - 1] : null;
  });

  // The live run follows the target set while it is the source (D3: read-only, no edit here).
  $effect(() => {
    if (review.kind !== 'live') return;
    const stars = app.field.targets?.stars ?? [];
    const band = app.photometry.live?.band ?? null;
    untrack(() => {
      review.store.applyTargets(stars, band);
      if (review.info) review.info = { ...review.info, targets: [...stars] };
    });
  });

  let r1El = $state<SessionReview | undefined>();
  const logFilter = new LogFilter({ persist: 'argos.log.filter' });
  // L opens R1's Log tab while R1 is shown; elsewhere the shared drawer (app.logOpen).
  $effect(() => {
    const el = r1El;
    if (app.reviewScreen !== 'r1' || !el) return;
    untrack(() => {
      if (app.logOpen) {
        app.logOpen = false;
        el.showLog(true);
      }
      app.reviewLog = { shown: () => el.logShown(), set: (open) => el.showLog(open) };
    });
    return () => {
      if (app.reviewLog) app.reviewLog = null;
    };
  });
  // The palette's Re-run / Export entries, once R1 is shown.
  $effect(() => {
    const ask = app.reviewAsk;
    const el = r1El;
    if (!ask || !el || app.reviewScreen !== 'r1') return;
    untrack(() => {
      app.reviewAsk = null;
      el.act(ask.kind);
    });
  });

  // -- R2 ------------------------------------------------------------------------------------------
  const sourceLabel = $derived(review.info ? (review.kind === 'live' ? `${review.info.object || 'Live run'} · live run` : review.info.folder) : null);
  function inspect(path: string | null, why?: string): void {
    if (!path) {
      app.toast('warning', 'Frame unavailable', why ?? 'Its FITS file is not on disk');
      return;
    }
    app.r2.setSession(frames.lights, sourceLabel);
    app.reviewScreen = 'r2';
    void app.r2.open(path).then((err) => {
      if (err) app.toast('error', 'Could not open the frame', err);
    });
  }
  const activeProfile = $derived(app.profiles?.profiles.find((p) => p.key === app.profiles?.active) ?? null);

  // -- Dialogs ---------------------------------------------------------------------------------------
  type Of<K extends ReviewIntent['kind']> = Extract<ReviewIntent, { kind: K }>;
  let aavso = $state.raw<Of<'export-aavso'> | null>(null);
  let csv = $state.raw<Of<'export-csv'> | null>(null);
  let rerun = $state.raw<{ session: string; label: string; live: boolean; site: string | null } | null>(null);
  let aavsoOpen = $state(false);
  let csvOpen = $state(false);
  let rerunOpen = $state(false);
  const wheel = $derived(app.filterwheel?.slots ?? []);

  function route(i: ReviewIntent): void {
    switch (i.kind) {
      case 'export-aavso':
        aavso = i;
        aavsoOpen = true;
        break;
      case 'export-csv':
        csv = i;
        csvOpen = true;
        break;
      case 'rerun': {
        const session = i.path ?? app.photometry.live?.run_root ?? app.sequence.state?.run_root ?? null;
        if (!session) {
          app.toast('info', 'Re-run photometry unavailable', 'The live run has no session folder yet: its first sub is not saved');
          return;
        }
        // RR Lyr 2026-09-25: the Settings site was not the run's (A68 site check), so a re-run's
        // airmass would be wrong too; the dialog says so before Start.
        const site = i.path && review.info?.path === i.path ? review.info.siteNote : null;
        rerun = { session, label: i.label, live: i.path === null, site };
        rerunOpen = true;
        break;
      }
      case 'open-frame':
        inspect(i.path);
        break;
      case 'sessions':
        app.showReviewSessions();
        break;
      case 'open-fits':
        app.reviewPickFits++;
        break;
      case 'settings':
        if (i.category === 'observer') app.openSettings('observer_site', 'observer.obscode');
        else app.openSettings(i.category);
        break;
    }
  }

  function started(s: JobStart): void {
    app.noteReviewJob(s);
  }

  // -- Jobs: the strip, the outcome toast, the download ------------------------------------------
  const KINDS = ['rerun', 'export', 'session_open'];
  // A session open shows while it runs (R1 then names the session); a re-run's or an export's
  // outcome stays until dismissed (a failure is never only a toast).
  const stripJobs = $derived(
    app.jobs.all.filter((j) => KINDS.includes(j.kind) && (jobActive(j) || (j.kind !== 'session_open' && app.reviewJobIds.includes(j.id)))),
  );
  const showStrip = $derived(stripJob(stripJobs).job !== null);
  // Short words: the strip sits in R1's toolbar (the count, the ETA and Cancel need the room).
  const JOB_TITLE: Record<string, string> = { rerun: 'Re-run', export: 'Export', session_open: 'Opening' };
  const jobTitle = (j: JobEntry) => JOB_TITLE[j.kind] ?? j.kind;
  function resultText(j: JobEntry): string | null {
    if (j.kind === 'rerun') {
      const r = parseRerunResult(j.result);
      return r ? rerunResultText(r) : null;
    }
    if (j.kind === 'export') {
      const r = parseExportResult(j.result);
      return r ? `${r.rows} ${r.rows === 1 ? 'row' : 'rows'} → ${r.download ? r.name : baseName(r.path ?? r.name)}` : j.message;
    }
    return j.message;
  }

  async function saveDownload(id: string, fallback: string): Promise<void> {
    try {
      const { blob, name } = await app.client.jobDownload(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = name ?? fallback;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (e) {
      app.reportError('Download the export', e);
    }
  }

  // Once per job this page started: the toast, and the browser download the observer chose.
  const settled = new Set<string>();
  $effect(() => {
    const mine = app.reviewJobIds;
    const done = mine.map((id) => app.jobs.get(id)).filter((j): j is JobEntry => !!j && !jobActive(j) && !settled.has(j.id));
    if (!done.length) return;
    untrack(() => {
      // In Review the job strip says it (one home per value, BRAND 11.1): a success toasts
      // only when the observer is in another section; a failure always does.
      const away = app.section !== 'analyze';
      for (const j of done) {
        settled.add(j.id);
        if (j.kind === 'export' && j.state === 'done') {
          const r = parseExportResult(j.result);
          if (r?.download) void saveDownload(j.id, r.name);
          // Reveal in Finder (desktop app, W8) for a file written on disk, not a download.
          if (away) app.toast('info', 'Exported', r ? `${r.rows} ${r.rows === 1 ? 'row' : 'rows'} to ${r.download ? `${r.name} (download)` : `${baseName(r.path ?? r.name)} in ${baseName(parentPath(r.path ?? ''))}`}` : (j.message ?? ''), app.revealAction(r && !r.download ? r.path : null));
        } else if (j.kind === 'rerun' && j.state === 'done') {
          const r = parseRerunResult(j.result);
          if (away) app.toast('info', 'Photometry re-run', r ? `${r.frames_done} frames → ${r.folder || r.out_dir}` : (j.message ?? ''), app.revealAction(r?.out_dir));
        } else if (j.state === 'failed' && j.kind !== 'session_open') {
          app.toast('error', j.kind === 'rerun' ? 'Re-run failed' : 'Export failed', j.error?.message ?? j.message ?? '');
        }
      }
    });
  });

  function openRerunResult(j: JobEntry): void {
    const r = parseRerunResult(j.result);
    if (r) void openSource(r.source.kind === 'live' ? { kind: 'live' } : r.source);
  }
</script>

{#snippet frameStrip(height: number)}
  {#if stripData}
    <FrameStrip
      points={stripData.points}
      current={stripRow ? midOf(stripRow) : null}
      {height}
      summary={{ position: app.r2.near.position, dt: stripRow?.t != null && stripPrev?.t != null ? stripRow.t - stripPrev.t : null, hfd: stripRow?.hfd ?? null, name: stripData.name }}
      onpick={(path) => void app.r2.open(path)}
    />
  {/if}
{/snippet}

<div class="review" style:grid-template-rows="minmax(0, 1fr) {app.reviewScreen !== 'r1' && app.logOpen ? '216px' : '0px'}">
  {#if app.reviewScreen === 'r2'}
    <FrameInspector
      store={app.r2}
      tools={app.r2Tools}
      theme={app.theme}
      tint={app.viewerTint}
      saturatedColour={app.viewerSaturated}
      rotation={app.rotation}
      onrotation={(r) => app.setRotation(r)}
      fullWell={profileLimits(activeProfile).fullWell}
      profileBayer={app.camera?.sensor?.bayer ?? null}
      linkDown={app.stale}
      onback={app.r2.sessionLabel && review.kind ? () => (app.reviewScreen = 'r1') : null}
      onopenfits={() => app.reviewPickFits++}
      onallsettings={(c) => app.openSettings(c)}
      onglimitcommit={(v) => void app.patchConfig({ 'catalog.display_mag_limit': v }).catch((e) => app.reportError('Save the magnitude limit', e))}
      ontoast={(level, title, detail) => app.toast(level, title, detail ?? '')}
      shortcuts={app.shortcuts}
      strip={stripData && app.r2.sessionLabel ? frameStrip : undefined}
    />
  {:else if app.reviewScreen === 'r1' && review.kind}
    <SessionReview
      bind:this={r1El}
      source={review}
      layout={app.reviewLayout}
      theme={app.theme}
      obscode={String(app.configValues?.['observer.obscode'] ?? '') || null}
      band={String(app.configValues?.['photometry.default_band'] ?? '') || null}
      {wheel}
      shortcuts={app.shortcuts}
      notify={(level, title, message) => app.toast(level, title, message ?? '')}
      onintent={route}
      job={showStrip ? job : undefined}
      framesTab={framesTab}
      logTab={logTab}
      drawerTools={drawerTools}
    />
  {:else}
    <SessionsLanding
      bind:this={landingEl}
      page={app.landing.page}
      loading={app.landing.loading}
      error={app.landing.error}
      linkDown={app.stale}
      live={liveSource}
      recent={app.landing.recent}
      bind:query={app.landing.query}
      scope={app.landing.scope}
      {opening}
      {openError}
      onscope={(s) => app.landing.setScope(s)}
      list={app.listFiles}
      onopen={(src) => openSource(src)}
      onrefresh={() => void app.landing.load()}
      onforget={(i) => app.landing.forget(i)}
      ondismisserror={() => (openError = null)}
      onsettings={() => app.openSettings('data_storage', 'sessions_path')}
      openFitsKey={app.shortcuts.keyFor('file.open-fits')}
      shortcuts={app.shortcuts}
    />
  {/if}
  {#if app.reviewScreen !== 'r1' && app.logOpen}<LogDrawer label="Review drawer" />{/if}
</div>

{#snippet job()}
  <JobStrip
    jobs={stripJobs}
    title={jobTitle}
    unit={(j) => (j.kind === 'rerun' ? 'frames' : j.kind === 'session_open' ? 'frames' : '')}
    {resultText}
    oncancel={(id) => void app.jobs.cancel(id)}
    ondismiss={(id) => app.jobs.dismiss(id)}
    now={app.clock}
    label="Review jobs"
  >
    {#snippet actions(j)}
      {#if j.kind === 'rerun' && j.state === 'done' && parseRerunResult(j.result)}
        <IconButton icon="open-session" label="Open the new run" size="s" variant="secondary" tooltip="bottom" onclick={() => openRerunResult(j)} />
      {:else if j.kind === 'export' && j.state === 'done' && parseExportResult(j.result)?.download}
        <IconButton icon="export" label="Save the file again" size="s" variant="ghost" tooltip="bottom" onclick={() => void saveDownload(j.id, parseExportResult(j.result)?.name ?? 'export.txt')} />
      {/if}
    {/snippet}
  </JobStrip>
{/snippet}

{#snippet framesTab()}
  <FramesTable
    view={frames}
    height="100%"
    loading={review.status === 'loading'}
    onselect={(row) => {
      const t = row ? midOf(row) : null;
      if (t !== null && review.link.selection.t !== t) review.link.select(t);
    }}
    onactivate={(row) => inspect(row.path)}
    onmissing={(_row, why) => app.toast('warning', 'Frame unavailable', why)}
    oncopy={(_tsv, n) => app.toast('info', `Copied ${n} rows as TSV`)}
  />
{/snippet}

{#snippet logTab()}
  <LogView store={app.log} filter={logFilter} markSeen />
{/snippet}

{#snippet drawerTools(tab: string)}
  {#if tab === 'frames'}
    <FramesTools view={frames} oncopied={(n) => app.toast('info', `Copied ${n} frames as TSV`)} />
  {:else if tab === 'log'}
    <LogControls store={app.log} filter={logFilter} />
  {/if}
{/snippet}

{#if aavso}
  <ExportAavsoDialog
    bind:open={aavsoOpen}
    source={aavso.source}
    sourceLabel={aavso.label}
    curves={aavso.curves}
    filter={aavso.filter}
    keys={aavso.keys}
    getPreview={(b, s) => app.reviewExports.aavsoPreview(b, s)}
    start={(b, t) => app.reviewExports.exportAavso(b, t)}
    onstarted={started}
    onsettings={() => app.openSettings('observer_site', 'observer.obscode')}
    list={app.listFiles}
    filterNames={wheel}
    defaultDir={aavso.source.kind === 'session' ? aavso.source.path : null}
  />
{/if}
{#if csv}
  <ExportCsvDialog
    bind:open={csvOpen}
    source={csv.source}
    sourceLabel={csv.label}
    object={csv.object}
    curves={csv.curves}
    folder={csv.folder}
    filter={csv.filter}
    keys={csv.keys}
    start={(b, t) => app.reviewExports.exportCsv(b, t)}
    onstarted={started}
    list={app.listFiles}
    filterNames={wheel}
  />
{/if}
{#if rerun}
  <RerunDialog
    bind:open={rerunOpen}
    session={rerun.session}
    sessionLabel={rerun.label}
    liveTargets={rerun.live}
    diagnosticsDefault={app.configValues?.['diagnostics.enabled'] === true}
    getPlan={(b, s) => app.reviewExports.rerunPlan(b, s)}
    start={(b) => app.reviewExports.rerun(b)}
    onstarted={started}
    onsettings={() => app.openSettings('photometry')}
    list={app.listFiles}
    siteWarning={rerun.site}
  />
{/if}

<style>
  .review {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    height: 100%;
    min-height: 0;
    min-width: 0;
  }
</style>
