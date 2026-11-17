<!--
  R1, one session or the live run under review (spec 07 §2.1-2.4 WF-B / WF-G, 08 §2; README
  R1, M80-M92, M95-M96, D3, D5, D6). Offline and read-only: it never moves hardware and never
  edits the target set.

  - Toolbar (one row): Sessions (R0) and Open FITS; the identity (one line, ellipsis, the
    full text in its tooltip) with the readiness badge (Complete, or N issues with the list)
    or, for the live run, the Preview chip; the job strip of front-end B replaces the identity
    while a job runs; the filter shown when two or more are loaded (S49, S53); the time axis
    UTC / JD / BJD (BJD disabled without a site); U error bars, M relative flux, F fit and
    the zoom state's name; Re-run photometry…, Export CSV…, Export AAVSO…; Plots (cells, rail
    cards, Reset layout); the drawer (D) and the rail (P).
  - The plot wall (PlotWall), the rail (Selected point, Ensemble, Session, AAVSO export) and
    the drawer (Frames: front-end B's table; Ensemble: every column; Log: the app's).
  - Every action outside R1 is an intent (intents.ts) the integrator routes.
  - Keys (README 3.10, scope analyze.r1): F, + / −, U, M, ← / →, Enter, D, P through
    `shortcuts` (the app's registry); a focused cell handles its own as well.
-->
<script lang="ts">
  import { untrack, type Snippet } from 'svelte';
  import { SectionLayout } from '../app/layout.svelte';
  import Control from '../components/Control.svelte';
  import Drawer from '../components/Drawer.svelte';
  import PanelsPopover from '../components/PanelsPopover.svelte';
  import Popover from '../components/Popover.svelte';
  import Segmented from '../components/Segmented.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import Table from '../components/Table.svelte';
  import type { Column } from '../components/table';
  import { tooltip } from '../components/tooltip';
  import { filterLabel } from '../format/filter';
  import { fixed, int } from '../format/number';
  import { AXIS_LABEL, ZOOM_STEP } from '../charts/lightcurve/view.svelte';
  import type { TimeAxisMode } from '../charts/uplot/axes';
  import AavsoCard from './cards/AavsoCard.svelte';
  import EnsembleCard from './cards/EnsembleCard.svelte';
  import PointCard from './cards/PointCard.svelte';
  import SessionCard from './cards/SessionCard.svelte';
  import type { ReviewIntent } from './intents';
  import type { WallLayoutState } from './layout.svelte';
  import PlotWall from './PlotWall.svelte';
  import { aavsoChecks, airmassWrongSite, ensembleRows, pointInfo, type EnsembleRow, type PointInfo } from './rail';
  import type { ReviewSource } from './session.svelte';
  import { defaultCells } from './wall';

  interface Props {
    source: ReviewSource;
    layout: WallLayoutState;
    theme?: unknown;
    /** Settings values the cards read (observer.obscode, photometry.default_band). */
    obscode?: string | null;
    band?: string | null;
    /** The wheel's filter names (labels "IR" for the token "ir"). */
    wheel?: readonly string[];
    notify?: (kind: 'info' | 'error', title: string, message?: string) => void;
    /** The app's shortcut registry (scope analyze.r1). */
    shortcuts?: { handle(id: string, fn: (e: { key: string }) => void, when?: () => boolean): () => void };
    onintent?: (intent: ReviewIntent) => void;
    /** Front-end B's job strip: replaces the identity while a job runs. */
    job?: Snippet;
    /** Front-end B's Frames table (drawer tab "Frames"). */
    framesTab?: Snippet;
    /** The Log tab (the app's log view). */
    logTab?: Snippet;
    /** The active drawer tab's tools, right of the tabs (Frames: filter, columns, copy; Log: levels). */
    drawerTools?: Snippet<[string]>;
    /** Gallery: open the readiness popover. */
    issuesOpen?: boolean;
    /** The right rail (P); the wall has 3 columns from 1200 px without it. */
    railOpen?: boolean;
    /** Where the rail cards and the drawer are remembered (default the browser's; null: not kept). */
    prefs?: Storage | null;
    /** Open the drawer at this tab on mount (gallery; the app keeps the observer's choice). */
    drawerAt?: 'frames' | 'ensemble' | 'log' | null;
    /** Each star cell's data push (ms), for the large-session check. */
    onperf?: (ms: number, points: number) => void;
  }

  let { source, layout, theme, obscode = null, band = null, wheel = [], notify, shortcuts, onintent, job, framesTab, logTab, drawerTools, issuesOpen = $bindable(false), railOpen = $bindable(true), prefs, drawerAt = null, onperf }: Props = $props();
  /** The toolbar's width: below 1300 px (a 1280 px window), Re-run gives up its label before the identity is cut. */
  let toolbarW = $state(1440);

  const PANEL_DEFAULTS = { panels: { point: true, ensemble: true, session: true, aavso: true }, drawer: { open: false, tab: 'frames' } };
  const panels = untrack(() => (prefs === undefined ? new SectionLayout('analyze', PANEL_DEFAULTS) : new SectionLayout('analyze', PANEL_DEFAULTS, prefs)));
  untrack(() => {
    if (drawerAt) panels.setDrawer({ open: true, tab: drawerAt });
  });
  let badgeEl = $state<HTMLElement | null>(null);

  const version = $derived(source.version);
  const info = $derived(source.info);
  const kind = $derived(source.kind);
  const filter = $derived.by(() => {
    void version;
    void source.display.filter;
    return source.shownFilter();
  });
  const report = $derived.by(() => {
    void version;
    void filter;
    return source.report();
  });
  const target = $derived.by(() => {
    void version;
    return source.store.primary('target', null, filter);
  });
  const hasCurves = $derived.by(() => {
    void version;
    for (const s of source.store.stars.values()) if (s.n) return true;
    return false;
  });
  const bjdOk = $derived.by(() => {
    void version;
    const c = target?.cols;
    if (!c || !c.n) return false;
    for (let i = 0; i < c.n; i++) if (!Number.isFinite(c.bjd[i])) return false;
    return true;
  });

  // -- Identity and readiness ---------------------------------------------------------------------
  const lights = $derived(source.frames.filter((f) => f.light).length);
  const missing = $derived(source.frames.filter((f) => f.light && f.missing).length);
  const identity = $derived.by(() => {
    if (!info) return { short: source.opening ? `Opening ${source.opening}…` : 'No session', full: '' };
    if (kind === 'live') return { short: `${info.object || 'Live run'} · live run`, full: `${info.object || 'Live run'} · the live run, read-only (its points keep arriving)` };
    if (kind === 'import') return { short: `Imported · ${info.folder} · ${source.store.stars.size} curves`, full: info.path };
    const started = info.startedUtc ? info.startedUtc.slice(5, 16).replace('T', ' ') : null;
    const filters = Object.keys(info.filters).filter((f) => f && f !== '—').join(', ');
    const parts = [info.object || info.folder, started, `${int(lights)} L`, filters || null].filter(Boolean);
    return { short: parts.join(' · '), full: `${parts.join(' · ')} · ${info.path}` };
  });
  // A68 readiness issues (the core's warnings are among them, one each), then the curve problems.
  const issues = $derived([...(info?.issues ?? []), ...(info?.warnings ?? []).filter((w) => !(info?.issues ?? []).some((i) => i.includes(w))), ...source.problems.filter((p) => !(info?.issues ?? []).includes(p))]);
  const blocked = $derived(info?.readiness === 'blocked');

  // -- Selection ------------------------------------------------------------------------------------
  const point: PointInfo | null = $derived.by(() => {
    void version;
    const t = source.link.selection.t;
    if (t === null) return null;
    const c = target?.cols;
    const cad = c && c.n > 1 ? (c.t[c.n - 1] - c.t[0]) / (c.n - 1) : 30;
    return pointInfo(source.store, t, { filter, frames: source.frames, tol: Math.max(1, cad / 2), imported: kind === 'import', filtersLoaded: source.filters.length, extras: source.extras, airmassSource: source.airmassSource() });
  });
  // The airmass's source in words (RR Lyr 2026-09-25: the Settings site was wrong, so the CSV's
  // airmass is wrong and the FITS header's, from the mount, is shown).
  const airmassNote = $derived.by(() => {
    if (!point?.airmassFrom) return null;
    if (point.airmassFrom === 'header')
      return info?.siteNote ? `FITS header AIRMASS (the mount's). ${info.siteNote}${point.airmassOther ? ` The CSV says ${point.airmassOther}.` : ''}` : `FITS header AIRMASS (the photometry CSV has none)`;
    return `Photometry CSV airmass (computed for the Settings site; the AAVSO AMASS)${point.airmassOther ? `. The FITS header says ${point.airmassOther}.` : ''}`;
  });

  function step(dir: -1 | 1): void {
    const s = target ?? [...source.store.stars.values()].find((x) => x.n) ?? null;
    if (!s || !s.n) return;
    const c = s.cols;
    const t = source.link.selection.t;
    const i = t === null ? (dir > 0 ? 0 : c.n - 1) : Math.max(0, Math.min(c.n - 1, c.nearest(t) + dir));
    source.link.select(c.t[i]);
    const v = source.link.zoom.view;
    if (v && (c.t[i] < v[0] || c.t[i] > v[1])) source.link.zoom.panBy((c.t[i] - (v[0] + v[1]) / 2) / (v[1] - v[0]), true);
  }

  function openFrame(p: PointInfo | null = point): void {
    if (!p) return;
    if (p.frameReason || !p.frame?.path) {
      notify?.('info', 'Frame not available', p.frameReason ?? 'No frame at this time');
      return;
    }
    onintent?.({ kind: 'open-frame', path: p.frame.path, filename: p.frame.filename, t: p.t });
  }

  function showCell(cellId: string): void {
    if (layout.isHidden(cellId)) layout.setHidden(cellId, false);
    if (layout.expanded && layout.expanded !== cellId) layout.expanded = null;
    requestAnimationFrame(() => document.querySelector(`[data-cell="${CSS.escape(cellId)}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }));
    selectedStar = cellId;
  }
  let selectedStar = $state<string | null>(null);

  // -- Cards ------------------------------------------------------------------------------------------
  const ensemble: EnsembleRow[] = $derived.by(() => {
    void version;
    return ensembleRows(source.store, filter, report, info?.targets ?? [], info?.band ?? band);
  });
  const curveCounts = $derived.by(() => {
    void version;
    const n = { target: 0, check: 0, comparison: 0 };
    for (const s of source.store.stars.values()) if (s.n) n[s.role]++;
    return n;
  });
  const aavso = $derived.by(() => {
    void version;
    // OBSCODE and FILT are the Settings' (observer.obscode, photometry.default_band), as A77-A78.
    return aavsoChecks({ store: source.store, filter, filters: source.filters, obscode: obscode ?? info?.obscode ?? null, band: band ?? info?.band ?? null, frameFilters: info?.filters ?? {}, chartId: info?.chartId ?? null, wheel, airmassWrong: airmassWrongSite(source.airmassSource(), source.airmassFixed()) });
  });

  function targetKeys(): string[] {
    return [...source.store.stars.values()].filter((s) => s.role === 'target' && (!filter || s.filter === null || s.filter === filter)).map((s) => s.key);
  }
  /** The dialogs' one-line source ("RR Lyr · 20260925T200453Z_RR_Lyr · session photometry"). */
  const sourceLabel = $derived(
    !info ? '' : kind === 'live' ? `${info.object || 'Live run'} · the live run` : kind === 'import' ? `${info.object ? `${info.object} · ` : ''}${info.folder} · imported CSV` : `${info.object || info.folder} · ${info.folder} · session photometry`,
  );
  function exportAavso(): void {
    const ref = source.ref();
    if (ref) onintent?.({ kind: 'export-aavso', source: ref, label: sourceLabel, curves: source.curveRefs(), filter, keys: targetKeys() });
  }
  function exportCsv(): void {
    const ref = source.ref();
    if (ref) onintent?.({ kind: 'export-csv', source: ref, label: sourceLabel, curves: source.curveRefs(), object: info?.object || null, folder: kind === 'session' ? (info?.path ?? null) : null, filter, keys: [] });
  }

  // -- Toolbar values --------------------------------------------------------------------------------
  const axisOptions = $derived(
    (['utc', 'jd', 'bjd'] as TimeAxisMode[]).map((a) => ({ value: a, label: AXIS_LABEL[a], disabledReason: a === 'bjd' && !bjdOk ? 'No BJD_TDB: the observing site was not set' : null })),
  );
  const filterOptions = $derived(source.filters.map((f) => ({ value: f, label: filterLabel(f, wheel) })));
  const zoomText = $derived(source.link.mode === 'fit' ? (kind === 'live' ? 'Whole run' : 'Whole session') : 'Zoom kept · F');
  const noData = $derived(!hasCurves ? (source.status === 'loading' ? 'Opening the session' : 'No curve in this source') : null);

  const cellsForPanel = $derived.by(() => {
    void version;
    return defaultCells(source.store, filter, { filtersLoaded: source.filters.length, wheel, conditions: source.frames.length > 0 });
  });
  const panelGroups = $derived([
    { title: 'Plots', panels: cellsForPanel.map((c) => ({ id: `plot:${c.id}`, label: c.kind === 'conditions' ? 'Conditions' : c.label })) },
    { title: 'Right rail', panels: [{ id: 'point', label: 'Selected point' }, { id: 'ensemble', label: 'Ensemble' }, { id: 'session', label: 'Session' }, { id: 'aavso', label: 'AAVSO export' }] },
  ]);
  const panelVisible = (id: string) => (id.startsWith('plot:') ? !layout.isHidden(id.slice(5)) : panels.visible(id));
  const panelChange = (id: string, on: boolean) => (id.startsWith('plot:') ? layout.setHidden(id.slice(5), !on) : panels.setVisible(id, on));
  function resetLayout(): void {
    layout.reset();
    panels.reset();
    railOpen = true;
    notify?.('info', 'Review layout restored', 'Every plot and card, the default order');
  }

  const drawerTabs = $derived([...(kind === 'session' ? [{ id: 'frames', label: 'Frames', icon: 'frames' }] : []), { id: 'ensemble', label: 'Ensemble', icon: 'comparison-quality' }, ...(logTab ? [{ id: 'log', label: 'Log', icon: 'log' }] : [])]);
  const drawerTab = $derived(drawerTabs.some((t) => t.id === panels.drawer.tab) ? panels.drawer.tab : drawerTabs[0].id);

  /** Every row's scatter from the same place ("vetting report"): said once, in the column's title. */
  const fromAll = $derived.by(() => {
    const f = new Set(ensemble.map((r) => r.from));
    return f.size === 1 ? (f.has('report') ? 'vetting report' : f.has('estimate') ? 'estimate made here' : null) : null;
  });
  // AUID only when it differs from a name; "From" once in its title when every row says the
  // same; σ at the cells' 3 decimals (design review).
  const ensembleColumns: Column<EnsembleRow>[] = $derived([
    { id: 'name', label: 'Comparison', value: (r: EnsembleRow) => r.name, width: '16ch' },
    ...(ensemble.some((r) => r.auid && r.auid !== r.name) ? [{ id: 'auid', label: 'AUID', value: (r: EnsembleRow) => r.auid, width: '13ch' }] : []),
    { id: 'status', label: 'Status', value: (r: EnsembleRow) => r.status, width: '17ch' },
    { id: 'cat', label: 'Cat. mag', title: 'Catalogue magnitude in the band it calibrates with', value: (r: EnsembleRow) => r.catMag, format: (r: EnsembleRow) => fixed(r.catMag, 3), numeric: true, width: '9ch' },
    { id: 'n', label: 'Points', title: 'Points in its curve (this filter)', value: (r: EnsembleRow) => r.n, format: (r: EnsembleRow) => int(r.n), numeric: true, width: '7ch' },
    { id: 'valid', label: 'Valid', title: 'Valid points of the vetting (unsaturated, finite)', value: (r: EnsembleRow) => r.nValid, format: (r: EnsembleRow) => int(r.nValid), numeric: true, width: '6ch' },
    { id: 'scatter', label: 'Scatter', title: `Point-to-point scatter, mag (robust second differences / √6)${fromAll ? ` · from the ${fromAll}` : ''}`, value: (r: EnsembleRow) => r.scatter, format: (r: EnsembleRow) => fixed(r.scatter, 3), numeric: true, width: '8ch' },
    { id: 'err', label: 'Median err', title: 'Median formal error, mag', value: (r: EnsembleRow) => r.medianErr, format: (r: EnsembleRow) => fixed(r.medianErr, 3), numeric: true, width: '10ch' },
    ...(fromAll ? [] : [{ id: 'from', label: 'From', title: 'photometry_quality.json, or estimated here', value: (r: EnsembleRow) => (r.from === 'report' ? 'vetting report' : r.from === 'estimate' ? 'estimated' : '—'), width: '14ch' }]),
  ] as Column<EnsembleRow>[]);

  // -- Keys (the app's registry, scope analyze.r1) -----------------------------------------------------
  $effect(() => {
    const reg = shortcuts;
    if (!reg) return;
    const z = source.link.zoom;
    const offs = [
      reg.handle('r1.fit', () => z.fit(true)),
      reg.handle('r1.zoom-in', () => z.zoomBy(1 / ZOOM_STEP, undefined, true)),
      reg.handle('r1.zoom-out', () => z.zoomBy(ZOOM_STEP, undefined, true)),
      reg.handle('r1.error-bars', () => (source.display.errors = !source.display.errors)),
      reg.handle('r1.flux', () => (source.display.flux = !source.display.flux)),
      reg.handle('r1.point', (e) => step(e.key === 'ArrowLeft' ? -1 : 1)),
      reg.handle('r1.open-frame', () => openFrame(), () => source.link.selection.t !== null),
      reg.handle('drawer.toggle.other', () => panels.setDrawer({ open: !panels.drawer.open })),
      reg.handle('rail.toggle.other', () => (railOpen = !railOpen)),
    ];
    return () => offs.forEach((f) => f());
  });

  // -- What the app asks of R1 (the integrator: the palette's entries, the L key) ---------------------
  /** The palette's Re-run / Export entries: the same as the toolbar's buttons, with their reasons. */
  export function act(what: 'rerun' | 'export-aavso' | 'export-csv'): void {
    if (what === 'rerun') {
      const why = kind === 'import' ? 'An imported file has no frames to measure' : !info ? 'No session open' : null;
      if (why) notify?.('info', 'Re-run photometry unavailable', why);
      else onintent?.({ kind: 'rerun', path: kind === 'live' ? null : (info?.path ?? null), label: sourceLabel });
    } else if (noData) notify?.('info', 'Nothing to export', noData);
    else if (what === 'export-csv') exportCsv();
    else if (!targetKeys().length) notify?.('info', 'Nothing to export', 'No target curve in this filter');
    else exportAavso();
  }
  /** L in R1: the Log tab of the drawer. */
  export function logShown(): boolean {
    return !!logTab && panels.drawer.open && drawerTab === 'log';
  }
  export function showLog(open: boolean): void {
    panels.setDrawer(open ? { open: true, tab: 'log' } : { open: false });
  }

  // ← / → when the focus is on the screen but not in a cell (a cell steps by itself).
  function onKey(e: KeyboardEvent): void {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
    const el = e.target as HTMLElement | null;
    if (el && (el.closest('input, textarea, select, [role="menu"], [role="listbox"], [role="grid"], table') || el.isContentEditable)) return;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      if (el?.closest('.lc')) return;
      step(e.key === 'ArrowLeft' ? -1 : 1);
      e.preventDefault();
    }
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="r1" class:rail={railOpen} class:drawer={panels.drawer.open} style:--drawer-h="{panels.drawer.height}px" onkeydown={onKey}>
  <div class="toolbar" role="toolbar" aria-label="Review session" bind:clientWidth={toolbarW}>
    <Control icon="open-session" label="Sessions" shortcut="Mod+Shift+O" variant="ghost" tooltip="bottom" onclick={() => onintent?.({ kind: 'sessions' })} />
    <Control icon="open-image" label="Open FITS…" shortcut="Mod+O" variant="ghost" tooltip="bottom" onclick={() => onintent?.({ kind: 'open-fits' })} />
    <span class="divider" aria-hidden="true"></span>
    <!-- The identity and its readiness badge stay while a job runs (the strip takes the spacer's room). -->
    <div class="ident" aria-live="polite">
        <span class="name" use:tooltip={{ text: identity.full || identity.short }}>{identity.short}</span>
        {#if kind === 'live'}
          <span class="chip" use:tooltip={{ text: 'Live preview photometry: unregistered frames, no flat or dark. Confirm the result on calibrated frames (Siril / star_var_script).' }}>Preview</span>
        {:else if info && kind === 'session'}
          <button type="button" class="badge" bind:this={badgeEl} aria-haspopup="dialog" aria-expanded={issuesOpen} onclick={() => (issuesOpen = !issuesOpen)}>
            <StatusBadge tone={blocked ? 'error' : issues.length ? 'busy' : 'idle'} label={issues.length ? `${issues.length} ${issues.length === 1 ? 'issue' : 'issues'}` : 'Complete'} plain live={false} />
          </button>
        {:else if kind === 'import' && issues.length}
          <button type="button" class="badge" bind:this={badgeEl} aria-haspopup="dialog" aria-expanded={issuesOpen} onclick={() => (issuesOpen = !issuesOpen)}>
            <StatusBadge tone="busy" label="{issues.length} {issues.length === 1 ? 'issue' : 'issues'}" plain live={false} />
          </button>
        {/if}
    </div>
    {#if source.filters.length > 1}
      <Segmented label="Filter shown" size="s" mono options={filterOptions} value={filter ?? source.filters[0]} onchange={(f: string) => (source.display.filter = f)} />
    {/if}
    <Segmented label="Time axis" size="s" options={axisOptions} value={source.display.axis} onchange={(a: TimeAxisMode) => (source.display.axis = a)} />
    <span class="divider" aria-hidden="true"></span>
    <Control icon="error-bars" label="Error bars" shortcut="U" variant="ghost" pressed={source.display.errors} tooltip="bottom" onclick={() => (source.display.errors = !source.display.errors)} />
    <Control icon="relative-flux" label="Relative flux" shortcut="M" variant="ghost" pressed={source.display.flux} tooltip="bottom" onclick={() => (source.display.flux = !source.display.flux)} />
    <Control icon="zoom-fit" label="Fit every plot" shortcut="F" variant="ghost" tooltip="bottom" disabledReason={noData} onclick={() => source.link.zoom.fit(true)} />
    <span class="zoom" class:kept={source.link.mode !== 'fit'}>{zoomText}</span>
    {#if job}<div class="jobslot">{@render job()}</div>{:else}<span class="grow"></span>{/if}
    <Control icon="rerun-photometry" label="Re-run photometry…" showLabel={toolbarW > 1300 && !job} variant="ghost" tooltip={toolbarW > 1300 && !job ? "none" : "bottom"} disabledReason={kind === 'import' ? 'An imported file has no frames to measure' : !info ? 'No session open' : null} onclick={() => onintent?.({ kind: 'rerun', path: kind === 'live' ? null : (info?.path ?? null), label: sourceLabel })} />
    <!-- While a job shows, the secondary actions give up their words to the strip (icon and tooltip). -->
    <Control icon="export" label="Export CSV…" showLabel={!job} variant="ghost" tooltip={job ? 'bottom' : 'none'} disabledReason={noData} onclick={exportCsv} />
    <Control icon="export-aavso" label="Export AAVSO…" showLabel tooltip="none" disabledReason={noData ?? (targetKeys().length ? null : 'No target curve in this filter')} onclick={exportAavso} />
    <span class="divider" aria-hidden="true"></span>
    <PanelsPopover section="Review" groups={panelGroups} visible={panelVisible} onchange={panelChange} onreset={resetLayout} />
    <Control icon="frames" label="Drawer" shortcut="D" variant="ghost" layoutToggle pressed={panels.drawer.open} tooltip="bottom" onclick={() => panels.setDrawer({ open: !panels.drawer.open })} />
    <Control icon="panels" label="Right rail" shortcut="P" variant="ghost" layoutToggle pressed={railOpen} tooltip="bottom" onclick={() => (railOpen = !railOpen)} />
  </div>

  <div class="wall">
    <PlotWall {source} {layout} {railOpen} {theme} {wheel} {onperf} notify={(t, m) => notify?.('info', t, m)} onopenframe={() => openFrame()} />
  </div>

  {#if railOpen}
    <aside class="rail-col" aria-label="Review panels">
      {#if panels.visible('point')}
        <PointCard info={point} {airmassNote} onopenframe={(p) => openFrame(p)} onstar={showCell} onclear={() => source.link.select(null)} />
      {/if}
      <!-- WF-B: the AAVSO export card in the first screen, under the selected point. -->
      {#if panels.visible('aavso')}
        <AavsoCard checks={aavso.checks} rows={aavso.rows} blocked={aavso.blocked} onexport={exportAavso} onsettings={() => onintent?.({ kind: 'settings', category: 'observer' })} />
      {/if}
      {#if panels.visible('ensemble')}
        <EnsembleCard rows={ensemble} {report} live={kind === 'live'} selected={selectedStar} onstar={showCell} oncopy={(_t, n) => notify?.('info', `Copied ${n} rows as TSV`)} />
      {/if}
      {#if panels.visible('session')}
        <SessionCard {info} {kind} {lights} {missing} curves={curveCounts} filters={source.filters} problems={source.problems} oncopy={(t, n) => navigator.clipboard?.writeText(t).then(() => notify?.('info', `Copied ${n} rows as TSV`)).catch(() => notify?.('error', 'Copy failed', 'The clipboard is not available'))} />
      {/if}
    </aside>
  {/if}

  {#if panels.drawer.open}
    <div class="drawer-row">
      <Drawer label="Review drawer" tabs={drawerTabs} tab={drawerTab} height={panels.drawer.height} resizable closeShortcut="D" tools={drawerTools} ontab={(t) => panels.setDrawer({ tab: t })} onheight={(h) => panels.setDrawer({ height: h })} onclose={() => panels.setDrawer({ open: false })}>
        {#snippet children(tab)}
          {#if tab === 'frames'}
            {#if framesTab}{@render framesTab()}{:else}<p class="tab-empty">The Frames table is not wired in this build.</p>{/if}
          {:else if tab === 'ensemble'}
            <Table label="Comparison stars, every column" columns={ensembleColumns} rows={ensemble} rowKey={(r) => r.cellId} selected={selectedStar} density="compact" persist="review.ensemble" empty="No comparison star in this source" onselect={(r) => r && showCell(r.cellId)} oncopy={(_t, n) => notify?.('info', `Copied ${n} rows as TSV`)} />
          {:else if tab === 'log' && logTab}
            {@render logTab()}
          {/if}
        {/snippet}
      </Drawer>
    </div>
  {/if}
</div>

<Popover open={issuesOpen} anchor={badgeEl} title={issues.length ? `${issues.length} ${issues.length === 1 ? 'issue' : 'issues'} in this session` : 'Session complete'} placement="bottom-start" width={360} onclose={() => (issuesOpen = false)}>
  {#if issues.length}
    <ul class="issues">
      {#each issues as it (it)}<li>{it}</li>{/each}
    </ul>
  {:else}
    <p class="ok">Every frame listed in session.json is on disk and every curve was read.</p>
  {/if}
</Popover>

<style>
  .r1 {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: var(--toolbar-h) minmax(0, 1fr);
    height: 100%;
    min-height: 0;
    min-width: 0;
    background: var(--bg);
  }
  .r1.rail {
    grid-template-columns: minmax(0, 1fr) var(--rail-w);
  }
  .r1.drawer {
    grid-template-rows: var(--toolbar-h) minmax(0, 1fr) auto;
  }
  .toolbar {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    gap: var(--space-1);
    min-width: 0;
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg);
  }
  .divider {
    width: 1px;
    height: 20px;
    margin: 0 var(--space-1);
    background: var(--border-soft);
    flex: none;
  }
  .grow {
    flex: 1 1 0;
    min-width: var(--space-2);
  }
  .ident {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex: 0 1 auto;
    min-width: 120px;
    max-width: 42%;
  }
  /* A job's strip takes the spacer's room; the identity may shrink to its minimum, never go. */
  .jobslot {
    display: flex;
    flex: 1 1 0;
    min-width: 220px;
  }
  .jobslot > :global(.strip) {
    flex: 1 1 0;
    min-width: 0;
  }
  .name {
    min-width: 0;
    overflow: hidden;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .badge {
    flex: none;
    padding: 0;
    border: 0;
    border-radius: var(--radius-s);
    background: none;
    cursor: pointer;
  }
  .badge:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
  .chip {
    flex: none;
    padding: 0 6px;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    color: var(--fg-muted);
    font-size: var(--text-xs);
    line-height: 18px;
  }
  .zoom {
    flex: none;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .zoom.kept {
    color: var(--fg);
  }
  .wall {
    min-width: 0;
    min-height: 0;
  }
  .rail-col {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-height: 0;
    min-width: 0;
    padding: var(--space-3);
    border-left: var(--border-w) solid var(--border);
    background: var(--bg-2);
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .drawer-row {
    grid-column: 1 / -1;
    min-width: 0;
  }
  .tab-empty {
    margin: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .issues {
    margin: 0;
    padding-left: var(--space-4);
    color: var(--fg);
    font-size: var(--text-s);
    line-height: var(--leading-relaxed);
  }
  .ok {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>
