<!--
  Mount: live position (RA / Dec / Alt / Az in Plex Mono, tabular figures,
  formats of BRAND section 5), state, tracking, GoTo, park / unpark, stop.

  - GoTo accepts sexagesimal or decimal input (lib/format/astro.ts) and shows
    the parsed value before the slew, so a typo never moves the telescope.
  - Park asks for confirmation inline (it physically closes the Seestar arm),
    as the Qt dock does with a dialog.
  - Coordinates are ICRS/J2000, as everywhere in ARGOS.
  - The state and position are also in the status bar (this card can sit
    below the fold). With the server link down the readouts are the last
    known ones: greyed, and every command is refused.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { formatDec, formatDegrees, formatRA, parseDec, parseRA, separationDeg } from '../format/astro';
  import { fixed, signed } from '../format/number';
  import { useApp } from '../app/state.svelte';
  import { mountStatus } from '../app/status';
  import Card from '../components/Card.svelte';
  import IconButton from '../components/IconButton.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import TextField from '../components/TextField.svelte';

  const app = useApp();

  // The mount's own device record decides: with the camera alone the v1
  // connection reads "connected" while the mount record is a placeholder.
  const badge = $derived(mountStatus(app.mount, app.mountReady, app.stale));
  const m = $derived(app.mountReady ? app.mount : null);
  const parked = $derived(m?.state === 'parked');
  /** Why mount commands are refused right now, or null. */
  const offline = $derived(
    app.stale ? 'the ARGOS server is not reachable' : !m ? 'the mount is not connected' : null,
  );

  let raText = $state('');
  let decText = $state('');
  let touched = $state(false);
  let confirmPark = $state(false);

  const ra = $derived(raText.trim() ? parseRA(raText) : null);
  const dec = $derived(decText.trim() ? parseDec(decText) : null);
  const target = $derived(
    ra?.ok && dec?.ok ? { ra: ra.value, dec: dec.value } : null,
  );

  const toTarget = $derived(
    m && m.target ? separationDeg(m.ra_hours, m.dec_deg, m.target.ra_hours, m.target.dec_deg) : null,
  );

  /**
   * Slew is the deliberate action (brass) only while the typed target is a
   * new one: farther than the "on target" tolerance (0.01°) from where the
   * mount points. Otherwise it stays secondary (design review: a filled brass
   * Slew next to "on target" was the largest brass area of Observe).
   */
  const newTarget = $derived(
    !!target && (!m || separationDeg(m.ra_hours, m.dec_deg, target.ra, target.dec) >= 0.01),
  );

  const gotoReason = $derived.by(() => {
    if (app.stale) return 'the ARGOS server is not reachable';
    if (!app.mountReady) return 'connect the mount first';
    if (parked) return 'unpark the mount first';
    if (!target) return 'enter a valid RA and Dec';
    return null;
  });

  function submit(e: SubmitEvent): void {
    e.preventDefault();
    touched = true;
    if (gotoReason || !target) return;
    void app.goto(target.ra, target.dec);
  }

  // A GoTo commanded elsewhere (another client, a script) fills an empty form,
  // so the observer sees what the mount was sent to.
  let lastTarget = '';
  $effect(() => {
    const t = m?.target;
    const key = t ? `${t.ra_hours},${t.dec_deg}` : '';
    if (key === lastTarget) return;
    lastTarget = key;
    if (!t) return;
    untrack(() => {
      if (!raText.trim() && !decText.trim()) {
        raText = formatRA(t.ra_hours);
        decText = formatDec(t.dec_deg);
      }
    });
  });

  /** Fill the form with the current pointing (handy to nudge a target). */
  function useCurrent(): void {
    if (!m) return;
    raText = formatRA(m.ra_hours);
    decText = formatDec(m.dec_deg);
  }

  function park(): void {
    confirmPark = false;
    void app.park();
  }
</script>

<Card title="Mount" icon="mount" collapsible persist="mount">
  {#snippet status()}
    <StatusBadge tone={badge.tone} label={badge.label} />
  {/snippet}
  {#snippet summary()}
    {#if m}Alt {formatDegrees(m.alt_deg)} · Az {formatDegrees(m.az_deg)}{/if}
  {/snippet}

  <div class="readouts" class:offline={!m || app.stale}>
    <div class="readout">
      <span class="micro">RA</span>
      <span class="value num">{m ? formatRA(m.ra_hours) : '—'}</span>
    </div>
    <div class="readout">
      <span class="micro">Dec</span>
      <span class="value num">{m ? formatDec(m.dec_deg) : '—'}</span>
    </div>
    <div class="readout">
      <span class="micro">Alt</span>
      <span class="value num">{m ? formatDegrees(m.alt_deg) : '—'}</span>
    </div>
    <div class="readout">
      <span class="micro">Az</span>
      <span class="value num">{m ? formatDegrees(m.az_deg) : '—'}</span>
    </div>
  </div>

  <p class="target" class:none={!m?.target}>
    <span class="micro">Target</span>
    {#if m?.target}
      <span class="num">{formatRA(m.target.ra_hours)}</span>
      <span class="num">{formatDec(m.target.dec_deg)}</span>
      {#if toTarget !== null}
        <span class="away num">{toTarget < 0.01 ? 'on target' : `${formatDegrees(toTarget)} away`}</span>
      {/if}
    {:else}
      <span class="num">—</span>
    {/if}
  </p>

  <div class="row">
    <IconButton
      icon="tracking"
      label="Tracking"
      showLabel
      size="s"
      pressed={!!m?.tracking}
      busy={!!app.busy.tracking}
      disabledReason={offline ?? (parked ? 'the mount is parked' : null)}
      tooltipText={m?.tracking ? 'Stop sidereal tracking' : 'Start sidereal tracking'}
      tooltip="top"
      onclick={() => app.setTracking(!m?.tracking)}
    />
    <span class="spacer"></span>
    {#if confirmPark}
      <span class="confirm" role="group" aria-label="Confirm park">
        <span class="question">Park the mount?</span>
        <button type="button" class="text-btn strong" onclick={park}>Park</button>
        <button type="button" class="text-btn" onclick={() => (confirmPark = false)}>Cancel</button>
      </span>
    {:else if parked}
      <IconButton
        icon="unpark"
        label="Unpark"
        showLabel
        size="s"
        busy={!!app.busy.unpark}
        disabledReason={offline}
        onclick={() => app.unpark()}
      />
    {:else}
      <IconButton
        icon="park"
        label="Park"
        showLabel
        size="s"
        busy={!!app.busy.park}
        disabledReason={offline}
        tooltipText="Park: closes the Seestar arm and stops tracking"
        tooltip="top"
        onclick={() => (confirmPark = true)}
      />
    {/if}
  </div>

  <form class="goto" onsubmit={submit} novalidate>
    <div class="goto-fields">
      <TextField
        label="Target RA"
        bind:value={raText}
        mono
        placeholder="05h 35m 17.3s"
        error={touched || raText ? (ra && !ra.ok ? ra.error : null) : null}
        hint={ra?.ok ? `= ${fixed(ra.value, 5)} h` : 'h m s, or decimal hours'}
      />
      <TextField
        label="Target Dec"
        bind:value={decText}
        mono
        placeholder="−05° 23′ 28″"
        error={touched || decText ? (dec && !dec.ok ? dec.error : null) : null}
        hint={dec?.ok ? `= ${signed(dec.value, 5)}°` : '° ′ ″, or decimal degrees'}
      />
    </div>
    <div class="row">
      <IconButton
        type="submit"
        icon="goto"
        label="Slew"
        showLabel
        size="s"
        variant={newTarget && !gotoReason ? 'primary' : 'secondary'}
        busy={!!app.busy.goto}
        disabledReason={gotoReason}
        tooltipText="Slew to the target (J2000)"
        tooltip="top"
      />
      <IconButton
        icon="abort"
        label="Abort"
        showLabel
        size="s"
        variant={app.slewing ? 'danger' : 'secondary'}
        shortcut="Escape"
        busy={!!app.busy.mountStop}
        disabledReason={offline ?? (app.slewing ? null : 'the mount is not moving')}
        tooltipText="Abort the slew"
        tooltip="top"
        onclick={() => app.stopMount()}
      />
      <span class="spacer"></span>
      <button type="button" class="text-btn" disabled={!m || app.stale} onclick={useCurrent}>Use current</button>
    </div>
  </form>
</Card>

<style>
  .readouts {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3) var(--space-4);
    padding: var(--space-3) var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }

  .readout {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .micro {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }

  .value {
    color: var(--fg);
    font-size: var(--readout); /* 17 px; 20 px in Comfortable density (owner D7) */
    font-weight: var(--weight-medium);
    line-height: var(--leading-tight);
    white-space: nowrap;
  }
  .offline .value {
    color: var(--text-muted);
  }

  .target {
    display: flex;
    align-items: baseline;
    gap: var(--space-3);
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
    white-space: nowrap;
  }
  .target .micro {
    min-width: 52px;
  }
  .target.none .num {
    color: var(--text-muted);
  }
  .away {
    margin-left: auto;
    color: var(--text-muted);
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .spacer {
    flex: 1;
  }

  .goto {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding-top: var(--space-4);
    border-top: var(--border-w) solid var(--border-soft);
  }

  .goto-fields {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
  }

  .confirm {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .question {
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
  }

  /* Text-only buttons: confirmations and minor helpers (BRAND section 7). */
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
  .text-btn:hover:not(:disabled) {
    background: var(--hover-bg);
  }
  .text-btn.strong {
    border-color: var(--primary-border);
    background: var(--primary-bg);
    color: var(--primary-fg);
  }
  .text-btn.strong:hover {
    background: var(--primary-bg-hover);
    color: var(--primary-fg-hover);
  }
  .text-btn:disabled {
    border-color: var(--border-soft);
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
</style>
