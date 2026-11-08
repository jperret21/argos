<!--
  Observe toolbar (README 1.1, 1.2; PROPOSAL 3.3 "Data-driven toolbar",
  "Split button"; owner D1, D8): one 44 px row.

  - Left, fixed: the equipment button (D10: Connect all / Disconnect all,
    asking first while something runs, Q-C5), then the task modes (D1).
  - Middle: the data-driven Toolbar (components/Toolbar): Open FITS (Mod+O),
    Take shot (E: a split button whose face says the frame type and the
    exposure it will use; its options set them, never run them), Live (V),
    Stop, Autofocus (a split button: the sweep's range and positions; while
    it runs, "Stop AF" with the sweep's ring), then the view and display
    tools. Take shot, Live and Stop never leave the row; when the window is
    narrow the view tools go first into the counted overflow menu.
  - Right, fixed: [arrange] (Arrange: this mode's cards, band, drawer, rail,
    Reset) and [panels] (P).
  Routine tools are icon-only with a tooltip (label + key); actions that
  move hardware or stop a run carry their label (BRAND 7). The theme switch
  is in the rail footer (D15). The registry binds the keys (ImagingScreen);
  the `shortcut` fields read the same keymap.
-->
<script lang="ts">
  import type { FrameType } from '../api/types';
  import { useApp } from '../app/state.svelte';
  import ConfirmDialog from '../components/ConfirmDialog.svelte';
  import IconButton from '../components/IconButton.svelte';
  import type { MenuChoice, MenuEntry } from '../components/menu';
  import Toolbar from '../components/Toolbar.svelte';
  import type { ToolDef } from '../components/toolbar';
  import { disconnectRisk } from '../connection/model';
  import { int, percent, seconds } from '../format/number';
  import ArrangePopover from './modes/ArrangePopover.svelte';
  import { modeDef } from './modes/layout';
  import ModeBar from './modes/ModeBar.svelte';

  interface Props {
    hasFrame: boolean;
    onzoom: (action: 'in' | 'out' | 'fit' | 'fill' | '1to1') => void;
  }

  let { hasFrame, onzoom }: Props = $props();
  const app = useApp();
  const ws = app.observe;
  const key = (id: string) => app.shortcuts.keyFor(id);

  const TYPE_WORD: Record<string, string> = { light: 'Light', dark: 'Dark', flat: 'Flat', bias: 'Bias' };
  const EXPOSURES = [0.5, 1, 2, 5, 10, 30, 60, 120];

  // -- Reasons -------------------------------------------------------------------------------
  const exposureReason = $derived.by(() => {
    if (app.stale) return 'the ARGOS server is not reachable';
    if (!app.cameraReady) return app.connected ? 'connect the camera first' : 'connect the equipment first';
    return app.exposureProblem();
  });
  const owner = $derived(app.cameraOwner);
  const ownerReason = $derived(
    owner === 'autofocus' ? 'autofocus owns the camera until it ends' : owner === 'sequence' ? 'the sequence owns the camera' : null,
  );
  const settings = $derived(app.settings);
  const frameType = $derived<FrameType>(settings?.frame_type ?? 'light');
  const exposure = $derived(settings?.exposure_s ?? app.exposure);
  const shotPending = $derived(!!app.camera?.save_pending || app.camera?.waiting_for === 'filterwheel');
  const shotReason = $derived.by(() => {
    if (exposureReason) return exposureReason;
    if (ownerReason) return ownerReason;
    if (owner === 'single' || shotPending) return null; // busy, shown by the spinner / ring
    return app.darkGuard();
  });
  const liveReason = $derived(app.live ? (app.stale ? 'the ARGOS server is not reachable' : null) : (exposureReason ?? ownerReason ?? (owner === 'single' ? 'wait for the exposure in progress' : null)));
  const viewReason = $derived(hasFrame ? null : 'no frame yet');
  const stopRunning = $derived(app.cameraBusy || app.slewing);
  // While autofocus owns the camera, plain Stop would end the sweep without returning the
  // focuser: it is unavailable, and says which control does what (design review W3).
  const stopReason = $derived.by(() => {
    if (app.stale) return 'the ARGOS server is not reachable';
    if (owner === 'autofocus' && !app.slewing) return 'autofocus owns the camera: Stop AF returns the focuser to its start, the focuser’s Halt stops it where it is';
    return stopRunning ? null : 'nothing is running';
  });
  /** The widest face the Take shot split can show: reserved, so the toolbar never reflows. */
  const shotTextMin = $derived.by(() => {
    let widest = '';
    for (const t of Object.values(TYPE_WORD)) {
      for (const e of [...EXPOSURES, exposure]) {
        const s = `${t} · ${seconds(e)}`;
        if (s.length > widest.length) widest = s;
      }
    }
    return widest;
  });

  // -- Progress of the frame in progress (the time ring) ---------------------------------------
  let now = $state(Date.now());
  $effect(() => {
    if (!app.camera?.current || app.stale) return;
    const id = setInterval(() => (now = Date.now()), 100);
    return () => clearInterval(id);
  });
  const frameProgress = $derived.by(() => {
    const c = app.camera?.current;
    if (!c || app.stale || !(c.exposure_s > 0)) return null;
    const t0 = Date.parse(c.started_utc);
    if (!Number.isFinite(t0)) return null;
    return Math.min(1, Math.max(0, (now - t0) / 1000 / c.exposure_s));
  });
  const shotProgress = $derived(owner === 'single' || (app.live && app.camera?.current?.save) ? frameProgress : null);
  const shotText = $derived.by(() => {
    if (app.camera?.waiting_for === 'filterwheel') return 'Waiting for the wheel to settle on Dark';
    const c = app.camera?.current;
    if (shotProgress !== null && c) return `${app.live ? 'Saving the next frame · ' : ''}${seconds((shotProgress ?? 0) * c.exposure_s)} / ${seconds(c.exposure_s)}`;
    if (app.camera?.save_pending) return 'Saving the next live frame';
    return undefined;
  });

  // -- Autofocus -------------------------------------------------------------------------------
  const af = $derived(app.autofocus);
  const afRunning = $derived(app.autofocusRunning);
  const afProgress = $derived(af?.state === 'running' && (af.total ?? 0) > 0 ? Math.min(1, (af.step ?? 0) / (af.total ?? 1)) : null);
  const afReason = $derived(afRunning ? (app.stale ? 'the ARGOS server is not reachable' : af?.state === 'stopping' ? 'returning to the start position' : null) : app.autofocusProblem());

  // -- Menus -----------------------------------------------------------------------------------
  const shotItems = $derived<MenuEntry[]>([
    { kind: 'header', label: 'Exposure' },
    ...EXPOSURES.map((s) => ({
      kind: 'radio' as const,
      id: `exp-${s}`,
      label: seconds(s),
      checked: Math.abs(exposure - s) < 1e-9,
      disabledReason:
        ownerReason ?? (app.cameraReady && app.camera?.limits && (s < app.camera.limits.exposure_min_s || s > app.camera.limits.exposure_max_s) ? 'outside the driver limits' : null),
    })),
    { kind: 'separator' },
    { kind: 'header', label: 'Frame type' },
    ...(['light', 'dark', 'flat', 'bias'] as FrameType[]).map((f) => ({
      kind: 'radio' as const,
      id: `type-${f}`,
      label: TYPE_WORD[f],
      checked: frameType === f,
      detail: f === 'dark' || f === 'bias' ? 'The wheel turns to Dark first (no shutter)' : undefined,
      disabledReason: ownerReason,
    })),
    { kind: 'separator' },
    {
      id: 'shot-info',
      label: app.live ? 'During live view: saves the next frame' : 'Saves one FITS in the session folder',
      icon: 'save',
      disabledReason: 'the main button does it',
    },
  ]);

  const afItems = $derived<MenuEntry[]>([
    { kind: 'header', label: 'Sweep range' },
    ...[
      { v: 1000, l: '±1 000 steps' },
      { v: null, l: '±2 000 steps (default)' },
      { v: 4000, l: '±4 000 steps' },
    ].map((o) => ({ kind: 'radio' as const, id: `af-range-${o.v ?? 'default'}`, label: o.l, checked: app.afOptions.half_range === o.v })),
    { kind: 'separator' },
    { kind: 'header', label: 'Positions' },
    ...[
      { v: 7, l: '7 positions' },
      { v: null, l: '9 positions (default)' },
      { v: 13, l: '13 positions' },
    ].map((o) => ({ kind: 'radio' as const, id: `af-steps-${o.v ?? 'default'}`, label: o.l, checked: app.afOptions.num_steps === o.v })),
    { kind: 'separator' },
    {
      id: 'af-frames',
      label: settings ? `AF frames: ${seconds(Math.min(10, settings.exposure_s))}, gain ${int(settings.gain)}` : 'AF frames: the Camera card settings',
      detail: 'Exposure (at most 10 s) and gain of the Camera card',
      disabledReason: 'set them in the Camera card',
    },
  ]);

  function option(toolId: string, item: MenuChoice): void {
    const id = item.id;
    if (toolId === 'shot') {
      if (id.startsWith('exp-')) void app.setExposure(Number(id.slice(4))).catch((e) => app.reportError('Exposure', e));
      else if (id.startsWith('type-')) void app.setFrameType(id.slice(5) as FrameType);
    } else if (toolId === 'autofocus') {
      if (id.startsWith('af-range-')) {
        const v = id.slice(9);
        app.setAfOptions({ half_range: v === 'default' ? null : Number(v) });
      } else if (id.startsWith('af-steps-')) {
        const v = id.slice(9);
        app.setAfOptions({ num_steps: v === 'default' ? null : Number(v) });
      }
    }
  }

  function act(id: string): void {
    switch (id) {
      case 'open':
        app.openFitsOpen = true;
        break;
      case 'shot':
        void app.takeShot();
        break;
      case 'live':
        void app.toggleLive();
        break;
      case 'stop':
        app.stopAll();
        break;
      case 'autofocus':
        void app.runAutofocus();
        break;
      case 'zoom-out':
        onzoom('out');
        break;
      case 'zoom':
      case 'zoom-fit':
        onzoom('fit');
        break;
      case 'zoom-in':
        onzoom('in');
        break;
      case 'zoom-fill':
        onzoom('fill');
        break;
      case 'zoom-1to1':
        onzoom('1to1');
        break;
      case 'stretch-auto':
        app.setAutoStretch(!app.autoStretch);
        break;
      case 'stretch-reset':
        app.resetStretch();
        break;
      case 'band':
        ws.toggleBand();
        break;
      case 'crosshair':
        app.crosshair = !app.crosshair;
        break;
    }
  }

  const tools = $derived<ToolDef[]>([
    {
      id: 'open',
      group: 'file',
      kind: 'button',
      icon: 'open-image',
      label: 'Open FITS image…',
      shortcut: key('file.open-fits'),
      priority: 3,
      disabledReason: app.stale ? 'the ARGOS server is not reachable' : null,
    },
    {
      id: 'shot',
      group: 'cam',
      kind: 'split',
      icon: 'capture',
      label: 'Take shot',
      text: `${TYPE_WORD[frameType]} · ${seconds(exposure)}`,
      textMin: shotTextMin,
      shortcut: key('observe.capture'),
      items: shotItems,
      priority: Infinity,
      busy: !!app.busy.capture || (shotPending && shotProgress === null),
      progress: shotProgress,
      progressText: shotText,
      disabledReason: app.busy.capture || shotPending || owner === 'single' ? null : shotReason,
      optionsReason: app.stale ? 'the ARGOS server is not reachable' : ownerReason,
    },
    {
      id: 'live',
      group: 'cam',
      kind: 'toggle',
      icon: 'live',
      label: app.live ? 'Stop live view' : 'Start live view',
      shortcut: key('observe.live'),
      pressed: app.live,
      busy: !!app.busy.live,
      progress: app.live && !app.camera?.current?.save ? frameProgress : null,
      progressText: app.live && frameProgress !== null && app.camera?.current ? `frame ${seconds(frameProgress * app.camera.current.exposure_s)} / ${seconds(app.camera.current.exposure_s)}` : undefined,
      disabledReason: liveReason,
      priority: Infinity,
    },
    {
      id: 'stop',
      group: 'cam',
      kind: 'button',
      icon: 'stop',
      label: 'Stop',
      showLabel: true,
      variant: app.slewing ? 'danger' : 'secondary',
      glyphTone: stopRunning && !stopReason ? 'danger' : undefined,
      busy: !!app.busy.cameraStop,
      disabledReason: stopReason,
      priority: Infinity,
    },
    {
      id: 'autofocus',
      group: 'af',
      kind: 'split',
      icon: afRunning ? 'stop' : 'autofocus',
      label: afRunning ? 'Stop autofocus (return to the start)' : 'Autofocus',
      buttonText: afRunning ? 'Stop AF' : 'Autofocus',
      showLabel: true,
      // The count lives in the Focus band and the status-bar chip; the ring shows progress here.
      variant: 'secondary',
      items: afItems,
      busy: !!app.busy.autofocus || af?.state === 'stopping',
      stoppable: afRunning,
      progress: afProgress,
      progressText: afRunning ? `${af?.stage ?? ''} · sample ${af?.step ?? 0} of ${af?.total ?? '?'}` : undefined,
      disabledReason: afReason,
      optionsReason: afRunning ? 'the sweep is running' : null,
      priority: 9,
    },
    { id: 'zoom-out', group: 'zoom', kind: 'button', icon: 'zoom-out', label: 'Zoom out', shortcut: key('view.zoom-out'), priority: 6, disabledReason: viewReason },
    { id: 'zoom', group: 'zoom', kind: 'readout', icon: 'zoom-fit', label: 'Zoom: click to fit', text: hasFrame ? percent(app.zoom) : '—', priority: 6, width: 52 },
    { id: 'zoom-in', group: 'zoom', kind: 'button', icon: 'zoom-in', label: 'Zoom in', shortcut: key('view.zoom-in'), priority: 6, disabledReason: viewReason },
    { id: 'zoom-fit', group: 'zoom', kind: 'button', icon: 'zoom-fit', label: 'Fit: whole frame', shortcut: key('view.fit'), priority: 7, disabledReason: viewReason },
    { id: 'zoom-fill', group: 'zoom', kind: 'button', icon: 'zoom-fill', label: 'Fill the viewer (crops the long sides)', shortcut: key('view.fill'), priority: 4, disabledReason: viewReason },
    { id: 'zoom-1to1', group: 'zoom', kind: 'button', icon: 'zoom-1to1', label: 'Actual pixels (1:1)', shortcut: key('view.one-to-one'), priority: 5, disabledReason: viewReason },
    { id: 'stretch-auto', group: 'display', kind: 'toggle', icon: 'stretch-auto', label: 'Auto stretch', shortcut: key('view.stretch-auto'), pressed: app.autoStretch, priority: 6 },
    { id: 'stretch-reset', group: 'display', kind: 'button', icon: 'stretch-reset', label: 'Reset stretch (linear, full range)', shortcut: key('view.stretch-reset'), priority: 3, disabledReason: viewReason },
    {
      id: 'band',
      group: 'display',
      kind: 'toggle',
      icon: 'histogram',
      label: `Band under the image: ${modeDef(ws.mode).band.toLowerCase()}`,
      shortcut: key('view.levels'),
      pressed: ws.layout.bandOpen,
      layoutToggle: true,
      priority: 5,
    },
    { id: 'crosshair', group: 'display', kind: 'toggle', icon: 'crosshair', label: 'Crosshair on image', shortcut: key('view.crosshair'), pressed: app.crosshair, priority: 2 },
  ]);

  // -- Equipment (D10) -------------------------------------------------------------------------
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
    if (risk || app.autofocusRunning) confirmOpen = true;
    else void app.disconnectAll();
  }
</script>

<div class="bar" aria-label="Observe toolbar" role="group">
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

  <ModeBar {ws} keyFor={key} />

  <span class="sep" aria-hidden="true"></span>

  <Toolbar embedded label="Imaging tools" {tools} onact={act} onoption={option} />

  <div class="end">
    <ArrangePopover {ws} />
    <IconButton
      icon="panels"
      label="Instrument panels"
      shortcut={key('rail.toggle')}
      variant="ghost"
      pressed={ws.layout.railOpen}
      layoutToggle
      tooltip="left"
      onclick={() => ws.toggleRail()}
    />
  </div>
</div>

<ConfirmDialog
  bind:open={confirmOpen}
  title="Disconnect the equipment?"
  message={`${risk ?? 'Autofocus is running: the focuser stops where it is.'} Disconnecting releases the mount, the camera, the filter wheel and the focuser.`}
  confirmLabel="Disconnect all"
  destructive
  onconfirm={() => app.disconnectAll()}
/>

<style>
  .bar {
    container: toolbar / inline-size;
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: var(--toolbar-h); /* one 44 px row, border included (owner D8) */
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg);
    min-width: 0;
  }
  .bar > :global(.toolbar) {
    min-width: 0;
  }
  .end {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--space-1);
  }
  .sep {
    flex: none;
    width: 1px;
    height: 20px;
    background: var(--border-soft);
  }
</style>
