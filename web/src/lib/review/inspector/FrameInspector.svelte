<!--
  Review R2, the frame inspector (web/spec/07-review-analysis.md 1.11, 2.2 rows 1.11, WF-D,
  2.4; README M100, M101, M102, D12, D19; 04 2.3 "inspect" mode): one FITS, read-only, the
  image the hero (at least 75 % of the width with the rail open).

  - Toolbar (one row): [Session › file] back to R1 (Alt+←), previous / next light frame of the
    session (PageUp / PageDown) with "7 / 195", Open FITS (⌘/Ctrl+O); zoom (+ − F 1); Auto
    stretch (A), Reset stretch (Shift+A), View options (CFA preview, palette, rotation,
    crosshair mode, loupe magnification); crosshair (X), loupe (Z), saturation (C); Identify
    field (S; while ASTAP runs the same place cancels it), coordinate grid (G), Catalogue
    layers (O; its footer opens Settings › Catalogues or › Plate solving in a sheet over R2,
    the same category form as Settings, D12, M101; "All settings" goes to Settings); rail (P).
  - The viewer is Observe's (FitsViewer, FieldOverlay, Hud, ViewerMenu) in inspect mode: a
    click measures the star there (A73) and fills the Selected star card; no role is ever
    assigned (Review never edits the target set); the context menu has no role items (M102).
  - Rail cards: Frame, Selected star (aperture r 2-30 px, remembered), Identification (solve
    with progress and Cancel, then the catalogue), Display (histogram with handles), FITS
    header (filter, Copy).
  - States: no file, loading ("Loading {file}…", the previous frame stays), error (banner; the
    previous frame stays, P28), solving, catalogue failed, link down.
  Wiring: the integrator mounts it with an InspectorStore, sets the shortcut scope
  "analyze.r2", and handles `onback` and `onopenfits` (the R0 FITS picker).
-->
<script lang="ts">
  import { untrack, type Snippet } from 'svelte';
  import type { ShortcutRegistry } from '../../app/shortcuts';
  import { isActive } from '../../app/jobs';
  import Card from '../../components/Card.svelte';
  import Icon from '../../components/Icon.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import SearchField from '../../components/SearchField.svelte';
  import Sheet from '../../components/Sheet.svelte';
  import Spinner from '../../components/Spinner.svelte';
  import Stepper from '../../components/Stepper.svelte';
  import { tooltip } from '../../components/tooltip';
  import { formatDec, formatRA } from '../../format/astro';
  import { int } from '../../format/number';
  import { middleEllipsis, middleName } from '../../format/path';
  import Histogram from '../../imaging/Histogram.svelte';
  import CatalogPopover from '../../imaging/field/CatalogPopover.svelte';
  import Catalogues from '../../settings/pages/Catalogues.svelte';
  import PlateSolving from '../../settings/pages/PlateSolving.svelte';
  import type { Theme } from '../../app/theme';
  import FitsViewer from '../../viewer/FitsViewer.svelte';
  import Hud from '../../viewer/Hud.svelte';
  import { cursorReadout, type HudChip } from '../../viewer/hud';
  import { fromFrameWcs, pixelToSky, type TanWcs } from '../../viewer/hud/wcs';
  import FieldOverlay, { type SelectAt } from '../../viewer/overlay/FieldOverlay.svelte';
  import { LAYER_IDS, type LayerId } from '../../viewer/overlay/layers';
  import { frameKind } from '../../viewer/palettes/cfa';
  import { effectivePalette } from '../../viewer/palettes/lut';
  import type { RotationMode } from '../../viewer/rotation';
  import type { Histogram16 } from '../../viewer/stretch';
  import { composeView, download, viewFileName } from '../../viewer/tools/exportview';
  import { displayedSize, type ViewerGeometry } from '../../viewer/tools/geometry';
  import RegionTool from '../../viewer/tools/RegionTool.svelte';
  import type { ViewerTools } from '../../viewer/tools/tools.svelte';
  import ViewerMenu from '../../viewer/tools/ViewerMenu.svelte';
  import type { ViewerMenuAction } from '../../viewer/tools/viewermenu';
  import ViewOptions from '../../viewer/tools/ViewOptions.svelte';
  import type { PointerInfo } from '../../viewer/types';
  import { APERTURE_MAX, APERTURE_MIN, cardsText, catalogueWarning, countsFor, filterCards, frameLines, measureView, nextReason, prevReason, solutionLines } from './inspect';
  import type { InspectorStore } from './inspector.svelte';

  interface Props {
    store: InspectorStore;
    /** R2's own viewer tools (CFA preview, palette, loupe, saturation, region; remembered). */
    tools: ViewerTools;
    theme: Theme;
    /** --viewer-tint and --viewer-saturated as 0..1 RGB (the app's). */
    tint: readonly [number, number, number];
    saturatedColour: readonly [number, number, number];
    /** Display rotation, shared with Observe (ui.display.rotation). */
    rotation: RotationMode;
    onrotation: (r: RotationMode) => void;
    /** The profile's full well (saturation threshold, ADU), null when unknown. */
    fullWell?: number | null;
    /** The CFA pattern of the camera profile, for a frame whose header carries none. */
    profileBayer?: string | null;
    /** The server link is down: actions say why. */
    linkDown?: boolean;
    /** Back to the session (R1); null outside a session (a FITS opened alone). */
    onback?: (() => void) | null;
    onopenfits?: () => void;
    /** The sheet's "All settings": Settings at that category (the app's openSettings). */
    onallsettings?: (category: 'catalogues' | 'plate_solving') => void;
    /** Save catalog.display_mag_limit once per release (D12). */
    onglimitcommit?: (v: number) => void;
    /** Copy feedback, errors (the caller's toasts). */
    ontoast?: (level: 'info' | 'error', title: string, detail?: string) => void;
    /** The registry: R2 binds its keys while mounted (scope "analyze.r2"). */
    shortcuts?: ShortcutRegistry | null;
    /** Gallery: the histogram and pointer of a still. */
    previewHistogram?: Histogram16 | null;
    /** The band a landscape frame leaves under itself (BRAND 11.1): the session strip, given its height. */
    strip?: Snippet<[number]>;
  }

  let {
    store,
    tools,
    theme,
    tint,
    saturatedColour,
    rotation,
    onrotation,
    fullWell = null,
    profileBayer = null,
    linkDown = false,
    onback = null,
    onopenfits,
    onallsettings,
    onglimitcommit,
    ontoast,
    shortcuts = null,
    previewHistogram = null,
    strip,
  }: Props = $props();

  const key = (id: string) => shortcuts?.keyFor(id);
  const offline = $derived(linkDown ? 'the ARGOS server is not reachable' : null);
  const noFrame = $derived(store.frame ? null : 'no frame yet');
  const nightRed = $derived(theme === 'night-red');

  // -- Viewer ------------------------------------------------------------------------------------
  let viewer = $state<FitsViewer | undefined>();
  let stageEl = $state<HTMLDivElement | undefined>();
  let stageW = $state(0);
  let stageH = $state(0);
  let geometry = $state.raw<ViewerGeometry | null>(null);
  let imageRect = $state.raw<{ left: number; top: number; width: number; height: number } | null>(null);
  let pointer = $state.raw<PointerInfo | null>(null);
  let histogram = $state.raw<Histogram16 | null>(null);
  $effect(() => {
    if (previewHistogram) histogram = previewHistogram;
  });

  const header = $derived(store.frame?.header ?? null);
  const bayer = $derived(store.info?.bayer ?? profileBayer ?? null);
  const kind = $derived(frameKind(header?.channels ?? 1, bayer));
  const wcs = $derived.by((): TanWcs | null => {
    const w = store.solution ? fromFrameWcs(store.solution.wcs) : null;
    const shape = store.solution?.solution.frame_shape;
    if (!w || (shape && header && (shape[0] !== header.height || shape[1] !== header.width))) return null;
    return w;
  });
  const sky = $derived(wcs && geometry ? { wcs, frame: geometry.frame, turns: geometry.turns, scale: geometry.view.scale } : null);
  // The band rule (BRAND 11.1, as Observe): a frame fitted to the column's width leaves
  // `band` px under it; the session strip takes them (at most 240, at least 40), so the image
  // keeps its fitted size and no black band is left (W7 design review).
  let colW = $state(0);
  let colH = $state(0);
  const band = $derived.by(() => {
    // As displayed: a portrait sensor frame shown a quarter turn round is landscape.
    const shown = geometry ? displayedSize(geometry) : { width: header?.width ?? 0, height: header?.height ?? 0 };
    const w = shown.width;
    const h = shown.height;
    if (!strip || !w || !h || colW <= 0) return 0;
    const free = Math.floor(colH - (colW * h) / w);
    return free >= 40 ? Math.min(240, free) : 0;
  });
  // A new frame: the HUD forgets the previous one's pixel and sky position (design review).
  $effect(() => {
    void store.path;
    untrack(() => (pointer = null));
  });
  const cursor = $derived.by(() => {
    const s = pointer && wcs ? pixelToSky(wcs, pointer.x, pointer.y) : null;
    return cursorReadout(pointer, s ? { ra: formatRA(s.raHours), dec: formatDec(s.decDeg, 1) } : null);
  });
  const chips = $derived.by((): HudChip[] => {
    if (!header) return [];
    const out: HudChip[] = [{ id: 'state', text: 'File', kind: 'state', title: 'A saved frame, read-only (Review)' }];
    if (store.near.position) out.push({ id: 'pos', text: store.near.position, kind: 'num', title: 'Light frame of the session' });
    if (header.exposure_s) out.push({ id: 'exp', text: `${header.exposure_s} s`, kind: 'num' });
    const filter = store.row?.filter_name || store.info?.filter;
    if (filter) out.push({ id: 'filter', text: filter, kind: 'text' });
    return out;
  });
  const saturation = $derived(tools.saturation && fullWell !== null ? { threshold: fullWell, colour: saturatedColour } : null);
  const markers = $derived(store.layers?.layers ?? null);
  const ring = $derived.by(() => {
    const m = store.measure;
    if (m?.found && m.x !== null && m.y !== null) return { x: m.x, y: m.y, r_px: Math.max(6, (m.radius_green_px ?? store.aperture) * 2), space: 'frame' };
    const at = store.measureAt_;
    return at && store.measuring ? { x: at.x, y: at.y, r_px: store.aperture * 2, space: 'frame' } : null;
  });

  function zoom(how: 'in' | 'out' | 'fit' | '1to1'): void {
    if (!viewer) return;
    if (how === 'fit') viewer.fit();
    else if (how === '1to1') viewer.oneToOne();
    else viewer.zoomBy(how === 'in' ? 1.25 : 0.8);
  }

  function select(at: SelectAt): void {
    if (offline) return;
    const hit = at.hit as { x?: number; y?: number } | null;
    void store.measureAt(hit?.x ?? at.x, hit?.y ?? at.y);
  }

  async function menuAction(action: ViewerMenuAction, pixel: { x: number; y: number } | null): Promise<void> {
    if (action === 'fit') zoom('fit');
    else if (action === 'one') zoom('1to1');
    else if (action === 'identify' && pixel) void store.measureAt(pixel.x, pixel.y);
    else if (action === 'region' && pixel && header) tools.regionAt({ width: header.width, height: header.height }, pixel);
    else if (action === 'clear') store.clearMeasure();
    else if (action === 'save-png') {
      const v = stageEl?.querySelector<HTMLElement>('[role="application"]');
      const pic = viewer?.snapshot();
      if (!stageEl || !v || !pic) return;
      const blob = await composeView(stageEl, v, pic);
      if (blob) download(blob, viewFileName(null).replace('argos_view_', `argos_${(store.info?.file_name ?? 'frame').replace(/\.[^.]+$/, '')}_`));
      else ontoast?.('error', 'Save view as PNG', 'The browser could not encode the picture');
    }
  }

  // -- Jobs: a solve leads to the catalogue (07 2.4 "Busy") -------------------------------------
  $effect(() => {
    const j = store.solveJob;
    if (j && !isActive(j)) untrack(() => store.finishSolve(j));
  });
  $effect(() => {
    const j = store.catalogueJob;
    if (j && !isActive(j)) untrack(() => store.finishCatalogue(j));
  });

  async function identify(): Promise<void> {
    if (store.solving) store.cancelSolve();
    else {
      const why = await store.identify();
      if (why) ontoast?.('error', 'Identify field', why);
    }
  }

  async function step(delta: -1 | 1): Promise<void> {
    const why = await store.step(delta);
    if (why) ontoast?.('error', 'Could not open the frame', why);
  }

  // -- Catalogue layers popover --------------------------------------------------------------------
  let catalogueOpen = $state(false);
  let catalogueBtn = $state<HTMLButtonElement | null>(null);
  const counts = $derived(countsFor(LAYER_IDS as readonly LayerId[], store.solution ? (store.layers?.counts ?? {}) : null));
  const catalogState = $derived(
    store.fetching ? { state: 'fetching' as const } : store.catalogueError ? { state: 'error' as const, error: store.catalogueError } : store.layers ? { state: 'ready' as const, warnings: store.layers.warnings.map((w) => catalogueWarning(w).short) } : { state: 'idle' as const },
  );
  const gMax = $derived(Math.max(18, store.layers?.display_mag_limit ?? 18));

  /** Settings at the point of use (D12, M101): the same category form, in a sheet over R2. */
  let sheetOpen = $state(false);
  let sheetKind: 'catalogues' | 'plate_solving' = $state('catalogues');
  function openSheet(kind: 'catalogues' | 'plate_solving'): void {
    sheetKind = kind;
    catalogueOpen = false;
    sheetOpen = true;
  }

  // -- FITS header card ------------------------------------------------------------------------------
  let headerQuery = $state('');
  const cards = $derived(store.header ? filterCards(store.header.cards, headerQuery) : []);
  async function copyHeader(): Promise<void> {
    try {
      await navigator.clipboard.writeText(cardsText(cards));
      ontoast?.('info', 'FITS header copied', `${int(cards.length)} cards`);
    } catch {
      /* clipboard refused */
    }
  }
  async function copyPath(): Promise<void> {
    if (!store.path) return;
    try {
      await navigator.clipboard.writeText(store.path);
      ontoast?.('info', 'Path copied', store.path);
    } catch {
      /* clipboard refused */
    }
  }

  const mv = $derived(store.measure ? measureView(store.measure) : null);
  const fileName = $derived(store.info?.file_name ?? (store.path ? store.path.slice(store.path.lastIndexOf('/') + 1) : null));

  // -- Keys (scope analyze.r2) ------------------------------------------------------------------------
  $effect(() => {
    const reg = shortcuts;
    if (!reg) return;
    const has = () => !!store.frame;
    const offs = [
      reg.handle('r2.frame-prev', () => void step(-1), () => !!store.near.prev),
      reg.handle('r2.frame-next', () => void step(1), () => !!store.near.next),
      reg.handle('r2.back', () => onback?.(), () => !!onback),
      reg.handle('r2.view.zoom-in', () => zoom('in'), has),
      reg.handle('r2.view.zoom-out', () => zoom('out'), has),
      reg.handle('r2.view.fit', () => zoom('fit'), has),
      reg.handle('r2.view.one-to-one', () => zoom('1to1'), has),
      reg.handle('r2.view.stretch-auto', () => store.toggleAuto(), has),
      reg.handle('r2.view.stretch-reset', () => store.resetStretch(), has),
      reg.handle('r2.view.crosshair', () => (store.crosshair = !store.crosshair), has),
      reg.handle('r2.view.loupe', () => tools.toggleLoupe(), has),
      reg.handle('r2.view.saturation', () => tools.toggleSaturation(), has),
      reg.handle('r2.view.region', () => header && tools.toggleRegion({ width: header.width, height: header.height }), has),
      reg.handle('r2.field.solve', () => void identify(), () => has() && !offline),
      reg.handle('r2.field.grid', () => store.setVisible('grid', !store.visibility.grid), () => !!store.solution),
      reg.handle('r2.field.catalogue', () => (catalogueOpen = !catalogueOpen), has),
      reg.handle('rail.toggle.other', () => store.toggleRail()),
    ];
    return () => offs.forEach((f) => f());
  });
</script>

<div class="r2" class:rail-closed={!store.railOpen}>
  <div class="toolbar" role="toolbar" aria-label="Frame inspector">
    {#if onback}
      <button type="button" class="crumb" use:tooltip={{ text: 'Back to the session', placement: 'bottom' }} aria-keyshortcuts={key('r2.back')} onclick={() => onback?.()}>
        <Icon name="open-session" size={16} />
        <span class="crumb-session">{store.sessionLabel ?? 'Session'}</span>
      </button>
      <span class="crumb-sep" aria-hidden="true">›</span>
    {/if}
    <span class="file num" use:tooltip={{ text: store.path ?? 'No file', placement: 'bottom' }}>{fileName ? middleName(fileName, 32) : 'No file'}</span>
    {#if store.lights.length}
      <IconButton icon="frame-prev" label="Previous frame" size="s" tooltip="bottom" shortcut={key('r2.frame-prev')} disabledReason={store.frame ? prevReason(store.near) : noFrame} busy={!!store.loading && store.loading === store.near.prev?.path} onclick={() => void step(-1)} />
      <span class="pos num" aria-live="polite">{store.near.position ?? '—'}</span>
      <IconButton icon="frame-next" label="Next frame" size="s" tooltip="bottom" shortcut={key('r2.frame-next')} disabledReason={store.frame ? nextReason(store.near) : noFrame} busy={!!store.loading && store.loading === store.near.next?.path} onclick={() => void step(1)} />
    {/if}
    <span class="divider" aria-hidden="true"></span>
    <IconButton icon="open-image" label="Open FITS" size="s" tooltip="bottom" shortcut={key('file.open-fits')} disabledReason={offline} onclick={() => onopenfits?.()} />
    <span class="divider" aria-hidden="true"></span>
    <IconButton icon="zoom-in" label="Zoom in" size="s" tooltip="bottom" shortcut={key('r2.view.zoom-in')} disabledReason={noFrame} onclick={() => zoom('in')} />
    <IconButton icon="zoom-out" label="Zoom out" size="s" tooltip="bottom" shortcut={key('r2.view.zoom-out')} disabledReason={noFrame} onclick={() => zoom('out')} />
    <IconButton icon="zoom-fit" label="Fit the whole frame" size="s" tooltip="bottom" shortcut={key('r2.view.fit')} disabledReason={noFrame} onclick={() => zoom('fit')} />
    <IconButton icon="zoom-1to1" label="Actual pixels (1:1)" size="s" tooltip="bottom" shortcut={key('r2.view.one-to-one')} disabledReason={noFrame} onclick={() => zoom('1to1')} />
    <span class="divider" aria-hidden="true"></span>
    <IconButton icon="stretch-auto" label="Auto stretch" size="s" tooltip="bottom" shortcut={key('r2.view.stretch-auto')} pressed={store.autoStretch} disabledReason={noFrame} onclick={() => store.toggleAuto()} />
    <IconButton icon="stretch-reset" label="Reset stretch (linear)" size="s" tooltip="bottom" shortcut={key('r2.view.stretch-reset')} disabledReason={noFrame} onclick={() => store.resetStretch()} />
    <ViewOptions {tools} {kind} {rotation} {onrotation} {nightRed} threshold={fullWell} saturationKey={key('r2.view.saturation')} />
    <span class="divider" aria-hidden="true"></span>
    <IconButton icon="crosshair" label="Crosshair" size="s" tooltip="bottom" shortcut={key('r2.view.crosshair')} pressed={store.crosshair} disabledReason={noFrame} onclick={() => (store.crosshair = !store.crosshair)} />
    <IconButton icon="loupe" label="Loupe" size="s" tooltip="bottom" shortcut={key('r2.view.loupe')} pressed={tools.loupe} disabledReason={noFrame} onclick={() => tools.toggleLoupe()} />
    <IconButton icon="saturation" label="Saturation highlight" size="s" tooltip="bottom" shortcut={key('r2.view.saturation')} pressed={tools.saturation} disabledReason={noFrame ?? (fullWell === null ? 'the full well of the camera profile is unknown' : null)} onclick={() => tools.toggleSaturation()} />
    <span class="divider" aria-hidden="true"></span>
    <IconButton
      icon={store.solving ? 'stop' : 'plate-solve'}
      label={store.solving ? 'Cancel identification' : 'Identify field'}
      size="s"
      tooltip="bottom"
      shortcut={key('r2.field.solve')}
      busy={store.solving && !!store.solveJob?.cancelling}
      disabledReason={noFrame ?? offline}
      onclick={() => void identify()}
    />
    <IconButton icon="sky-grid" label="Coordinate grid" size="s" tooltip="bottom" shortcut={key('r2.field.grid')} pressed={store.visibility.grid} disabledReason={store.solution ? null : 'Identify the field first (S)'} onclick={() => store.setVisible('grid', !store.visibility.grid)} />
    <IconButton bind:el={catalogueBtn} icon="catalogue" label="Catalogue layers" size="s" tooltip="bottom" shortcut={key('r2.field.catalogue')} pressed={catalogueOpen} layoutToggle busy={store.fetching} disabledReason={noFrame} onclick={() => (catalogueOpen = !catalogueOpen)} />
    <span class="grow"></span>
    <IconButton icon="panels" label="Right rail" size="s" tooltip="bottom" shortcut={key('rail.toggle.other')} pressed={store.railOpen} layoutToggle onclick={() => store.toggleRail()} />
  </div>

  {#if store.error}
    <div class="banner" role="alert">
      <Icon name="open-image" size={16} />
      <span class="msg">{store.error}{store.frame ? ' · the previous frame stays on screen.' : ''}</span>
      <IconButton icon="close" label="Dismiss" size="s" variant="ghost" tooltip="bottom" onclick={() => (store.error = null)} />
    </div>
  {/if}

  <div class="workspace">
    <div class="col" bind:clientWidth={colW} bind:clientHeight={colH}>
    <div class="stage" bind:this={stageEl} bind:clientWidth={stageW} bind:clientHeight={stageH} data-theme-applied={theme} aria-busy={store.loading ? true : undefined}>
      <FitsViewer
        bind:this={viewer}
        frame={store.frame}
        autoStretch={store.autoStretch}
        stretch={store.manual}
        crosshair={store.crosshair}
        crosshairMode={tools.crosshairMode}
        palette={tools.palette}
        preview={tools.preview}
        {bayer}
        {saturation}
        loupe={tools.loupe ? { mag: tools.loupeMag, top: 8 } : null}
        ongeometry={(g) => (geometry = g)}
        nightTint={nightRed}
        {tint}
        {rotation}
        label="Frame inspector image"
        onrect={(r) => (imageRect = r)}
        onpointer={(p) => (pointer = p)}
        ondisplay={(info) => {
          histogram = info.histogram;
          store.autoLevels = info.auto;
        }}
      >
        {#snippet overlay({ width, height })}
          <rect class="frame-edge" x="-0.5" y="-0.5" {width} {height} vector-effect="non-scaling-stroke" />
        {/snippet}
        {#snippet empty()}
          <div class="empty">
            {#if linkDown}
              <Icon name="network" size={48} />
              <p class="title">Waiting for the ARGOS server</p>
              <p class="hint">The frame opens when it answers.</p>
            {:else if store.loading}
              <Spinner size={24} />
              <p class="title">Loading <span class="num">{middleEllipsis(store.loading.slice(store.loading.lastIndexOf('/') + 1), 48)}</span>…</p>
            {:else}
              <Icon name="open-image" size={48} />
              <p class="title">No frame open</p>
              <p class="hint">Open a frame from the session (Frames tab, a point's “Open frame”) or any FITS file.</p>
              <div class="cta"><IconButton icon="open-image" label="Open FITS…" showLabel variant="secondary" disabledReason={offline} onclick={() => onopenfits?.()} /></div>
            {/if}
          </div>
        {/snippet}
      </FitsViewer>

      <FieldOverlay
        {geometry}
        stage={{ width: stageW, height: stageH }}
        {markers}
        visibility={store.visibility}
        gLimit={store.gLimit}
        grid={wcs && store.visibility.grid ? (store.solution?.grid ?? null) : null}
        {ring}
        apertureR={store.aperture * 2}
        interactive={!!store.frame && !offline}
        onselect={select}
      />

      <Hud {chips} {cursor} mini={null} rect={imageRect} stage={{ width: stageW, height: stageH }} {theme} solved={!!wcs} {sky} resetKey={store.path} />
      <RegionTool {tools} {geometry} stage={{ width: stageW, height: stageH }} />
      <ViewerMenu
        {geometry}
        skyAt={wcs ? (x, y) => pixelToSky(wcs!, x, y) : null}
        keys={{ fit: key('r2.view.fit'), one: key('r2.view.one-to-one'), region: key('r2.view.region') }}
        canIdentify={!!store.frame && !offline}
        identifyReason={store.frame ? offline : 'no frame yet'}
        hasSelection={!!store.measure}
        onaction={(a, p) => void menuAction(a, p)}
        oncopied={(what, text) => ontoast?.('info', `${what} copied`, text)}
      />
      {#if store.loading && store.frame}
        <div class="loading-chip" role="status"><Spinner size={12} /><span class="num">Loading {middleEllipsis(store.loading.slice(store.loading.lastIndexOf('/') + 1), 40)}…</span></div>
      {/if}
    </div>
    {#if strip && band > 0}{@render strip(band)}{/if}
    </div>

    {#if store.railOpen}
      <aside class="rail" aria-label="Frame inspector cards">
        <Card title="Frame" icon="metadata" collapsible persist="review.r2.frame">
          {#if store.frame}
            <p class="mono-line num" use:tooltip={{ text: store.path ?? '', placement: 'left' }}>{fileName}</p>
            {#each frameLines({ width: store.frame.header.width, height: store.frame.header.height }, store.info, store.header?.keywords ?? null, store.row) as line, i (i)}
              <p class="line num">{line}</p>
            {/each}
            {#if store.info && !store.info.raw}<p class="note">Converted for display (not 16-bit counts); measurements read the file’s own values.</p>{/if}
            <div class="row-actions"><IconButton icon="copy" label="Copy the path" size="s" tooltip="left" onclick={() => void copyPath()} /></div>
          {:else}
            <p class="muted">No frame.</p>
          {/if}
        </Card>

        <Card title="Selected star" icon="crosshair" collapsible persist="review.r2.star">
          {#if store.measuring && !store.measure}
            <p class="muted"><Spinner size={12} /> Measuring…</p>
          {:else if store.measureError}
            <p class="line" role="alert">{store.measureError}</p>
          {:else if mv}
            <p class="mono-line num">{mv.title}{#if store.measuring}<Spinner size={12} />{/if}</p>
            {#if mv.rows.length}
              <dl class="kv">
                {#each mv.rows as r (r.label)}
                  <dt use:tooltip={{ text: r.title ?? r.label, placement: 'left', disabled: !r.title }}>{r.label}</dt>
                  <dd class="num">{r.value}</dd>
                {/each}
              </dl>
              <p class="line num">{mv.sky}</p>
            {/if}
          {:else}
            <p class="muted">Click a star on the image to measure it (FWHM, HFD, SNR, peak, sky).</p>
          {/if}
          <div class="aperture">
            <Stepper label="Aperture radius (green px)" value={store.aperture} min={APERTURE_MIN} max={APERTURE_MAX} unit="px" limitSource="allowed" onchange={(v) => store.setAperture(v)} />
          </div>
        </Card>

        <Card title="Identification" icon="plate-solve" collapsible persist="review.r2.solve">
          {#snippet status()}
            {#if store.solving}<span class="badge">Solving</span>{:else if store.solution}<span class="badge">Identified</span>{/if}
          {/snippet}
          {#if store.solving}
            <p class="line"><Spinner size={12} /> {store.solveJob?.message ?? store.solveJob?.stage ?? 'Identifying field (ASTAP)…'}</p>
          {:else if store.solution}
            {#each solutionLines(store.solution.solution) as line, i (i)}<p class="line num">{line}</p>{/each}
            {#if store.fetching}
              <p class="line muted"><Spinner size={12} /> Identifying catalogue sources…</p>
            {:else if store.catalogueError}
              {@const w = catalogueWarning(store.catalogueError)}
              <p class="line" role="alert" use:tooltip={{ text: w.full }}>Catalogues unavailable: {w.short}</p>
            {:else if store.layers}
              <p class="line muted num">{int(Object.values(store.layers.counts).reduce((a, b) => a + (b ?? 0), 0))} catalogue markers</p>
              {#each store.layers.warnings.map(catalogueWarning) as w, i (i)}
                <p class="line muted" use:tooltip={{ text: w.full }}>{w.short}</p>
              {/each}
            {/if}
          {:else if store.solveError}
            <p class="line" role="alert">{store.solveError}</p>
          {:else}
            <p class="muted">Not identified: RA / Dec, the grid and the catalogues need a plate solve (ASTAP).</p>
          {/if}
          <div class="row-actions">
            <IconButton
              icon={store.solving ? 'stop' : 'plate-solve'}
              label={store.solving ? 'Cancel' : store.solution ? 'Identify again' : 'Identify field'}
              showLabel
              size="s"
              variant="secondary"
              glyphTone={store.solving ? 'danger' : undefined}
              disabledReason={noFrame ?? offline}
              onclick={() => void identify()}
            />
          </div>
        </Card>

        <Card title="Display" icon="histogram" collapsible persist="review.r2.display">
          <Histogram histogram={histogram} levels={store.levels} {theme} height={72} handles transfer {tint} palette={effectivePalette(tools.palette, nightRed)} onlevel={(p) => store.setLevel(p)} />
          <p class="note">{store.autoStretch ? 'Auto stretch (A): the levels follow each frame.' : 'Manual levels: they stay as you step through frames.'}</p>
        </Card>

        <Card title="FITS header" icon="metadata" collapsible open={false} persist="review.r2.header">
          {#if store.header}
            <div class="hdr-tools">
              <SearchField label="Filter the header" value={headerQuery} placeholder="Filter: key, value…" width="100%" count={headerQuery.trim() ? `${int(cards.length)} of ${int(store.header.cards.length)}` : null} oninput={(v) => (headerQuery = v)} />
              <IconButton icon="copy" label="Copy the header" size="s" tooltip="left" onclick={() => void copyHeader()} />
            </div>
            <div class="cards" role="list" aria-label="FITS header cards">
              {#each cards as c, i (i)}
                <div class="card-line num" role="listitem"><span class="ck">{c.key}</span><span class="cv">{c.value}</span>{#if c.comment}<span class="cc">/ {c.comment}</span>{/if}</div>
              {/each}
              {#if !cards.length}<p class="muted">No card matches.</p>{/if}
            </div>
          {:else if store.headerError}
            <p class="line" role="alert">{store.headerError}</p>
          {:else}
            <p class="muted">No frame.</p>
          {/if}
        </Card>
      </aside>
    {/if}
  </div>
</div>

<CatalogPopover
  external
  anchor={catalogueBtn}
  bind:open={catalogueOpen}
  visibility={store.visibility}
  {counts}
  solved={!!store.solution}
  solving={store.solving}
  catalog={catalogState}
  gLimit={store.gLimit ?? gMax}
  {gMax}
  gridKey={key('r2.field.grid')}
  labelsKey={key('r2.field.labels')}
  onvisible={(id, on) => store.setVisible(id, on)}
  onglimit={(v) => (store.gLimit = v)}
  onglimitcommit={(v) => onglimitcommit?.(Math.round(v * 10) / 10)}
  onidentify={() => void identify()}
  oncatalogsettings={() => openSheet('catalogues')}
  onsolvesettings={() => openSheet('plate_solving')}
/>

<Sheet
  bind:open={sheetOpen}
  title={sheetKind === 'catalogues' ? 'Catalogue settings' : 'Field identification settings'}
  subtitle="Saved as you change them; identify the field again to fetch the catalogues with them"
>
  {#if sheetKind === 'catalogues'}<Catalogues />{:else}<PlateSolving />{/if}
  {#snippet footer()}
    {#if onallsettings}
      <button
        type="button"
        class="all"
        onclick={() => {
          sheetOpen = false;
          onallsettings?.(sheetKind);
        }}>All settings</button
      >
    {/if}
  {/snippet}
</Sheet>

<style>
  .r2 {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-width: 0;
    min-height: 0;
    background: var(--bg);
  }
  .toolbar {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--space-1);
    height: var(--toolbar-h);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg);
    min-width: 0;
    overflow: hidden;
  }
  .crumb {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: var(--space-1);
    height: 30px;
    max-width: 220px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font: inherit;
    font-size: var(--text-s);
    cursor: pointer;
  }
  .crumb:hover {
    background: var(--hover-bg);
  }
  .crumb:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
  .crumb :global(svg) {
    flex: none;
    color: var(--fg-muted);
  }
  .crumb-session {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .crumb-sep {
    color: var(--text-muted);
  }
  .file {
    min-width: 0;
    max-width: 280px;
    overflow: hidden;
    color: var(--fg);
    font-size: var(--text-s);
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-right: var(--space-1);
  }
  .pos {
    flex: none;
    min-width: 9ch;
    white-space: nowrap;
    color: var(--text-muted);
    font-size: var(--text-s);
    text-align: center;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .divider {
    flex: none;
    width: var(--border-w);
    height: 20px;
    margin: 0 var(--space-1);
    background: var(--border);
  }
  .grow {
    flex: 1;
  }
  .banner {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--space-2);
    min-height: 32px;
    padding: var(--space-1) var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    background: var(--bg-2);
    box-shadow: inset 3px 0 0 var(--danger);
    font-size: var(--text-s);
  }
  .banner .msg {
    flex: 1;
    min-width: 0;
  }
  .workspace {
    display: grid;
    flex: 1 1 0;
    grid-template-columns: minmax(0, 1fr) var(--rail-min-w);
    min-height: 0;
  }
  .rail-closed .workspace {
    grid-template-columns: minmax(0, 1fr);
  }
  /* The image is the hero (WF-D: at least 75 % of the width): the rail takes 25 % at most. */
  .workspace {
    grid-template-columns: minmax(0, 1fr) clamp(280px, 25%, var(--rail-min-w));
  }
  .col {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }
  .col > .stage {
    flex: 1 1 0;
  }
  .stage {
    position: relative;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    background: var(--viewer-bg, var(--bg-2));
  }
  .stage :global(.frame-edge) {
    fill: none;
    stroke: var(--border);
    stroke-width: 1;
  }
  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    height: 100%;
    padding: var(--space-6);
    color: var(--fg-muted);
    text-align: center;
  }
  .empty .title {
    margin: var(--space-2) 0 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .empty .hint {
    max-width: 44ch;
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .empty .cta {
    margin-top: var(--space-2);
  }
  .loading-chip {
    position: absolute;
    /* Below the HUD's chip row (top left), so a narrow stage keeps both readable. */
    top: var(--toolbar-h);
    left: 50%;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--surface);
    color: var(--fg);
    font-size: var(--text-xs);
    transform: translateX(-50%);
    max-width: calc(100% - var(--space-6));
    white-space: nowrap;
    overflow: hidden;
  }
  .rail {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
    min-height: 0;
    padding: var(--space-2);
    overflow-y: auto;
    border-left: var(--border-w) solid var(--border);
    background: var(--bg);
  }
  .line,
  .mono-line,
  .note,
  .muted {
    margin: 0;
    font-size: var(--text-s);
  }
  .line,
  .mono-line {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .mono-line {
    font-weight: var(--weight-medium);
  }
  .note,
  .muted {
    color: var(--text-muted);
  }
  .note {
    font-size: var(--text-xs);
  }
  .row-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
  .kv {
    display: grid;
    grid-template-columns: 6ch minmax(0, 1fr);
    gap: var(--space-1) var(--space-3);
    margin: var(--space-2) 0;
    font-size: var(--text-s);
  }
  .kv dt {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
    align-self: center;
  }
  .kv dd {
    margin: 0;
    text-align: right;
  }
  .aperture {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
  .all {
    padding: var(--space-1) 0;
    border: none;
    background: none;
    color: var(--fg-muted);
    font: inherit;
    font-size: var(--text-s);
    text-decoration: underline;
    cursor: pointer;
  }
  .all:hover {
    color: var(--fg);
  }
  .all:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }
  .badge {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .hdr-tools {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-2);
  }
  .hdr-tools :global(.search) {
    flex: 1;
  }
  .cards {
    max-height: 320px;
    overflow: auto;
    font-size: var(--text-xs);
  }
  .card-line {
    display: grid;
    grid-template-columns: 9ch minmax(0, 1fr);
    column-gap: var(--space-2);
    padding: 1px 0;
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .ck {
    color: var(--text-muted);
  }
  .cv {
    overflow-wrap: anywhere;
  }
  .cc {
    grid-column: 2;
    color: var(--text-muted);
    overflow-wrap: anywhere;
  }
</style>
