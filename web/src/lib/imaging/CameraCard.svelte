<!--
  Camera: exposure and gain, the camera state, the exposure progress and the
  settings in use. The capture / live / stop actions live in the toolbar
  (E, V); this card holds the settings they use. Frame number and exposure
  of the frame on screen are on the image's chips.

  The fields always show the settings in use (they follow the server's
  camera record). While live view runs, a change is committed on Enter, on
  blur or after a short pause, sent at once, and applies from the next
  frame: until then the card says "Next frame: 2.0 s (now 1.0 s)", with a
  button to drop the change.
-->
<script lang="ts">
  import { EXPOSURE_LIMITS, GAIN_LIMITS, useApp } from '../app/state.svelte';
  import { cameraStatus } from '../app/status';
  import Card from '../components/Card.svelte';
  import IconButton from '../components/IconButton.svelte';
  import NumberField from '../components/NumberField.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { fixed, int, seconds } from '../format/number';

  const app = useApp();

  /** Commit pause of the fields (also on Enter and blur). */
  const SETTLE_MS = 600;

  const badge = $derived(cameraStatus(app.camera, app.cameraReady, app.stale));
  const cam = $derived(app.cameraReady ? app.camera : null);
  const sensor = $derived(cam?.sensor ?? null);

  // Exposure progress, estimated on the client from the request and the time
  // the state (or the last live frame) started. 10 Hz while it runs; the bar
  // jumps without easing, like every value (BRAND section 9).
  let now = $state(performance.now());
  let phaseStart = $state(performance.now());
  let lastPhase: string | undefined;

  $effect(() => {
    const phase = cam?.state;
    if (phase !== lastPhase) {
      lastPhase = phase;
      phaseStart = performance.now();
    }
  });

  $effect(() => {
    if (!app.cameraBusy || app.stale) return;
    const id = setInterval(() => (now = performance.now()), 100);
    return () => clearInterval(id);
  });

  const progress = $derived.by(() => {
    if (!cam || !app.cameraBusy || app.stale || cam.exposure_s <= 0) return null;
    if (cam.state === 'downloading') return { fraction: 1, elapsed: cam.exposure_s };
    const start = cam.state === 'live' ? Math.max(phaseStart, app.lastFrameAt ?? 0) : phaseStart;
    const elapsed = Math.max(0, (now - start) / 1000);
    return { fraction: Math.min(1, elapsed / cam.exposure_s), elapsed: Math.min(elapsed, cam.exposure_s) };
  });

  /** The live change waiting for the next frame, in words. */
  const pending = $derived.by(() => {
    if (!app.livePending || !cam) return null;
    const parts: string[] = [];
    if (Math.abs(cam.exposure_s - app.exposure) > 1e-9) {
      parts.push(`${seconds(app.exposure)} (now ${seconds(cam.exposure_s)})`);
    }
    if (cam.gain !== Math.round(app.gain)) parts.push(`gain ${int(app.gain)} (now ${int(cam.gain)})`);
    return parts.join(', ');
  });
</script>

<Card title="Camera" icon="camera" collapsible persist="camera">
  {#snippet status()}
    <StatusBadge tone={badge.tone} label={badge.label} />
  {/snippet}
  {#snippet summary()}
    {#if cam}{seconds(cam.exposure_s)} · gain {int(cam.gain)}{/if}
  {/snippet}

  <div class="fields">
    <NumberField
      label="Exposure"
      value={app.exposure}
      bind:invalid={app.exposureInvalid}
      unit="s"
      min={EXPOSURE_LIMITS.min}
      max={EXPOSURE_LIMITS.max}
      step={0.5}
      settleMs={SETTLE_MS}
      onchange={(v) => app.setExposure(v)}
    />
    <NumberField
      label="Gain"
      value={app.gain}
      bind:invalid={app.gainInvalid}
      min={GAIN_LIMITS.min}
      max={GAIN_LIMITS.max}
      step={10}
      integer
      settleMs={SETTLE_MS}
      onchange={(v) => app.setGain(v)}
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

  <div class="progress" class:idle={!progress} aria-hidden={!progress}>
    <div class="track">
      <div class="bar" style:width="{(progress?.fraction ?? 0) * 100}%"></div>
    </div>
    <span class="num">
      {#if progress && cam}
        {cam.state === 'downloading' ? 'Downloading' : `${fixed(progress.elapsed, 1, { group: true })} / ${fixed(cam.exposure_s, 1, { group: true })} s`}
      {:else}
        &nbsp;
      {/if}
    </span>
  </div>

  <dl class="facts" class:stale={app.stale}>
    <div>
      <dt>In use</dt>
      <dd class="num">{cam ? `${seconds(cam.exposure_s)}, gain ${int(cam.gain)}` : '—'}</dd>
    </div>
    <div>
      <dt>Sensor</dt>
      <dd class="num">
        {sensor ? `${int(sensor.width)} × ${int(sensor.height)} ${sensor.bayer ?? 'mono'}` : '—'}
      </dd>
    </div>
  </dl>
</Card>

<style>
  .fields {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
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

  .progress {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }

  .track {
    height: 3px;
    border-radius: 2px;
    background: var(--border-soft);
    overflow: hidden;
  }

  /* Neutral ink: a progress bar is a long fill, never brass (BRAND 3, 8; owner
     decisions 2026-11-01). The time ring around Capture carries the brass. */
  .bar {
    height: 100%;
    background: var(--fg-muted);
  }
  .progress.idle .track {
    visibility: hidden;
  }

  .facts {
    display: grid;
    grid-template-columns: 1fr 1.2fr;
    gap: var(--space-3);
    margin: 0;
  }
  .facts div {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
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
