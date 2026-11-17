<!--
  The desktop app's overlays, mounted once by App.svelte (W8, M18): the Quit dialog
  (confirm / forcing), the shutdown scrim (stopping, closing, a remote shutdown and its
  end) and the crash notice. The crash notice wins over the scrim (a restart, its
  failure, a crash); a shutdown asked by another client keeps the scrim's "shut down"
  panel when the shell then reports the exit (one notice per event, desktop.svelte.ts
  `crash`). In a browser tab only the remote shutdown can show (there is no Quit there).
  A local quit's scrim panel waits SCRIM_DELAY_MS (no flash), the app inert meanwhile.
-->
<script lang="ts">
  import CrashNotice from './CrashNotice.svelte';
  import type { DesktopShell } from './desktop.svelte';
  import QuitDialog from './QuitDialog.svelte';
  import { SCRIM_DELAY_MS } from './quit.svelte';
  import ShutdownScrim from './ShutdownScrim.svelte';

  interface Props {
    desktop: DesktopShell;
    version?: string | null;
    /** Reconnect the page (after a remote shutdown, once the server runs again). */
    onreconnect: () => void;
  }

  let { desktop, version = null, onreconnect }: Props = $props();

  const quit = $derived(desktop.quit);
  const crash = $derived(desktop.crash);
</script>

{#if quit.phase === 'confirm' || quit.phase === 'forcing'}
  <QuitDialog
    open
    items={quit.busy}
    sentences={quit.sentences}
    message={quit.message}
    error={quit.error}
    forcing={quit.phase === 'forcing'}
    oncancel={() => quit.cancel()}
    onforce={() => quit.force()}
  />
{/if}
{#if crash}
  <CrashNotice
    view={crash}
    {version}
    onrestart={() => desktop.restartServer()}
    onopenlogs={() => desktop.openLogFolder()}
    onquit={() => quit.exitNow()}
  />
{:else if quit.scrim}
  <ShutdownScrim
    phase={quit.phase}
    stages={quit.stages}
    startedAt={quit.startedAt}
    stuck={quit.stuck}
    closeStalled={quit.closeStalled}
    budgetS={quit.budgetS}
    delayMs={SCRIM_DELAY_MS}
    desktop={desktop.available}
    onquitnow={() => (quit.phase === 'closing' ? void quit.request() : quit.quitNow())}
    onreconnect={desktop.available ? () => desktop.restartServer() : onreconnect}
    reconnectLabel={desktop.available ? 'Restart server' : 'Reconnect'}
  />
{/if}
