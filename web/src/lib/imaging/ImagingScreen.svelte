<!--
  Observe (imaging) screen: toolbar; the 16-bit image viewer with the levels
  strip docked under it (sized to the band a 16:9 frame leaves, BRAND 11.1)
  and the optional activity log; the right rail of cards (camera, mount).
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
  import { SectionLayout } from '../app/layout.svelte';
  import { useApp } from '../app/state.svelte';
  import Icon from '../components/Icon.svelte';
  import IconButton from '../components/IconButton.svelte';
  import { seconds } from '../format/number';
  import LogDrawer from '../shell/LogDrawer.svelte';
  import FitsViewer from '../viewer/FitsViewer.svelte';
  import { displaySize, effectiveTurns } from '../viewer/rotation';
  import CameraCard from './CameraCard.svelte';
  import ImagingToolbar from './ImagingToolbar.svelte';
  import { stripLayout } from './layout';
  import LevelsStrip from './LevelsStrip.svelte';
  import MountCard from './MountCard.svelte';

  interface Props {
    perf?: boolean;
  }

  let { perf = false }: Props = $props();
  const app = useApp();
  let viewer: FitsViewer | undefined = $state();

  const ZOOM_STEP = 1.5;
  const LOG_H = 216;
  const hasFrame = $derived(!!app.shown);
  const seq = $derived(app.shown?.frame.header.seq ?? 0);
  const header = $derived(app.shown?.frame.header ?? null);

  // -- Layout: the strip takes the band under the fitted frame ----------------
  let centerW = $state(0);
  let centerH = $state(0);
  let stageW = $state(0);
  let stageH = $state(0);

  /** Displayed (rotated) frame size: the frame on screen, else the sensor, else a Seestar's. */
  const displayed = $derived.by(() => {
    let w = header?.width;
    let h = header?.height;
    const sensor = app.cameraReady ? app.camera?.sensor : null;
    if (!w || !h) [w, h] = sensor ? [sensor.width, sensor.height] : [1080, 1920];
    return displaySize(w, h, effectiveTurns(app.rotation, w, h));
  });
  const strip = $derived(
    stripLayout({ width: centerW, height: centerH }, displayed, app.logOpen ? LOG_H : 0, app.stripOpen),
  );

  // -- Frame chips ------------------------------------------------------------
  const stale = $derived(app.frameStale);
  const sourceChip = $derived.by(() => {
    if (!header) return '';
    if (header.source === 'file') return 'File';
    if (stale) return `Last frame · ${new Date(header.timestamp).toISOString().slice(11, 19)} UTC`;
    return header.source === 'simulator' ? 'Simulator' : 'Seestar';
  });
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

  /** Rail cards shown (Panels popover) and Reset layout (D16): card folds included. */
  const layout = new SectionLayout('imaging', {
    panels: { camera: true, mount: true },
    extraKeys: ['argos.card.camera', 'argos.card.mount'],
  });

  // Observe keys, through the one registry (scope "imaging"): bound while
  // this screen is mounted, so the "?" sheet and the tooltips read the same map.
  $effect(() => {
    const r = app.shortcuts;
    const off = [
      r.handle('observe.capture', () => {
        if (!app.cameraBusy && app.canCamera && !app.exposureProblem()) void app.capture();
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
      r.handle('view.levels', () => app.toggleStrip()),
      r.handle('view.crosshair', () => (app.crosshair = !app.crosshair)),
      r.handle('rail.toggle', () => app.toggleRail()),
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

<div class="imaging">
  <ImagingToolbar {hasFrame} onzoom={zoom} {layout} />

  <div class="workspace" class:rail-closed={!app.railOpen}>
    <div
      class="center"
      bind:clientWidth={centerW}
      bind:clientHeight={centerH}
      style:grid-template-rows="minmax(0, 1fr) {strip.height}px {app.logOpen ? `${LOG_H}px` : '0px'}"
    >
      <div
        class="stage"
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

        {#if header}
          <div
            class="hud"
            aria-hidden="true"
            style:left="{Math.max(0, app.imageRect?.left ?? 0) + 8}px"
            style:top="{Math.max(0, app.imageRect?.top ?? 0) + 8}px"
          >
            {#if app.live && !stale}
              <span class="chip live"><span class="dot"></span>Live</span>
            {:else if app.camera?.state === 'exposing' && !stale}
              <span class="chip"><span class="dot busy"></span>Exposing</span>
            {/if}
            <span class="chip num" class:muted={stale}>#{header.seq}</span>
            <span class="chip num" class:muted={stale} class:pending={exposureChip.includes('→')}>
              {exposureChip}
            </span>
            <span class="chip" class:muted={stale}>{sourceChip}</span>
            {#if filling}
              <span class="chip">Fill · cropped</span>
            {/if}
          </div>

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

      {#if strip.height > 0}
        <LevelsStrip height={strip.height} compact={strip.compact} />
      {:else}
        <div></div>
      {/if}

      {#if app.logOpen}
        <LogDrawer />
      {/if}
    </div>

    {#if app.railOpen}
      <!-- Observing cards first (camera), then the mount; set-up folds away once connected (BRAND 11.1). -->
      <aside class="rail" aria-label="Instrument panels">
        {#key layout.generation}
          {#if layout.visible('camera')}<CameraCard />{/if}
          {#if layout.visible('mount')}<MountCard />{/if}
          {#if !layout.visible('camera') && !layout.visible('mount')}
            <p class="rail-empty">Every card is hidden: show them again from the Panels menu at the right of the toolbar.</p>
          {/if}
        {/key}
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

  .workspace {
    display: grid;
    grid-template-columns: minmax(0, 1fr) var(--rail-w); /* 400 px default, 360-580 when resizable (D8) */
    min-height: 0;
  }
  .workspace.rail-closed {
    grid-template-columns: minmax(0, 1fr);
  }

  .center {
    display: grid;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }

  .stage {
    position: relative;
    min-height: 0;
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

  /* Frame chips sit over the image, in its top-left corner (BRAND 11.1). */
  .hud {
    position: absolute;
    display: flex;
    gap: var(--space-1);
    pointer-events: none;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 20px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
  }
  .chip.live {
    color: var(--fg);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
  }
  .dot {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
    background: var(--accent);
  }
  .dot.busy {
    background: var(--warning);
  }
  .chip.muted {
    color: var(--text-muted);
  }
  .chip.pending {
    border-color: var(--status-busy);
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
    padding: var(--space-4);
    border-left: var(--border-w) solid var(--border);
    background: var(--bg-2);
    overflow-y: auto;
    overscroll-behavior: contain;
  }
</style>
