<!--
  Root of the workspace lab: the shell (rail, section, status bar), the
  global keys and the overlays (palette, Watch, overview, attention, lab
  panel, toasts).

  URL parameters (for review links and the capture script):
    ?scene=framing|focus|field|run|run-healthy|run-complete   instrument state
    ?mode=framing|focus|field|run   Observe mode (default: the scene's)
    ?frame=N  run frame shown;  ?speed=S  simulated s per real s (0 freezes)
    ?view=watch|overview|palette;  ?section=connection|plan|review|settings
    ?select=ID  star in the Inspector;  ?drawer=log|curve|conditions|ensemble
    ?attention=open;  ?arrange=open;  ?dim=60|30;  ?q=text (palette query)
    ?frames=server&api=http://127.0.0.1:8784&token=dev  real simulator frames
  Keys: Mod+K palette, W Watch, Alt+1-4 modes, P rail, H band, D drawer,
  L log, F / Shift+F fit / fill, A auto stretch, X crosshair, G grid,
  N labels, R region, U error bars, Esc closes the top layer, ` lab panel.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { isTypingTarget } from '../../lib/app/shortcuts';
  import { MODES, type DrawerTab, type Mode } from './model/layout';
  import { sim, ws } from './model/app.svelte';
  import type { Scene } from './model/sim.svelte';
  import type { Section } from './model/workspace.svelte';
  import LabRail from './shell/LabRail.svelte';
  import StatusBar from './shell/StatusBar.svelte';
  import ObserveScreen from './observe/ObserveScreen.svelte';
  import SectionSketch from './overview/SectionSketch.svelte';
  import CommandPalette from './overlays/CommandPalette.svelte';
  import WatchView from './overlays/WatchView.svelte';
  import SectionsOverview from './overview/SectionsOverview.svelte';
  import LabPanel from './overlays/LabPanel.svelte';
  import Toasts from './overlays/Toasts.svelte';

  const SCENES: Scene[] = ['framing', 'focus', 'field', 'run', 'run-healthy', 'run-complete'];
  const SCENE_MODE: Record<Scene, Mode> = {
    framing: 'framing',
    focus: 'focus',
    field: 'field',
    run: 'run',
    'run-healthy': 'run',
    'run-complete': 'run',
  };

  const q = new URLSearchParams(location.search);
  const scene = (SCENES as string[]).includes(q.get('scene') ?? '') ? (q.get('scene') as Scene) : 'run';
  const modeParam = q.get('mode');
  ws.mode = MODES.some((m) => m.id === modeParam) ? (modeParam as Mode) : SCENE_MODE[scene];
  const section = q.get('section');
  if (section && ['connection', 'observe', 'plan', 'review', 'settings'].includes(section)) ws.section = section as Section;
  const view = q.get('view');
  if (view === 'watch' || view === 'overview' || view === 'palette') ws.overlay = view;
  if (q.get('attention') === 'open') ws.attentionOpen = true;
  if (q.get('arrange') === 'open') ws.arrangeOpen = true;
  const dim = Number(q.get('dim'));
  if (dim === 60 || dim === 30) ws.watchDim = dim;
  const sel = Number(q.get('select'));
  if (sel) ws.select(sel);
  const hov = Number(q.get('hover'));
  if (hov) ws.hovered = hov;
  const drawer = q.get('drawer');
  if (drawer && ['log', 'curve', 'conditions', 'ensemble'].includes(drawer)) {
    ws.layouts[ws.mode].drawerOpen = true;
    ws.layouts[ws.mode].drawerTab = drawer as DrawerTab;
  }
  if (q.get('rail') === 'closed') ws.layouts[ws.mode].railOpen = false;

  onMount(() => {
    const speed = q.has('speed') ? Number(q.get('speed')) : undefined;
    const frame = q.has('frame') ? Number(q.get('frame')) : undefined;
    sim.start(scene, { speed, frame, source: q.get('frames') === 'server' ? 'server' : 'synthetic' });
    // Hooks for the capture script and for review in the console.
    (window as unknown as { __ws: unknown }).__ws = { ws, sim };
    return () => sim.dispose();
  });

  function closeTop(): boolean {
    if (ws.overlay === 'palette') return (ws.overlay = 'none'), true;
    if (ws.attentionOpen) return (ws.attentionOpen = false), true;
    if (ws.arrangeOpen) return (ws.arrangeOpen = false), true;
    if (ws.labOpen) return (ws.labOpen = false), true;
    if (ws.overlay !== 'none') return (ws.overlay = 'none'), true;
    if (ws.tool !== 'none') return (ws.tool = 'none'), true;
    if (ws.selected !== null) return ws.select(null), true;
    return false;
  }

  function onKey(e: KeyboardEvent): void {
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      ws.overlay = ws.overlay === 'palette' ? 'none' : 'palette';
      return;
    }
    if (e.key === 'Escape') {
      // Esc also aborts mount motion in the app (D21); nothing moves in the lab.
      if (closeTop()) e.preventDefault();
      return;
    }
    if (e.code === 'Backquote' && !isTypingTarget(e.target)) {
      ws.labOpen = !ws.labOpen;
      return;
    }
    if (isTypingTarget(e.target) || ws.overlay === 'palette') return;
    // Watch: only W, Esc, ? and Mod+K act; a key pressed to wake the screen does nothing.
    if (ws.overlay === 'watch') {
      if (e.key === 'w' || e.key === 'W') ws.overlay = 'none';
      return;
    }
    if (e.altKey && !mod && /^Digit[1-4]$/.test(e.code)) {
      e.preventDefault();
      ws.setMode(MODES[Number(e.code.slice(5)) - 1].id);
      return;
    }
    if (mod || e.altKey) return;
    if (ws.section !== 'observe' && e.key.toLowerCase() !== 'w') return;
    const k = e.key;
    const act: Record<string, () => void> = {
      w: () => {
        sim.armSound();
        ws.overlay = 'watch';
      },
      p: () => ws.toggleRail(),
      h: () => ws.toggleBand(),
      d: () => ws.toggleDrawer(),
      l: () => ws.toggleDrawer('log'),
      f: () => {
        ws.fitMode = 'fit';
        ws.viewer?.fit();
      },
      F: () => (ws.fitMode = ws.fitMode === 'fill' ? 'fit' : 'fill'),
      a: () => (ws.autoStretch = !ws.autoStretch),
      x: () => (ws.crosshair = !ws.crosshair),
      g: () => (ws.grid = !ws.grid),
      n: () => (ws.labels = !ws.labels),
      r: () => (ws.tool = ws.tool === 'region' ? 'none' : 'region'),
      u: () => (ws.errorBars = !ws.errorBars),
      '1': () => ws.viewer?.oneToOne(),
      '+': () => ws.viewer?.zoomBy(1.25),
      '=': () => ws.viewer?.zoomBy(1.25),
      '-': () => ws.viewer?.zoomBy(0.8),
    };
    const fn = act[k] ?? act[k.toLowerCase()];
    if (k === 'F' && e.shiftKey) {
      e.preventDefault();
      act.F();
      return;
    }
    if (fn) {
      e.preventDefault();
      fn();
    }
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="shell" class:watching={ws.overlay === 'watch'}>
  <LabRail />
  <main class="section" aria-label="Section">
    {#if ws.section === 'observe'}
      <ObserveScreen />
    {:else}
      <SectionSketch section={ws.section} />
    {/if}
  </main>
  <StatusBar />
</div>

{#if ws.overlay === 'watch'}
  <WatchView />
{:else if ws.overlay === 'overview'}
  <SectionsOverview />
{/if}
{#if ws.overlay === 'palette'}
  <CommandPalette initial={q.get('q') ?? ''} />
{/if}
{#if ws.labOpen}
  <LabPanel />
{/if}
<Toasts />

<style>
  .shell {
    display: grid;
    grid-template-columns: var(--sidebar-w) minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) var(--lab-statusbar-h);
    grid-template-areas:
      'rail section'
      'status status';
    height: 100vh;
    overflow: hidden;
    background: var(--bg);
  }
  .section {
    grid-area: section;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  /* Watch is a full-window view: the shell underneath is inert. */
  .watching {
    visibility: hidden;
  }
</style>
