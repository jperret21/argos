<!--
  Filter selection for the Camera card (spec 05 §2.2 1.1 #3, §2.4 "Busy";
  web/lab/PROPOSAL.md 3.3 "Segmented ... manual activation for hardware,
  busy segment"). The rules are filterwheel.ts.

  - The slots of the active profile, in wheel order, as a Segmented control
    with MANUAL activation: the arrows walk the slots, Space / Enter choose,
    so walking never moves the wheel three times.
  - DEFERRED: choosing only requests the slot (POST /api/filterwheel/select);
    the block stays on the slot the wheel reports and slides when the wheel
    says it settled. While it turns the requested slot spins and the others
    wait (aria-busy). A refused move shows the server's words and the slot
    the wheel is really on (H9).
  - Without a wheel, the slot is the capture setting `filter`, FITS metadata
    only (Q-O5): chosen at once, and the line says so.
-->
<script lang="ts">
  import { refusalText } from '../../components/commit.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import { settledSlot, wheelBusy, wheelLine, wheelMode, wheelOptions, wheelReason } from './filterwheel';
  import type { FilterWheelView } from './types';

  interface Props {
    wheel: FilterWheelView | null;
    /** The capture setting `filter` (CameraState.settings.filter): the value without a wheel. */
    filter?: string | null;
    /** The active profile's slot names, when no wheel record exists yet. */
    slots?: readonly string[];
    /** Who drives the camera (CameraState.owner): autofocus and a sequence refuse a change. */
    cameraOwner?: string | null;
    /**
     * With a wheel: POST /api/filterwheel/select {name}; without: PUT
     * /api/camera/settings {filter}. Reject with the server's words.
     */
    onselect?: (name: string) => Promise<unknown> | unknown;
    label?: string;
    size?: 's' | 'm';
    /** Show the visible key label ("FILTER") before the control. */
    showLabel?: boolean;
    /** Gallery: a refusal to show. */
    pinError?: string | null;
    /**
     * Inside a card that already says who owns the camera: no owner line, and
     * "Turning to …" stays on the control (spinner + tooltip) instead of
     * inserting a line that shifts the rail (design review of wave 3).
     */
    quiet?: boolean;
  }

  let { wheel, filter = null, slots: profileSlots = [], cameraOwner = null, onselect, label = 'Filter', size = 's', showLabel = true, pinError = null, quiet = false }: Props = $props();

  let requested: string | null = $state(null);
  let error: string | null = $state(null);

  const mode = $derived(wheelMode(wheel));
  const slots = $derived(wheel?.slots?.length ? wheel.slots : profileSlots);
  const options = $derived(wheelOptions(slots));
  const value = $derived(mode === 'wheel' ? (settledSlot(wheel) ?? '') : (filter ?? ''));
  // The request in flight, until the wheel reports it turning (then its own target).
  const busyValue = $derived(wheelBusy(wheel) ?? requested);
  const reason = $derived(wheelReason(wheel, { cameraOwner }));
  // What failed, else why it cannot be chosen now (in words, not only in the tooltip), else the wheel's state.
  const line = $derived(
    error || pinError
      ? { kind: 'bad', text: (pinError ?? error)! }
      : reason
        ? quiet
          ? null
          : { kind: 'reason', text: reason }
        : quiet && wheel?.state === 'moving'
          ? null
          : wheelLine(wheel, filter),
  );

  let giveUp: ReturnType<typeof setTimeout> | null = null;

  async function choose(name: string): Promise<void> {
    if (!onselect) return;
    error = null;
    requested = mode === 'wheel' ? name : null;
    if (giveUp) clearTimeout(giveUp);
    // The server bounds a move to 20 s; past that the record decides alone.
    if (requested) giveUp = setTimeout(() => (requested = null), 25_000);
    try {
      await onselect(name);
    } catch (err) {
      error = refusalText(err);
      requested = null;
    }
  }

  // The request spins until the wheel's own record takes over: turning, settled, or failed.
  $effect(() => {
    if (!requested || !wheel) return;
    if (wheel.state === 'moving' || wheel.state === 'error' || settledSlot(wheel) === requested) requested = null;
  });
  $effect(() => () => {
    if (giveUp) clearTimeout(giveUp);
  });
</script>

<div class="wheel">
  <div class="row">
    {#if showLabel}<span class="key" aria-hidden="true">{label}</span>{/if}
    <Segmented
      {label}
      {options}
      {value}
      {size}
      mono
      activation="manual"
      deferred={mode === 'wheel'}
      {busyValue}
      busyReason={busyValue ? `The wheel is turning to ${busyValue}` : undefined}
      disabledReason={reason}
      onchange={(v: string) => void choose(v)}
    />
  </div>
  {#if line}
    <p class="line kind-{line.kind}" aria-live="polite">{line.text}</p>
  {/if}
</div>

<style>
  .wheel {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .key {
    min-width: 52px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .line {
    margin: 0;
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
  .kind-reason::before {
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .kind-bad::before {
    background: var(--danger);
  }
</style>
