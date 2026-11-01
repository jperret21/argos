<!--
  Connection screen (F1; web/spec/02-connection-and-settings.md 2.3 W1,
  README 1.2; Qt ConnectionPage connection_page.py:49, M21-M26): the
  start-of-night stop. Everything needed to get the equipment ready is on
  one screen without a disclosure; nothing scrolls but the log.

    toolbar   Connection · (mark) n of 4 devices ready · what runs ... [Connect all] [Disconnect all]
    left      Instrument (profile, specs, validated, caveats, site) · Link (mode, address,
              port, Discover job, reachability, server, setup checklist)
    right     Devices (four rows, full reasons, per-device actions) · Planetarium
    bottom    Connection log: the one log store filtered on the topics connection,
              discovery and planetarium (README 3.8); L (or its [log] switch, or the
              status-bar Log button) widens it to every topic in place: this screen
              has no drawer, so the same lines are never shown twice (D17)

  Header actions (icon + label, BRAND 7): Connect all connects only what is
  not connected yet (A15) with the link chosen in the Link card; it reads
  "Equipment ready" (disabled) when the four are, so the summary beside it
  only counts. Disconnect all asks first only while an exposure, live view
  or a slew runs (Q-C5, 02 W10b); it also stops a Connect all from its
  first moment (the server claims the devices at once). No single key
  connects or disconnects (README 3.10).

  Server link lost: every record here is the last one received. The
  summary says "Last known", the device rows lose their state colours and
  every action waits for the link (the status bar says "Server link lost").
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import ConfirmDialog from '../components/ConfirmDialog.svelte';
  import IconButton from '../components/IconButton.svelte';
  import LogPanel from '../components/LogPanel.svelte';
  import DeviceMark from './DeviceMark.svelte';
  import DevicesCard from './DevicesCard.svelte';
  import InstrumentCard from './InstrumentCard.svelte';
  import LinkCard from './LinkCard.svelte';
  import { disconnectRisk } from './model';
  import PlanetariumCard from './PlanetariumCard.svelte';

  const app = useApp();

  const LOG_TOPICS = ['connection', 'discovery', 'planetarium'] as const;

  const summary = $derived(app.equipment);
  const stale = $derived(app.stale);
  const summaryMark = $derived(
    stale
      ? 'ring'
      : summary.anyError
        ? 'cross'
        : summary.anyConnecting
          ? 'half'
          : summary.allReady
            ? 'filled'
            : summary.ready > 0
              ? 'half'
              : 'ring',
  );
  const summaryText = $derived(
    stale
      ? `Last known: ${summary.ready} of ${summary.total} ready`
      : summary.progress
        ? `${summary.text} · ${summary.progress}`
        : summary.text,
  );

  const connectReason = $derived.by(() => {
    if (stale) return 'the ARGOS server is not reachable';
    if (summary.allReady) return 'every device is connected';
    const problem = app.connectProblem();
    return problem ? (problem.startsWith('the ARGOS') ? problem : `${problem} in the Link card`) : null;
  });
  const disconnectReason = $derived(
    !app.linkOpen ? 'the ARGOS server is not reachable' : summary.anyLinked ? null : 'nothing is connected',
  );

  let confirmOpen = $state(false);
  const risk = $derived(disconnectRisk(app.running));

  function disconnectAll(): void {
    if (risk) confirmOpen = true;
    else void app.disconnectAll();
  }
</script>

<div class="connection">
  <div class="toolbar" role="toolbar" aria-label="Connection">
    <h1>Connection</h1>
    <span class="summary" class:stale aria-live="polite">
      <DeviceMark mark={summaryMark} tone={stale ? 'idle' : summary.tone} spinning={!stale && summary.anyConnecting} />
      <span>{summaryText}</span>
    </span>
    <span class="spacer"></span>
    <IconButton
      icon={app.connectMode === 'simulator' ? 'simulator' : 'connect'}
      label={summary.allReady && !stale ? 'Equipment ready' : 'Connect all'}
      tooltipText={app.connectMode === 'simulator'
        ? 'Connect every device of the simulator not connected yet'
        : `Connect every device not connected yet at ${app.alpacaHost || 'the Seestar address'}:${app.alpacaPort}`}
      showLabel
      variant="primary"
      tooltip="bottom"
      busy={!!app.busy.connectAll}
      disabledReason={connectReason}
      onclick={() => void app.connectAll()}
    />
    <IconButton
      icon="disconnect"
      label="Disconnect all"
      tooltipText="Disconnect the mount, the camera, the filter wheel and the focuser (also stops a Connect all and attempts in progress)"
      showLabel
      variant="danger"
      tooltip="bottom"
      busy={!!app.busy.disconnectAll}
      disabledReason={disconnectReason}
      onclick={disconnectAll}
    />
  </div>

  <div class="body">
    <div class="columns">
      <div class="col">
        <InstrumentCard />
        <LinkCard />
      </div>
      <div class="col">
        <DevicesCard />
        <PlanetariumCard />
      </div>
    </div>
    <div class="log">
      <LogPanel
        store={app.log}
        title={app.connectionLogAll ? 'Activity log' : 'Connection log'}
        topics={app.connectionLogAll ? null : LOG_TOPICS}
        persist="argos.connection.log"
        markSeen={app.connectionLogAll}
        empty="Connection, discovery and Stellarium messages appear here: what was tried, what answered, and every error in full."
      >
        {#snippet actions()}
          <IconButton
            icon="log"
            label={app.connectionLogAll ? 'Show the connection topics only' : 'Show every topic (the whole activity log)'}
            shortcut={app.shortcuts.keyFor('log.toggle')}
            variant="ghost"
            size="s"
            pressed={app.connectionLogAll}
            layoutToggle
            tooltip="left"
            onclick={() => app.toggleLog()}
          />
        {/snippet}
      </LogPanel>
    </div>
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
  .connection {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    height: 100%;
    min-height: 0;
    background: var(--bg);
  }

  /* One row, the height of the Observe toolbar, so the rail's edge continues it. */
  .toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: calc(var(--control-h-m) + 2 * var(--space-2) + var(--border-w));
    padding: 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border);
    min-width: 0;
  }
  h1 {
    margin: 0 var(--space-2) 0 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
    white-space: nowrap;
  }
  .summary {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding-left: var(--space-3);
    border-left: var(--border-w) solid var(--border-soft);
    color: var(--fg);
    font-size: var(--text-s);
    white-space: nowrap;
  }
  .summary.stale {
    color: var(--text-muted);
  }
  .spacer {
    flex: 1;
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-height: 0;
    padding: var(--space-3);
  }

  .columns {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: var(--space-3);
    flex: none;
  }
  .col {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }

  .log {
    flex: 1;
    min-height: 120px;
  }
</style>
