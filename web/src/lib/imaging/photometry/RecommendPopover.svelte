<!--
  Recommend comparison stars (08 2.3 E, 1.6 #2 and #7; A58): the "Recommend from pilot" and
  "Automatically propose" controls of Qt's ensemble tab (comparison_table.py:105-160) in one
  popover with an explicit button for each action (changing the count no longer re-selects
  by itself, 08 P11):

  - Proposed comparisons (1-20, `photometry.auto_comparisons`; sent with the action, which
    saves it);
  - the pilot gate in words, from Settings › Photometry (SNR, Δmag, distance);
  - Complete ensemble (adds missing calibrated VSP members up to the count) and Replace VSP
    picks (manual choices stay); during a run Replace asks first (the zero point of every
    following frame changes).
-->
<script lang="ts">
  import Button from '../../components/Button.svelte';
  import ConfirmDialog from '../../components/ConfirmDialog.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import NumberField from '../../components/NumberField.svelte';
  import NumText from '../../components/NumText.svelte';
  import Popover from '../../components/Popover.svelte';
  import { fixed, int } from '../../format/number';
  import type { RecommendMode } from './types';

  interface Props {
    /** `photometry.auto_comparisons`. */
    count: number;
    gate: { snr: number | null; dmag: number | null; sepArcmin: number | null };
    /** Why nothing can be recommended now (null: available). */
    reason?: string | null;
    /** A sequence owns the observation: Replace asks first. */
    running?: boolean;
    busy?: RecommendMode | null;
    /** The trigger shows its label (card) or only its icon. */
    showLabel?: boolean;
    /** Calibrated comparisons in the set now, and how many of them are VSP picks (the buttons say the effect). */
    inSet?: number | null;
    vspPicks?: number | null;
    preview?: boolean;
    onrecommend: (mode: RecommendMode, count: number) => Promise<unknown> | void;
  }

  let { count, gate, reason = null, running = false, busy = null, showLabel = true, inSet = null, vspPicks = null, preview = false, onrecommend }: Props = $props();

  let open = $state(false);
  let trigger: HTMLSpanElement | undefined = $state();
  let chosen: number | null = $state(null);
  const n = $derived(chosen ?? count);
  let confirm = $state(false);
  const id = `recommend-${Math.random().toString(36).slice(2, 8)}`;

  const gateText = $derived(
    [
      gate.snr !== null ? `SNR ≥ ${int(gate.snr)}` : null,
      gate.dmag !== null ? `Δmag ≤ ${fixed(gate.dmag, 1)}` : null,
      gate.sepArcmin !== null ? `≤ ${int(gate.sepArcmin)}′` : null,
    ]
      .filter(Boolean)
      .join(' · '),
  );

  /** What each action does, in numbers from the current set. */
  const adds = $derived(inSet === null ? null : Math.max(0, n - inSet));
  const completeText = $derived(adds === null ? 'Complete ensemble' : `Complete: +${adds}`);
  const completeReason = $derived(reason ?? (adds === 0 ? `The set already has ${inSet} calibrated comparisons (${n} proposed)` : null));
  const replaceText = $derived(vspPicks ? `Replace ${vspPicks} VSP pick${vspPicks === 1 ? '' : 's'} with up to ${n}` : `Replace VSP picks (up to ${n})`);

  async function run(mode: RecommendMode): Promise<void> {
    if (mode === 'replace' && running && !confirm) {
      confirm = true;
      return;
    }
    confirm = false;
    await onrecommend(mode, n);
    open = false;
  }
</script>

{#snippet body()}
  <div class="rec">
    <div class="count">
      <span class="lbl" aria-hidden="true">Proposed comparisons</span>
      <NumberField hideLabel label="Proposed comparisons (calibrated stars)" value={n} integer min={1} max={20} step={1} width="56px" send={(v: number) => (chosen = v)} />
      <span class="lbl" aria-hidden="true">calibrated stars</span>
    </div>
    <p class="gate"><span class="k">Pilot gate</span> <NumText text={gateText || '—'} /></p>
    <p class="muted">Measured on the newest solved frame; the limits are in Settings › Photometry.</p>
    <p class="muted">Replacing removes every VSP pick and keeps manual choices. During a run the zero point of all following frames changes.</p>
    {#if reason}<p class="reason">{reason}</p>{/if}
  </div>
{/snippet}

{#snippet footer()}
  <div class="actions">
    <Button variant="secondary" size="s" disabled={!!busy} disabledReason={completeReason} busy={busy === 'complete'} onclick={() => run('complete')}><NumText text={completeText} /></Button>
    <!-- Replace removes picks: the deliberate style during a run (it also asks first). -->
    <Button variant={running ? 'danger' : 'secondary'} size="s" disabled={!!busy} disabledReason={reason} busy={busy === 'replace'} onclick={() => run('replace')}><NumText text={replaceText} /></Button>
  </div>
{/snippet}

{#if preview}
  <Popover open title="Recommend comparison stars" preview width={340} {footer}>
    {@render body()}
  </Popover>
{:else}
  <span bind:this={trigger} class="anchor" class:dim={!!reason}>
    <IconButton
      icon="recommend-comparisons"
      label="Recommend…"
      {showLabel}
      size="s"
      variant="secondary"
      busy={!!busy}
      tooltip={open || showLabel ? 'none' : undefined}
      tooltipText="Recommend comparison stars from the solved frame"
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-controls={id}
      onclick={() => (open = !open)}
    />
  </span>
  <Popover bind:open anchor={trigger} title="Recommend comparison stars" {id} width={340} placement="bottom-end" {footer}>
    {@render body()}
  </Popover>
  <ConfirmDialog
    bind:open={confirm}
    title="Replace the VSP comparisons during the run?"
    message="The zero point of every following frame changes. Manual comparisons stay."
    confirmLabel="Replace VSP picks"
    cancelLabel="Keep the ensemble"
    onconfirm={() => run('replace')}
  />
{/if}

<style>
  .anchor {
    display: inline-flex;
  }
  /* Nothing to recommend now: it still opens and says why, but does not look ready. */
  .anchor.dim :global(.ctl) {
    --fg-c: var(--fg-disabled);
    --edge: var(--border-soft);
  }
  .rec {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    font-size: var(--text-s);
  }
  p {
    margin: 0;
  }
  .count {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .lbl {
    color: var(--fg);
    white-space: nowrap;
  }
  .gate {
    color: var(--fg);
    font-variant-numeric: var(--numeric);
  }
  .k {
    color: var(--text-muted);
    margin-right: var(--space-1);
  }
  .muted {
    color: var(--text-muted);
  }
  .reason {
    color: var(--fg);
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    width: 100%;
  }
</style>
