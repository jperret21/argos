<!--
  Link card (02 2.2 / 2.3 W1 and W2, Qt connection_page.py:176-190, M22,
  M26): how ARGOS reaches the equipment.

  - Equipment: Simulator | Seestar (Alpaca) (web only). Locked while a
    device holds the link (one link at a time, protocol.md "Devices").
  - Seestar address and Alpaca port: written to the server config
    (`alpaca.host` / `alpaca.port`) on commit (Enter or leaving the field),
    never per keystroke (fixes the Qt write-per-keystroke and the probe of
    half-typed addresses). Esc in the address reverts it. A refusal is
    shown under the field in the server's words.
  - Discover: a cancellable server job (A16). Its row is always there (a
    hint before the first search), so starting one never moves the cards:
    while it runs, a compact JobProgress with the stage and Cancel; one
    device found fills the address (as Qt), several open the choice popover
    (W2), none says so in warning tone. The server never fills the address.
  - Reachability (A18, Q-G13): the Seestar probe every 10 s with the time
    of the last check; the internet only when the observer asks (the same
    "check now" glyph for both, next to what it checks). While the
    simulator is the link, an unreachable Seestar is "not in use", idle.
  - The ARGOS server line, with Retry when the link is down.
  - Setup (Q-G11): one muted line while the observer code or ASTAP is
    missing, with one Settings link. The site has its home in the
    Instrument card (Q-C10), so it is not repeated here.
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import Button from '../components/Button.svelte';
  import Card from '../components/Card.svelte';
  import IconButton from '../components/IconButton.svelte';
  import JobProgress from '../components/JobProgress.svelte';
  import NumberField from '../components/NumberField.svelte';
  import Popover from '../components/Popover.svelte';
  import Segmented from '../components/Segmented.svelte';
  import TextField from '../components/TextField.svelte';
  import { tooltip } from '../components/tooltip';
  import DeviceMark from './DeviceMark.svelte';
  import {
    deviceAddress,
    firstRunChecklist,
    networkView,
    parseDiscoveryResult,
    searchedText,
  } from './model';

  const app = useApp();

  const MODES = [
    { value: 'simulator', label: 'Simulator' },
    { value: 'alpaca', label: 'Seestar (Alpaca)' },
  ] as const;

  const LINK_WORDS: Record<string, string> = {
    idle: 'not started',
    connecting: 'connecting',
    open: 'link open',
    reconnecting: 'link lost, retrying',
    unauthorized: 'token rejected',
    forbidden: 'page refused',
  };

  const linked = $derived(app.equipment.anyLinked);
  const lockReason = $derived(
    !app.linkOpen
      ? 'the ARGOS server is not reachable'
      : linked
        ? 'disconnect the equipment first: the devices hold this link'
        : null,
  );

  // -- Address: a draft committed on Enter / blur ---------------------------
  let hostDraft = $state('');
  let hostFocused = $state(false);
  let hostError: string | null = $state(null);
  let portError: string | null = $state(null);

  $effect(() => {
    const committed = app.alpacaHost;
    if (!hostFocused) hostDraft = committed;
  });

  async function commitHost(): Promise<void> {
    if (hostDraft.trim() === app.alpacaHost) {
      hostError = null;
      return;
    }
    const r = await app.saveAddress(hostDraft, app.alpacaPort);
    hostError = r.ok ? null : (r.fields?.['alpaca.host'] ?? r.message ?? 'Refused by the server');
  }

  async function commitPort(port: number): Promise<void> {
    const r = await app.saveAddress(app.alpacaHost, port);
    portError = r.ok ? null : (r.fields?.['alpaca.port'] ?? r.message ?? 'Refused by the server');
  }

  function onHostKey(e: KeyboardEvent): void {
    if (e.key === 'Enter') {
      e.preventDefault();
      void commitHost();
    } else if (e.key === 'Escape') {
      hostDraft = app.alpacaHost;
      hostError = null;
    }
  }

  // -- Discovery (A16) ---------------------------------------------------------
  let discoverAnchor: HTMLElement | undefined = $state();
  const job = $derived(app.discoveryJob);
  const running = $derived(app.discovering);
  const result = $derived(job && job.state === 'done' ? parseDiscoveryResult(job.result) : null);
  const choices = $derived(app.discoveryChoices);
  let choice = $state(0);
  let choiceOpen = $state(false);
  $effect(() => {
    choiceOpen = choices.length > 1;
    choice = 0;
  });

  const discoverReason = $derived(
    !app.linkOpen
      ? 'the ARGOS server is not reachable'
      : linked
        ? 'disconnect the equipment first: a new address cannot replace the one in use'
        : null,
  );

  function useChoice(): void {
    const d = choices[choice];
    if (d) void app.useDiscovered(d.host, d.port);
    choiceOpen = false;
  }

  function onChoiceClose(): void {
    app.dismissDiscoveryChoice();
  }

  // -- Network (A18) ----------------------------------------------------------
  const net = $derived(networkView(app.network, app.clock, app.connectMode === 'alpaca'));
  const probed = $derived(app.network?.host ? `${app.network.host}:${app.network.port}` : null);

  // -- Setup (Q-G11): the site lives in the Instrument card -------------------
  const checklist = $derived(firstRunChecklist(app.configValues, app.appInfo?.astap_configured));
  const missing = $derived(app.configValues ? checklist.filter((c) => !c.done && c.id !== 'site') : []);
  const setupText = $derived.by(() => {
    const names = missing.map((c) => (c.id === 'obscode' ? 'observer code' : c.label));
    const list = names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names.at(-1)}` : names[0];
    return `${list ? list.charAt(0).toUpperCase() + list.slice(1) : ''} ${names.length > 1 ? 'are' : 'is'} not set`;
  });

  const serverLine = $derived(
    [
      app.config.apiBase.replace(/^https?:\/\//, ''),
      app.serverVersion ? `ARGOS ${app.serverVersion}` : null,
      app.serverApi !== null ? `API ${app.serverApi}` : null,
      LINK_WORDS[app.events.link] ?? app.events.link,
    ]
      .filter(Boolean)
      .join(' · '),
  );
  const serverDown = $derived(app.events.link !== 'open');
</script>

<Card title="Link" icon="connect" dense>
  <div class="grid">
    <span class="key" aria-hidden="true">Equipment</span>
    <div class="row">
      <div class="modes">
        <Segmented
          label="Equipment"
          options={MODES}
          value={app.connectMode}
          disabled={!!lockReason}
          onchange={(v) => app.setConnectMode(v)}
        />
      </div>
      {#if linked}<span class="caption">Held by the connected devices</span>{/if}
    </div>

    <span class="key" aria-hidden="true">Address</span>
    <div class="row address">
      <div class="host">
        <TextField
          label="Seestar address"
          hideLabel
          mono
          placeholder="192.168.x.x"
          bind:value={hostDraft}
          error={hostError}
          disabled={!!lockReason}
          readonly={running}
          onfocus={() => (hostFocused = true)}
          onblur={() => {
            hostFocused = false;
            void commitHost();
          }}
          onkeydown={onHostKey}
        />
      </div>
      <span class="key inline" aria-hidden="true">Port</span>
      <div class="port">
        <NumberField
          label="Alpaca port"
          hideLabel
          lazy
          integer
          min={1}
          max={65535}
          value={app.alpacaPort}
          bind:invalid={app.alpacaPortInvalid}
          disabled={!!lockReason || running}
          onchange={(v) => void commitPort(v)}
        />
      </div>
      <span class="anchor" bind:this={discoverAnchor}>
        <IconButton
          icon="discover"
          label="Discover"
          showLabel
          size="s"
          tooltip="top"
          tooltipText="Search the local network for Alpaca devices (broadcast, known addresses, then a subnet scan; up to about 15 s)"
          busy={running || !!app.busy.discover}
          disabledReason={running ? null : discoverReason}
          onclick={() => void app.startDiscovery()}
        />
      </span>
    </div>
    {#if portError}
      <span></span>
      <p class="field-error" role="alert">{portError}</p>
    {/if}

    <!-- Always present (a hint before the first search): a search never moves the cards. -->
    <span class="key" aria-hidden="true">Search</span>
    {#if job && (running || job.state === 'failed' || job.state === 'cancelled')}
      <div class="job">
        <JobProgress
          {job}
          title="Discovery"
          variant="strip"
          now={app.clock}
          oncancel={() => app.cancelDiscovery()}
          ondismiss={() => app.dismissDiscovery()}
          onretry={() => void app.startDiscovery()}
        />
      </div>
    {:else if app.discoveryNote}
      {@const note = app.discoveryNote}
      <div class="row note" role="status">
        <DeviceMark
          mark={note.tone === 'warning' ? 'ring' : note.tone === 'error' ? 'cross' : 'filled'}
          tone={note.tone === 'warning' ? 'busy' : note.tone === 'error' ? 'error' : 'ok'}
        />
        <span class="note-text">{note.text}</span>
        {#if result && result.searched.length}<span class="caption">{searchedText(result)}</span>{/if}
        <span class="spacer"></span>
        <IconButton icon="close" label="Dismiss" variant="ghost" size="s" tooltip="top" onclick={() => app.dismissDiscovery()} />
      </div>
    {:else}
      <div class="row note">
        <span class="caption">Not searched yet: Discover looks for a Seestar on this network (about 15 s)</span>
      </div>
    {/if}

    <span class="key" aria-hidden="true">Seestar</span>
    <div class="row reach" aria-label="Seestar reachability: {net.seestar.word}">
      <DeviceMark mark={net.seestar.mark} tone={net.seestar.tone} />
      <span class="word">{net.seestar.word}</span>
      {#if probed && net.seestar.word !== 'not configured'}<span class="num caption">{probed}</span>{/if}
      {#if net.checked}<span class="caption">checked {net.checked}</span>{/if}
      <IconButton
        icon="refresh"
        label="Check the Seestar now"
        variant="ghost"
        size="s"
        tooltip="top"
        busy={!!app.busy.network}
        disabledReason={!app.linkOpen ? 'the ARGOS server is not reachable' : app.network?.seestar === null ? 'no Seestar address configured' : null}
        onclick={() => void app.checkNetwork(false)}
      />
    </div>

    <span class="key" aria-hidden="true">Internet</span>
    <div class="row reach" aria-label="Internet: {net.internet.word}">
      <DeviceMark mark={net.internet.mark} tone={net.internet.tone} />
      <span class="word">{net.internet.word}</span>
      {#if net.internetChecked}<span class="caption">checked {net.internetChecked}</span>{:else}<span class="caption">checked only when you ask</span>{/if}
      <IconButton
        icon="refresh"
        label="Check the internet"
        tooltipText="Check the internet once (TCP to 1.1.1.1, then 8.8.8.8, port 53). ARGOS never checks it in the background."
        variant="ghost"
        size="s"
        tooltip="top"
        busy={!!app.busy.network}
        disabledReason={!app.linkOpen ? 'the ARGOS server is not reachable' : null}
        onclick={() => void app.checkNetwork(true)}
      />
    </div>

    <span class="key" aria-hidden="true">Server</span>
    <div class="row server" class:down={serverDown}>
      <DeviceMark
        mark={serverDown ? (app.events.link === 'unauthorized' || app.events.link === 'forbidden' ? 'cross' : 'ring') : 'filled'}
        tone={serverDown ? 'error' : 'ok'}
      />
      <span class="num server-text" use:tooltip={{ text: `ARGOS server ${app.config.apiBase}`, placement: 'top' }}>{serverLine}</span>
      <span class="spacer"></span>
      {#if serverDown}
        <IconButton icon="refresh" label="Retry server" showLabel size="s" tooltip="top" onclick={() => app.reconnect()} />
      {/if}
    </div>

    {#if missing.length}
      <span class="key" aria-hidden="true">Setup</span>
      <div class="row setup" aria-label="Setup before observing">
        <DeviceMark mark="ring" tone="busy" />
        <span class="setup-text">{setupText}</span>
        <IconButton
          icon="nav-configuration"
          label="Settings"
          showLabel
          size="s"
          variant="ghost"
          tooltip="top"
          tooltipText="The observer code and ASTAP are set in Settings (F5)"
          onclick={() => app.go('configuration')}
        />
      </div>
    {/if}
  </div>
</Card>

<Popover bind:open={choiceOpen} anchor={discoverAnchor} title="Devices found" placement="bottom-start" width={320} onclose={onChoiceClose}>
  <div class="choices" role="radiogroup" aria-label="Devices found">
    {#each choices as d, i (deviceAddress(d))}
      <label class="choice" class:checked={choice === i}>
        <input
          class="visually-hidden"
          type="radio"
          name="discovered"
          value={i}
          checked={choice === i}
          onchange={() => (choice = i)}
        />
        <span class="radio" aria-hidden="true"></span>
        <span class="num">{deviceAddress(d)}</span>
        {#if d.name}<span class="caption">{d.name}</span>{/if}
      </label>
    {/each}
  </div>
  {#if result && result.searched.length}<p class="caption searched">{searchedText(result)}</p>{/if}
  {#snippet footer()}
    <div class="choice-actions">
      <Button
        label="Cancel"
        onclick={() => {
          choiceOpen = false;
          app.dismissDiscoveryChoice();
        }}
      />
      <Button label="Use address" variant="primary" onclick={useChoice} />
    </div>
  {/snippet}
</Popover>

<style>
  .grid {
    display: grid;
    grid-template-columns: 64px minmax(0, 1fr);
    align-items: center;
    gap: var(--space-2) var(--space-3);
    font-size: var(--text-s);
  }

  .key {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .key.inline {
    flex: none;
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
    min-height: 26px;
  }

  .modes {
    width: 280px;
    flex: none;
  }

  .address {
    gap: var(--space-3);
    align-items: flex-start;
  }
  .address .key.inline {
    line-height: 28px;
  }
  .host {
    flex: 1 1 180px;
    min-width: 0;
  }
  .port {
    width: 84px;
    flex: none;
  }
  /* A range message stays on one line under the narrow field. */
  .port :global(.help) {
    white-space: nowrap;
  }
  .anchor {
    display: inline-flex;
    flex: none;
  }

  .field-error {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-xs);
  }

  .job {
    min-width: 0;
  }

  .note-text {
    color: var(--fg);
    min-width: 0;
  }

  .word {
    color: var(--fg);
  }

  .caption {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .spacer {
    flex: 1;
  }

  .server-text {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--fg);
  }

  .setup-text {
    min-width: 0;
    overflow: hidden;
    color: var(--text-muted);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* The search row keeps one height whatever it shows (hint, note, progress). */
  .note,
  .job {
    min-height: 30px;
  }
  .note {
    display: flex;
    align-items: center;
  }

  .reach :global(.icon-button),
  .note :global(.icon-button),
  .server :global(.icon-button),
  .setup :global(.icon-button) {
    height: 26px;
  }

  .choices {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .choice {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: 28px;
    padding: 0 var(--space-2);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-s);
    cursor: pointer;
  }
  .choice:hover {
    background: var(--hover-bg);
  }
  .choice.checked {
    background: var(--toggled-bg);
  }
  /* Token-drawn radio (no native control: it draws grey in Night Red, BRAND 4.3). */
  /* Drawn in --fg like the Menu radios: brass stays for the primary button and focus. */
  .radio {
    position: relative;
    width: 12px;
    height: 12px;
    flex: none;
    border-radius: var(--radius-round);
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .choice.checked .radio {
    box-shadow: inset 0 0 0 1.5px var(--fg);
  }
  .choice.checked .radio::after {
    content: '';
    position: absolute;
    inset: 3px;
    border-radius: var(--radius-round);
    background: var(--fg);
  }
  .choice:has(input:focus-visible) {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .searched {
    margin: var(--space-2) 0 0;
    white-space: normal;
  }
  .choice-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
  }
</style>
