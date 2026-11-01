<!--
  Connection: simulator or a Seestar over ASCOM Alpaca (host + port), the
  link state in words, and the connect / disconnect action (icon + label:
  it moves hardware, BRAND section 7). The server link itself (WebSockets)
  is summarised on the last line.

  - The card folds itself once the equipment is connected and unfolds on a
    disconnection, an error, or a lost server link (its Retry is here). The
    toolbar's connection chip unfolds and focuses it.
  - Connect is a secondary button here: the viewer's prompt holds the one
    primary call to action, and uses the mode chosen here.
  - Disconnecting while live view or a slew runs asks first, inline.
-->
<script lang="ts">
  import { tick } from 'svelte';
  import { useApp } from '../app/state.svelte';
  import { connectionStatus } from '../app/status';
  import Card from '../components/Card.svelte';
  import IconButton from '../components/IconButton.svelte';
  import NumberField from '../components/NumberField.svelte';
  import Segmented from '../components/Segmented.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import TextField from '../components/TextField.svelte';

  const app = useApp();

  const badge = $derived(connectionStatus(app.connection, app.events.link));
  const conn = $derived(app.connection);
  const connected = $derived(app.connected);
  const connecting = $derived(conn?.state === 'connecting' || !!app.busy.connection);
  const running = $derived(app.cameraBusy || app.slewing);

  const MODES = [
    { value: 'simulator', label: 'Simulator' },
    { value: 'alpaca', label: 'Seestar (Alpaca)' },
  ] as const;

  let confirmDisconnect = $state(false);

  const connectReason = $derived(app.connectProblem());

  // Fold once connected (the chip and the status bar keep the state in view);
  // unfold on a disconnection, an error or a lost link, when the form or the
  // Retry button is needed again.
  let wasConnected: boolean | null = null;
  $effect(() => {
    const now = connected && app.linkOpen;
    if (wasConnected === null || now !== wasConnected) app.connectionOpen = !now;
    if (conn?.state === 'error' || !app.linkOpen) app.connectionOpen = true;
    wasConnected = now;
  });

  // The toolbar chip asked for the card: unfold it and move the focus there.
  $effect(() => {
    if (!app.connectionReveal) return;
    app.connectionReveal = false;
    app.connectionOpen = true;
    void tick().then(() => {
      const toggle = document.querySelector<HTMLElement>('#card-connection .toggle');
      toggle?.scrollIntoView({ block: 'nearest' });
      toggle?.focus();
    });
  });

  $effect(() => {
    if (!connected) confirmDisconnect = false;
  });

  function disconnect(): void {
    confirmDisconnect = false;
    void app.disconnect();
  }

  const LINK_WORDS: Record<string, string> = {
    idle: 'idle',
    connecting: 'connecting',
    open: 'open',
    reconnecting: 'retrying',
    unauthorized: 'token rejected',
    forbidden: 'origin refused',
  };
</script>

<Card title="Connection" icon="connect" collapsible anchor="card-connection" bind:open={app.connectionOpen}>
  {#snippet status()}
    <StatusBadge tone={badge.tone} label={badge.label} />
  {/snippet}

  <Segmented
    label="Equipment"
    options={MODES}
    bind:value={app.connectMode}
    disabled={connected || connecting}
  />

  {#if app.connectMode === 'alpaca'}
    <div class="alpaca">
      <TextField
        label="Seestar address"
        bind:value={app.alpacaHost}
        mono
        placeholder="192.168.1.20"
        disabled={connected || connecting}
      />
      <NumberField
        label="Alpaca port"
        bind:value={app.alpacaPort}
        bind:invalid={app.alpacaPortInvalid}
        min={1}
        max={65535}
        integer
        disabled={connected || connecting}
      />
    </div>
  {/if}

  <dl class="facts">
    <div>
      <dt>Device</dt>
      <dd>{connected && conn?.device_name ? conn.device_name : '—'}</dd>
    </div>
    {#if conn?.message}
      <div>
        <dt>Message</dt>
        <dd class="message">{conn.message}</dd>
      </div>
    {/if}
    <div>
      <dt>Server</dt>
      <dd class="num">
        {app.config.apiBase.replace(/^https?:\/\//, '')}{app.serverVersion
          ? ` · v${app.serverVersion}`
          : ''} · {LINK_WORDS[app.events.link]}
      </dd>
    </div>
  </dl>

  <div class="actions">
    {#if confirmDisconnect}
      <span class="confirm" role="group" aria-label="Confirm disconnect">
        <span class="question">Stop {app.slewing ? 'the slew' : 'live view'} and disconnect?</span>
        <button type="button" class="text-btn strong" onclick={disconnect}>Disconnect</button>
        <button type="button" class="text-btn" onclick={() => (confirmDisconnect = false)}>Cancel</button>
      </span>
    {:else if connected}
      <IconButton
        icon="disconnect"
        label="Disconnect"
        showLabel
        size="s"
        busy={!!app.busy.connection}
        disabledReason={app.stale ? 'the ARGOS server is not reachable' : null}
        tooltip="top"
        onclick={() => (running ? (confirmDisconnect = true) : disconnect())}
      />
    {:else}
      <IconButton
        icon={app.connectMode === 'simulator' ? 'simulator' : 'connect'}
        label={app.connectMode === 'simulator' ? 'Connect simulator' : 'Connect Seestar'}
        showLabel
        size="s"
        busy={connecting}
        disabledReason={connectReason}
        tooltip="top"
        onclick={() => app.connect()}
      />
    {/if}
    {#if app.events.link === 'unauthorized' || app.events.link === 'reconnecting' || app.events.link === 'forbidden'}
      <IconButton
        icon="refresh"
        label="Retry server"
        showLabel
        size="s"
        variant="ghost"
        onclick={() => app.reconnect()}
      />
    {/if}
  </div>
</Card>

<style>
  .alpaca {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 112px;
    gap: var(--space-3);
  }

  .facts {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin: 0;
  }
  .facts div {
    display: grid;
    grid-template-columns: 104px minmax(0, 1fr);
    gap: var(--space-3);
    align-items: baseline;
  }
  dt {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  dd {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
    text-align: right;
    overflow-wrap: anywhere;
  }
  /* Driver errors can be long Python reprs: three lines here, all of it in the log. */
  .message {
    display: -webkit-box;
    overflow: hidden;
    text-align: left;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    line-clamp: 3;
  }

  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .confirm {
    display: inline-flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .question {
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
  }

  /* Text-only buttons: confirmations (BRAND section 7). */
  .text-btn {
    height: var(--control-h-s);
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    cursor: pointer;
  }
  .text-btn:hover {
    background: var(--hover-bg);
  }
  .text-btn.strong {
    border-color: var(--danger);
  }
  .text-btn.strong:hover {
    background: var(--danger);
    color: var(--on-danger);
  }
</style>
