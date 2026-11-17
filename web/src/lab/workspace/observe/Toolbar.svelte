<!--
  Observe toolbar, one 44 px row:
  [equipment] [mode bar] | capture · live · stop | zoom | auto stretch |
  [mode tool group] ...... [command field ⌘K] watch · arrange · panels

  The common part never moves; only the mode group changes with the mode
  (functional-spaces 4.1). During a run the camera belongs to the sequence:
  capture and live stay in place, disabled with the reason. The command
  field is the palette's visible entry point (Mod+K), not a search box.
-->
<script lang="ts">
  import { formatShortcut } from '../../../lib/app/shortcuts';
  import Icon from '../../../lib/components/Icon.svelte';
  import IconButton from '../../../lib/components/IconButton.svelte';
  import { tooltip } from '../../../lib/components/tooltip';
  import { sim, ws } from '../model/app.svelte';
  import ToolButton from '../ui/ToolButton.svelte';
  import ArrangePopover from './ArrangePopover.svelte';
  import ModeBar from './ModeBar.svelte';

  const cameraBusy = $derived(sim.inRun && sim.running ? 'the sequence owns the camera' : null);
  const zoomText = $derived(`${Math.round(ws.zoom * 100)}%`);

  function solve(): void {
    ws.toast('Identifying the field (ASTAP)…', 'info');
    setTimeout(() => {
      sim.solved = true;
      sim.addLog('OK', 'field', 'Field identified · 2.39″/px · rotation 91.2°');
      if (ws.mode !== 'field') ws.suggestion = { text: 'Field identified', mode: 'field' };
    }, 1200);
  }
</script>

<div class="toolbar" role="toolbar" aria-label="Observe tools">
  <div class="row">
    <button type="button" class="equip" use:tooltip={{ text: 'Equipment: Seestar S50 · 4 devices ready (Connection F1)' }}>
      <Icon name="connect" size={16} />
      <span>Seestar</span>
      <span class="ok" aria-hidden="true"></span>
    </button>

    <ModeBar />

    <span class="sep" aria-hidden="true"></span>
    <IconButton icon="capture" label="Take one exposure" shortcut="E" variant="ghost" disabledReason={cameraBusy} onclick={() => ws.toast('Shot: 2.0 s, gain 80', 'info')} />
    <IconButton icon="live" label="Live view" shortcut="V" variant="ghost" pressed={sim.live} disabledReason={cameraBusy} onclick={() => sim.setLive(!sim.live)} />
    {#if sim.live}
      <IconButton icon="stop" label="Stop" showLabel variant="secondary" glyphTone="danger" size="s" onclick={() => sim.setLive(false)} />
    {/if}

    <span class="sep" aria-hidden="true"></span>
    <IconButton icon="zoom-fit" label="Fit the whole frame" shortcut="F" variant="ghost" onclick={() => { ws.fitMode = 'fit'; ws.viewer?.fit(); }} />
    <IconButton icon="zoom-fill" label="Fill the viewer (crops)" shortcut="Shift+F" variant="ghost" pressed={ws.fitMode === 'fill'} layoutToggle onclick={() => (ws.fitMode = ws.fitMode === 'fill' ? 'fit' : 'fill')} />
    <IconButton icon="zoom-1to1" label="Actual pixels (1:1)" shortcut="1" variant="ghost" onclick={() => ws.viewer?.oneToOne()} />
    <span class="zoom num" aria-label="Zoom {zoomText}">{zoomText}</span>
    <IconButton icon="stretch-auto" label="Auto stretch" shortcut="A" variant="ghost" pressed={ws.autoStretch} onclick={() => (ws.autoStretch = !ws.autoStretch)} />

    <span class="sep" aria-hidden="true"></span>
    <div class="group" aria-label="{ws.mode} tools">
      {#if ws.mode === 'framing'}
        <IconButton icon="crosshair" label="Crosshair" shortcut="X" variant="ghost" pressed={ws.crosshair} onclick={() => (ws.crosshair = !ws.crosshair)} />
        <IconButton icon="saturation" label="Clipped pixels" shortcut="C" variant="ghost" onclick={() => ws.toast('Clipped-pixel highlight: planned (04)', 'info')} />
        <IconButton icon="region-stats" label="Region statistics" shortcut="R" variant="ghost" pressed={ws.tool === 'region'} onclick={() => (ws.tool = ws.tool === 'region' ? 'none' : 'region')} />
      {:else if ws.mode === 'focus'}
        <IconButton icon="loupe" label="Loupe" shortcut="Z" variant="ghost" onclick={() => ws.toast('Loupe: planned (04)', 'info')} />
        <IconButton icon="crosshair" label="Crosshair" shortcut="X" variant="ghost" pressed={ws.crosshair} onclick={() => (ws.crosshair = !ws.crosshair)} />
        <IconButton icon="region-stats" label="Region statistics" shortcut="R" variant="ghost" pressed={ws.tool === 'region'} onclick={() => (ws.tool = ws.tool === 'region' ? 'none' : 'region')} />
      {:else if ws.mode === 'field'}
        <IconButton icon="plate-solve" label="Identify field" shortcut="S" variant="ghost" onclick={solve} />
        <IconButton icon="sky-grid" label="Coordinate grid" shortcut="G" variant="ghost" pressed={ws.grid} onclick={() => (ws.grid = !ws.grid)} />
        <IconButton icon="labels" label="Object labels" shortcut="N" variant="ghost" pressed={ws.labels} onclick={() => (ws.labels = !ws.labels)} />
        <IconButton icon="catalogue" label="Catalogue layers" shortcut="O" variant="ghost" onclick={() => ws.toast('Catalogue layers popover: see the research lab', 'info')} />
      {:else}
        <IconButton icon="sky-grid" label="Coordinate grid" shortcut="G" variant="ghost" pressed={ws.grid} onclick={() => (ws.grid = !ws.grid)} />
        <IconButton icon="labels" label="Object labels" shortcut="N" variant="ghost" pressed={ws.labels} onclick={() => (ws.labels = !ws.labels)} />
        <IconButton icon="error-bars" label="Error bars" shortcut="U" variant="ghost" pressed={ws.errorBars} onclick={() => (ws.errorBars = !ws.errorBars)} />
      {/if}
    </div>

    <span class="spacer"></span>

    <button type="button" class="command" onclick={() => (ws.overlay = 'palette')} aria-keyshortcuts="Meta+K Control+K">
      <Icon name="search" size={16} />
      <span class="ph">Find an action, a star, a setting</span>
      <kbd class="key">{formatShortcut('Mod+K').replace(/\s/g, '')}</kbd>
    </button>
    <ToolButton
      icon="lab-watch"
      label="Watch: the run from a distance"
      shortcut="W"
      onclick={() => {
        sim.armSound();
        ws.overlay = 'watch';
      }}
    />
    <div class="anchor">
      <IconButton
        icon="arrange"
        label="Panels and layout of {ws.mode}"
        variant="ghost"
        pressed={ws.arrangeOpen}
        layoutToggle
        onclick={() => (ws.arrangeOpen = !ws.arrangeOpen)}
      />
      {#if ws.modified}<span class="mod" aria-hidden="true"></span>{/if}
      {#if ws.arrangeOpen}<ArrangePopover />{/if}
    </div>
    <IconButton icon="panels" label="Right panel" shortcut="P" variant="ghost" pressed={ws.layout.railOpen} layoutToggle onclick={() => ws.toggleRail()} />
  </div>
</div>

<style>
  .toolbar {
    container: toolbar / inline-size;
    flex: none;
    height: var(--lab-toolbar-h);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg);
  }
  .row {
    display: flex;
    align-items: center;
    gap: 2px;
    height: 100%;
    padding: 0 var(--space-2);
  }
  .equip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 30px;
    margin-right: var(--space-2);
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    cursor: pointer;
  }
  .equip :global(.icon) {
    color: var(--fg-muted);
  }
  .equip:hover {
    background: var(--hover-bg);
  }
  .ok {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
    background: var(--status-ok);
  }
  .sep {
    width: 1px;
    height: 20px;
    margin: 0 var(--space-2);
    background: var(--border-soft);
  }
  .zoom {
    min-width: 40px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    text-align: center;
  }
  .group {
    display: inline-flex;
    gap: 2px;
  }
  .spacer {
    flex: 1;
  }
  .command {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    width: 248px;
    height: 30px;
    margin-right: var(--space-2);
    padding: 0 var(--space-2) 0 var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg-muted);
    font-size: var(--text-s);
    cursor: pointer;
    transition: border-color var(--duration-fast) var(--ease-standard);
  }
  .command:hover {
    border-color: var(--border);
    color: var(--fg);
  }
  .ph {
    flex: 1;
    color: var(--text-muted);
    text-align: left;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .anchor {
    position: relative;
    display: inline-flex;
  }
  .anchor .mod {
    position: absolute;
    top: 5px;
    right: 5px;
    width: 5px;
    height: 5px;
    border-radius: var(--radius-round);
    background: var(--fg-muted);
    pointer-events: none;
  }

  @container toolbar (max-width: 1240px) {
    .command {
      width: 34px;
      padding: 0;
      justify-content: center;
    }
    .ph,
    .command .key {
      display: none;
    }
    .zoom {
      display: none;
    }
  }
</style>
