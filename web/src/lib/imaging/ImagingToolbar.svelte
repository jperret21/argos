<!--
  Imaging toolbar: routine, reversible tools are icon-only with a tooltip
  (label + shortcut); actions that stop a run keep their label (BRAND
  section 7, icon-inventory.json "display"). Groups, left to right:
  connection chip, acquisition, view, display, panels and theme.

  The first slot is a chip, not a button that connects or disconnects:
  connecting belongs to the Connection card (where the device is chosen) and
  the viewer's prompt; the chip says what is connected and, clicked, opens
  that card. Keyboard shortcuts are wired in ImagingScreen (they need the
  viewer); the `shortcut` props here only document them (tooltip +
  aria-keyshortcuts).
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import { connectionStatus } from '../app/status';
  import { nextTheme, THEME_LABELS } from '../app/theme';
  import IconButton from '../components/IconButton.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { tooltip } from '../components/tooltip';

  interface Props {
    hasFrame: boolean;
    onzoom: (action: 'in' | 'out' | 'fit' | 'fill' | '1to1') => void;
  }

  let { hasFrame, onzoom }: Props = $props();
  const app = useApp();

  const exposureReason = $derived.by(() => {
    if (app.stale) return 'the ARGOS server is not reachable';
    if (!app.connected) return 'connect the equipment first';
    return app.exposureProblem();
  });
  const captureReason = $derived(
    exposureReason ?? (app.cameraBusy ? 'the camera is busy' : null),
  );
  const viewReason = $derived(hasFrame ? null : 'no frame yet');

  const conn = $derived(connectionStatus(app.connection, app.events.link));
  /** Short name for the chip: the full device name is in its tooltip. */
  const chipName = $derived.by(() => {
    if (!app.linkOpen || !app.connected) return conn.label;
    if (app.connection?.mode === 'simulator') return 'Simulator';
    return app.connection?.device_name ?? 'Seestar';
  });
  const stopRunning = $derived(app.cameraBusy || app.slewing);
</script>

<div class="toolbar" role="toolbar" aria-label="Imaging tools">
  <button
    type="button"
    class="chip"
    aria-label={`Connection: ${chipName}. Show the Connection card`}
    use:tooltip={{
      text: app.connected && app.connection?.device_name
        ? `${app.connection.device_name}: show the Connection card`
        : 'Show the Connection card',
      placement: 'bottom',
    }}
    onclick={() => app.revealConnection()}
  >
    <StatusBadge tone={conn.tone} label={chipName} plain />
  </button>

  <span class="sep" aria-hidden="true"></span>

  <div class="group">
    <IconButton
      icon="capture"
      label="Take one exposure"
      shortcut="E"
      variant="ghost"
      busy={!!app.busy.capture || app.camera?.state === 'exposing' || app.camera?.state === 'downloading'}
      disabledReason={app.camera?.state === 'exposing' || app.camera?.state === 'downloading'
        ? null
        : captureReason}
      onclick={() => app.capture()}
    />
    <IconButton
      icon="live"
      label={app.live ? 'Stop live view' : 'Start live view'}
      shortcut="V"
      variant="ghost"
      pressed={app.live}
      busy={!!app.busy.live}
      disabledReason={app.live ? (app.stale ? 'the ARGOS server is not reachable' : null) : captureReason}
      onclick={() => app.toggleLive()}
    />
    <!-- Stopping live view is routine: red glyph only. A slew is motion: full danger. -->
    <IconButton
      icon="stop"
      label="Stop"
      tooltipText="Stop the exposure, live view or slew"
      showLabel
      variant={app.slewing ? 'danger' : 'secondary'}
      glyphTone={stopRunning ? 'danger' : undefined}
      busy={!!app.busy.cameraStop}
      disabledReason={app.stale ? 'the ARGOS server is not reachable' : stopRunning ? null : 'nothing is running'}
      onclick={() => app.stopAll()}
    />
  </div>

  <span class="sep" aria-hidden="true"></span>

  <div class="group">
    <IconButton
      icon="zoom-out"
      label="Zoom out"
      shortcut="-"
      variant="ghost"
      disabledReason={viewReason}
      onclick={() => onzoom('out')}
    />
    <span class="zoom num" aria-live="off">{hasFrame ? `${Math.round(app.zoom * 100)}%` : '—'}</span>
    <IconButton
      icon="zoom-in"
      label="Zoom in"
      shortcut="+"
      variant="ghost"
      disabledReason={viewReason}
      onclick={() => onzoom('in')}
    />
    <IconButton
      icon="zoom-fit"
      label="Fit: whole frame"
      shortcut="F"
      variant="ghost"
      disabledReason={viewReason}
      onclick={() => onzoom('fit')}
    />
    <IconButton
      icon="zoom-fill"
      label="Fill the viewer (crops the long sides)"
      shortcut="Shift+F"
      variant="ghost"
      disabledReason={viewReason}
      onclick={() => onzoom('fill')}
    />
    <IconButton
      icon="zoom-1to1"
      label="Actual pixels (1:1)"
      shortcut="1"
      variant="ghost"
      disabledReason={viewReason}
      onclick={() => onzoom('1to1')}
    />
  </div>

  <span class="sep" aria-hidden="true"></span>

  <div class="group">
    <IconButton
      icon="stretch-auto"
      label="Auto stretch"
      shortcut="A"
      variant="ghost"
      pressed={app.autoStretch}
      onclick={() => app.setAutoStretch(!app.autoStretch)}
    />
    <IconButton
      icon="stretch-reset"
      label="Reset stretch (linear, full range)"
      shortcut="Shift+A"
      variant="ghost"
      disabledReason={viewReason}
      onclick={() => app.resetStretch()}
    />
    <IconButton
      icon="histogram"
      label="Levels strip (histogram)"
      shortcut="H"
      variant="ghost"
      pressed={app.stripOpen}
      layoutToggle
      onclick={() => app.toggleStrip()}
    />
    <IconButton
      icon="crosshair"
      label="Crosshair on image"
      shortcut="X"
      variant="ghost"
      pressed={app.crosshair}
      onclick={() => (app.crosshair = !app.crosshair)}
    />
  </div>

  <span class="spacer"></span>

  <div class="group">
    <IconButton
      icon="panels"
      label="Instrument panels"
      shortcut="P"
      variant="ghost"
      pressed={app.railOpen}
      layoutToggle
      tooltip="left"
      onclick={() => app.toggleRail()}
    />
    <IconButton
      icon="theme"
      label="Switch theme"
      tooltipText={`Theme: ${THEME_LABELS[app.theme]} (next: ${THEME_LABELS[nextTheme(app.theme)]})`}
      variant="ghost"
      tooltip="left"
      onclick={() => app.cycleTheme()}
    />
  </div>
</div>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: calc(var(--control-h-m) + 2 * var(--space-2) + var(--border-w));
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg);
    min-width: 0;
  }

  .group {
    display: flex;
    align-items: center;
    gap: var(--space-1);
  }

  .sep {
    width: 1px;
    height: 20px;
    background: var(--border-soft);
  }

  .spacer {
    flex: 1;
  }

  /* Connection chip: reads as a status, behaves as a link to the card. */
  .chip {
    display: inline-flex;
    align-items: center;
    height: var(--control-h-s);
    max-width: 200px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    cursor: pointer;
    overflow: hidden;
  }
  .chip:hover {
    background: var(--hover-bg);
  }

  .zoom {
    min-width: 5ch;
    color: var(--text-muted);
    font-size: var(--text-s);
    text-align: center;
  }
</style>
