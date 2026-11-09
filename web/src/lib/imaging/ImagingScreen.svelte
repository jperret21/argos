<!--
  Observe (imaging) screen: toolbar with the task modes (owner decision D1:
  Framing, Focus; Field and Run listed, unavailable in this version); the
  16-bit image viewer with its HUD (frame chips, cursor readout, D6); the task
  band under the image, whose content follows the mode (Framing: levels and
  exposure check; Focus: V-curve and HFD trend), sized by bandLayout (BRAND
  11.1: exactly the space the fitted frame leaves, unless the observer dragged
  it); the drawer (Conditions, Log); the right rail of cards. Each mode
  remembers its rail width, card states, band and drawer (imaging/modes).
  Separators are 1 px lines with a 7 px hit area (WAI-ARIA window splitters,
  app/attachments/splitter.ts); while one is dragged the HUD says what the
  layout costs.
  The Connection card left the rail (D10): the toolbar's equipment button
  connects or disconnects everything, the details live on the Connection
  screen (F1).

  Wave 4 viewer tools (web/spec/04-viewer-and-image-tools.md; viewer/tools,
  viewer/palettes, viewer/hud): View options in the band header of every mode
  (CFA preview, palette, rotation, crosshair, loupe, clipping), the loupe (Z),
  the saturation highlight (C), the region box (R) and the Statistics card (I,
  hidden by default, D9), the context menu, the N / E compass and the scale bar
  once the field has a WCS, and the Field mode.

  Wave 4 field (web/spec/03-observe-page.md 2.2-2.4; imaging/field, viewer/overlay): the
  catalogue layers, grid, target reticle and roles drawn over the image in screen space
  (FieldOverlay), moved by the per-frame tracking transform (A48); a click identifies or
  measures what is under it (A49) and opens the star card, whose role buttons write the
  target set (A52, Undo toast); the HUD field chip says the field state in words; the Field
  band holds the candidates table, the Inspector card the picked star. S identifies the
  field, G the grid, N the labels, O the Catalogue layers popover; Escape also closes the
  star card (and still aborts a slew).

  Single-key shortcuts (icon-inventory.json, BRAND section 7) are bound in
  the one registry (scope "imaging", active while this screen is shown):
  they only fire when focus is not in a text field and never move hardware;
  Escape aborts a slew (global binding, D21). Tracking keeps no single key
  (the inventory proposes T, but starting or stopping the sidereal drive
  moves the mount).

  A frame that is not current (equipment disconnected, server link down, or
  no new frame for max(5 s, three exposures)) says so: its source chip reads
  "Last frame · 21:34:05 UTC", the frame edge is dashed, and a prompt to
  connect sits at the bottom of the image, never over its centre.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { splitter } from '../app/attachments/splitter';
  import { useApp } from '../app/state.svelte';
  import ConditionsTimeline from '../charts/ConditionsTimeline.svelte';
  import ConditionsTools from '../charts/ConditionsTools.svelte';
  import Icon from '../components/Icon.svelte';
  import IconButton from '../components/IconButton.svelte';
  import { seconds } from '../format/number';
  import LogDrawer from '../shell/LogDrawer.svelte';
  import FitsViewer from '../viewer/FitsViewer.svelte';
  import { clipping } from '../viewer/framestats';
  import Hud from '../viewer/Hud.svelte';
  import { cursorReadout, frameChips, miniHistogram, showMiniHistogram, type FrameHeaderV3 } from '../viewer/hud';
  import { displaySize, effectiveTurns } from '../viewer/rotation';
  import { formatDec, formatRA } from '../format/astro';
  import { frameKind } from '../viewer/palettes/cfa';
  import { effectivePalette } from '../viewer/palettes/lut';
  import { fromFrameWcs, pixelToSky, trackedWcs, COMPASS_SIZE, type FieldMotion, type TanWcs } from '../viewer/hud/wcs';
  import type { ViewerGeometry } from '../viewer/tools/geometry';
  import { composeView, download, viewFileName } from '../viewer/tools/exportview';
  import Marks from '../viewer/tools/Marks.svelte';
  import RegionTool from '../viewer/tools/RegionTool.svelte';
  import StatisticsCard from '../viewer/tools/StatisticsCard.svelte';
  import ViewerMenu from '../viewer/tools/ViewerMenu.svelte';
  import type { ViewerMenuAction } from '../viewer/tools/viewermenu';
  import ViewOptions from '../viewer/tools/ViewOptions.svelte';
  import Card from '../components/Card.svelte';
  import { openLayers, ownsEscape } from '../components/layers';
  import type { HudChip } from '../viewer/hud';
  import FieldOverlay, { type SelectAt } from '../viewer/overlay/FieldOverlay.svelte';
  import type { LayerId, Marker, Role } from '../viewer/overlay/layers';
  import { applyTransform, placeRing, type ScreenMap } from '../viewer/overlay/project';
  import { candidateRows, ensembleRows as fieldEnsembleRows, type CandidateRow } from './field/candidates';
  import LightCurvePlot from '../charts/lightcurve/LightCurvePlot.svelte';
  import { LiveCurveStore } from '../charts/lightcurve/store';
  import type { TimeAxisMode } from '../charts/uplot/axes';
  import { loadPref, savePref } from '../app/prefs';
  import EnsembleTable from './photometry/EnsembleTable.svelte';
  import EnsembleVerdict from './photometry/EnsembleVerdict.svelte';
  import LightCurveTab from './photometry/LightCurveTab.svelte';
  import LiveStatus from './photometry/LiveStatus.svelte';
  import PhotometryCard from './photometry/PhotometryCard.svelte';
  import { countLine, curveFor, ensembleRows, ensembleTsv, filterVariables, measuredCount, minPoints, statusLine, verdict as verdictOf, type EnsembleRow } from './photometry/present';
  import type { FieldVariable, RecommendMode } from './photometry/types';
  import RecommendPopover from './photometry/RecommendPopover.svelte';
  import VariablesTab from './photometry/VariablesTab.svelte';
  import ConfirmDialog from '../components/ConfirmDialog.svelte';
  import type { TargetStar } from './field/types';
  import InspectorCard from './field/InspectorCard.svelte';
  import { cardText, fieldChip } from './field/present';
  import StarCard from './field/StarCard.svelte';
  import type { Selection } from './field/types';
  import CameraCard from './CameraCard.svelte';
  import FocuserCard from './FocuserCard.svelte';
  import ImagingToolbar from './ImagingToolbar.svelte';
  import Band from './modes/Band.svelte';
  import DisplayTools from './modes/DisplayTools.svelte';
  import { exposureCheck, profileLimits, recent } from './modes/exposure';
  import FieldBand from './field/FieldBand.svelte';
  import FocusBand from './modes/FocusBand.svelte';
  import FramingBand from './modes/FramingBand.svelte';
  import { BAND, bandLayout, bandMax, DRAWER_TABS, drawerHeight, layoutCost, RAIL, type CardId, type DrawerTab } from './modes/layout';
  import MountCard from './MountCard.svelte';

  interface Props {
    perf?: boolean;
  }

  let { perf = false }: Props = $props();
  /** Stars an exposure-check row hovers (frame px), ringed on the image (W3 leftover). */
  let exposureMark = $state.raw<{ x: number; y: number }[] | null>(null);
  const app = useApp();
  let viewer: FitsViewer | undefined = $state();
  /** The Catalogue layers popover of the toolbar (O). */
  let catalogueOpen = $state(false);

  const ZOOM_STEP = 1.5;
  const ws = app.observe;
  const hasFrame = $derived(!!app.shown);
  const seq = $derived(app.shown?.frame.header.seq ?? 0);
  const header = $derived((app.shown?.frame.header ?? null) as FrameHeaderV3 | null);

  // -- Layout: the band takes the space under the fitted frame (BRAND 11.1) ----
  let centerW = $state(0);
  let centerH = $state(0);
  let stageW = $state(0);
  let stageH = $state(0);
  let dragging = $state<'band' | 'drawer' | 'rail' | null>(null);

  /** Displayed (rotated) frame size: the frame on screen, else the sensor, else a Seestar's. */
  const displayed = $derived.by(() => {
    let w = header?.width;
    let h = header?.height;
    const sensor = app.cameraReady ? app.camera?.sensor : null;
    if (!w || !h) [w, h] = sensor ? [sensor.width, sensor.height] : [1080, 1920];
    return displaySize(w, h, effectiveTurns(app.rotation, w, h));
  });
  const layout = $derived(ws.layout);
  const center = $derived({ width: centerW, height: centerH });
  const drawerH = $derived(drawerHeight(layout, centerH));
  const band = $derived(bandLayout(center, displayed, drawerH, layout.bandOpen, layout.bandH));
  /** The height that fits the image (the band's detent and its reset value). */
  const bandFit = $derived(bandLayout(center, displayed, drawerH, true, null).height);
  const railW = $derived(layout.railOpen ? layout.railW : 0);

  // What a separator costs while it is dragged, on the image (PROPOSAL 2.5).
  $effect(() => {
    const what = dragging;
    const b = band;
    const text = what ? layoutCost(what, b, { drawer: drawerH, rail: layout.railW, fits: layout.bandH === null }) : null;
    if (ws.dragReadout !== text) ws.dragReadout = text;
  });

  // A press on the image ends typing in a field (the viewer keeps the pointer for
  // panning, so the browser would leave the focus in the field and the single-key
  // shortcuts would stay off): the field blurs, which commits it (README 3.4).
  let stageEl: HTMLDivElement | undefined = $state();
  $effect(() => {
    const el = stageEl;
    if (!el) return;
    const onDown = () => {
      const a = document.activeElement as HTMLElement | null;
      if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA') && !el.contains(a)) a.blur();
    };
    el.addEventListener('pointerdown', onDown, true);
    return () => el.removeEventListener('pointerdown', onDown, true);
  });

  // -- HUD (viewer/hud.ts) -------------------------------------------------------
  const stale = $derived(app.frameStale);
  /** "1.0 → 2.0 s" while a live change waits for the next frame. */
  const exposureChip = $derived.by(() => {
    if (!header) return '';
    if (app.livePending && !stale && Math.abs(app.exposure - header.exposure_s) > 1e-9) {
      return `${seconds(header.exposure_s).replace(' s', '')} → ${seconds(app.exposure)}`;
    }
    return seconds(header.exposure_s);
  });
  /** Fill mode is cropping the frame: never hidden (BRAND 11.1). */
  const filling = $derived.by(() => {
    const r = app.imageRect;
    if (!r || !app.fitted || app.fitMode !== 'fill') return false;
    return r.width > stageW + 0.5 || r.height > stageH + 0.5;
  });

  function zoom(action: 'in' | 'out' | 'fit' | 'fill' | '1to1'): void {
    if (!viewer) return;
    if (action === 'in') viewer.zoomBy(ZOOM_STEP);
    else if (action === 'out') viewer.zoomBy(1 / ZOOM_STEP);
    else if (action === 'fit' || action === 'fill') {
      app.setFitMode(action);
      viewer.fit();
    } else viewer.oneToOne();
  }

  const frameChipList = $derived(
    frameChips(
      {
        header,
        live: app.live && !stale,
        exposing: app.camera?.state === 'exposing' && !stale,
        stale,
        object: app.observation?.object_name || null,
        savedName: app.lastSaved && header && app.lastSaved.frame_seq === header.seq ? app.lastSaved.name : null,
        cropped: filling,
        exposureText: exposureChip,
        afRunning: app.autofocusRunning,
      },
      seconds,
    ),
  );
  // The field chip (03 2.4): after the frame chips, in words (never colour alone). Shown in
  // Field mode, and in the other modes once something happened (solving, solved, failed, moved).
  const solveJob = $derived(app.field.solving ? app.jobs.latest('field_solve') : null);
  const fieldHud = $derived.by((): HudChip | null => {
    const f = app.field;
    const state = f.field?.state ?? 'none';
    if (!hasFrame || (state === 'none' && ws.mode !== 'field' && !f.field?.auto)) return null;
    const c = fieldChip(f.field, f.catalog, f.activeTransform);
    const stage = solveJob && (solveJob.state === 'running' || solveJob.state === 'queued') ? solveJob.stage : null;
    return {
      id: 'field',
      text: stage ? `${c.text} · ${stage}` : c.text,
      title: c.tone === 'busy' && f.solving ? `${c.title}. The toolbar's Identify field button cancels it.` : c.title,
      kind: 'text',
      dot: c.tone === 'busy' ? 'busy' : null,
      icon: c.tone === 'warn' ? 'attention' : state === 'solved' || (f.solved && state !== 'failed') ? 'plate-solve' : undefined,
    };
  });
  /** The frame centre in RA / Dec, shown with the grid (04 2.1 E3 "centre label"; tracked WCS). */
  const centreHud = $derived.by((): HudChip | null => {
    if (!fieldWcs || !header || !app.field.visibility.grid) return null;
    const c = pixelToSky(fieldWcs, (header.width - 1) / 2, (header.height - 1) / 2);
    return c ? { id: 'centre', text: `Centre ${formatRA(c.raHours)} ${formatDec(c.decDeg)}`, kind: 'num', title: 'Centre of the frame on screen (plate solution, J2000)' } : null;
  });
  const chips = $derived([...frameChipList, ...(fieldHud ? [fieldHud] : []), ...(centreHud ? [centreHud] : [])]);
  /**
   * The bottom prompt (no equipment, link lost) sits above the cursor readout row, which the
   * HUD keeps 8 px inside the image's bottom edge (Hud.svelte): never under it at 1280 px or
   * with a tall drawer (wave 5 design review).
   */
  const promptBottom = $derived.by(() => {
    const r = app.imageRect;
    const hudBottom = Math.max(8, stageH - Math.min(stageH, (r?.top ?? 0) + (r?.height ?? stageH)) + 8);
    return hudBottom + 34 + 8;
  });
  const cursor = $derived.by(() => {
    const p = app.pointer;
    const s = p && fieldWcs ? pixelToSky(fieldWcs, p.x, p.y) : null;
    return cursorReadout(p, s ? { ra: formatRA(s.raHours), dec: formatDec(s.decDeg, 1) } : null);
  });
  const mini = $derived(
    showMiniHistogram(ws.mode, layout.bandOpen) ? miniHistogram(app.shown?.histogram ?? null, app.levels) : null,
  );

  // -- Band content ---------------------------------------------------------------
  const activeProfile = $derived(app.profiles?.profiles.find((p) => p.key === app.profiles?.active) ?? null);
  const limits = $derived(profileLimits(activeProfile));

  // -- Viewer tools (W4: viewer/tools, viewer/palettes) ---------------------------------
  const tools = app.viewTools;
  let geometry = $state.raw<ViewerGeometry | null>(null);
  /** The CFA pattern of the frame on screen (its header, else the camera profile's). */
  const bayer = $derived(header?.bayer !== undefined ? (header?.bayer ?? null) : (app.camera?.sensor?.bayer ?? null));
  const kind = $derived(frameKind(header?.channels ?? 1, bayer));
  const nightRed = $derived(app.theme === 'night-red');
  const saturation = $derived(tools.saturation && limits.fullWell !== null ? { threshold: limits.fullWell, colour: app.viewerSaturated } : null);

  // The region box is measured on the frame on screen (raw samples), at each frame and move.
  $effect(() => {
    void tools.region;
    void tools.regionRect;
    const f = app.shown?.frame ?? null;
    const b = bayer;
    const t = limits.fullWell;
    untrack(() => tools.measure(f, { bayer: b, threshold: t }));
  });

  /** I: the Statistics card shown (and the rail with it) or hidden again (D9). */
  function toggleStatistics(): void {
    const show = layout.cards.statistics === 'hidden';
    ws.setCard('statistics', show ? 'open' : 'hidden');
    if (show && !layout.railOpen) ws.toggleRail();
  }

  function toggleRegion(): void {
    tools.toggleRegion(header ? { width: header.width, height: header.height } : null);
  }

  /** The field's WCS for the frame on screen (the tracking transform applied), when solved. */
  const fieldWcs = $derived.by((): TanWcs | null => {
    const f = app.field;
    const w = f.solved ? fromFrameWcs(f.field?.wcs ?? null) : null;
    // A WCS of another frame geometry (an opened file of another size) is not this frame's.
    const shape = f.field?.wcs && (f.field.wcs as { frame_shape?: number[] }).frame_shape;
    if (!w || (shape && header && (shape[0] !== header.height || shape[1] !== header.width))) return null;
    return trackedWcs(w, f.activeTransform as FieldMotion | null);
  });
  const sky = $derived(
    fieldWcs && geometry ? { wcs: fieldWcs, frame: geometry.frame, turns: geometry.turns, scale: geometry.view.scale } : null,
  );
  // -- Field: overlay, star card, Inspector (W4) ------------------------------------------------
  const field = app.field;
  /** Frame px -> stage px, from the viewer's geometry (as FieldOverlay computes it). */
  const screenMap = $derived.by((): ScreenMap | null => {
    const g = geometry;
    if (!g || !(g.frame.width > 0)) return null;
    const d = displaySize(g.frame.width, g.frame.height, g.turns);
    return { rect: { left: g.view.tx, top: g.view.ty, width: d.width * g.view.scale, height: d.height * g.view.scale }, frame: g.frame, turns: g.turns };
  });
  const sel = $derived(field.selection?.selection ?? null);
  /** The set's star the selection is (by key, else within 2″ of its catalogue position). */
  const selStar = $derived.by(() => {
    if (!sel) return null;
    const stars = field.targets?.stars ?? [];
    const byKey = sel.key ? stars.find((s) => s.key === sel.key) : null;
    if (byKey) return byKey;
    const p = sel.pending_star;
    if (!p || !Number.isFinite(p.ra_deg) || !Number.isFinite(p.dec_deg)) return null;
    const cosd = Math.cos((p.dec_deg * Math.PI) / 180);
    return stars.find((s) => s.ra_deg != null && Math.hypot((s.ra_deg - p.ra_deg) * cosd, s.dec_deg - p.dec_deg) * 3600 < 2) ?? null;
  });
  /** The card follows the set: a role given or removed here or elsewhere shows at once (P20). */
  const cardSel = $derived.by((): Selection | null => {
    if (!sel) return null;
    if (!field.targets) return sel;
    return { ...sel, key: selStar?.key ?? sel.key, role: selStar?.role ?? null, removable: !!selStar };
  });
  const cardAt = $derived(screenMap && sel?.ring ? placeRing(screenMap, field.activeTransform, sel.ring) : null);
  // The toast column sits at the bottom left of the stage, above the scale bar (HUD), so an
  // Undo toast never covers the rail's controls right after a role change.
  $effect(() => {
    const el = stageEl;
    void stageW;
    void stageH;
    void band.viewer;
    if (!el) return;
    const r = el.getBoundingClientRect();
    app.toastAnchor = { left: Math.round(r.left + 12), bottom: Math.round(window.innerHeight - r.bottom + 40) };
  });
  $effect(() => () => {
    app.toastAnchor = null;
  });
  // Framing and Focus keep their own layer toggles (the grid and the set by default).
  $effect(() => {
    app.field.mode = ws.mode;
  });
  /** The set's target (the card's facts give the separation from it). */
  const cardTarget = $derived.by(() => {
    const t = field.targets?.stars.find((x) => x.role === 'target');
    if (!t || typeof t.dec_deg !== 'number') return null;
    const ra = typeof t.ra_hours === 'number' ? t.ra_hours : typeof t.ra_deg === 'number' ? t.ra_deg / 15 : null;
    return ra === null ? null : { ra_hours: ra, dec_deg: t.dec_deg };
  });
  /** One star in two catalogues: the VSP candidate at the same position names it too. */
  const cardAlias = $derived.by(() => {
    const p = sel?.pending_star;
    if (!p || sel?.kind === 'vsp' || typeof p.dec_deg !== 'number') return null;
    const ra = typeof p.ra_hours === 'number' ? p.ra_hours : p.ra_deg / 15;
    const cosd = Math.cos((p.dec_deg * Math.PI) / 180);
    const c = field.candidates.find(
      (k) => typeof k.ra_hours === 'number' && typeof k.dec_deg === 'number' && Math.hypot((k.ra_hours - ra) * 15 * cosd, k.dec_deg - p.dec_deg) * 3600 < 2,
    );
    return c?.auid ? `VSP ${c.auid}` : null;
  });
  let busyRole = $state<Role | 'remove' | null>(null);
  const ROLE_WORDS: Record<Role, string> = { target: 'Target', comparison: 'Comparison', check: 'Check star' };

  async function onSelect(at: SelectAt): Promise<void> {
    // A catalogue candidate clicked on the image goes to the Inspector too.
    const k = at.hit?.marker.key;
    if (k && field.candidates.some((c) => c.key === k)) field.inspect(k);
    try {
      await field.select(app.client, { x: at.x, y: at.y, seq: header?.seq ?? undefined, tol_px: at.tol_px });
    } catch (err) {
      app.reportError('Identify the star', err);
    }
  }

  async function setRole(role: Role): Promise<void> {
    const s = cardSel;
    if (!s || busyRole) return;
    busyRole = role;
    try {
      const before = new Set((field.targets?.stars ?? []).map((x) => x.key));
      const { set, undo } = await field.setRole(app.client, role, { selection: s.id, key: s.key });
      const star = set?.stars.find((x) => x.key === s.key) ?? set?.stars.find((x) => !before.has(x.key) && x.role === role);
      const name = star?.display_name || star?.name || cardText(s).title || 'the star';
      const file = set?.path ? set.path.split(/[\\/]/).slice(-2).join('/') : null;
      if (undo) app.undo.push({ title: `${ROLE_WORDS[role]}: ${name}`, detail: file ? `Written to ${file}` : undefined, group: 'roles', undo: () => undo.run() });
    } catch (err) {
      app.reportError(ROLE_WORDS[role], err);
    } finally {
      busyRole = null;
    }
  }

  async function removeRole(): Promise<void> {
    const s = cardSel;
    if (!s?.key || busyRole) return;
    busyRole = 'remove';
    try {
      const { undo } = await field.remove(app.client, s.key);
      if (undo) app.undo.push({ title: `Removed from the target set: ${cardText(s).title}`, group: 'roles', undo: () => undo.run() });
    } catch (err) {
      app.reportError('Remove from the set', err);
    } finally {
      busyRole = null;
    }
  }

  /** A star picked in a list (Candidates, Variables, Stars) is selected on the image (its card, A49). */
  function pickAt(x: number, y: number): void {
    const p = applyTransform(field.activeTransform, x, y, header ? { width: header.width, height: header.height } : null);
    const tol = geometry ? 10 / geometry.view.scale : 20;
    void field.select(app.client, { x: p.x, y: p.y, seq: header?.seq ?? undefined, tol_px: tol }).catch((err) => app.reportError('Identify the star', err));
  }
  function listPick(_layer: LayerId, m: Marker): void {
    pickAt(m.x, m.y);
  }
  function rowPick(r: CandidateRow): void {
    if (r.x !== null && r.y !== null) pickAt(r.x, r.y);
  }

  // -- Live photometry (W5, imaging/photometry): card, drawer tabs, Field band status ----------
  const phot = app.photometry;
  const setStars = $derived(field.targets?.stars ?? []);
  const photTarget = $derived(setStars.find((s) => s.role === 'target') ?? null);
  const photLine = $derived(
    statusLine({
      status: phot.status,
      connected: app.health === 'ok',
      solved: field.solved,
      hasTarget: !!photTarget,
      comparisons: setStars.filter((s) => s.role === 'comparison').length,
      points: photTarget ? measuredCount(curveFor(phot.curves, photTarget)) : 0,
    }),
  );
  const photVerdict = $derived(verdictOf(phot.quality));
  /** The field's words for a set star (Δ(B−V), far, clipped, blended, variable?), by key. */
  const fieldFlags = $derived.by(() => {
    const rows = fieldEnsembleRows(field.candidates, setStars, app.shown ? clipping(app.shown.histogram, null).topCode : null, field.layers?.limits ?? null);
    return new Map(rows.map((r) => [r.key, r.flags]));
  });
  const ensRows = $derived(ensembleRows(setStars, phot.quality, { flagsOf: (s) => fieldFlags.get(s.key) ?? [], lastJd: phot.status?.last?.jd_utc ?? null, curves: phot.curves }));
  /** The set star hovered on the image marks its row (TargetSetList, Ensemble). */
  const setHotKey = $derived(field.hover?.source === 'image' ? field.hover.key : null);
  let removingKey = $state<string | null>(null);
  let confirmRemove = $state<TargetStar | null>(null);
  let recommendBusy = $state<RecommendMode | null>(null);
  const cfgNum = (k: string) => {
    const v = app.configValues?.[k];
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
  };
  const recommendReason = $derived(app.recommendProblem());

  /** A set star hovered in a list rings it on the image (reference px, moved by the tracking). */
  function hoverStar(s: { key: string; x?: number | null; y?: number | null } | null): void {
    if (!s || typeof s.x !== 'number' || typeof s.y !== 'number') return field.setHover(null, 'list');
    field.setHover({ source: 'list', key: s.key, points: [{ x: s.x, y: s.y }], reference: true });
  }
  /** A set star picked in a list: its card on the image (A49) and the Inspector. */
  function pickStar(s: { key: string; x?: number | null; y?: number | null }): void {
    if (field.candidates.some((c) => c.key === s.key)) field.inspect(s.key);
    if (typeof s.x === 'number' && typeof s.y === 'number') pickAt(s.x, s.y);
  }
  /** Remove = immediate + Undo; during a run the zero point changes, so ask first (D24, 08 P12). */
  function askRemove(s: TargetStar): void {
    if (phot.running) confirmRemove = s;
    else void removeStar(s);
  }
  async function removeStar(s: TargetStar): Promise<void> {
    if (removingKey) return;
    removingKey = s.key;
    try {
      const { undo } = await field.remove(app.client, s.key);
      const name = s.display_name || s.name || s.auid || s.key;
      if (undo) app.undo.push({ title: `Removed from the target set: ${name}`, group: 'roles', undo: () => undo.run() });
    } catch (err) {
      app.reportError('Remove from the set', err);
    } finally {
      removingKey = null;
    }
  }
  /** A58: complete the ensemble or replace the VSP picks (ArgosApp, shared with the palette). */
  async function recommend(mode: RecommendMode, count: number): Promise<void> {
    recommendBusy = mode;
    try {
      await app.recommendComparisons(mode, count);
    } finally {
      recommendBusy = null;
    }
  }
  /** A variable from the Variables tab becomes the target (A52 `variable_index`), with Undo. */
  let variableBusy = $state(false);
  async function variableTarget(v: FieldVariable): Promise<void> {
    if (variableBusy) return;
    variableBusy = true;
    try {
      const { set, undo } = await field.setRole(app.client, 'target', { variableIndex: v.index, key: v.key });
      const auto = set?.auto_selected?.length ?? 0;
      const file = set?.path ? set.path.split(/[\\/]/).slice(-2).join('/') : null;
      if (undo) {
        app.undo.push({
          title: `Target: ${v.name}${auto ? ` · ${auto} comparison${auto === 1 ? '' : 's'} chosen` : ''}`,
          detail: file ? `Written to ${file}` : undefined,
          group: 'roles',
          undo: () => undo.run(),
        });
      }
    } catch (err) {
      app.reportError('Set as target', err);
    } finally {
      variableBusy = false;
    }
  }
  /** D7: the Variables filter drives the image's variable markers. */
  $effect(() => {
    const q = field.variableQuery;
    const lim = field.variableMagLimit;
    const rows = phot.variables?.rows ?? null;
    const shown = rows && (q.trim() || (lim !== null && lim > 0)) ? new Set(filterVariables(rows, q, lim).map((r) => r.index)) : null;
    untrack(() => (field.variablesShown = shown));
  });
  const shownMarkers = $derived.by(() => {
    const l = field.layersAvailable ? field.layers?.layers : null;
    const keep = field.variablesShown;
    if (!l || !keep || !l.variables) return l;
    return { ...l, variables: l.variables.filter((m) => m.index === undefined || keep.has(m.index)) };
  });
  function copyText(text: string, what: string, n: number): void {
    void navigator.clipboard
      .writeText(text)
      .then(() => app.toast('info', `Copied ${n} ${what}`, 'Tab-separated, ready to paste in a spreadsheet'))
      .catch((err: unknown) => app.reportError('Copy', err));
  }
  function copyEnsemble(): void {
    copyText(ensembleTsv(ensRows, { ra: formatRA, dec: (d) => formatDec(d) }), ensRows.length === 1 ? 'row' : 'rows', ensRows.length);
  }
  /** The plot's time axis, error bars and flux view, remembered per viewer (README 3.11). */
  let lcAxis = $state<TimeAxisMode>(loadPref('argos.lightcurve.axis', (v): v is TimeAxisMode => v === 'utc' || v === 'jd' || v === 'bjd', 'utc'));
  let lcErrors = $state(loadPref('argos.lightcurve.errors', (v): v is boolean => typeof v === 'boolean', true));
  let lcFlux = $state(loadPref('argos.lightcurve.flux', (v): v is boolean => typeof v === 'boolean', false));
  $effect(() => savePref('argos.lightcurve.axis', lcAxis));
  $effect(() => savePref('argos.lightcurve.errors', lcErrors));
  $effect(() => savePref('argos.lightcurve.flux', lcFlux));
  /** The plot's own store (charts/lightcurve), fed by the validated stream. */
  const curveStore = new LiveCurveStore();
  // The wire types are shared (types.ts records are assignable to the plot store's): no cast.
  // Subscribed once (untracked): feed() reads the held curves, and an effect that re-ran on every
  // point would reload the whole plot per frame (Qt's S19) and lose its catalogue offsets.
  $effect(() => untrack(() => phot.feed({ load: (s) => curveStore.load(s), apply: (ev) => curveStore.apply(ev), reset: (ev) => curveStore.reset(ev) })));
  $effect(() => {
    const stars = setStars;
    const band = phot.live?.band ?? null;
    untrack(() => curveStore.applyTargets(stars, band));
  });
  /** The card's drawer buttons: open the tab, or close the drawer when it is on screen. */
  function drawerTab(id: 'light-curve' | 'variables' | 'ensemble'): void {
    ws.toggleDrawer(id);
  }

  /** The Inspector shows the star the card is about (when it is a candidate) and the band's pick. */
  $effect(() => {
    const k = cardSel?.key;
    if (k && untrack(() => field.candidates.some((c) => c.key === k) && field.inspected !== k)) untrack(() => field.inspect(k));
  });
  const inspRows = $derived(
    candidateRows(field.candidates, 'candidates', app.shown ? clipping(app.shown.histogram, null).topCode : null, { limits: field.layers?.limits, stars: field.targets?.stars ?? [] }),
  );
  const inspRow = $derived(inspRows.find((r) => r.key === field.inspected) ?? null);
  const inspAt = $derived(
    inspRow && inspRow.x !== null && inspRow.y !== null && header ? applyTransform(field.activeTransform, inspRow.x, inspRow.y, { width: header.width, height: header.height }) : null,
  );
  /** History chips: a short ID ("BCG-523": the sequence prefix tells AAVSO charts apart) and the role. */
  const inspHistory = $derived(
    field.history.map((k) => {
      const r = inspRows.find((row) => row.key === k);
      const name = r?.name ?? k;
      return { key: k, label: name.split('-').slice(-2).join('-'), name, role: r?.role ?? null };
    }),
  );
  const geom = $derived(field.targets?.geometry ?? null);

  /** Inspector card (rail): shown when hidden, opened when folded. */
  function showInspector(): void {
    if (layout.cards.inspector !== 'open') ws.setCard('inspector', 'open');
    if (!layout.railOpen) ws.toggleRail();
  }

  // Escape closes the star card when nothing above it takes the key (a menu, a popover, a
  // dialog, a field with a draft); the registry's binding still aborts a slew (D21).
  $effect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || !field.selection || openLayers().length || ownsEscape(e.target)) return;
      void field.clearSelection(app.client);
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  });

  /** The loupe sits under the compass when the compass is shown. */
  const loupeTop = $derived(sky ? Math.max(0, app.imageRect?.top ?? 0) + 8 + COMPASS_SIZE + 8 : 8);

  async function menuAction(action: ViewerMenuAction, pixel: { x: number; y: number } | null): Promise<void> {
    if (action === 'fit') zoom('fit');
    else if (action === 'one') zoom('1to1');
    else if (action === 'region' && pixel && header) tools.regionAt({ width: header.width, height: header.height }, pixel);
    else if (action === 'identify' && pixel && geometry) {
      // The same request as a click on the star (A49): 10 screen px of tolerance at this zoom.
      await app.field
        .select(app.client, { x: pixel.x, y: pixel.y, seq: header?.seq ?? null, tol_px: 10 / geometry.view.scale })
        .catch((err) => app.reportError('Measure / identify', err));
    } else if (action === 'clear') await app.field.clearSelection(app.client);
    else if (action === 'save-png') {
      const v = stageEl?.querySelector<HTMLElement>('[role="application"]');
      const pic = viewer?.snapshot();
      if (!stageEl || !v || !pic) return;
      const blob = await composeView(stageEl, v, pic);
      if (blob) download(blob, viewFileName(header?.seq ?? null));
      else app.toast('error', 'Save view as PNG', 'The browser could not encode the picture');
    }
  }

  const clip = $derived(app.shown && ws.mode === 'framing' ? clipping(app.shown.histogram, limits.linearity) : null);
  const check = $derived(
    exposureCheck({
      seq: header?.seq ?? null,
      peaks: app.frameStats?.peaks ?? null,
      clip,
      metrics: app.frameMetrics,
      linearity: limits.linearity,
      fullWell: limits.fullWell,
      rows: band.height - BAND.headerH > 240 ? 6 : band.height - BAND.headerH > 200 ? 5 : 4,
    }),
  );
  const metricsNow = $derived(app.frameMetrics && recent(app.frameMetrics.seq, header?.seq ?? null) ? app.frameMetrics : null);
  // A frame shown while another mode was on (an opened file, a solve in Field mode) is
  // measured when the Framing band comes back, instead of "Measuring…" until a new frame.
  $effect(() => {
    if (ws.mode !== 'framing' || !layout.bandOpen) return;
    untrack(() => {
      const info = app.shown;
      const fs = app.frameStats;
      if (!info || !fs || fs.peaks?.seq === info.frame.header.seq) return;
      const h = info.frame.header as { bayer?: string | null };
      fs.measure(info.frame, h.bayer !== undefined ? (h.bayer ?? null) : (app.camera?.sensor?.bayer ?? null));
    });
  });

  // -- Cards: one order (D10), the state each mode remembers -----------------------
  const cardOpen = (id: CardId) => layout.cards[id] === 'open';
  const visibleCards = $derived((['camera', 'statistics', 'inspector', 'photometry', 'mount', 'focuser'] as CardId[]).filter((id) => layout.cards[id] !== 'hidden'));
  /** The Focus band shows the V-curve now (the Focuser card does not repeat it). */
  const bandVCurve = $derived(ws.mode === 'focus' && layout.bandOpen && band.height > 0 && !band.compact);

  // Observe keys, through the one registry (scope "imaging"): bound while
  // this screen is mounted, so the "?" sheet and the tooltips read the same map.
  $effect(() => {
    const r = app.shortcuts;
    const off = [
      // Take shot (A23): also during live view (the next live frame is saved).
      r.handle('observe.capture', () => {
        const owner = app.cameraOwner;
        if (app.canCamera && !app.exposureProblem() && (owner === 'idle' || owner === 'live')) void app.takeShot();
      }),
      r.handle('observe.live', () => {
        if (app.canCamera && (app.live || !app.exposureProblem())) void app.toggleLive();
      }),
      r.handle('view.zoom-in', () => zoom('in')),
      r.handle('view.zoom-out', () => zoom('out')),
      r.handle('view.fit', () => zoom('fit')),
      r.handle('view.fill', () => zoom('fill')),
      r.handle('view.one-to-one', () => zoom('1to1')),
      r.handle('view.stretch-auto', () => app.setAutoStretch(!app.autoStretch)),
      r.handle('view.stretch-reset', () => app.resetStretch()),
      r.handle('view.levels', () => ws.toggleBand()),
      r.handle('view.crosshair', () => (app.crosshair = !app.crosshair)),
      r.handle('view.loupe', () => tools.toggleLoupe()),
      r.handle('view.saturation', () => {
        if (limits.fullWell !== null || tools.saturation) tools.toggleSaturation();
      }),
      r.handle('view.region', () => toggleRegion()),
      r.handle('view.statistics', () => toggleStatistics()),
      r.handle('rail.toggle', () => ws.toggleRail()),
      r.handle('drawer.toggle', () => ws.toggleDrawer()),
      r.handle('observe.mode.framing', () => ws.setMode('framing')),
      r.handle('observe.mode.focus', () => ws.setMode('focus')),
      r.handle('observe.mode.field', () => ws.setMode('field')),
      r.handle('field.solve', () => void app.identifyField()),
      r.handle('field.grid', () => {
        if (field.solved) field.toggle('grid');
      }),
      r.handle('field.labels', () => {
        if (field.solved) field.toggle('labels');
      }),
      r.handle('field.catalogue', () => (catalogueOpen = !catalogueOpen)),
      r.handle('observe.jog-arm', () => {
        if (app.jogArmed || !app.jogProblem()) app.toggleJogArmed();
      }),
    ];
    return () => off.forEach((f) => f());
  });

  function onPerf(): void {
    const info = app.shown;
    if (!perf || !info) return;
    const t = info.timing;
    const h = info.frame.header;
    console.info(
      `[perf] seq=${t.seq} ${h.width}x${h.height}x${h.channels} decode=${t.decodeMs?.toFixed(2)}ms ` +
        `upload=${t.uploadMs.toFixed(2)}ms stats=${t.statsMs.toFixed(2)}ms draw=${t.drawMs.toFixed(2)}ms`,
    );
  }

  // One verb for the bulk action everywhere (Connection, toolbar, prompt); the link is in the tooltip.
  const connectTip = $derived(
    app.connectMode === 'alpaca'
      ? `Connect every device not connected yet at ${app.alpacaHost || 'the Seestar address'}:${app.alpacaPort}`
      : 'Connect every device of the simulator not connected yet',
  );
  /** Some equipment is connected, but not the camera (the mount alone, or the camera failed). */
  const cameraMissing = $derived(app.connected && !app.cameraReady);
  const connectReason = $derived.by(() => {
    const problem = app.connectProblem();
    return problem && app.linkOpen ? `${problem} on the Connection screen` : problem;
  });
</script>

{#snippet connectButton()}
  <IconButton
    icon={app.connectMode === 'alpaca' ? 'connect' : 'simulator'}
    label="Connect all"
    tooltipText={connectTip}
    showLabel
    variant="primary"
    tooltip="top"
    busy={!!app.busy.connectAll || app.equipment.anyConnecting}
    disabledReason={connectReason}
    onclick={() => app.connectAll()}
  />
{/snippet}

{#snippet openConnection()}
  <IconButton
    icon="nav-connection"
    label="Connection screen"
    showLabel
    variant="ghost"
    shortcut={app.shortcuts.keyFor('nav.connection')}
    tooltip="top"
    onclick={() => app.go('connection')}
  />
{/snippet}

<div class="imaging" data-mode={ws.mode}>
  <ImagingToolbar {hasFrame} onzoom={zoom} bind:catalogueOpen />

  <div class="workspace" style:--rail-cols="{railW}px">
    <div class="center" bind:clientWidth={centerW} bind:clientHeight={centerH}>
      <div
        class="stage"
        bind:this={stageEl}
        style:height="{band.viewer}px"
        bind:clientWidth={stageW}
        bind:clientHeight={stageH}
        data-frame-seq={seq}
        data-theme-applied={app.theme}
        data-stale={stale || undefined}
      >
        <FitsViewer
          bind:this={viewer}
          frame={app.frame}
          autoStretch={app.autoStretch}
          stretch={app.manual}
          crosshair={app.crosshair}
          crosshairMode={tools.crosshairMode}
          palette={tools.palette}
          preview={tools.preview}
          bayer={app.camera?.sensor?.bayer ?? null}
          {saturation}
          loupe={tools.loupe ? { mag: tools.loupeMag, top: loupeTop } : null}
          ongeometry={(g) => (geometry = g)}
          nightTint={app.theme === 'night-red'}
          tint={app.viewerTint}
          rotation={app.rotation}
          fitMode={app.fitMode}
          onrect={(r) => (app.imageRect = r)}
          onfitted={(f) => (app.fitted = f)}
          syncTiming={perf}
          label="Live image"
          onpointer={(p) => (app.pointer = p)}
          ondisplay={(info) => {
            app.onDisplay(info);
            onPerf();
          }}
          onzoom={(z) => (app.zoom = z)}
        >
          {#snippet overlay({ width, height })}
            <!-- Frame outline: pixel centres are integers, so the edge sits at -0.5. -->
            <rect
              class="frame-edge"
              class:stale
              x="-0.5"
              y="-0.5"
              {width}
              {height}
              vector-effect="non-scaling-stroke"
            />
          {/snippet}
          {#snippet empty()}
            <div class="empty">
              {#if app.events.link === 'unauthorized'}
                <Icon name="network" size={48} />
                <p class="title">The server rejected the token</p>
                <p class="hint">
                  Open the UI with <span class="num">?token=…</span> as printed by the server
                  (<span class="num">ARGOS_TOKEN=</span>).
                </p>
              {:else if app.events.link === 'forbidden'}
                <Icon name="network" size={48} />
                <p class="title">The server refused this page</p>
                <p class="hint">
                  Open the UI from <span class="num">localhost</span> or
                  <span class="num">127.0.0.1</span>, as the server only answers local pages.
                </p>
              {:else if !app.linkOpen}
                <Icon name="network" size={48} />
                <p class="title">Waiting for the ARGOS server</p>
                <p class="hint">
                  Expected at <span class="num">{app.config.apiBase}</span>. Start it with
                  <span class="num">python -m argos.server</span>; this page reconnects by itself.
                </p>
              {:else if !app.cameraReady}
                <Icon name={app.connectMode === 'alpaca' ? 'connect' : 'simulator'} size={48} />
                <p class="title">{cameraMissing ? 'Camera not connected' : 'No equipment connected'}</p>
                <p class="hint">
                  {app.connectMode === 'alpaca'
                    ? app.alpacaHost
                      ? `Link: Seestar at ${app.alpacaHost}:${app.alpacaPort}.`
                      : 'Link: Seestar, no address yet.'
                    : 'Link: the built-in simulator.'} The telescope profile and each device are on the Connection screen.
                </p>
                <div class="cta">{@render connectButton()}{@render openConnection()}</div>
              {:else}
                <Icon name="capture" size={48} />
                <p class="title">Ready for a first frame</p>
                <p class="hint">
                  <kbd class="key">V</kbd> live view · <kbd class="key">E</kbd> one
                  <span class="num">{seconds(app.exposure)}</span> exposure
                </p>
                <div class="cta">
                  <IconButton
                    icon="live"
                    label="Start live view"
                    showLabel
                    variant="primary"
                    busy={!!app.busy.live}
                    onclick={() => app.startLive()}
                  />
                </div>
              {/if}
            </div>
          {/snippet}
        </FitsViewer>

        <!-- Catalogue layers, grid, reticle and roles in screen space; clicks identify (A49). -->
        <FieldOverlay
          {geometry}
          stage={{ width: stageW, height: stageH }}
          markers={shownMarkers}
          transform={field.activeTransform}
          visibility={field.visibility}
          gLimit={field.depth}
          grid={fieldWcs ? field.field?.grid : null}
          reticle={field.solved ? field.field?.target_reticle : null}
          ring={sel?.ring}
          mark={field.listMark}
          hotKey={field.hover?.source === 'candidates' ? field.hover.key : null}
          apertureR={field.apertureR}
          tracking={field.activeTransform?.tracking ?? null}
          interactive={hasFrame}
          onselect={(a) => void onSelect(a)}
          onhover={(h) => field.hoverMarker(h)}
        />

        <Hud
          {chips}
          {cursor}
          {mini}
          rect={app.imageRect}
          stage={{ width: stageW, height: stageH }}
          dragReadout={ws.dragReadout}
          theme={app.theme}
          solved={!!fieldWcs}
          {sky}
        />

        <Marks {geometry} points={exposureMark} stage={{ width: stageW, height: stageH }} />
        <RegionTool {tools} {geometry} stage={{ width: stageW, height: stageH }} />
        {#if cardSel}
          <StarCard
            selection={cardSel}
            setTarget={cardTarget}
            alias={cardAlias}
            phase={field.selection?.state}
            message={field.selection?.message}
            at={cardAt}
            bounds={{ width: stageW, height: stageH }}
            {busyRole}
            onrole={(r) => void setRole(r)}
            onremove={() => void removeRole()}
            onclose={() => void field.clearSelection(app.client)}
            oninspect={showInspector}
          />
        {/if}
        <ViewerMenu
          {geometry}
          skyAt={fieldWcs ? (x, y) => pixelToSky(fieldWcs!, x, y) : null}
          keys={{ fit: app.shortcuts.keyFor('view.fit'), one: app.shortcuts.keyFor('view.one-to-one'), region: app.shortcuts.keyFor('view.region') }}
          canIdentify={!!header}
          identifyReason={header ? null : 'no frame yet'}
          hasSelection={!!app.field.selection?.selection}
          onaction={(a, p) => void menuAction(a, p)}
          oncopied={(what, text) => app.toast('info', `${what} copied`, text)}
        />

        {#if header}
          <!-- A frame on screen but no equipment: the prompt sits at the bottom, off the image centre. -->
          {#if app.linkOpen && !app.cameraReady}
            <div class="prompt" style:bottom="{promptBottom}px" role="group" aria-label={cameraMissing ? 'Camera not connected' : 'No equipment connected'}>
              <span class="prompt-text">{cameraMissing ? 'Camera not connected' : 'No equipment connected'}</span>
              {@render connectButton()}
            </div>
          {:else if app.stale && app.events.link !== 'idle'}
            <div class="prompt" style:bottom="{promptBottom}px" role="status">
              <!-- Says what is on screen: the frame chip reads "Last frame", the edge is dashed, readouts are muted. -->
              <span class="prompt-text">Server link lost: last frame and readouts received, commands paused</span>
              <IconButton
                icon="refresh"
                label="Retry server"
                showLabel
                variant="secondary"
                size="s"
                onclick={() => app.reconnect()}
              />
            </div>
          {/if}
        {/if}
      </div>

      {#if layout.bandOpen && band.height > 0}
        <!-- svelte-ignore a11y_no_noninteractive_tabindex (a focusable separator is the WAI-ARIA window splitter) -->
        <div
          class="hsep"
          role="separator"
          aria-orientation="horizontal"
          aria-label="Band height: drag, or arrows; Enter fits the image"
          aria-valuenow={band.height}
          aria-valuemin={BAND.compactH}
          aria-valuemax={bandMax(center, drawerH)}
          tabindex="0"
          class:active={dragging === 'band'}
          {@attach splitter({
            axis: 'y',
            invert: true,
            get: () => band.height,
            set: (v) => ws.setBandHeight(Math.abs(v - bandFit) <= 2 ? null : v),
            min: BAND.compactH,
            max: () => bandMax(center, drawerH),
            reset: () => bandFit,
            snaps: () => [bandFit],
            ondrag: (a) => (dragging = a ? 'band' : null),
          })}
        ></div>
        <div class="band-cell" style:height="{Math.max(0, band.height - 1)}px">
          <Band
            mode={ws.mode}
            height={Math.max(0, band.height - 1)}
            compact={band.compact}
            userHeight={layout.bandH}
            hideKey={app.shortcuts.keyFor('view.levels')}
            onhide={() => ws.toggleBand()}
            onfit={() => ws.setBandHeight(null)}
          >
            {#snippet tools()}
              {#if ws.mode === 'framing'}
                <DisplayTools mode={app.levels?.mode ?? 'linear'} disabled={!app.levels} onmode={(mode) => app.setLevel({ mode })} />
              {/if}
              <ViewOptions
                tools={app.viewTools}
                {kind}
                rotation={app.rotation}
                onrotation={(r) => app.setRotation(r)}
                {nightRed}
                threshold={limits.fullWell}
                saturationKey={app.shortcuts.keyFor('view.saturation')}
              />
            {/snippet}
            {#snippet children({ height, compact })}
              {#if ws.mode === 'field'}
                <!-- The comparison workspace (imaging/field, W4): the candidates table linked to the image. -->
                <FieldBand field={app.field} {compact} topCode={app.shown ? clipping(app.shown.histogram, null).topCode : null} onlistpick={listPick} onrowpick={rowPick}>
                  {#snippet live(small: boolean)}
                    <LiveStatus line={photLine} status={phot.status} compact={small} onopen={() => ws.setDrawer({ drawerOpen: true, drawerTab: 'light-curve' })} />
                  {/snippet}
                </FieldBand>
              {:else if ws.mode === 'focus'}
                <FocusBand
                  {height}
                  {compact}
                  af={app.autofocus}
                  metrics={metricsNow}
                  conditions={app.conditions}
                  periods={app.afPeriods}
                  view={app.conditionsView}
                  expecting={app.live}
                  theme={app.theme}
                />
              {:else}
                <FramingBand
                  {height}
                  {compact}
                  histogram={app.shown?.histogram ?? null}
                  levels={app.levels}
                  auto={app.autoStretch}
                  theme={app.theme}
                  tint={app.viewerTint}
                  {check}
                  linearityAdu={limits.linearity}
                  fullWellAdu={limits.fullWell}
                  peaksUnsupported={!!app.frameStats && !app.frameStats.supported}
                  onlevel={(patch) => app.setLevel(patch)}
                  onhoverstars={(points) => (exposureMark = points)}
                  palette={effectivePalette(app.viewTools.palette, nightRed)}
                />
              {/if}
            {/snippet}
          </Band>
        </div>
      {/if}

      {#if layout.drawerOpen && drawerH > 0}
        <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
        <div
          class="hsep strong"
          role="separator"
          aria-orientation="horizontal"
          aria-label="Drawer height: drag, or arrows; Enter restores 216 px"
          aria-valuenow={drawerH}
          aria-valuemin={160}
          aria-valuemax={Math.max(160, Math.floor(centerH / 2))}
          tabindex="0"
          class:active={dragging === 'drawer'}
          {@attach splitter({
            axis: 'y',
            invert: true,
            get: () => drawerH,
            set: (v) => ws.setDrawer({ drawerH: v }),
            min: 160,
            max: () => Math.max(160, Math.floor(centerH / 2)),
            reset: 216,
            snaps: [216],
            ondrag: (a) => (dragging = a ? 'drawer' : null),
          })}
        ></div>
        <div class="drawer-cell" style:height="{Math.max(0, drawerH - 1)}px">
          <LogDrawer
            label="Observe drawer"
            tabs={DRAWER_TABS.filter((t) => t.id !== 'log')}
            tab={layout.drawerTab}
            ontab={(id) => ws.setDrawer({ drawerTab: id as DrawerTab })}
          >
            {#snippet tools(id: string)}
              {#if id === 'conditions'}
                <ConditionsTools store={app.conditions} view={app.conditionsView} expecting={app.live} />
              {:else if id === 'light-curve'}
                <!-- No target: no verdict (the empty state says what to do; a report of a previous set may still be held). -->
                {#if photTarget}<EnsembleVerdict verdict={photVerdict} minPoints={minPoints(phot.quality)} />{/if}
              {:else if id === 'ensemble'}
                <RecommendPopover
                  count={cfgNum('photometry.auto_comparisons') ?? 5}
                  gate={{ snr: cfgNum('photometry.comparison_min_snr'), dmag: cfgNum('photometry.comparison_max_delta_mag'), sepArcmin: cfgNum('photometry.comparison_max_separation_arcmin') }}
                  reason={recommendReason}
                  running={phot.running}
                  busy={recommendBusy}
                  showLabel={false}
                  onrecommend={recommend}
                />
                <IconButton
                  icon="refresh"
                  label="Refresh catalogue"
                  size="s"
                  variant="ghost"
                  busy={field.fetching}
                  disabledReason={field.solved ? null : 'identify the field first (S)'}
                  tooltipText="Fetch the VSP comparison stars again for the solved field"
                  onclick={() => void field.refetch(app.client).catch((err) => app.reportError('Refresh catalogue', err))}
                />
                <IconButton icon="copy" label="Copy the ensemble (TSV)" size="s" variant="ghost" disabledReason={ensRows.length ? null : 'no star in the ensemble'} onclick={copyEnsemble} />
              {/if}
            {/snippet}
            {#snippet content(id: string)}
              {#if id === 'conditions'}
                <ConditionsTimeline store={app.conditions} view={app.conditionsView} theme={app.theme} expecting={app.live} periods={app.afPeriods} rows />
              {:else if id === 'light-curve'}
                <LightCurveTab stars={setStars} curves={phot.curves} line={photLine}>
                  {#snippet plot()}
                    <LightCurvePlot
                      store={curveStore}
                      facets={drawerH >= 300 ? ['target', 'check', 'ensemble'] : ['target', 'check']}
                      variant="drawer"
                      expecting={field.field?.auto === true && app.live}
                      theme={app.theme}
                      targetKey={photTarget ? (curveFor(phot.curves, photTarget)?.key ?? null) : null}
                      notify={(title, message) => app.toast('info', title, message ?? '')}
                      label="Live light curve"
                      bind:axis={lcAxis}
                      bind:errors={lcErrors}
                      bind:flux={lcFlux}
                    />
                  {/snippet}
                </LightCurveTab>
              {:else if id === 'variables'}
                <VariablesTab
                  rows={phot.variables?.available ? phot.variables.rows : null}
                  solving={field.solving}
                  error={phot.variablesError}
                  query={field.variableQuery}
                  magLimit={field.variableMagLimit}
                  hotKey={field.hover?.source === 'image' && field.hover.key ? field.hover.key : null}
                  targetReason={field.solved ? null : 'identify the field first (S)'}
                  busy={variableBusy}
                  onquery={(q) => (field.variableQuery = q)}
                  onmaglimit={(v) => (field.variableMagLimit = v)}
                  onhover={(r) => hoverStar(r)}
                  onpick={(r) => pickStar(r)}
                  ontarget={(r) => void variableTarget(r)}
                  oncopy={(_tsv, n) => app.toast('info', `Copied ${n} row${n === 1 ? '' : 's'}`)}
                />
              {:else if id === 'ensemble'}
                <EnsembleTable
                  rows={ensRows}
                  verdict={photVerdict}
                  minPoints={minPoints(phot.quality)}
                  countText={countLine(setStars)}
                  hotKey={setHotKey}
                  selected={field.inspected}
                  removeReason={null}
                  removing={removingKey}
                  onremove={(r: EnsembleRow) => {
                    const s = setStars.find((x) => x.key === r.key);
                    if (s) askRemove(s);
                  }}
                  onhover={(r) => hoverStar(r)}
                  onpick={(r) => pickStar(r)}
                  oncopy={(_tsv, n) => app.toast('info', `Copied ${n} row${n === 1 ? '' : 's'}`)}
                />
              {/if}
            {/snippet}
          </LogDrawer>
        </div>
      {/if}
    </div>

    {#if layout.railOpen}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div
        class="vsep"
        role="separator"
        aria-orientation="vertical"
        aria-label="Right panel width: drag, or arrows; Enter restores 400 px"
        aria-valuenow={layout.railW}
        aria-valuemin={RAIL.min}
        aria-valuemax={RAIL.max}
        tabindex="0"
        class:active={dragging === 'rail'}
        {@attach splitter({
          axis: 'x',
          invert: true,
          get: () => layout.railW,
          set: (v) => ws.setRailWidth(v),
          min: RAIL.min,
          max: () => RAIL.max,
          reset: RAIL.default,
          snaps: [RAIL.default],
          ondrag: (a) => (dragging = a ? 'rail' : null),
        })}
      ></div>
      <!-- One card order in every mode (D10); each mode remembers open / folded / hidden. -->
      <aside class="rail" aria-label="Instrument panels">
        {#if visibleCards.includes('camera')}
          <CameraCard bind:open={() => cardOpen('camera'), (v) => ws.setCardOpen('camera', v)} />
        {/if}
        {#if visibleCards.includes('statistics')}
          <StatisticsCard
            bind:open={() => cardOpen('statistics'), (v) => ws.setCardOpen('statistics', v)}
            histogram={app.shown?.histogram ?? null}
            seq={header?.seq ?? null}
            cfa={kind === 'cfa'}
            metrics={app.frameMetrics}
            region={tools.regionResult}
            regionOn={tools.region}
            regionKey={app.shortcuts.keyFor('view.region')}
            starRadius={typeof app.configValues?.['imaging.star_radius_px'] === 'number' ? (app.configValues['imaging.star_radius_px'] as number) : null}
            onradius={(px) => app.patchConfig({ 'imaging.star_radius_px': px })}
            onregion={toggleRegion}
          />
        {/if}
        {#if visibleCards.includes('inspector')}
          <Card title="Inspector" icon="inspector" collapsible bind:open={() => cardOpen('inspector'), (v) => ws.setCardOpen('inspector', v)}>
            {#snippet summary()}{inspRow ? inspRow.name : 'No star picked'}{/snippet}
            <InspectorCard
              row={inspRow}
              frame={app.shown?.frame ?? null}
              at={inspAt}
              levels={app.levels}
              turns={geometry?.turns ?? 0}
              apertureR={geom?.aperture_r_px ?? field.apertureR}
              annulusIn={geom?.annulus_in_r_px ?? null}
              annulusOut={geom?.annulus_out_r_px ?? null}
              scaleArcsec={field.field?.solution?.scale_arcsec_px ?? null}
              history={inspHistory}
              onpick={(k) => field.inspect(k)}
              theme={app.theme}
            />
          </Card>
        {/if}
        {#if visibleCards.includes('photometry')}
          <PhotometryCard
            bind:open={() => cardOpen('photometry'), (v) => ws.setCardOpen('photometry', v)}
            stars={setStars}
            curves={phot.curves}
            report={phot.quality}
            line={photLine}
            showLine={!(ws.mode === 'field' && layout.bandOpen && band.height > 0)}
            geometry={field.targets?.geometry ?? null}
            seriesFwhm={phot.live?.geometry?.series_fwhm_px ?? null}
            band={phot.live?.band ?? null}
            hotKey={setHotKey}
            removing={removingKey}
            recommend={{
              count: cfgNum('photometry.auto_comparisons') ?? 5,
              gate: { snr: cfgNum('photometry.comparison_min_snr'), dmag: cfgNum('photometry.comparison_max_delta_mag'), sepArcmin: cfgNum('photometry.comparison_max_separation_arcmin') },
              reason: recommendReason,
              running: phot.running,
              busy: recommendBusy,
            }}
            drawerTab={layout.drawerOpen ? layout.drawerTab : null}
            onrecommend={recommend}
            onremove={askRemove}
            onhover={hoverStar}
            onpick={pickStar}
            ondrawer={drawerTab}
          />
        {/if}
        {#if visibleCards.includes('mount')}
          <MountCard bind:open={() => cardOpen('mount'), (v) => ws.setCardOpen('mount', v)} fieldMode={ws.mode === 'field'} />
        {/if}
        {#if visibleCards.includes('focuser')}
          <FocuserCard bandShowsVCurve={bandVCurve} bind:open={() => cardOpen('focuser'), (v) => ws.setCardOpen('focuser', v)} />
        {/if}
        {#if visibleCards.length === 0}
          <p class="rail-empty">Every card is hidden in this mode: show them again from Arrange at the right of the toolbar.</p>
        {/if}
      </aside>
    {/if}
    <ConfirmDialog
      open={confirmRemove !== null}
      title="Remove {confirmRemove?.display_name || confirmRemove?.name || 'the star'} during the run?"
      message="The ensemble of every following frame changes (its zero point for a comparison). Undo puts the star back."
      confirmLabel="Remove from the set"
      cancelLabel="Keep it"
      destructive
      onconfirm={() => {
        const s = confirmRemove;
        confirmRemove = null;
        if (s) void removeStar(s);
      }}
      oncancel={() => (confirmRemove = null)}
    />
  </div>
</div>

<style>
  .imaging {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    height: 100%;
    min-width: 0;
  }

  /* Centre, the 1 px separator, the right panel at the width this mode remembers (D8: 360-580). */
  .workspace {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto var(--rail-cols);
    min-height: 0;
  }

  .center {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }

  .stage {
    position: relative;
    flex: none;
    min-height: 0;
    overflow: hidden;
  }
  .band-cell,
  .drawer-cell {
    flex: none;
    min-height: 0;
    min-width: 0;
  }

  /* 1 px separators with a 7 px hit area (--splitter-hit), WAI-ARIA window splitters. */
  .hsep,
  .vsep {
    position: relative;
    flex: none;
    background: var(--border);
    z-index: 3;
  }
  .hsep {
    height: 1px;
    cursor: row-resize;
  }
  .vsep {
    width: 1px;
    cursor: col-resize;
  }
  .hsep::after,
  .vsep::after {
    content: '';
    position: absolute;
  }
  .hsep::after {
    left: 0;
    right: 0;
    top: calc(var(--splitter-hit) / -2);
    height: var(--splitter-hit);
  }
  .vsep::after {
    top: 0;
    bottom: 0;
    left: calc(var(--splitter-hit) / -2);
    width: var(--splitter-hit);
  }
  /* Hover, drag, focus: the line thickens in --fg-muted (no brass: a layout). */
  .hsep:hover,
  .hsep.active,
  .hsep:focus-visible,
  .vsep:hover,
  .vsep.active,
  .vsep:focus-visible {
    box-shadow: 0 0 0 1px var(--fg-muted);
    background: var(--fg-muted);
    outline: none;
  }

  :global(.frame-edge) {
    fill: none;
    stroke: var(--border-soft);
    stroke-width: 1;
  }
  :global(.frame-edge.stale) {
    stroke-dasharray: 4 3;
  }

  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    max-width: 380px;
    color: var(--fg-muted);
  }
  .empty .title {
    margin: var(--space-3) 0 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .empty .hint {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
    line-height: var(--leading-relaxed);
  }
  .empty .num {
    color: var(--fg);
  }
  /* The viewer's message layer ignores the pointer; the call to action does not. */
  .cta {
    display: flex;
    gap: var(--space-2);
    margin-top: var(--space-3);
    pointer-events: auto;
  }
  .rail-empty {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
    line-height: var(--leading-relaxed);
  }

  /* Connect prompt over a frame: bottom centre of the image area, compact. */
  .prompt {
    position: absolute;
    left: 50%;
    bottom: var(--space-4);
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-2) var(--space-2) var(--space-4);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg-2);
    box-shadow: var(--shadow-2);
    white-space: nowrap;
  }
  .prompt-text {
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
  }

  .rail {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-height: 0;
    min-width: 0;
    padding: var(--space-4);
    background: var(--bg-2);
    overflow-y: auto;
    overscroll-behavior: contain;
  }
</style>
