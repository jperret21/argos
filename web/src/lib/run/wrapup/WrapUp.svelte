<!--
  The end-of-night wrap-up (owner D2; PROPOSAL 3.1; functional-spaces §4.14): when a run
  ends, the Run card turns into the next steps. Body content for the Run card's "ended"
  branch (the card keeps its title and state chip). From the server's WrapUp record
  (wrapup.ts); while the server still measures the last frames the record is null and the
  card says so.
  - The outcome in words (the server's sentence verbatim when it failed), the run's span,
    its points (flagged, frames without a point) and the attention items it raised.
  - What the mount does now ("Tracking is still on."): the end action may have left it on.
  - Calibration for tonight's lights: darks per (exposure, gain), biases per gain, the time
    each takes at tonight's measured cost per frame; "Prepare in Plan" replaces the Plan
    draft with them (nothing starts; the host offers Undo with the draft it replaced).
  - Park by hold (D4; the Mount card's wording) when the mount is connected and not parked.
  - The session folder: its name and size; Copy path puts the full path on the clipboard
    (the card never prints the full path, design review W6a).
-->
<script lang="ts">
  import type { SequenceResult } from '../../api/sequence';
  import type { MountPhase } from '../../api/types';
  import Button from '../../components/Button.svelte';
  import HoldButton from '../../components/HoldButton.svelte';
  import type { HoldPhase } from '../../components/hold';
  import IconButton from '../../components/IconButton.svelte';
  import { fixed } from '../../format/number';
  import { folderName, outcomeOf, outcomeText } from '../run';
  import { aboutText, attentionLine, entryLine, entryTitle, mountLine, pointsLine, runLine, sizeText, totalEstimate, type WrapUpView } from './wrapup';

  interface Props {
    /** How the run ended (SequenceState.last_result). */
    result: SequenceResult;
    /** The server's record; null while it measures the last frames. */
    wrap: WrapUpView | null;
    objectName?: string | null;
    /** The mount now (the live record); default: the record's state after the end action. */
    mount?: { state: MountPhase; tracking: boolean } | null;
    /** POST /api/sequence/calibration-plan, then show Plan (the host offers Undo). */
    onprepare?: () => Promise<unknown> | void;
    /** Park the mount (hold-to-confirm). */
    onpark?: () => Promise<unknown> | unknown;
    parkReason?: string | null;
    /** Copy the session folder's full path. */
    oncopy?: (path: string) => void;
    /** Open the attention list (the run's items). */
    onattention?: () => void;
    onplan?: () => void;
    ondismiss?: () => void;
    /** Gallery: freeze the Park hold. */
    pinPark?: { phase: HoldPhase; progress?: number } | null;
  }
  let { result, wrap, objectName = null, mount, onprepare, onpark, parkReason = null, oncopy, onattention, onplan, ondismiss, pinPark = null }: Props = $props();

  const outcome = $derived(outcomeOf(result));
  const cal = $derived(wrap?.calibration ?? null);
  const list = $derived(result.frames_saved > 0 ? (cal?.entries ?? []) : []);
  const total = $derived(totalEstimate(list));
  const m = $derived(mountLine(mount !== undefined ? mount : (wrap?.mount ?? null), wrap?.mount?.endAction ?? result.on_complete));
  const parked = $derived((mount !== undefined ? mount?.state : wrap?.mount?.state) === 'parked');
  const connected = $derived(mount !== undefined ? !!mount : !!wrap?.mount?.connected);
  const root = $derived(wrap?.runRoot ?? result.run_root);
  const folder = $derived(wrap?.runFolder ?? folderName(root));
  const size = $derived(sizeText(wrap?.runBytes ?? null));
  const points = $derived(pointsLine(wrap?.points ?? null, wrap?.frames.lights ?? null));
  const alerts = $derived(attentionLine(wrap?.attention ?? null));
  let preparing = $state(false);
  let failure = $state<string | null>(null);

  async function prepare(): Promise<void> {
    if (!onprepare || preparing) return;
    preparing = true;
    failure = null;
    try {
      await onprepare();
    } catch (err) {
      failure = err instanceof Error ? err.message : String(err);
    } finally {
      preparing = false;
    }
  }
</script>

<div class="wrap">
  <p class="outcome o-{outcome}"><span class="mark" aria-hidden="true"></span>{outcomeText(result)}</p>
  <p class="meta num">{runLine(objectName ?? wrap?.objectName ?? null, result)}</p>
  {#if points}<p class="meta num">{points}</p>{/if}
  {#if alerts}
    <p class="meta">
      {#if onattention}<button type="button" class="link" onclick={onattention}>{alerts}</button>{:else}{alerts}{/if}
    </p>
  {/if}

  <p class="mount" class:on={m.tracking}>{m.text}</p>

  {#if !wrap && result.frames_saved > 0}
    <p class="note" role="status">Measuring the last frames; the calibration plan follows.</p>
  {:else if list.length}
    <section class="calib" aria-label="Calibration for tonight's lights">
      <h3>Calibration for tonight's lights</h3>
      <ul>
        {#each list as e (`${e.kind}|${e.exposure_s}|${e.gain}`)}
          <li>
            <span class="what">{entryTitle(e)}</span>
            <span class="how num">{entryLine(e, cal?.darkSlot ?? false)}</span>
            <span class="time num">{aboutText(e.estimate_s)}</span>
          </li>
        {/each}
      </ul>
      <p class="note num">
        {#if total !== null && cal?.overhead != null}
          {aboutText(total)} in all · {fixed(cal.overhead, 0)} s readout and save per frame, measured tonight.
        {:else if total !== null}
          {aboutText(total)} in all.
        {:else}
          No cadence measured: the time is not estimated.
        {/if}
        {#if cal && !cal.darkSlot && !cal.note}Put the lid on first: this wheel has no Dark slot.{/if}
        {#if cal?.note}{cal.note}{/if}
      </p>
      {#if onprepare}
        <div class="row">
          <Button label="Prepare in Plan" size="s" busy={preparing} onclick={prepare} />
          <span class="hint">Replaces the Plan draft; nothing starts until you press Start.</span>
        </div>
      {/if}
      {#if failure}<p class="refused" role="alert"><span class="mark" aria-hidden="true"></span>{failure}</p>{/if}
    </section>
  {/if}

  {#if onpark && connected && !parked}
    <div class="park">
      <HoldButton icon="park" label="Park" size="l" verb="park" confirmTitle="Park the mount?" confirmBody="Parking physically closes the Seestar arm and stops tracking." busyLabel="Parking…" doneLabel="Parked" disabledReason={parkReason} onconfirm={onpark} pin={pinPark} />
    </div>
  {/if}

  {#if folder}
    <div class="session">
      <span class="k">Session</span>
      <span class="name num" title={folder}>{folder}</span>
      {#if size}<span class="meta num">{size}</span>{/if}
      {#if oncopy && root}
        <IconButton icon="copy" label="Copy the session folder's path" size="s" variant="ghost" onclick={() => oncopy?.(root ?? '')} />
      {/if}
    </div>
  {/if}

  {#if onplan || ondismiss}
    <div class="row">
      {#if onplan}<Button label="Open Plan" size="s" variant="ghost" onclick={onplan} />{/if}
      <span class="grow"></span>
      {#if ondismiss}<Button label="Dismiss" size="s" variant="ghost" onclick={ondismiss} />{/if}
    </div>
  {/if}
</div>

<style>
  .wrap {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  p {
    margin: 0;
  }
  .outcome {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .meta {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .link {
    padding: 0;
    border: none;
    background: none;
    color: var(--fg);
    font: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;
    cursor: pointer;
  }
  .link:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
  .mount {
    margin-top: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .mount.on {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .calib {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-top: var(--space-1);
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }
  h3 {
    margin: 0;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  li {
    display: grid;
    grid-template-columns: 72px minmax(0, 1fr) auto;
    align-items: baseline;
    gap: var(--space-2);
    font-size: var(--text-s);
  }
  .what {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .how {
    min-width: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .time {
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .note,
  .hint {
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
  }
  .row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .grow {
    flex: 1;
  }
  .park {
    margin-top: var(--space-1);
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .session {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .refused {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .mark {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    align-self: center;
  }
  .o-completed .mark {
    background: var(--status-ok);
  }
  .o-stopped .mark {
    box-shadow: inset 0 0 0 1.5px var(--status-idle);
  }
  .o-failed .mark,
  .refused .mark {
    background: var(--danger);
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
</style>
