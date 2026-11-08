<!--
  Planetarium card (02 2.2 / 2.3 W1, Qt stellarium_card.py:33, M25): the
  Stellarium Telescope Control bridge (server row A19).

  - State badge: Stopped / Listening / Error. The bind error is shown here
    in full (the Qt card only logged it, 02 H14), with the host and port.
  - Host (read-only fact, `stellarium.host`, now visible: the Qt help said
    "this host" without showing it) and Port (`stellarium.port`, saved on
    commit, not only when the bridge starts: fixes the Qt behaviour;
    disabled while the bridge runs, as in Qt).
  - [planetarium Start bridge] / [stop Stop bridge]: icon + label (BRAND 7:
    a GoTo from Stellarium moves the mount).
  - Facts while it runs: Stellarium clients connected, and the last GoTo
    (RA / Dec J2000, UTC time, outcome: "mount slewing", "mount not
    connected"...). It never reverts to a stale label (the Qt flash did).
  - "Look up target names online after a GoTo" (`stellarium.online_target_lookup`,
    same text and caption as Qt), saved at once.
  - "How to connect Stellarium": the Qt help text in a disclosure,
    remembered per viewer.
  - Wave 3 (A20): after a GoTo the server offers catalogue names near it
    (TargetSuggestions, also in the Observe Mount card); "Use as target
    name" sets the observation's name and target (A39).
-->
<script lang="ts">
  import { isBoolean, loadPref, savePref } from '../app/prefs';
  import { useApp } from '../app/state.svelte';
  import { utcClock } from '../app/log';
  import Card from '../components/Card.svelte';
  import Checkbox from '../components/Checkbox.svelte';
  import Icon from '../components/Icon.svelte';
  import IconButton from '../components/IconButton.svelte';
  import NumberField from '../components/NumberField.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { formatDec, formatRA } from '../format/astro';
  import TargetSuggestions from '../imaging/TargetSuggestions.svelte';

  const app = useApp();

  const values = $derived(app.configValues);
  const host = $derived(typeof values?.['stellarium.host'] === 'string' ? (values['stellarium.host'] as string) : '127.0.0.1');
  const port = $derived(typeof values?.['stellarium.port'] === 'number' ? (values['stellarium.port'] as number) : 10001);
  const lookup = $derived(values?.['stellarium.online_target_lookup'] === true);
  const lookupHelp = $derived(
    app.configMeta?.['stellarium.online_target_lookup']?.help ??
      'When no local catalogue match exists, send the GoTo coordinates to CDS/SIMBAD to suggest a target name. ARGOS always asks before changing FITS metadata.',
  );

  const bridge = $derived(app.events.stellarium);
  const running = $derived(!!bridge?.running);
  const badge = $derived.by(() => {
    if (app.stale) return { tone: 'idle' as const, label: 'No link' };
    if (running) return { tone: 'ok' as const, label: `Listening · ${bridge?.port}` };
    if (bridge?.error) return { tone: 'error' as const, label: 'Error' };
    return { tone: 'idle' as const, label: 'Stopped' };
  });
  const editReason = $derived(
    !app.linkOpen
      ? 'the ARGOS server is not reachable'
      : !values
        ? 'loading the settings'
        : running
          ? 'stop the bridge to change its port'
          : null,
  );
  const bridgeReason = $derived(!app.linkOpen ? 'the ARGOS server is not reachable' : !bridge ? 'waiting for the server' : null);
  const lastGoto = $derived(bridge?.last_goto ?? null);
  const OUTCOMES: Record<string, string> = { slewing: 'mount slewing' };

  let portError: string | null = $state(null);
  let helpOpen = $state(loadPref('argos.connection.stellarium-help', isBoolean, false));

  async function commitPort(v: number): Promise<void> {
    const r = await app.commitConfig({ 'stellarium.port': v });
    portError = r.ok ? null : (r.fields?.['stellarium.port'] ?? r.message ?? 'Refused by the server');
  }

  function toggleHelp(): void {
    helpOpen = !helpOpen;
    savePref('argos.connection.stellarium-help', helpOpen);
  }
</script>

<Card title="Planetarium · Stellarium" icon="planetarium" dense>
  {#snippet status()}
    <StatusBadge tone={badge.tone} label={badge.label} />
  {/snippet}

  <div class="row">
    <span class="key">Host</span>
    <span class="num value">{host}</span>
    <span class="key port-key" aria-hidden="true">Port</span>
    <div class="port">
      <NumberField
        label="Stellarium bridge port"
        hideLabel
        lazy
        integer
        group={false}
        min={1024}
        max={65535}
        value={port}
        disabled={!!editReason}
        onchange={(v) => void commitPort(v)}
      />
    </div>
    <span class="spacer"></span>
    {#if running}
      <IconButton
        icon="stop"
        label="Stop bridge"
        tooltipText="Close the Stellarium bridge and disconnect Stellarium"
        showLabel
        size="s"
        variant="secondary"
        glyphTone="danger"
        tooltip="left"
        busy={!!app.busy.stellarium}
        disabledReason={bridgeReason}
        onclick={() => void app.stopStellarium()}
      />
    {:else}
      <IconButton
        icon="planetarium"
        label="Start bridge"
        tooltipText={`Listen on ${host}:${port} for Stellarium's Telescope Control: a GoTo there slews the mount`}
        showLabel
        size="s"
        variant="secondary"
        tooltip="left"
        busy={!!app.busy.stellarium}
        disabledReason={bridgeReason}
        onclick={() => void app.startStellarium()}
      />
    {/if}
  </div>
  {#if portError}<p class="field-error" role="alert">{portError}</p>{/if}
  {#if bridge?.error && !running}
    <p class="bridge-error" role="alert"><span class="x" aria-hidden="true"></span>Stellarium: {bridge.error}</p>
  {/if}
  {#if running}
    <div class="facts" class:stale={app.stale}>
      <span class="key">Clients</span>
      <span class="num value">{bridge?.clients ?? 0}</span>
      <span class="key goto-key">Last GoTo</span>
      {#if lastGoto}
        <span class="num value goto">
          {formatRA(lastGoto.ra_hours)} {formatDec(lastGoto.dec_deg)} · {utcClock(lastGoto.t)} UTC
        </span>
        <span class="outcome" class:problem={lastGoto.outcome !== 'slewing'}>{OUTCOMES[lastGoto.outcome] ?? lastGoto.outcome}</span>
      {:else}
        <span class="muted">none yet</span>
      {/if}
    </div>
  {/if}
  {#if app.suggestions}
    <!-- Wave 3 (A20): names near the GoTo, offered; nothing changes until one is chosen. -->
    <TargetSuggestions
      suggestion={app.suggestions}
      current={app.observation?.object_name ?? ''}
      busy={!!app.busy.target}
      onuse={(c) => void app.useSuggestion(c)}
      ondismiss={() => app.dismissSuggestion()}
    />
  {/if}

  <Checkbox
    label="Look up target names online after a GoTo"
    detail={lookupHelp}
    checked={lookup}
    disabledReason={!app.linkOpen ? 'the ARGOS server is not reachable' : !values ? 'loading the settings' : null}
    size="s"
    onchange={(on) => void app.commitConfig({ 'stellarium.online_target_lookup': on })}
  />

  <div class="help">
    <button type="button" class="disclosure" aria-expanded={helpOpen} onclick={toggleHelp}>
      <span class="chev" class:open={helpOpen}><Icon name="disclosure" size="s" /></span>
      How to connect Stellarium
    </button>
    {#if helpOpen}
      <p>
        In Stellarium: Telescope Control plugin → add a telescope “External software or remote computer
        (TCP)” on host <span class="num">{host}</span>, port <span class="num">{port}</span>, then select an
        object and press Ctrl+1 (⌘+1) to slew. A cached target name is suggested locally; online lookup is
        optional.
      </p>
    {/if}
  </div>
</Card>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-width: 0;
    font-size: var(--text-s);
  }
  .key {
    color: var(--text-muted);
  }
  .value {
    color: var(--fg);
  }
  .port-key {
    margin-left: var(--space-3);
  }
  .port {
    width: 84px;
    flex: none;
  }
  /* A range message stays on one line under the narrow field. */
  .port :global(.help) {
    white-space: nowrap;
  }
  .spacer {
    flex: 1;
  }

  .field-error {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-xs);
  }

  .bridge-error {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
    overflow-wrap: anywhere;
  }
  /* The error mark: a cross (shape, not colour alone). */
  .x {
    position: relative;
    flex: none;
    width: 10px;
    height: 10px;
  }
  .x::before,
  .x::after {
    content: '';
    position: absolute;
    left: 4px;
    top: -1px;
    bottom: -1px;
    width: 2px;
    border-radius: 1px;
    background: var(--danger);
    transform: rotate(45deg);
  }
  .x::after {
    transform: rotate(-45deg);
  }

  .facts {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    min-width: 0;
    font-size: var(--text-s);
    white-space: nowrap;
  }
  .goto-key {
    margin-left: var(--space-4);
  }
  .goto {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .outcome {
    color: var(--text-muted);
  }
  .outcome.problem {
    color: var(--fg);
  }
  .muted,
  .stale .value {
    color: var(--text-muted);
  }

  .help p {
    margin: var(--space-1) 0 0 22px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-relaxed);
  }
  .disclosure {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 24px;
    margin-left: calc(-1 * var(--space-1));
    padding: 0 var(--space-1);
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-s);
    cursor: pointer;
  }
  .disclosure:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .disclosure:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .chev {
    display: inline-flex;
    transform: rotate(-90deg);
    transition: transform var(--duration-fast) var(--ease-standard);
  }
  .chev.open {
    transform: none;
  }
</style>
