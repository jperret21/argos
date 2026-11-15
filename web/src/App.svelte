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
  - Sections: Connection (wave 1), Observe and Settings (wave 2), Plan (wave 6a)
    and Review (wave 7: R0 sessions, R1 a session or the live run, R2 a frame;
    lib/review/ReviewScreen.svelte) are built. Every section has the Log
    drawer (L).
  - The mount-motion interlock (wave 6a, D2): one InterlockDialog for every section; every
    mount control goes through app.interlock.
  - Global overlays (wave 2): the support bundle dialog (Help menu,
    Settings › Privacy & diagnostics, D14), the command palette (Mod+K) and
    the one Undo queue, drawn in the toasts' column.
  Add ?perf to the URL to log per-frame decode/upload/stats/draw timings
  (upload and draw are then fenced with a 1-px readPixels: measurements only).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { ArgosApp, provideApp } from './lib/app/state.svelte';
  import ConnectionScreen from './lib/connection/ConnectionScreen.svelte';
  import ImagingScreen from './lib/imaging/ImagingScreen.svelte';
  import PlanScreen from './lib/plan/PlanScreen.svelte';
  import ReviewScreen from './lib/review/ReviewScreen.svelte';
  import InterlockDialog from './lib/run/InterlockDialog.svelte';
  import SettingsScreen from './lib/settings/SettingsScreen.svelte';
  import CommandPalette from './lib/shell/CommandPalette.svelte';
  import KeyHintBanner from './lib/shell/KeyHintBanner.svelte';
  import SupportBundle from './lib/shell/SupportBundle.svelte';
  import OpenFits from './lib/shell/OpenFits.svelte';
  import LogDrawer from './lib/shell/LogDrawer.svelte';
  import NavRail, { type NavEntry } from './lib/shell/NavRail.svelte';
  import StartupScreen from './lib/shell/StartupScreen.svelte';
  import StatusBar from './lib/shell/StatusBar.svelte';
  import WatchHost from './lib/shell/WatchHost.svelte';
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
    {:else if app.section === 'sequencer'}
      <PlanScreen />
    {:else if app.section === 'analyze'}
      <ReviewScreen />
    {:else}
      <div class="placeholder" style:grid-template-rows="minmax(0, 1fr) {app.logOpen ? '216px' : '0px'}">
        <SettingsScreen />
        {#if app.logOpen}<LogDrawer label="Settings drawer" />{/if}
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
<!-- W6a (D2): a mount command refused during a run asks here, from any section. -->
<InterlockDialog lock={app.interlock} exposureS={app.sequence.state?.current?.exposure_s ?? app.sequence.state?.step?.exposure_s ?? null} />
<!-- W6b (D3): Watch, the run read from 2 m; a modal layer over every section. -->
{#if app.watchOpen}
  <WatchHost attention={app.attention} keepAwake={app.keepAwake} onclose={() => (app.watchOpen = false)} />
{/if}
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
