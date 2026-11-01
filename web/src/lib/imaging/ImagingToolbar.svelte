<!--
  Imaging toolbar: routine, reversible tools are icon-only with a tooltip
  (label + shortcut); actions that stop a run keep their label (BRAND
  section 7, icon-inventory.json "display"). Groups, left to right:
  equipment, acquisition, view, display, then [arrange] (Panels popover)
  and [panels] (right rail, P) at the right end (D1).

  - Equipment (D10): the one shortcut to the Connection screen's actions:
    [connect Connect] (all four devices, with the link chosen on the
    Connection screen) or [disconnect Disconnect] (all, asking first when
    live view, an exposure or a slew runs, Q-C5). The details live on the
    Connection screen; the status-bar device cluster links there.
  - The theme switch moved to the rail footer (D15).
  - Keyboard shortcuts are bound by ImagingScreen through the registry; the
    `shortcut` props here read the same keymap (tooltip + aria-keyshortcuts).
-->
<script lang="ts">
  import type { SectionLayout } from '../app/layout.svelte';
  import { useApp } from '../app/state.svelte';
  import ConfirmDialog from '../components/ConfirmDialog.svelte';
  import IconButton from '../components/IconButton.svelte';
  import PanelsPopover, { type PanelGroup } from '../components/PanelsPopover.svelte';
  import { disconnectRisk } from '../connection/model';

  interface Props {
    hasFrame: boolean;
    onzoom: (action: 'in' | 'out' | 'fit' | 'fill' | '1to1') => void;
    layout: SectionLayout;
  }

  let { hasFrame, onzoom, layout }: Props = $props();
  const app = useApp();
  const key = (id: string) => app.shortcuts.keyFor(id);

  const exposureReason = $derived.by(() => {
    if (app.stale) return 'the ARGOS server is not reachable';
    if (!app.cameraReady) return app.connected ? 'connect the camera first' : 'connect the equipment first';
    return app.exposureProblem();
  });
  const captureReason = $derived(
    exposureReason ?? (app.cameraBusy ? 'the camera is busy' : null),
  );
  const viewReason = $derived(hasFrame ? null : 'no frame yet');

  const stopRunning = $derived(app.cameraBusy || app.slewing);

  // -- Equipment (D10) --------------------------------------------------------
  const equipment = $derived(app.equipment);
  const linked = $derived(equipment.anyLinked);
  const equipmentBusy = $derived(!!app.busy.connectAll || !!app.busy.disconnectAll || equipment.anyConnecting);
  const equipmentTip = $derived(`Equipment: ${equipment.text}. Details on the Connection screen (F1)`);
  const connectReason = $derived.by(() => {
    const problem = app.connectProblem();
    return problem && app.linkOpen ? `${problem} on the Connection screen` : problem;
  });
  let confirmOpen = $state(false);
  const risk = $derived(disconnectRisk(app.running));

  function equipmentAction(): void {
    if (!linked) {
      void app.connectAll();
      return;
    }
    if (risk) confirmOpen = true;
    else void app.disconnectAll();
  }

  // -- Panels popover (D1, D16) ------------------------------------------------
  const PANEL_GROUPS: PanelGroup[] = [
    {
      title: 'Right rail',
      panels: [
        { id: 'camera', label: 'Camera' },
        { id: 'mount', label: 'Mount' },
      ],
    },
    { title: 'Under the image', panels: [{ id: 'levels', label: 'Levels strip (histogram)' }] },
    { title: 'Bottom drawer', panels: [{ id: 'log', label: 'Log' }] },
  ];

  function panelVisible(id: string): boolean {
    if (id === 'levels') return app.stripOpen;
    if (id === 'log') return app.logOpen;
    return layout.visible(id);
  }

  function setPanel(id: string, on: boolean): void {
    if (id === 'levels') {
      if (app.stripOpen !== on) app.toggleStrip();
    } else if (id === 'log') app.setLogOpen(on);
    else {
      layout.setVisible(id, on);
      if (on && !app.railOpen) app.toggleRail();
    }
  }

  function resetLayout(): void {
    layout.reset();
    if (!app.stripOpen) app.toggleStrip();
    if (!app.railOpen) app.toggleRail();
    app.toast('info', 'Observe layout restored');
  }
</script>

<div class="toolbar" role="toolbar" aria-label="Imaging tools">
  <IconButton
    icon={linked ? 'disconnect' : app.connectMode === 'simulator' ? 'simulator' : 'connect'}
    label={linked ? 'Disconnect all' : 'Connect all'}
    tooltipText={linked ? `Disconnect all. ${equipmentTip}` : `Connect all. ${equipmentTip}`}
    showLabel
    size="s"
    variant="secondary"
    glyphTone={linked ? 'danger' : undefined}
    busy={equipmentBusy}
    disabledReason={app.stale ? 'the ARGOS server is not reachable' : linked ? null : connectReason}
    onclick={equipmentAction}
  />

  <span class="sep" aria-hidden="true"></span>

  <div class="group">
    <IconButton
      icon="capture"
      label="Take one exposure"
      shortcut={key('observe.capture')}
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
      shortcut={key('observe.live')}
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
      shortcut={key('view.zoom-out')}
      variant="ghost"
      disabledReason={viewReason}
      onclick={() => onzoom('out')}
    />
    <span class="zoom num" aria-live="off">{hasFrame ? `${Math.round(app.zoom * 100)}%` : '—'}</span>
    <IconButton
      icon="zoom-in"
      label="Zoom in"
      shortcut={key('view.zoom-in')}
      variant="ghost"
      disabledReason={viewReason}
      onclick={() => onzoom('in')}
    />
    <IconButton
      icon="zoom-fit"
      label="Fit: whole frame"
      shortcut={key('view.fit')}
      variant="ghost"
      disabledReason={viewReason}
      onclick={() => onzoom('fit')}
    />
    <IconButton
      icon="zoom-fill"
      label="Fill the viewer (crops the long sides)"
      shortcut={key('view.fill')}
      variant="ghost"
      disabledReason={viewReason}
      onclick={() => onzoom('fill')}
    />
    <IconButton
      icon="zoom-1to1"
      label="Actual pixels (1:1)"
      shortcut={key('view.one-to-one')}
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
      shortcut={key('view.stretch-auto')}
      variant="ghost"
      pressed={app.autoStretch}
      onclick={() => app.setAutoStretch(!app.autoStretch)}
    />
    <IconButton
      icon="stretch-reset"
      label="Reset stretch (linear, full range)"
      shortcut={key('view.stretch-reset')}
      variant="ghost"
      disabledReason={viewReason}
      onclick={() => app.resetStretch()}
    />
    <IconButton
      icon="histogram"
      label="Levels strip (histogram)"
      shortcut={key('view.levels')}
      variant="ghost"
      pressed={app.stripOpen}
      layoutToggle
      onclick={() => app.toggleStrip()}
    />
    <IconButton
      icon="crosshair"
      label="Crosshair on image"
      shortcut={key('view.crosshair')}
      variant="ghost"
      pressed={app.crosshair}
      onclick={() => (app.crosshair = !app.crosshair)}
    />
  </div>

  <span class="spacer"></span>

  <div class="group">
    <PanelsPopover groups={PANEL_GROUPS} visible={panelVisible} onchange={setPanel} onreset={resetLayout} section="Observe" />
    <IconButton
      icon="panels"
      label="Instrument panels"
      shortcut={key('rail.toggle')}
      variant="ghost"
      pressed={app.railOpen}
      layoutToggle
      tooltip="left"
      onclick={() => app.toggleRail()}
    />
  </div>
</div>

<ConfirmDialog
  bind:open={confirmOpen}
  title="Disconnect the equipment?"
  message={`${risk ?? ''} Disconnecting releases the mount, the camera, the filter wheel and the focuser.`}
  confirmLabel="Disconnect all"
  destructive
  onconfirm={() => app.disconnectAll()}
/>

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


  .zoom {
    min-width: 5ch;
    color: var(--text-muted);
    font-size: var(--text-s);
    text-align: center;
  }
</style>
