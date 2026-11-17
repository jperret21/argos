<!--
  Focuser card body (spec 05 §2.3 D, rail width 396 px). Promoted from
  src/lab/controls/instruments/FocuserControl.svelte (web/lab/PROPOSAL.md
  3.3 "Focuser card", 6, W3) onto the server's records (protocol.md
  "Focuser (A34, A35)", "Autofocus (A36)"); the pure rules are focuser.ts.
  The card that hosts it (imaging/, with Card and focuserBadge() in its
  header) passes the records through and wires the callbacks to the REST
  client; each callback rejects with the server's words to refuse.

  - Readouts: polled position (the needle's number), commanded target with
    the taps still queued, focuser temperature and its drift since the last
    autofocus (refocusing is due when the tube has cooled: the card says by
    how much).
  - Two-scale gauge (FocuserGauge): one tick = one tap.
  - Step (segmented, mono), Out / In (a tap = one step; held, it repeats at
    12 steps/s, no acceleration: hardware). Taps during a move are QUEUED
    ("+300 queued") and sent as one move when the current one ends (owner
    D9): never a Move while moving.
  - Go to: an ACTION field (NumberField `action`) on one row with its key:
    only Enter or its Move button send (arrows and the wheel step the draft
    by the step size); out of 0…MaxStep is refused in words, never clamped
    (H10); never rewritten while edited (Qt P5).
  - Autofocus (icon + label: minutes of hardware) becomes "Stop AF" with the
    sweep's time ring (the count is the Focus band's and the status bar's); Stop AF returns the focuser to its start
    (S23; "Returning…" until it is there). Halt is ALWAYS available while the
    focuser is connected, autofocus included (Qt P7): it stops where it is.
  - Out, In and Go to are refused while autofocus owns the focuser (H10).
  Disabled reasons in words everywhere; the layout never jumps between
  states. Neutral inks; brass only on the running autofocus (its ring).
-->
<script lang="ts">
  import NumText from '../../components/NumText.svelte';
  import { untrack, type Snippet } from 'svelte';
  import Control from '../../components/Control.svelte';
  import { refusalText } from '../../components/commit.svelte';
  import NumberField from '../../components/NumberField.svelte';
  import Readouts, { type ReadoutItem } from '../../components/Readouts.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import { REPEAT } from '../../components/values';
  import { DASH, fixed, int } from '../../format/number';
  import {
    afReference,
    autofocusActive,
    autofocusProgress,
    commandedTarget,
    commandText,
    DRIFT_WARN_C,
    driftSinceAf,
    driftText,
    FOCUS_STEPS,
    focuserLine,
    focuserOnline,
    manualReason,
    queuedDelta,
    queuedText,
    stepReason,
    TapQueue,
    travelText,
  } from './focuser';
  import FocuserGauge from './FocuserGauge.svelte';
  import type { AutofocusView, FocuserCommandResult, FocuserView } from './types';

  interface Props {
    focuser: FocuserView;
    autofocus?: AutofocusView | null;
    /** Step size (persisted per viewer by the card). */
    step?: number;
    /** The AF frames as the server takes them (the hint under Autofocus, S22 / P8). */
    afFrames?: { exposure_s: number; gain: number } | null;
    /** Why autofocus cannot start beyond the focuser (no camera, a sequence owns the camera). */
    autofocusReason?: string | null;
    /** Focuser temperature at the last autofocus, when the card knows it (else remembered here). */
    afTemperatureC?: number | null;
    /** Key shown on Halt when the screen binds it (Esc, Q-O4). */
    haltShortcut?: string;
    /** POST /api/focuser/step {delta}. */
    onstep?: (delta: number) => Promise<FocuserCommandResult | unknown>;
    /** POST /api/focuser/move {position}. */
    onmove?: (position: number) => Promise<FocuserCommandResult | unknown>;
    /** POST /api/focuser/halt. */
    onhalt?: () => Promise<unknown>;
    /** POST /api/autofocus/start. */
    onautofocus?: () => Promise<unknown>;
    /** POST /api/autofocus/stop (cancel and return to the start). */
    onstopautofocus?: () => Promise<unknown>;
    /** The V-curve (charts/VCurvePlot), under the actions. */
    vcurve?: Snippet;
    /** Gallery: show these taps as not yet sent. */
    pinPending?: number;
    /** Gallery: a last command result or failure. */
    pinResult?: string | null;
    pinError?: string | null;
  }

  let {
    focuser,
    autofocus = null,
    step = $bindable(100),
    afFrames = null,
    autofocusReason = null,
    afTemperatureC,
    haltShortcut,
    onstep,
    onmove,
    onhalt,
    onautofocus,
    onstopautofocus,
    vcurve,
    pinPending = 0,
    pinResult = null,
    pinError = null,
  }: Props = $props();

  let lastResult: string | null = $state(null);
  let lastError: string | null = $state(null);
  let actionError: { which: 'halt' | 'af' | 'step'; text: string } | null = $state(null);
  let busy: 'halt' | 'af' | 'stopaf' | null = $state(null);
  let unsent = $state(0);

  const queue = new TapQueue(
    (delta) => (onstep ? Promise.resolve(onstep(delta)) : Promise.resolve(null)),
    () => (unsent = queue.unsent),
    (r) => {
      const res = r as FocuserCommandResult | null;
      lastResult = res && typeof res === 'object' && 'clamped' in res ? commandText(res, focuser.max_step) : null;
    },
    (err) => {
      lastError = refusalText(err);
      actionError = { which: 'step', text: lastError };
    },
  );

  const pending = $derived(unsent + pinPending);
  const online = $derived(focuserOnline(focuser));
  const afActive = $derived(autofocusActive(autofocus));
  const common = $derived(manualReason(focuser, autofocus));
  const outReason = $derived(stepReason(-1, focuser, autofocus, pending));
  const inReason = $derived(stepReason(1, focuser, autofocus, pending));
  const commanded = $derived(online ? commandedTarget(focuser) : null);
  const finalTarget = $derived(commanded === null ? null : commanded + pending);
  const queued = $derived(queuedDelta(focuser, pending));
  const moving = $derived(focuser.state === 'moving');

  // The temperature at the last autofocus: from the card, else remembered when a run ends `done`.
  let afRef = $state<{ run: number; temperature_c: number } | null>(null);
  $effect(() => {
    const next = afReference(
      untrack(() => afRef),
      autofocus,
      focuser,
    );
    if (next !== untrack(() => afRef)) afRef = next;
  });
  const drift = $derived(driftSinceAf(focuser.temperature_c, afTemperatureC ?? afRef?.temperature_c ?? null));
  const afBest = $derived(autofocus?.best?.position ?? null);

  const items = $derived<ReadoutItem[]>([
    // One unit slot inline after each value (design review W3: "5 287 / steps" vs "5 287").
    {
      k: 'Position',
      v: online ? int(focuser.position) : DASH,
      unit: online && focuser.position != null ? 'steps' : undefined,
      key: true,
      note: online && moving ? 'polled · moving' : '',
    },
    {
      k: 'Target',
      v: finalTarget === null ? DASH : int(finalTarget),
      unit: finalTarget === null ? undefined : 'steps',
      note: queuedText(queued),
    },
    {
      k: 'Temperature',
      v: focuser.temperature_c === null || focuser.temperature_c === undefined ? DASH : fixed(focuser.temperature_c, 1),
      unit: focuser.temperature_c === null || focuser.temperature_c === undefined ? undefined : '°C',
      note: driftText(drift),
      flag: drift !== null && Math.abs(drift) >= DRIFT_WARN_C ? 'refocus' : undefined,
    },
  ]);

  const stepOptions = FOCUS_STEPS.map((v) => ({ value: String(v), label: int(v) }));

  // -- Out / In: tap = one step; held, repeats (no acceleration: hardware) ----------------
  let repeatDelay: ReturnType<typeof setTimeout> | null = null;
  let repeatTimer: ReturnType<typeof setInterval> | null = null;
  let held: 'out' | 'in' | null = $state(null);

  function stepOnce(dir: 1 | -1): void {
    if (stepReason(dir, focuser, autofocus, queue.unsent)) return stopRepeat();
    lastError = null;
    lastResult = null;
    actionError = null;
    queue.tap(dir * step);
  }

  function press(e: PointerEvent, dir: 1 | -1): void {
    if ((dir > 0 ? inReason : outReason) || e.button !== 0) return;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    held = dir > 0 ? 'in' : 'out';
    stepOnce(dir);
    repeatDelay = setTimeout(() => {
      repeatTimer = setInterval(() => stepOnce(dir), REPEAT.interval);
    }, REPEAT.delay);
  }

  function stopRepeat(): void {
    if (repeatDelay) clearTimeout(repeatDelay);
    if (repeatTimer) clearInterval(repeatTimer);
    repeatDelay = repeatTimer = null;
    held = null;
  }

  /** Keyboard activation (detail 0); the pointer acted on press. */
  function keyStep(e: MouseEvent, dir: 1 | -1): void {
    if (e.detail === 0) stepOnce(dir);
  }

  $effect(() => () => stopRepeat());
  // Autofocus took the focuser, or it went away: a held key stops repeating.
  $effect(() => {
    if (common) untrack(stopRepeat);
  });

  // -- Go to ---------------------------------------------------------------------------------
  async function moveTo(v: number | null): Promise<void> {
    if (v === null || !onmove) return;
    lastError = null;
    actionError = null;
    const r = (await onmove(v)) as FocuserCommandResult | null;
    lastResult = r && typeof r === 'object' && 'clamped' in r ? commandText(r, focuser.max_step) : null;
  }

  // -- Actions ---------------------------------------------------------------------------------
  async function run(which: 'halt' | 'af' | 'stopaf', fn?: () => Promise<unknown>): Promise<void> {
    if (!fn || busy) return;
    busy = which;
    actionError = null;
    lastError = null;
    lastResult = null;
    if (which === 'halt') {
      queue.clear();
      stopRepeat();
    }
    try {
      await fn();
    } catch (err) {
      actionError = { which: which === 'stopaf' ? 'af' : which, text: refusalText(err) };
      lastError = actionError.text;
    } finally {
      busy = null;
    }
  }

  const afProgress = $derived(autofocusProgress(autofocus));
  const afStartReason = $derived(
    !online ? 'Connect the focuser first' : (autofocusReason ?? (focuser.state === 'error' ? (focuser.message ?? 'The focuser reports an error') : null)),
  );
  const line = $derived(
    focuserLine(focuser, autofocus, {
      lastResult: pinResult ?? lastResult,
      lastError: pinError ?? lastError,
      frames: autofocus?.params ? { exposure_s: autofocus.params.exposure_s, gain: autofocus.params.gain } : afFrames,
    }),
  );
  const gotoValue = $derived(finalTarget);
</script>

<div class="focuser">
  <Readouts {items} cols={3} />

  <FocuserGauge position={online ? (focuser.position ?? null) : null} target={finalTarget} max={focuser.max_step ?? null} {step} {afBest} />

  <div class="row">
    <span class="key" aria-hidden="true">Step</span>
    <Segmented
      label="Focus step"
      options={stepOptions}
      value={String(step)}
      onchange={(v: string) => (step = Number(v))}
      size="s"
      mono
      disabledReason={online ? null : 'Connect the focuser first'}
    />
    <span class="grow"></span>
    <Control
      icon="focus-out"
      label="Focus out"
      tooltipText="Focus out: position −{int(step)}"
      hint={outReason ? null : 'Hold to repeat'}
      disabledReason={outReason}
      error={actionError?.which === 'step' ? actionError.text : null}
      data-force={held === 'out' ? 'active' : undefined}
      onpointerdown={(e: PointerEvent) => press(e, -1)}
      onpointerup={stopRepeat}
      onpointercancel={stopRepeat}
      onlostpointercapture={stopRepeat}
      onclick={(e: MouseEvent) => keyStep(e, -1)}
    />
    <Control
      icon="focus-in"
      label="Focus in"
      tooltipText="Focus in: position +{int(step)}"
      hint={inReason ? null : 'Hold to repeat'}
      disabledReason={inReason}
      data-force={held === 'in' ? 'active' : undefined}
      onpointerdown={(e: PointerEvent) => press(e, 1)}
      onpointerup={stopRepeat}
      onpointercancel={stopRepeat}
      onlostpointercapture={stopRepeat}
      onclick={(e: MouseEvent) => keyStep(e, 1)}
    />
  </div>

  <div class="row goto">
    <span class="key" aria-hidden="true">Go to</span>
    <div class="field">
      <NumberField
        label="Go to"
        hideLabel
        value={gotoValue}
        min={0}
        max={focuser.max_step ?? Infinity}
        {step}
        integer
        range={focuser.max_step === null || focuser.max_step === undefined ? travelText(focuser) : undefined}
        appliedNote="moving"
        reserve
        action={{ icon: 'focus-move', label: 'Move to this position' }}
        disabledReason={common}
        send={moveTo}
      />
    </div>
  </div>

  <div class="actions">
    {#if afActive}
      <Control
        icon="stop"
        label="Stop AF"
        showLabel
        busy={autofocus?.state === 'stopping' || busy === 'stopaf'}
        progress={autofocus?.state === 'running' ? afProgress : null}
        progressText={autofocus?.state === 'running' ? `step ${autofocus?.step ?? 0} of ${autofocus?.total ?? 0}` : undefined}
        tooltipText={autofocus?.state === 'stopping' ? 'Returning the focuser to its start position' : 'Cancel autofocus and return to the start position'}
        error={actionError?.which === 'af' ? actionError.text : null}
        disabledReason={autofocus?.state === 'stopping' ? 'Autofocus is already stopping' : null}
        onclick={() => void run('stopaf', onstopautofocus)}
      />
    {:else}
      <Control
        icon="autofocus"
        label="Autofocus"
        showLabel
        busy={busy === 'af'}
        tooltipText="Autofocus: V-curve sweep, then a verification frame"
        error={actionError?.which === 'af' ? actionError.text : null}
        disabledReason={afStartReason}
        onclick={() => void run('af', onautofocus)}
      />
    {/if}
    <span class="grow"></span>
    <Control
      icon="stop"
      label="Halt"
      showLabel
      variant="danger"
      shortcut={haltShortcut}
      busy={busy === 'halt'}
      tooltipText={afActive ? 'Halt: stop where it is (ends the autofocus there)' : 'Halt: stop where it is'}
      error={actionError?.which === 'halt' ? actionError.text : null}
      disabledReason={online ? null : 'Connect the focuser first'}
      onclick={() => void run('halt', onhalt)}
    />
  </div>

  <p class="line kind-{line.kind}" aria-live="polite"><NumText text={line.text} group /></p>

  {#if vcurve}<div class="vcurve">{@render vcurve()}</div>{/if}
</div>

<style>
  .focuser {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }
  .row,
  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    min-width: 0;
  }
  .actions {
    gap: var(--space-2);
  }
  .key {
    margin-right: var(--space-2);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .grow {
    flex: 1;
  }
  /* Go to on one row with its key, as Step: one row less in the rail (BRAND 11.1). */
  .row.goto {
    align-items: flex-start;
  }
  .goto .key {
    min-width: 44px;
    line-height: var(--input-h);
  }
  .row:not(.goto) .key {
    min-width: 44px;
  }
  .field {
    flex: 1;
    min-width: 0;
  }
  .line {
    min-height: 16px;
    margin: calc(-1 * var(--space-1)) 0 0;
    color: var(--fg);
    font-size: var(--text-xs);
    line-height: 16px;
  }
  .kind-muted,
  .kind-reason {
    color: var(--text-muted);
  }
  .kind-reason::before,
  .kind-bad::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: 6px;
    border-radius: var(--radius-round);
    vertical-align: 1px;
  }
  /* The tooltip's vocabulary: hollow ring = a reason, danger dot = what failed. */
  .kind-reason::before {
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .kind-bad::before {
    background: var(--danger);
  }
  .vcurve {
    min-width: 0;
  }
</style>
