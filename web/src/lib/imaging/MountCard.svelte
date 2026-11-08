<!--
  Mount (spec 05 §2.3 C, mapping M60, M61, M66; README D11, D21, D23; owner
  D4): live position (RA / Dec / Alt / Az in Plex Mono, BRAND 5 formats),
  geometry, tracking and its rate, Park by hold, the Target block (object
  name merged with the catalogue search, GoTo), the Stellarium name
  suggestion, and the Jog section.

  - Geometry (A29): the mount's AlignmentMode names the jog keys (axis words
    on alt-az, compass letters on EQ, Q-O4); the status bar shows it (Alt-Az /
    EQ), so the card does not repeat it.
  - Tracking (icon + label, never a single key) with its rate (A31):
    Sidereal / Lunar / Solar / King as the driver lists them, read back after
    a change (H6); hidden when the driver lists only one.
  - Park = 700 ms hold with the ring (owner D4); Enter / Space open the inline
    confirmation with the focus on Cancel. Unpark is a plain button.
  - Target block: Object (ObjectSearch: offline names while typing, Enter
    resolves); a result fills Target RA / Dec and Slew sends it WITH its name
    (Qt P16): the observation's name and target are set (A39) before the
    GoTo. "Set as target" does it without slewing. A name the catalogues do
    not know can still be the object name ("Use as object name"). Typed
    coordinates (sexagesimal or decimal) still work, the parsed value shown.
  - GoTo is refused with the server's reason while the mount clock is off
    (H4, `goto_blocked`), while parked, and while a slew runs (Abort, Esc).
  - Jog section (disclosure, per viewer): the pad with the server dead-man
    (A30). J arms the arrow keys from anywhere in Observe (D23); folding the
    section disarms and stops every axis.
  With the server link down the readouts are the last known ones, greyed,
  and every command is refused.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import type { Resolved, TrackingRate } from '../api/types';
  import { formatDec, formatDegrees, formatRA, parseDec, parseRA, separationDeg } from '../format/astro';
  import { fixed, signed } from '../format/number';
  import { useApp } from '../app/state.svelte';
  import { mountStatus } from '../app/status';
  import Card from '../components/Card.svelte';
  import Control from '../components/Control.svelte';
  import HoldButton from '../components/HoldButton.svelte';
  import Icon from '../components/Icon.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Segmented from '../components/Segmented.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import TextField from '../components/TextField.svelte';
  import { refusalText } from '../components/commit.svelte';
  import JogPad from './instruments/JogPad.svelte';
  import type { JogRate } from './instruments/jog';
  import ObjectSearch from './ObjectSearch.svelte';
  import TargetSuggestions from './TargetSuggestions.svelte';

  interface Props {
    /** Folded or open: the Observe mode owns it (imaging/modes); without a binding the card remembers its own. */
    open?: boolean;
  }

  let { open = $bindable() }: Props = $props();
  const app = useApp();

  // The mount's own device record decides: with the camera alone the v1
  // connection reads "connected" while the mount record is a placeholder.
  const badge = $derived(mountStatus(app.mount, app.mountReady, app.stale));
  const m = $derived(app.mountReady ? app.mount : null);
  const parked = $derived(m?.state === 'parked');
  /** Why mount commands are refused right now, or null. */
  const offline = $derived(app.stale ? 'the ARGOS server is not reachable' : !m ? 'the mount is not connected' : null);


  // -- Tracking rate (A31) ---------------------------------------------------------------
  const RATE_LABEL: Record<string, string> = { sidereal: 'Sidereal', lunar: 'Lunar', solar: 'Solar', king: 'King' };
  const rates = $derived((m?.tracking_rates ?? []).filter((r) => r in RATE_LABEL));
  const rateOptions = $derived(rates.map((r) => ({ value: r, label: RATE_LABEL[r] })));
  const rateReason = $derived(offline ?? (parked ? 'unpark the mount first' : null));

  // -- Target block --------------------------------------------------------------------------
  let raText = $state('');
  let decText = $state('');
  let touched = $state(false);
  /** The catalogue answer the GoTo fields hold, until they are edited by hand. */
  let resolved = $state.raw<Resolved | null>(null);
  /** A name the catalogues do not know, offered as a plain object name. */
  let unknownName: string | null = $state(null);
  let targetError: string | null = $state(null);
  let settingTarget = $state(false);
  let search: ObjectSearch | undefined = $state();

  const observation = $derived(app.observation);
  const objectName = $derived(observation?.object_name ?? '');
  const ra = $derived(raText.trim() ? parseRA(raText) : null);
  const dec = $derived(decText.trim() ? parseDec(decText) : null);
  const target = $derived(ra?.ok && dec?.ok ? { ra: ra.value, dec: dec.value } : null);
  /** The fields still hold the catalogue position (not edited since). */
  const fromCatalogue = $derived(
    !!resolved && !!target && Math.abs(target.ra - resolved.ra_hours) < 1e-4 && Math.abs(target.dec - resolved.dec_deg) < 1e-3,
  );

  const toTarget = $derived(m && m.target ? separationDeg(m.ra_hours, m.dec_deg, m.target.ra_hours, m.target.dec_deg) : null);

  /**
   * Slew is the deliberate action (brass) only while the observer has typed or
   * chosen a new target: the fields differ (beyond 0.01°) from the server's
   * target. Being away from the target (after a jog) is said in words, never
   * by a brass fill inviting a slew back; while the jog is armed, Slew stays
   * secondary (design review of wave 3).
   */
  const newTarget = $derived(
    !!target &&
      !app.jogArmed &&
      (!m?.target || separationDeg(m.target.ra_hours, m.target.dec_deg, target.ra, target.dec) >= 0.01),
  );

  const gotoReason = $derived.by(() => {
    if (app.stale) return 'the ARGOS server is not reachable';
    if (!app.mountReady) return 'connect the mount first';
    if (m?.goto_blocked) return m.goto_blocked.message;
    if (parked) return 'unpark the mount first';
    if (app.slewing) return 'the mount is slewing (Abort or Esc first)';
    if (!target) return 'enter a valid RA and Dec, or look up an object';
    return null;
  });
  const lockReason = $derived(observation?.locked ? (observation.locked_reason ?? 'a sequence runs') : null);

  function onResolved(r: Resolved): void {
    resolved = r;
    unknownName = null;
    targetError = null;
    raText = formatRA(r.ra_hours);
    decText = formatDec(r.dec_deg);
    touched = false;
  }

  async function setAsTarget(r: Resolved): Promise<boolean> {
    settingTarget = true;
    targetError = null;
    try {
      await app.setTarget({ name: r.name, ra_hours: r.ra_hours, dec_deg: r.dec_deg, object_type: r.object_type, source: r.source });
      search?.settle();
      return true;
    } catch (err) {
      targetError = refusalText(err);
      return false;
    } finally {
      settingTarget = false;
    }
  }

  async function useAsName(name: string): Promise<void> {
    settingTarget = true;
    targetError = null;
    try {
      await app.setObjectName(name);
      unknownName = null;
      search?.settle();
    } catch (err) {
      targetError = refusalText(err);
    } finally {
      settingTarget = false;
    }
  }

  /** The catalogue object, when the fields hold its position and it is not the target yet. */
  const pendingName = $derived(
    fromCatalogue && resolved && (observation?.target?.name !== resolved.name || objectName !== resolved.name) ? resolved : null,
  );

  async function submit(e: SubmitEvent): Promise<void> {
    e.preventDefault();
    touched = true;
    if (gotoReason || !target) return;
    // Slew sends the catalogue object WITH its name (D11, Qt P16).
    if (pendingName && !(await setAsTarget(pendingName))) return;
    void app.goto(target.ra, target.dec);
  }

  // A GoTo commanded elsewhere (another client, Stellarium) fills an empty form.
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
    resolved = null;
  }

  // -- Jog (A30, D23) ------------------------------------------------------------------------
  let jogRate: JogRate = $state(
    (() => {
      try {
        const v = localStorage.getItem('argos.mount.jog-rate');
        return v === '"slow"' || v === '"fast"' ? (JSON.parse(v) as JogRate) : 'normal';
      } catch {
        return 'normal';
      }
    })(),
  );
  $effect(() => {
    const r = jogRate;
    try {
      localStorage.setItem('argos.mount.jog-rate', JSON.stringify(r));
    } catch {
      // per-viewer convenience only
    }
  });
  const jogReason = $derived(app.jogProblem());
</script>

<Card title="Mount" icon="mount" collapsible bind:open={() => open ?? true, (v) => (open = v)} persist={open === undefined ? 'mount' : undefined}>
  {#snippet status()}
    <StatusBadge tone={badge.tone} label={badge.label} />
  {/snippet}
  {#snippet summary()}
    {#if m}Alt {formatDegrees(m.alt_deg)} · Az {formatDegrees(m.az_deg)}{#if objectName} · {objectName}{/if}{/if}
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
      layoutToggle
      busy={!!app.busy.tracking}
      disabledReason={offline ?? (parked ? 'the mount is parked' : null)}
      tooltipText={m?.tracking ? `Stop ${(m.tracking_rate ?? 'sidereal')} tracking` : `Start ${(m?.tracking_rate ?? 'sidereal')} tracking`}
      tooltip="top"
      onclick={() => app.setTracking(!m?.tracking)}
    />
    {#if rateOptions.length > 1}
      <Segmented
        label="Tracking rate"
        size="s"
        options={rateOptions}
        value={m?.tracking_rate ?? 'sidereal'}
        deferred
        busyValue={app.busy.trackingRate ? (m?.tracking_rate ?? null) : null}
        disabledReason={rateReason}
        onchange={(r) => app.setTrackingRate(r as TrackingRate)}
      />
    {/if}
  </div>
  {#if parked}
    <div class="park">
      <IconButton icon="unpark" label="Unpark" showLabel size="s" busy={!!app.busy.unpark} disabledReason={offline} onclick={() => app.unpark()} />
    </div>
  {:else}
    <div class="park">
      <HoldButton
        icon="park"
        label="Park"
        size="m"
        verb="park"
        confirmTitle="Park the mount?"
        confirmBody="Parking physically closes the Seestar arm and stops tracking."
        busyLabel="Parking…"
        doneLabel="Parked"
        disabledReason={offline ?? (app.slewing ? 'the mount is slewing (Esc aborts)' : null)}
        onconfirm={() => app.park()}
      />
    </div>
  {/if}

  <form class="goto" onsubmit={submit} novalidate>
    <ObjectSearch
      bind:this={search}
      current={objectName}
      suggest={(q, signal) => app.suggestNames(q, signal)}
      resolve={(q, signal) => app.resolveName(q, signal)}
      onresolved={onResolved}
      onnotfound={(typed) => (unknownName = typed)}
      ontyping={() => (unknownName = null)}
      disabledReason={app.stale ? 'the ARGOS server is not reachable' : lockReason}
    />
    {#if resolved && fromCatalogue}
      <div class="result">
        <span class="res-text">
          <span class="res-name">{resolved.name}</span>
          <span class="muted">· {resolved.type_label || resolved.object_type || 'object'}{resolved.is_variable ? ' · variable' : ''} · {resolved.source}</span>
        </span>
        {#if observation?.target?.name === resolved.name && objectName === resolved.name}
          <span class="muted in-use">the target</span>
        {:else}
          <Control
            icon="labels"
            label="Set as target"
            showLabel
            size="s"
            variant="ghost"
            busy={settingTarget}
            tooltipText="Object name and target, without slewing{resolved.is_variable ? ' (and the photometry target: a variable star)' : ''}"
            disabledReason={app.stale ? 'the ARGOS server is not reachable' : lockReason}
            onclick={() => resolved && void setAsTarget(resolved)}
          />
        {/if}
      </div>
    {:else if unknownName}
      <div class="result">
        <span class="res-text muted">Not in the catalogues: “{unknownName}” can still name the frames.</span>
        <Control label="Use as object name" size="s" variant="ghost" busy={settingTarget} onclick={() => unknownName && void useAsName(unknownName)} />
      </div>
    {/if}
    {#if targetError}<p class="error">{targetError}</p>{/if}

    {#if app.suggestions}
      <TargetSuggestions
        suggestion={app.suggestions}
        current={objectName}
        busy={!!app.busy.target}
        onuse={(c) => void app.useSuggestion(c)}
        ondismiss={() => app.dismissSuggestion()}
      />
    {/if}

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
        busy={!!app.busy.goto || settingTarget}
        disabledReason={gotoReason}
        tooltipText={pendingName ? `Slew to ${pendingName.name} (sets it as the object name and target)` : 'Slew to the target (J2000)'}
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
    {#if m?.goto_blocked}
      <p class="error"><Icon name="attention" size={14} />{m.goto_blocked.message}</p>
    {/if}
  </form>

  <div class="jog">
    <button type="button" class="disclosure" aria-expanded={app.jogOpen} onclick={() => app.setJogOpen(!app.jogOpen)}>
      <span class="chev" class:open={app.jogOpen}><Icon name="disclosure" size="s" /></span>
      <span class="micro">Jog</span>
      <span class="sum">{app.jogArmed ? 'arrow keys armed' : app.jogOpen ? '' : 'hold to move · J arms the arrow keys'}</span>
    </button>
    {#if app.jogOpen}
      <JogPad
        alignment={m?.alignment ?? 'altaz'}
        report={m?.jog ?? null}
        transport={app.jogTransport}
        linked={app.linkOpen}
        blockedReason={jogReason}
        pointing={m ? { alt_deg: m.alt_deg, az_deg: m.az_deg, ra_hours: m.ra_hours, dec_deg: m.dec_deg } : null}
        bind:rate={jogRate}
        bind:armed={app.jogArmed}
      />
    {/if}
  </div>
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
    color: var(--text-muted);
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .spacer {
    flex: 1;
  }
  .park {
    display: flex;
    justify-content: flex-start;
    margin-top: calc(-1 * var(--space-1));
  }

  .goto {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding-top: var(--space-3);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .goto-fields {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
  }
  .result {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-top: calc(-1 * var(--space-2));
    min-width: 0;
    font-size: var(--text-s);
  }
  .res-text {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .res-name {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .muted {
    color: var(--text-muted);
  }
  .in-use {
    font-size: var(--text-xs);
  }
  .error {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    margin: 0;
    color: var(--fg);
    font-size: var(--text-xs);
    line-height: var(--leading-relaxed);
  }
  .error :global(svg) {
    flex: none;
    color: var(--warning);
  }

  .jog {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .disclosure {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    height: var(--control-h-s);
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--fg);
    cursor: pointer;
    text-align: left;
  }
  .disclosure:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }
  /* The disclosure glyph points down; folded, it points right (as the other disclosures). */
  .chev {
    display: inline-flex;
    color: var(--text-muted);
    transform: rotate(-90deg);
    transition: transform var(--duration-fast) var(--ease-standard);
  }
  .chev.open {
    transform: none;
  }
  .sum {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }

  /* Text-only buttons: minor helpers (BRAND section 7). */
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
  .text-btn:disabled {
    border-color: var(--border-soft);
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
</style>
