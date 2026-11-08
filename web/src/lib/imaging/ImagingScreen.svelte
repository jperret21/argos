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
  import CameraCard from './CameraCard.svelte';
  import FocuserCard from './FocuserCard.svelte';
  import ImagingToolbar from './ImagingToolbar.svelte';
  import Band from './modes/Band.svelte';
  import DisplayTools from './modes/DisplayTools.svelte';
  import { exposureCheck, profileLimits, recent } from './modes/exposure';
  import FocusBand from './modes/FocusBand.svelte';
  import FramingBand from './modes/FramingBand.svelte';
  import { BAND, bandLayout, bandMax, DRAWER_TABS, drawerHeight, layoutCost, RAIL, type CardId } from './modes/layout';
  import MountCard from './MountCard.svelte';

  interface Props {
    perf?: boolean;
  }

  let { perf = false }: Props = $props();
  const app = useApp();
  let viewer: FitsViewer | undefined = $state();

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

  const chips = $derived(
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
  const cursor = $derived(cursorReadout(app.pointer));
  const mini = $derived(
    showMiniHistogram(ws.mode, layout.bandOpen) ? miniHistogram(app.shown?.histogram ?? null, app.levels) : null,
  );

  // -- Band content ---------------------------------------------------------------
  const activeProfile = $derived(app.profiles?.profiles.find((p) => p.key === app.profiles?.active) ?? null);
  const limits = $derived(profileLimits(activeProfile));
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

  // -- Cards: one order (D10), the state each mode remembers -----------------------
  const cardOpen = (id: CardId) => layout.cards[id] === 'open';
  const visibleCards = $derived((['camera', 'mount', 'focuser'] as CardId[]).filter((id) => layout.cards[id] !== 'hidden'));
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
      r.handle('rail.toggle', () => ws.toggleRail()),
      r.handle('drawer.toggle', () => ws.toggleDrawer()),
      r.handle('observe.mode.framing', () => ws.setMode('framing')),
      r.handle('observe.mode.focus', () => ws.setMode('focus')),
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
  <ImagingToolbar {hasFrame} onzoom={zoom} />

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

        <Hud
          {chips}
          {cursor}
          {mini}
          rect={app.imageRect}
          stage={{ width: stageW, height: stageH }}
          dragReadout={ws.dragReadout}
          theme={app.theme}
        />

        {#if header}
          <!-- A frame on screen but no equipment: the prompt sits at the bottom, off the image centre. -->
          {#if app.linkOpen && !app.cameraReady}
            <div class="prompt" role="group" aria-label={cameraMissing ? 'Camera not connected' : 'No equipment connected'}>
              <span class="prompt-text">{cameraMissing ? 'Camera not connected' : 'No equipment connected'}</span>
              {@render connectButton()}
            </div>
          {:else if app.stale && app.events.link !== 'idle'}
            <div class="prompt" role="status">
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
                <DisplayTools
                  mode={app.levels?.mode ?? 'linear'}
                  rotation={app.rotation}
                  disabled={!app.levels}
                  onmode={(mode) => app.setLevel({ mode })}
                  onrotation={(r) => app.setRotation(r)}
                />
              {/if}
            {/snippet}
            {#snippet children({ height, compact })}
              {#if ws.mode === 'focus'}
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
            ontab={(id) => ws.setDrawer({ drawerTab: id as 'conditions' | 'log' })}
          >
            {#snippet tools(id: string)}
              {#if id === 'conditions'}
                <ConditionsTools store={app.conditions} view={app.conditionsView} expecting={app.live} />
              {/if}
            {/snippet}
            {#snippet content(id: string)}
              {#if id === 'conditions'}
                <ConditionsTimeline store={app.conditions} view={app.conditionsView} theme={app.theme} expecting={app.live} periods={app.afPeriods} rows />
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
        {#if visibleCards.includes('mount')}
          <MountCard bind:open={() => cardOpen('mount'), (v) => ws.setCardOpen('mount', v)} />
        {/if}
        {#if visibleCards.includes('focuser')}
          <FocuserCard bandShowsVCurve={bandVCurve} bind:open={() => cardOpen('focuser'), (v) => ws.setCardOpen('focuser', v)} />
        {/if}
        {#if visibleCards.length === 0}
          <p class="rail-empty">Every card is hidden in this mode: show them again from Arrange at the right of the toolbar.</p>
        {/if}
      </aside>
    {/if}
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
