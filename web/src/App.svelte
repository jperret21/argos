<!--
  ARGOS web UI shell (README 1.1, 01 2.3.1): navigation rail | section |
  status bar, plus toasts, the keyboard shortcuts sheet (in NavRail) and the
  start-up screen.

  - The app state (server link, settings, display, feedback, log, jobs, the
    shortcut registry) lives in one ArgosApp instance shared through context
    (lib/app/state.svelte.ts). Global keys (F1-F5, ?, L, Mod+, and Escape =
    abort motion, D21) are bound there, through the one registry.
  - Start-up screen (01 2.3.8, M1-M2): over the shell until GET /api/health
    answers and /ws/events has sent its first status; a failure stays on
    screen with Retry. It never comes back once the UI started: a later
    link loss shows in the status bar and the Link card.
  - Sections: Connection (wave 1), Observe and Settings (wave 2) are built;
    Plan and Review say what they will hold. Every section has the Log
    drawer (L).
  - Global overlays (wave 2): the support bundle dialog (Help menu,
    Settings › Privacy & diagnostics, D14), the command palette (Mod+K) and
    the one Undo queue, drawn in the toasts' column.
  Add ?perf to the URL to log per-frame decode/upload/stats/draw timings
  (upload and draw are then fenced with a 1-px readPixels: measurements only).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { ArgosApp, provideApp, type Section } from './lib/app/state.svelte';
  import ConnectionScreen from './lib/connection/ConnectionScreen.svelte';
  import ImagingScreen from './lib/imaging/ImagingScreen.svelte';
  import SettingsScreen from './lib/settings/SettingsScreen.svelte';
  import CommandPalette from './lib/shell/CommandPalette.svelte';
  import KeyHintBanner from './lib/shell/KeyHintBanner.svelte';
  import SupportBundle from './lib/shell/SupportBundle.svelte';
  import OpenFits from './lib/shell/OpenFits.svelte';
  import EmptySection from './lib/shell/EmptySection.svelte';
  import LogDrawer from './lib/shell/LogDrawer.svelte';
  import NavRail, { type NavEntry } from './lib/shell/NavRail.svelte';
  import StartupScreen from './lib/shell/StartupScreen.svelte';
  import StatusBar from './lib/shell/StatusBar.svelte';
  import Toasts from './lib/shell/Toasts.svelte';

  const app = provideApp(new ArgosApp());
  const perf = new URLSearchParams(location.search).has('perf');

  const key = (id: string) => app.shortcuts.keyFor(id) ?? '';

  const NAV: readonly NavEntry[] = [
    {
      id: 'connection',
      icon: 'nav-connection',
      label: 'Connection',
      hint: 'Connection: telescope profile, link and the four devices',
      shortcut: key('nav.connection'),
    },
    {
      id: 'imaging',
      icon: 'nav-imaging',
      label: 'Observe',
      hint: 'Observe: frame, focus and monitor the observation',
      shortcut: key('nav.observe'),
    },
    {
      id: 'sequencer',
      icon: 'nav-sequencer',
      label: 'Plan',
      hint: "Plan: build and run the night's sequence",
      shortcut: key('nav.plan'),
    },
    {
      id: 'analyze',
      icon: 'nav-analyze',
      label: 'Review',
      hint: 'Review: inspect the light curve and export to AAVSO',
      shortcut: key('nav.review'),
    },
    {
      id: 'configuration',
      icon: 'nav-configuration',
      label: 'Settings',
      hint: 'Settings: observer, site, paths, appearance',
      shortcut: key('nav.settings'),
    },
  ];

  type Placeholder = Exclude<Section, 'imaging' | 'connection' | 'configuration'>;
  const PLACEHOLDERS: Record<Placeholder, { title: string; text: string; items: string[] }> = {
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
  };

  onMount(() => app.start());

  // The start-up screen fades out once (--duration-base), then leaves the DOM.
  let startupGone = $state(false);
  $effect(() => {
    if (!app.started) return;
    const t = setTimeout(() => (startupGone = true), 220);
    return () => clearTimeout(t);
  });
</script>

<div class="shell" inert={!app.started || undefined}>
  <NavRail entries={NAV} />
  <main class="section" aria-label={NAV.find((n) => n.id === app.section)?.label}>
    {#if app.section === 'imaging'}
      <ImagingScreen {perf} />
    {:else if app.section === 'connection'}
      <ConnectionScreen />
    {:else if app.section === 'configuration'}
      <div class="placeholder" style:grid-template-rows="minmax(0, 1fr) {app.logOpen ? '216px' : '0px'}">
        <SettingsScreen />
        {#if app.logOpen}<LogDrawer label="Settings drawer" />{/if}
      </div>
    {:else}
      {@const p = PLACEHOLDERS[app.section]}
      {@const nav = NAV.find((n) => n.id === app.section)}
      <div class="placeholder" style:grid-template-rows="minmax(0, 1fr) {app.logOpen ? '216px' : '0px'}">
        <EmptySection icon={nav?.icon ?? 'nav-imaging'} title={p.title} text={p.text} items={p.items} />
        {#if app.logOpen}<LogDrawer label="{nav?.label ?? 'Section'} drawer" />{/if}
      </div>
    {/if}
  </main>
  <div class="status">
    <StatusBar />
  </div>
</div>
<Toasts />
<SupportBundle />
<OpenFits />
<CommandPalette />
<KeyHintBanner />
{#if !startupGone}
  <StartupScreen
    stages={app.startup.stages}
    version={app.serverVersion}
    failure={app.startup.failure}
    leaving={app.started}
    onretry={() => app.retryStartup()}
  />
{/if}

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

  .placeholder {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    height: 100%;
    min-height: 0;
  }

  .status {
    grid-column: 1 / -1;
  }
</style>
