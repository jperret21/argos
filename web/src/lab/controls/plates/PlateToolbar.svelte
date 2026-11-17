<!--
  Plate 02: toolbars. The Observe toolbar rebuilt from ToolDefs (one model,
  any width), split buttons, the overflow menu and key hints.
-->
<script lang="ts">
  import { formatShortcut } from '../../../lib/app/shortcuts';
  import type { MenuChoice, MenuEntry } from '../../../lib/components/menu';
  import Ctl from '../components/Ctl.svelte';
  import Panel from '../components/Panel.svelte';
  import SplitButton from '../components/SplitButton.svelte';
  import Toolbar from '../components/Toolbar.svelte';
  import { exposure as fmtExposure } from '../format';
  import { hints } from '../hints.svelte';
  import { clock } from '../sim.svelte';
  import type { Hardware, ToolDef } from '../types';

  let { hw }: { hw: Hardware } = $props();

  // -- State the toolbar reflects -----------------------------------------------------
  let expo = $state(2);
  let frameType = $state('light');
  let live = $state(true);
  let on: Record<string, boolean> = $state({
    'stretch-auto': true,
    histogram: true,
    crosshair: false,
    loupe: false,
    saturation: false,
    'sky-grid': true,
    labels: false,
    panels: true,
    log: false,
  });
  let zoom = $state(48);
  let last = $state('—');

  $effect(() => {
    const exp = hw.exposure;
    exp.seconds = expo;
    if (live) exp.start(true);
    else exp.stop();
    const release = clock.use();
    return () => {
      release();
      exp.stop();
    };
  });
  const frameProgress = $derived(
    live && hw.exposure.startedAt !== null ? Math.min(1, (clock.t - hw.exposure.startedAt) / (hw.exposure.seconds * 1000)) : null,
  );

  const captureItems = $derived<MenuEntry[]>([
    { kind: 'header', label: 'Exposure' },
    ...[0.5, 1, 2, 5, 10, 30].map((s) => ({ kind: 'radio' as const, id: `exp-${s}`, label: `${fmtExposure(s)} s`, checked: expo === s })),
    { kind: 'separator' },
    { kind: 'header', label: 'Frame' },
    ...['light', 'dark', 'flat', 'bias'].map((f) => ({
      kind: 'radio' as const,
      id: `type-${f}`,
      label: f.charAt(0).toUpperCase() + f.slice(1),
      checked: frameType === f,
      detail: f === 'dark' || f === 'bias' ? 'Moves the wheel to Dark first' : undefined,
    })),
    { kind: 'separator' },
    { id: 'save-next', label: 'Save the next live frame', icon: 'save', disabledReason: live ? null : 'Live view is off' },
  ]);

  const afItems: MenuEntry[] = [
    { kind: 'radio', id: 'af-full', label: 'Full sweep', detail: '9 coarse + 4 fine, about 2 min', checked: true },
    { kind: 'radio', id: 'af-fine', label: 'Fine only', detail: 'Around the last best focus', checked: false },
    { kind: 'separator' },
    { id: 'af-settings', label: 'Autofocus settings…', icon: 'settings' },
  ];

  const exportItems: MenuEntry[] = [
    { id: 'aavso', label: 'AAVSO extended format', icon: 'export-aavso' },
    { id: 'csv', label: 'Measurements as CSV', icon: 'export' },
    { id: 'tsv', label: 'Copy as TSV', icon: 'copy', shortcut: 'Mod+C' },
    { kind: 'separator' },
    { id: 'aavso-nocode', label: 'Submit to AAVSO WebObs', disabledReason: 'Set your observer code in Settings first' },
  ];

  const tools = $derived<ToolDef[]>([
    { id: 'equipment', group: 'equip', kind: 'button', icon: 'disconnect', label: 'Disconnect', showLabel: true, variant: 'secondary', priority: 2 },
    {
      id: 'capture',
      group: 'cam',
      kind: 'split',
      icon: 'capture',
      label: 'Take one exposure',
      shortcut: 'E',
      text: `${fmtExposure(expo)} s`,
      items: captureItems,
      priority: Infinity,
    },
    {
      id: 'live',
      group: 'cam',
      kind: 'toggle',
      icon: 'live',
      label: 'Live view',
      shortcut: 'V',
      pressed: live,
      progress: frameProgress,
      progressText: frameProgress === null ? undefined : `frame ${(frameProgress * expo).toFixed(1)} / ${fmtExposure(expo)} s`,
      priority: Infinity,
    },
    {
      id: 'stop',
      group: 'cam',
      kind: 'button',
      icon: 'stop',
      label: 'Stop',
      showLabel: true,
      variant: 'secondary',
      glyphTone: 'danger',
      disabledReason: live ? null : 'Live view is off',
      priority: Infinity,
    },
    { id: 'zoom-out', group: 'zoom', kind: 'button', icon: 'zoom-out', label: 'Zoom out', shortcut: '-', priority: 6 },
    { id: 'zoom', group: 'zoom', kind: 'readout', icon: 'zoom-fit', label: 'Zoom', text: `${zoom} %`, priority: 5 },
    { id: 'zoom-in', group: 'zoom', kind: 'button', icon: 'zoom-in', label: 'Zoom in', shortcut: '+', priority: 6 },
    { id: 'zoom-fit', group: 'zoom', kind: 'button', icon: 'zoom-fit', label: 'Fit the whole frame', shortcut: 'F', priority: 7 },
    { id: 'zoom-fill', group: 'zoom', kind: 'button', icon: 'zoom-fill', label: 'Fill the viewer (crops)', shortcut: 'Shift+F', priority: 3 },
    { id: 'zoom-1to1', group: 'zoom', kind: 'button', icon: 'zoom-1to1', label: 'Actual pixels (1:1)', shortcut: '1', priority: 3 },
    { id: 'stretch-auto', group: 'stretch', kind: 'toggle', icon: 'stretch-auto', label: 'Auto stretch', shortcut: 'A', pressed: on['stretch-auto'], priority: 6 },
    { id: 'stretch-reset', group: 'stretch', kind: 'button', icon: 'stretch-reset', label: 'Reset stretch (linear)', shortcut: 'Shift+A', priority: 4 },
    { id: 'histogram', group: 'stretch', kind: 'toggle', icon: 'histogram', label: 'Levels strip', shortcut: 'H', pressed: on.histogram, layoutToggle: true, priority: 5 },
    { id: 'plate-solve', group: 'field', kind: 'button', icon: 'plate-solve', label: 'Identify field', shortcut: 'S', priority: 5 },
    { id: 'sky-grid', group: 'field', kind: 'toggle', icon: 'sky-grid', label: 'Coordinate grid', shortcut: 'G', pressed: on['sky-grid'], priority: 3 },
    { id: 'labels', group: 'field', kind: 'toggle', icon: 'labels', label: 'Object labels', shortcut: 'N', pressed: on.labels, priority: 2 },
    { id: 'catalogue', group: 'field', kind: 'button', icon: 'catalogue', label: 'Catalogue layers', shortcut: 'O', priority: 3 },
    { id: 'crosshair', group: 'tools', kind: 'toggle', icon: 'crosshair', label: 'Crosshair', shortcut: 'X', pressed: on.crosshair, priority: 4 },
    { id: 'loupe', group: 'tools', kind: 'toggle', icon: 'loupe', label: 'Loupe', shortcut: 'Z', pressed: on.loupe, priority: 2 },
    { id: 'saturation', group: 'tools', kind: 'toggle', icon: 'saturation', label: 'Saturation highlight', shortcut: 'C', pressed: on.saturation, priority: 2 },
    { id: 'region-stats', group: 'tools', kind: 'button', icon: 'region-stats', label: 'Region statistics', shortcut: 'R', priority: 1 },
    { id: 'log', group: 'layout', kind: 'toggle', icon: 'log', label: 'Activity log', shortcut: 'L', pressed: on.log, layoutToggle: true, priority: 4, end: true },
    { id: 'panels', group: 'layout', kind: 'toggle', icon: 'panels', label: 'Instrument rail', shortcut: 'P', pressed: on.panels, layoutToggle: true, priority: Infinity, end: true },
  ]);

  function act(id: string): void {
    last = tools.find((t) => t.id === id)?.label ?? id;
    if (id === 'live') live = !live;
    else if (id === 'stop') live = false;
    else if (id === 'zoom-in') zoom = Math.min(800, Math.round(zoom * 1.25));
    else if (id === 'zoom-out') zoom = Math.max(6, Math.round(zoom / 1.25));
    else if (id === 'zoom-1to1') zoom = 100;
    else if (id === 'zoom-fit') zoom = 48;
    else if (id in on) on[id] = !on[id];
  }

  function option(_tool: string, item: MenuChoice): void {
    if (item.id.startsWith('exp-')) expo = Number(item.id.slice(4));
    else if (item.id.startsWith('type-')) frameType = item.id.slice(5);
    last = item.label;
  }

  // -- Resizable frame for the overflow demo --------------------------------------------
  let width = $state(760);
  const PRESETS = [1100, 920, 760, 560];
  let dragging = false;
  let startX = 0;
  let startW = 0;
  let frame: HTMLDivElement | undefined = $state();

  function gripDown(e: PointerEvent): void {
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragging = true;
    startX = e.clientX;
    startW = width;
  }
  function gripMove(e: PointerEvent): void {
    if (!dragging) return;
    const max = frame?.parentElement?.clientWidth ?? 1300;
    width = Math.round(Math.min(max - 16, Math.max(360, startW + e.clientX - startX)));
  }
  function gripKey(e: KeyboardEvent): void {
    const d = e.shiftKey ? 80 : 16;
    if (e.key === 'ArrowLeft') width = Math.max(360, width - d);
    else if (e.key === 'ArrowRight') width = Math.min(1300, width + d);
    else return;
    e.preventDefault();
  }

  const mod = formatShortcut('Mod+K').replace('K', '');
</script>

<div class="plate">
  <Panel
    code="B.1"
    title="Observe toolbar"
    note="One row of 46 px built from data (id, group, priority, shortcut). Capture, Live and Stop never move; the readout shows the zoom and opens nothing hidden. Capture is a split button that says the exposure it will take."
    shot="full"
  >
    {#snippet aside()}<span class="num">last: {last}</span>{/snippet}
    <div class="host">
      <Toolbar label="Observe tools" {tools} onact={act} onoption={option} />
    </div>
  </Panel>

  <Panel
    code="B.2"
    title="Priority overflow"
    note="Lowest priorities leave first, from the end of their group, into a menu whose trigger shows how many it holds. Toggles keep their state and every tool its key. Drag the grip or pick a width."
    shot="narrow"
  >
    {#snippet aside()}
      <span class="presets">
        {#each PRESETS as p (p)}
          <button type="button" class="preset num" class:on={width === p} onclick={() => (width = p)}>{p}</button>
        {/each}
        <span class="num w">{width} px</span>
      </span>
    {/snippet}
    <div class="resizable" bind:this={frame}>
      <div class="frame" style:width="{width}px">
        <Toolbar label="Observe tools, narrow" {tools} onact={act} onoption={option} />
      </div>
      <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions (a focusable window splitter, WAI-ARIA) -->
      <div
        class="grip"
        role="separator"
        aria-orientation="vertical"
        aria-label="Toolbar width"
        aria-valuenow={width}
        aria-valuemin={360}
        aria-valuemax={1300}
        tabindex="0"
        onpointerdown={gripDown}
        onpointermove={gripMove}
        onpointerup={() => (dragging = false)}
        onkeydown={gripKey}
      ></div>
    </div>
  </Panel>

  <Panel
    code="B.3"
    title="Compact density · S"
    note="The same model at 30 px controls in a 40 px row, for 1280 x 800 or a second toolbar (Review). Icons stay at 16 px, the pixel-exact size."
    shot="compact"
  >
    <div class="compact">
      <Toolbar label="Observe tools, compact" {tools} size="s" onact={act} onoption={option} />
    </div>
  </Panel>

  <div class="row">
    <Panel code="B.4" title="Split buttons" note="The main part acts with the options shown on it; the chevron (or ↓ on the main part) opens them. Choosing an option never runs the action." shot="splits">
      <div class="splits">
        <div class="sp">
          <span class="lab-eyebrow">Toolbar · ghost</span>
          <SplitButton icon="capture" label="Take one exposure" detail="{fmtExposure(expo)} s" shortcut="E" items={captureItems} menuLabel="Capture options" onselect={(i) => option('capture', i)} onaction={() => (last = 'Take one exposure')} />
        </div>
        <div class="sp">
          <span class="lab-eyebrow">Hover · main</span>
          <SplitButton icon="capture" label="Take one exposure" detail="{fmtExposure(expo)} s" items={captureItems} menuLabel="Capture options" force="main" />
        </div>
        <div class="sp">
          <span class="lab-eyebrow">Hover · options</span>
          <SplitButton icon="capture" label="Take one exposure" detail="{fmtExposure(expo)} s" items={captureItems} menuLabel="Capture options" force="menu" />
        </div>
        <div class="sp">
          <span class="lab-eyebrow">Card · secondary</span>
          <SplitButton icon="autofocus" label="Autofocus" text="Autofocus" variant="secondary" items={afItems} menuLabel="Autofocus options" onaction={() => (last = 'Autofocus')} />
        </div>
        <div class="sp">
          <span class="lab-eyebrow">Primary</span>
          <SplitButton icon="export-aavso" label="Export AAVSO" text="Export" variant="primary" items={exportItems} menuLabel="Export formats" onaction={() => (last = 'Export')} />
        </div>
        <div class="sp">
          <span class="lab-eyebrow">Unavailable</span>
          <SplitButton icon="export-aavso" label="Export AAVSO" text="Export" variant="secondary" items={exportItems} menuLabel="Export formats" disabledReason="Open a session with photometry first" />
        </div>
      </div>
    </Panel>

    <Panel
      code="B.5"
      title="Key hints"
      note="Hold {mod} alone for half a second: every control shows its key where it acts, and hides on release. A chord (⌘K) never flashes them. Teaches the keyboard without opening the sheet."
      shot="hints"
    >
      <div class="hintdemo">
        <div class="mini">
          <Ctl icon="capture" label="Take one exposure" variant="ghost" shortcut="E" />
          <Ctl icon="live" label="Live view" variant="ghost" shortcut="V" pressed />
          <span class="sep"></span>
          <Ctl icon="zoom-out" label="Zoom out" variant="ghost" shortcut="-" />
          <Ctl icon="zoom-fit" label="Fit" variant="ghost" shortcut="F" />
          <Ctl icon="zoom-in" label="Zoom in" variant="ghost" shortcut="+" />
          <span class="sep"></span>
          <Ctl icon="stretch-auto" label="Auto stretch" variant="ghost" shortcut="A" pressed />
          <Ctl icon="crosshair" label="Crosshair" variant="ghost" shortcut="X" />
          <Ctl icon="park" label="Park" showLabel disabledReason={null} />
        </div>
        <p class="lab-note">
          Park has no key on purpose (BRAND 7: hardware is never one key), so it shows none.
          <button type="button" class="link" onclick={() => (hints.pinned = !hints.pinned)}>{hints.pinned ? 'Hide' : 'Pin'} the hints</button>
        </p>
      </div>
    </Panel>
  </div>
</div>

<style>
  .plate {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .host {
    margin: 0 calc(-1 * var(--space-4));
    border-top: var(--border-w) solid var(--border-soft);
  }
  .host :global(.toolbar) {
    border-bottom: none;
  }
  .compact {
    width: min(100%, 1100px);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    overflow: hidden;
  }
  .compact :global(.toolbar) {
    border-bottom: none;
  }
  .resizable {
    display: flex;
    align-items: stretch;
    min-width: 0;
    padding: var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .frame {
    min-width: 0;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s) 0 0 var(--radius-s);
    overflow: hidden;
  }
  .frame :global(.toolbar) {
    border-bottom: none;
  }
  .grip {
    position: relative;
    width: 12px;
    border: var(--border-w) solid var(--border);
    border-left: none;
    border-radius: 0 var(--radius-s) var(--radius-s) 0;
    background: var(--surface);
    cursor: ew-resize;
    touch-action: none;
  }
  .grip::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 4px;
    width: 1px;
    height: 14px;
    margin-top: -7px;
    background: var(--fg-muted);
    box-shadow: 2px 0 0 var(--fg-muted);
  }
  .grip:hover {
    background: var(--hover-bg);
  }
  .grip:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
  .presets {
    display: inline-flex;
    align-items: center;
    gap: 2px;
  }
  .preset {
    height: 20px;
    padding: 0 6px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-2xs);
    cursor: pointer;
  }
  .preset:hover {
    color: var(--fg);
  }
  .preset.on {
    border-color: var(--border);
    background: var(--toggled-bg);
    color: var(--fg);
  }
  .preset:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .w {
    margin-left: var(--space-2);
    color: var(--fg);
    font-size: var(--text-2xs);
  }

  .row {
    display: grid;
    grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
    gap: var(--space-4);
  }
  .splits {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-4) var(--space-3);
  }
  .sp {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
  }

  .hintdemo {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .mini {
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 6px var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg);
  }
  .sep {
    width: 1px;
    height: 18px;
    margin: 0 6px;
    background: var(--border-soft);
  }
  .link {
    padding: 0;
    border: none;
    background: none;
    color: var(--fg);
    font-size: inherit;
    text-decoration: underline;
    text-decoration-color: var(--border);
    text-underline-offset: 3px;
    cursor: pointer;
  }
  .link:hover {
    text-decoration-color: var(--fg);
  }
</style>
