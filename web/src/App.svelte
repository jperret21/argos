<!--
  ARGOS web UI shell: navigation rail | section | status bar, plus toasts.

  The app state (server link, settings, display, feedback) lives in one
  ArgosApp instance shared through context (lib/app/state.svelte.ts).
  Sections other than Observe are placeholders in this spike.
  Add ?perf to the URL to log per-frame decode/upload/stats/draw timings
  (upload and draw are then fenced with a 1-px readPixels: measurements only).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { matchesShortcut } from './lib/app/shortcuts';
  import { ArgosApp, provideApp, type Section } from './lib/app/state.svelte';
  import ImagingScreen from './lib/imaging/ImagingScreen.svelte';
  import EmptySection from './lib/shell/EmptySection.svelte';
  import NavRail, { type NavEntry } from './lib/shell/NavRail.svelte';
  import StatusBar from './lib/shell/StatusBar.svelte';
  import Toasts from './lib/shell/Toasts.svelte';

  const app = provideApp(new ArgosApp());
  const perf = new URLSearchParams(location.search).has('perf');

  const NAV: readonly NavEntry[] = [
    {
      id: 'connection',
      icon: 'nav-connection',
      label: 'Connection',
      hint: 'Connection: set up the telescope equipment',
      shortcut: 'F1',
    },
    {
      id: 'imaging',
      icon: 'nav-imaging',
      label: 'Observe',
      hint: 'Observe: frame, focus and monitor the observation',
      shortcut: 'F2',
    },
    {
      id: 'sequencer',
      icon: 'nav-sequencer',
      label: 'Plan',
      hint: "Plan: build and run the night's sequence",
      shortcut: 'F3',
    },
    {
      id: 'analyze',
      icon: 'nav-analyze',
      label: 'Review',
      hint: 'Review: inspect the light curve and export to AAVSO',
      shortcut: 'F4',
    },
    {
      id: 'configuration',
      icon: 'nav-configuration',
      label: 'Settings',
      hint: 'Settings: observer, site, paths, appearance',
      shortcut: 'F5',
    },
  ];

  const PLACEHOLDERS: Record<Exclude<Section, 'imaging'>, { title: string; text: string; items: string[] }> = {
    connection: {
      title: 'Equipment set-up',
      text: 'The full set-up page of the Qt app comes later. The Connection card on the Observe screen already connects the simulator or a Seestar over ASCOM Alpaca.',
      items: ['Telescope profile and sensor', 'Alpaca discovery on the local network', 'Device health and firmware checks'],
    },
    sequencer: {
      title: "The night's sequence",
      text: 'Planning and running timed FITS sequences, with the target visibility and the expected end of the run.',
      items: ['Targets, exposures and filters', 'Visibility and meridian timing', 'Progress, ETA and per-frame quality'],
    },
    analyze: {
      title: 'Review the session',
      text: 'The differential light curve of the session, the frames behind every point, and the AAVSO export.',
      items: ['Light curve with comparison and check stars', 'Frame inspection from any point', 'AAVSO extended-format export'],
    },
    configuration: {
      title: 'Settings',
      text: 'Observer, site, storage paths and appearance. Until then, the theme switch sits at the right of the Observe toolbar.',
      items: ['Observer code and site coordinates', 'Output folders and file naming', 'Theme and display preferences'],
    },
  };

  onMount(() => app.start());

  function onKey(e: KeyboardEvent): void {
    // Rail shortcuts (Qt View menu): F1-F5, even from a text field.
    const hit = NAV.find((n) => matchesShortcut(e, n.shortcut));
    if (hit) {
      e.preventDefault();
      app.section = hit.id;
    }
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="shell">
  <NavRail entries={NAV} />
  <main class="section" aria-label={NAV.find((n) => n.id === app.section)?.label}>
    {#if app.section === 'imaging'}
      <ImagingScreen {perf} />
    {:else}
      {@const p = PLACEHOLDERS[app.section]}
      {@const nav = NAV.find((n) => n.id === app.section)}
      <EmptySection icon={nav?.icon ?? 'nav-imaging'} title={p.title} text={p.text} items={p.items} />
    {/if}
  </main>
  <div class="status">
    <StatusBar />
  </div>
</div>
<Toasts />

<style>
  .shell {
    display: grid;
    grid-template-columns: var(--sidebar-w) minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) var(--statusbar-h);
    height: 100%;
  }

  .section {
    min-width: 0;
    min-height: 0;
  }

  .status {
    grid-column: 1 / -1;
  }
</style>
