<!--
  Observe (imaging) screen: toolbar; the 16-bit image viewer with the levels
  strip docked under it (sized to the band a 16:9 frame leaves, BRAND 11.1)
  and the optional activity log; the right rail of cards (connection,
  camera, mount).

  Single-key shortcuts (icon-inventory.json, BRAND section 7) only fire when
  focus is not in a text field and never move hardware; Escape aborts a slew
  (and nothing else). Tracking keeps no single key (the inventory proposes T,
  but starting or stopping the sidereal drive moves the mount).

  A frame that is not current (equipment disconnected, server link down, or
  no new frame for max(5 s, three exposures)) says so: its source chip reads
  "Last frame · 21:34:05 UTC", the frame edge is dashed, and a prompt to
  connect sits at the bottom of the image, never over its centre.
-->
<script lang="ts">
  import { isTypingTarget, matchesShortcut } from '../app/shortcuts';
  import { useApp } from '../app/state.svelte';
  import Icon from '../components/Icon.svelte';
  import IconButton from '../components/IconButton.svelte';
  import LogDrawer from '../shell/LogDrawer.svelte';
  import FitsViewer from '../viewer/FitsViewer.svelte';
  import { displaySize, effectiveTurns } from '../viewer/rotation';
  import CameraCard from './CameraCard.svelte';
  import ConnectionCard from './ConnectionCard.svelte';
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
    const sensor = app.connected ? app.camera?.sensor : null;
    if (!w || !h) [w, h] = sensor ? [sensor.width, sensor.height] : [1080, 1920];
    return displaySize(w, h, effectiveTurns(app.rotation, w, h));
  });
  const strip = $derived(
    stripLayout({ width: centerW, height: centerH }, displayed, app.logOpen ? LOG_H : 0, app.stripOpen),
  );

  // -- Frame chips ------------------------------------------------------------
  const seconds = (s: number) => `${s.toFixed(s < 1 ? 3 : 1)} s`;
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

  const SHORTCUTS: [string, () => void][] = [
    ['E', () => !app.cameraBusy && app.canCommand && void app.capture()],
    ['V', () => app.canCommand && void app.toggleLive()],
    ['Escape', () => app.abortMotion()],
    ['+', () => zoom('in')],
    ['-', () => zoom('out')],
    ['F', () => zoom('fit')],
    ['Shift+F', () => zoom('fill')],
    ['1', () => zoom('1to1')],
    ['A', () => app.setAutoStretch(!app.autoStretch)],
    ['Shift+A', () => app.resetStretch()],
    ['H', () => app.toggleStrip()],
    ['X', () => (app.crosshair = !app.crosshair)],
    ['P', () => app.toggleRail()],
  ];

  function onKey(e: KeyboardEvent): void {
    if (e.defaultPrevented || e.repeat) return;
    // In a text field letters are text; Escape leaves the field and still
    // aborts a slew (a safety key works from anywhere).
    if (isTypingTarget(e.target)) {
      if (e.key === 'Escape') {
        (e.target as HTMLElement).blur();
        app.abortMotion();
      }
      return;
    }
    for (const [spec, action] of SHORTCUTS) {
      if (matchesShortcut(e, spec)) {
        e.preventDefault();
        action();
        return;
      }
    }
  }

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

  const connectLabel = $derived(app.connectMode === 'alpaca' ? 'Connect Seestar' : 'Connect simulator');
  const connectReason = $derived.by(() => {
    const problem = app.connectProblem();
    return problem && app.linkOpen ? `${problem} in the Connection card` : problem;
  });
</script>

<svelte:window onkeydown={onKey} />

{#snippet connectButton()}
  <IconButton
    icon={app.connectMode === 'alpaca' ? 'connect' : 'simulator'}
    label={connectLabel}
    showLabel
    variant="primary"
    tooltip="top"
    busy={!!app.busy.connection || app.connection?.state === 'connecting'}
    disabledReason={connectReason}
    onclick={() => app.connect()}
  />
{/snippet}

<div class="imaging">
  <ImagingToolbar {hasFrame} onzoom={zoom} />

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
              {:else if !app.connected}
                <Icon name={app.connectMode === 'alpaca' ? 'connect' : 'simulator'} size={48} />
                <p class="title">No equipment connected</p>
                <p class="hint">Choose the simulator or a Seestar in the Connection card.</p>
                <div class="cta">{@render connectButton()}</div>
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
          {#if app.linkOpen && !app.connected}
            <div class="prompt" role="group" aria-label="No equipment connected">
              <span class="prompt-text">No equipment connected</span>
              {@render connectButton()}
            </div>
          {:else if app.stale && app.events.link !== 'idle'}
            <div class="prompt" role="status">
              <span class="prompt-text">Server offline: the last frame and states are shown greyed</span>
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
        <ConnectionCard />
        <CameraCard />
        <MountCard />
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
    grid-template-columns: minmax(0, 1fr) var(--rail-min-w);
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
    margin-top: var(--space-3);
    pointer-events: auto;
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
