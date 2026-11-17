<!--
  Camera (spec 05 §2.3 B, mapping M59; README D10, D11, D18): the capture
  settings, which the server holds for every client (Q-O13) and the next
  frame uses in any mode (A22). The actions are in the toolbar: Take shot
  (E, a split button with the frame type and exposure written on it), Live
  (V), Stop; this card holds what they use.

  - Exposure and Gain: one PUT /api/camera/settings per commit (Enter, blur,
    a pause after the arrows), within the DRIVER's limits once connected
    (A21), never clamped: a refusal stays under the field in the server's
    words (README 3.4). While a frame exposes, a change applies from the next
    one; "Next frame: 2.0 s (now 1.0 s)" says so, with a button to drop it.
  - Frame: Light / Dark / Flat / Bias. Dark and Bias need the opaque Dark
    slot (the Seestar has no shutter, S1): the server turns the wheel to Dark
    first and refuses while the wheel is turning elsewhere; the line under
    the control says it before the shot, and while the shot waits.
  - Filter: the wheel's slots (FilterWheelControl: manual activation, the
    requested slot spins, a refusal shows where the wheel really is, H9);
    without a wheel the choice is FITS metadata only (Q-O5).
  - Sensor (disclosure, per viewer): Offset and Binning when the driver has
    them (read back from the driver). Preview quality is not here: the
    stream decimation of Q-O14 replaces it, and the metrics are always
    measured on the full frame (A26).
  - Facts: sensor temperature (10 s), the settings of the frame in progress
    or of the last one, the sensor geometry. HFD and stars live in the
    status bar and the task band (D18, one home per value).
  - While autofocus or a sequence owns the camera the fields are read-only
    with that reason (05 P39).
  The body carries data-capture-settings: a value still typed there is
  committed before an exposure starts (H11, app.flushSettings).
-->
<script lang="ts">
  import type { FrameType } from '../api/types';
  import { isBoolean, loadPref, savePref } from '../app/prefs';
  import { useApp } from '../app/state.svelte';
  import { cameraStatus } from '../app/status';
  import Card from '../components/Card.svelte';
  import Icon from '../components/Icon.svelte';
  import IconButton from '../components/IconButton.svelte';
  import NumberField from '../components/NumberField.svelte';
  import Segmented from '../components/Segmented.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { EXPOSURE_LADDER } from '../components/values';
  import { fixed, int, seconds } from '../format/number';
  import { frameNote as noteFor, ownerReason } from './capture';
  import FilterWheelControl from './instruments/FilterWheelControl.svelte';

  interface Props {
    /** Folded or open: the Observe mode owns it (imaging/modes); without a binding the card remembers its own. */
    open?: boolean;
  }

  let { open = $bindable() }: Props = $props();
  const app = useApp();

  const badge = $derived(cameraStatus(app.camera, app.cameraReady, app.stale));
  const cam = $derived(app.cameraReady ? app.camera : null);
  const sensor = $derived(cam?.sensor ?? null);
  const settings = $derived(app.settings);
  const lim = $derived(app.captureLimits);

  const FRAME_TYPES: { value: FrameType; label: string }[] = [
    { value: 'light', label: 'Light' },
    { value: 'dark', label: 'Dark' },
    { value: 'flat', label: 'Flat' },
    { value: 'bias', label: 'Bias' },
  ];
  const TYPE_WORD: Record<string, string> = { light: 'Light', dark: 'Dark', flat: 'Flat', bias: 'Bias' };

  /** Autofocus or a sequence owns the camera: the settings cannot change now. */
  const ownedReason = $derived(app.stale ? 'the ARGOS server is not reachable' : ownerReason(app.cameraOwner));
  const sensorReason = $derived(ownedReason ?? (app.cameraReady ? null : 'connect the camera first'));

  let sensorOpen = $state(loadPref('argos.camera.sensor-open', isBoolean, false));
  function toggleSensor(): void {
    sensorOpen = !sensorOpen;
    savePref('argos.camera.sensor-open', sensorOpen);
  }

  /** A change waiting for the next frame, in words ("2.0 s (now 1.0 s)"). */
  const pending = $derived.by(() => {
    if (!app.livePending || !cam) return null;
    const cur = cam.current ?? cam;
    const parts: string[] = [];
    if (Math.abs(cur.exposure_s - app.exposure) > 1e-9) parts.push(`${seconds(app.exposure)} (now ${seconds(cur.exposure_s)})`);
    if (cur.gain !== Math.round(app.gain)) parts.push(`gain ${int(app.gain)} (now ${int(cur.gain)})`);
    return parts.join(', ');
  });

  // -- Frame type and the Dark slot (S1) ---------------------------------------------------
  const frameType = $derived<FrameType>(settings?.frame_type ?? 'light');
  const wheel = $derived(app.filterwheel);
  /** What a Dark / Bias Take shot will do, said before the shot (and while it waits). */
  const frameNote = $derived(noteFor(frameType, wheel, cam?.waiting_for === 'filterwheel'));

  function chooseType(t: FrameType): void {
    void app.setFrameType(t);
  }

  // -- Sensor: offset and binning, read back from the driver --------------------------------
  const offsetRange = $derived(cam?.offset ?? null);
  const binMax = $derived(cam?.binning?.max ?? 1);
  const binOptions = $derived(
    Array.from({ length: Math.max(1, binMax) }, (_, i) => ({
      value: String(i + 1),
      label: `${i + 1}×`,
      disabledReason: i > 0 ? 'Take shot is refused binned: the FITS header would say 1×1 (fits_writer)' : null,
    })),
  );
  const sensorSummary = $derived.by(() => {
    const parts: string[] = [];
    if (offsetRange && settings?.offset !== null && settings?.offset !== undefined) parts.push(`offset ${int(settings.offset)}`);
    if (cam?.binning) parts.push(`bin ${settings?.binning ?? 1}×`);
    return parts.length ? parts.join(' · ') : cam ? 'no offset or binning on this driver' : '—';
  });

  /** "Light · 2.0 s · gain 80 · IR" of the frame being exposed (or the settings at rest). */
  const inUse = $derived.by(() => {
    if (!cam) return '—';
    const c = cam.current;
    if (c) return `${TYPE_WORD[c.frame_type] ?? c.frame_type} · ${seconds(c.exposure_s)} · gain ${int(c.gain)} · filter ${c.filter}`;
    const s = settings;
    // While the wheel turns, the next frame goes through the slot asked for.
    const turning = wheel?.state === 'moving' && wheel.target ? `filter ${wheel.target} (turning)` : null;
    return s
      ? `${TYPE_WORD[s.frame_type]} · ${seconds(s.exposure_s)} · gain ${int(s.gain)} · ${turning ?? `filter ${s.filter}`}`
      : `${seconds(cam.exposure_s)}, gain ${int(cam.gain)}`;
  });
  const temp = $derived(cam?.temperature_c ?? null);
</script>

<Card title="Camera" icon="camera" collapsible bind:open={() => open ?? true, (v) => (open = v)} persist={open === undefined ? 'camera' : undefined}>
  {#snippet status()}
    <StatusBadge tone={badge.tone} label={badge.label} />
  {/snippet}
  {#snippet summary()}
    {#if settings}{TYPE_WORD[settings.frame_type]} · {seconds(settings.exposure_s)} · gain {int(settings.gain)} · {settings.filter}{:else if cam}{seconds(cam.exposure_s)} · gain {int(cam.gain)}{/if}
  {/snippet}

  <div class="body" data-capture-settings>
    {#if ownedReason && !app.stale}
      <!-- One line for the card, not one per field (05 P39): the settings wait for the owner. -->
      <p class="owned" role="status"><span class="dot" aria-hidden="true"></span>{ownedReason[0].toUpperCase()}{ownedReason.slice(1)}: the settings apply after it.</p>
    {/if}
    <div class="fields">
      <NumberField
        label="Exposure"
        value={app.exposure}
        bind:invalid={app.exposureInvalid}
        unit="s"
        min={lim.exposureMin}
        max={lim.exposureMax}
        step={0.5}
        ladder={EXPOSURE_LADDER}
        format={(v) => fixed(v, v < 1 ? 3 : 1)}
        range="{fixed(lim.exposureMin, lim.exposureMin < 0.01 ? 3 : 2)}–{int(lim.exposureMax)} s{lim.driver ? ' · driver' : ''}"
        appliedNote="from the next frame"
        disabled={!!ownedReason && !app.stale}
        disabledReason={app.stale ? ownedReason : null}
        send={(v) => app.setExposure(v)}
      />
      <NumberField
        label="Gain"
        value={app.gain}
        bind:invalid={app.gainInvalid}
        min={lim.gainMin}
        max={lim.gainMax}
        step={10}
        integer
        range="{int(lim.gainMin)}–{int(lim.gainMax)}{lim.driver ? ' · driver' : ''}"
        appliedNote="from the next frame"
        disabled={!!ownedReason && !app.stale}
        disabledReason={app.stale ? ownedReason : null}
        send={(v) => app.setGain(v)}
      />
    </div>

    {#if pending}
      <p class="pending" role="status">
        <span class="dot" aria-hidden="true"></span>
        <span class="text">Next frame: <span class="num">{pending}</span></span>
        <IconButton
          icon="close"
          label="Cancel the change"
          tooltipText="Cancel the change: keep the settings in use"
          variant="ghost"
          size="s"
          tooltip="top"
          busy={!!app.busy.liveSettings}
          onclick={() => app.revertLiveSettings()}
        />
      </p>
    {/if}

    <div class="row">
      <span class="key">Frame</span>
      <div class="ctl">
        <Segmented
          label="Frame type"
          size="s"
          fill
          options={FRAME_TYPES}
          value={frameType}
          busyValue={app.busy.settings ? frameType : null}
          disabledReason={ownedReason}
          onchange={chooseType}
        />
      </div>
    </div>
    <!-- Only for Dark / Bias and the wheel guard: a Light frame leaves no empty line (no dead band). -->
    {#if frameNote}
      <p class="note" class:warn={frameNote.tone === 'warn'} role="status">
        {#if frameNote.tone === 'warn'}<Icon name="attention" size={14} />{/if}{frameNote.text}
      </p>
    {/if}

    <FilterWheelControl
      wheel={wheel}
      filter={settings?.filter ?? null}
      slots={wheel?.slots ?? []}
      cameraOwner={app.cameraOwner}
      quiet
      onselect={(name) => app.chooseFilter(name)}
    />

    <div class="sensor">
      <button type="button" class="disclosure" aria-expanded={sensorOpen} onclick={toggleSensor}>
        <span class="chev" class:open={sensorOpen}><Icon name="disclosure" size="s" /></span>
        <span class="key">Sensor</span>
        {#if !sensorOpen}<span class="sum num">{sensorSummary}</span>{/if}
      </button>
      {#if sensorOpen}
        <div class="sensor-body">
          {#if offsetRange}
            <NumberField
              label="Offset"
              value={settings?.offset ?? offsetRange.min}
              min={offsetRange.min}
              max={offsetRange.max}
              step={1}
              integer
              range="{int(offsetRange.min)}–{int(offsetRange.max)} · driver"
              appliedNote="read back from the driver"
              disabledReason={sensorReason}
              send={(v) => app.putSettings({ offset: Math.round(v) })}
            />
          {:else}
            <p class="fact-line">{cam ? 'This driver has no offset.' : 'Offset: connect the camera first.'}</p>
          {/if}
          {#if cam?.binning}
            <div class="bin">
              <span class="key">Binning</span>
              <Segmented
                label="Binning"
                size="s"
                mono
                options={binOptions}
                value={String(settings?.binning ?? 1)}
                disabledReason={sensorReason}
                onchange={(v) => void app.putSettings({ binning: Number(v) }).catch((e) => app.reportError('Binning', e))}
              />
            </div>
          {:else}
            <p class="fact-line">{cam ? 'Binning 1× only on this driver.' : ''}</p>
          {/if}
        </div>
      {/if}
    </div>

    <!-- The exposure's progress has one home, the toolbar's ring and the HUD: no bar here,
         and no reserved empty row at rest (design review of wave 3). -->
    <dl class="facts" class:stale={app.stale}>
      <div class="wide">
        <dt>{cam?.current ? 'Exposing' : 'Next frame'}</dt>
        <dd class="num">{inUse}</dd>
      </div>
      <div>
        <dt>Sensor</dt>
        <dd class="num">{temp !== null ? `${fixed(temp, 1)} °C` : '—'}</dd>
      </div>
      <div>
        <dt>Format</dt>
        <dd class="num">{sensor ? `${int(sensor.width)} × ${int(sensor.height)} ${sensor.bayer ?? 'mono'}` : '—'}</dd>
      </div>
    </dl>
  </div>
</Card>

<style>
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .fields {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
  }

  .row {
    display: grid;
    grid-template-columns: 52px minmax(0, 1fr);
    align-items: center;
    gap: var(--space-2);
  }
  .ctl {
    min-width: 0;
  }
  .key {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .note {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    min-height: 1.4em;
    margin: calc(-1 * var(--space-2)) 0 0 calc(52px + var(--space-2));
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-tight);
  }
  .note.warn {
    color: var(--fg);
  }
  .note :global(svg) {
    flex: none;
    color: var(--warning);
  }

  .owned {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
  }
  .owned .dot {
    width: 7px;
    height: 7px;
    flex: none;
    border-radius: var(--radius-round);
    background: var(--status-busy);
  }
  /* A pending change reads in --fg (it is information, not a hint). */
  .pending {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: calc(-1 * var(--space-2)) 0 0;
    color: var(--fg);
    font-size: var(--text-s);
  }
  .pending .text {
    flex: 1;
    min-width: 0;
  }
  .pending .dot {
    width: 7px;
    height: 7px;
    flex: none;
    border-radius: var(--radius-round);
    background: var(--status-busy);
  }

  .sensor {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
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
  .sensor-body {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
    align-items: start;
    padding-left: var(--space-5);
  }
  .bin {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .fact-line {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }

  .facts {
    display: grid;
    grid-template-columns: 1fr 1.4fr;
    gap: var(--space-2) var(--space-3);
    margin: 0;
  }
  .facts div {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .facts .wide {
    grid-column: 1 / -1;
  }
  dt {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  dd {
    margin: 0;
    color: var(--fg);
    font-size: var(--readout-s); /* 13 px compact, 16 px Comfortable (D7) */
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .stale dd {
    color: var(--text-muted);
  }
</style>
