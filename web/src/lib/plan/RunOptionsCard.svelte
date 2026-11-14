<!--
  Run options card (06 §2.2 rows 1.6 #1-#5, §2.3.1; M73): the plan-level fields.

  - Object (FITS): the observation's object, shared with Observe (one object per plan, Q-P1);
    a non-empty name sets the observation (the server re-keys the target set), an empty one
    never clears it (P10) and is a warning.
  - Repeat ×, Autofocus every N frames (0 = off; says when no focuser is connected: the run
    would skip it, P17), on filter change, End of run (Nothing, Stop tracking, Park mount).
  - Start (UTC) (W6b): the draft's own start time, any day ("YYYY-MM-DD hh:mm"; empty: Start
    runs at once). A transit prepared for a later night keeps its time; Start schedules it
    from 24 h before (the server's limit), and the line under the field says when.
  - Every value goes to the server as typed (one PUT per commit); what is wrong with it comes
    back as an issue shown under the field, never a silent clamp. Locked while a run is
    active (Q-P9): the reason is said once, under the object; the other fields are disabled.
-->
<script lang="ts">
  import type { SequencePlan } from '../api/plan';
  import { ON_COMPLETE } from '../api/plan';
  import Card from '../components/Card.svelte';
  import Checkbox from '../components/Checkbox.svelte';
  import CommitTextField from '../components/CommitTextField.svelte';
  import NumberField from '../components/NumberField.svelte';
  import Segmented from '../components/Segmented.svelte';
  import type { IssueIndex } from './model';
  import { draftStartText, parseDraftStart } from '../run/run';

  interface Props {
    plan: SequencePlan | null;
    issues: IssueIndex;
    lockedReason?: string | null;
    /** A focuser is connected (autofocus can run). */
    focuser: boolean;
    onset: (patch: Partial<Omit<SequencePlan, 'steps'>>) => Promise<unknown>;
    open?: boolean;
    /** Unix s (the app clock): the start field says when its time is. */
    now?: number | null;
  }

  let { plan, issues, lockedReason = null, focuser, onset, open = $bindable(true), now = null }: Props = $props();

  const END = [
    { value: 'Nothing', label: 'Nothing' },
    { value: 'Stop tracking', label: 'Stop tracking', icon: 'tracking' },
    { value: 'Park mount', label: 'Park', icon: 'park' },
  ];
  const endKnown = $derived(!plan || (ON_COMPLETE as readonly string[]).includes(plan.on_complete));
  const afNote = $derived(plan && !focuser && (plan.autofocus_every_n > 0 || plan.autofocus_on_filter_change) ? 'No focuser connected: the run skips autofocus' : null);
  const summaryText = $derived(
    plan
      ? `×${plan.repeat} · AF ${plan.autofocus_every_n > 0 ? `every ${plan.autofocus_every_n}` : 'off'} · end: ${plan.on_complete === 'Nothing' ? 'nothing' : plan.on_complete.toLowerCase()}`
      : '',
  );
  const reason = $derived(lockedReason ?? (plan ? null : 'the plan is not loaded yet'));
  const startT = $derived(plan?.start_at_utc ? Date.parse(plan.start_at_utc) / 1000 : null);
  const startHint = $derived.by(() => {
    if (startT === null || now === null) return 'Empty: Start runs at once. YYYY-MM-DD hh:mm for a later night';
    const p = parseDraftStart(draftStartText(startT), now);
    return p.ok ? p.text : 'This time has passed: Start runs at once';
  });
  function sendStart(v: string | null): Promise<unknown> {
    const p = parseDraftStart(v ?? '', now ?? Date.now() / 1000);
    if (!p.ok) return Promise.reject(new Error(p.error));
    return onset({ start_at_utc: p.t === null ? null : new Date(p.t * 1000).toISOString().replace('.000Z', 'Z') });
  }
</script>

{#snippet issuesOf(field: string)}
  {#each issues.plan(field) as i (i.code)}
    <p class="issue" class:warn={i.level === 'warning'} role={i.level === 'error' ? 'alert' : undefined}>
      <span class="mark" aria-hidden="true"></span>{i.message}
    </p>
  {/each}
{/snippet}

<Card title="Run options" icon="camera" collapsible bind:open persist="argos.card.plan.options">
  {#snippet summary()}{summaryText}{/snippet}
  <div class="grid">
    <div class="wide">
      <CommitTextField
        label="Object (FITS)"
        value={plan?.object_name ?? ''}
        placeholder="Unknown"
        maxlength={80}
        disabledReason={reason}
        hint="Shared with Observe (FITS OBJECT, run folder, target set)"
        send={(v: string | null) => onset({ object_name: (v ?? '').trim() })}
      />
      {@render issuesOf('object_name')}
    </div>
    <div>
      <NumberField label="Repeat plan" value={plan?.repeat ?? 1} unit="×" integer disabled={!!lockedReason} disabledReason={lockedReason ? null : reason} appliedWord="Saved" dirtyWord="Not saved" commitVerb="saves" send={(v: number) => onset({ repeat: v })} />
      {@render issuesOf('repeat')}
    </div>
    <div>
      <NumberField label="Autofocus every" value={plan?.autofocus_every_n ?? 0} unit={plan?.autofocus_every_n ? 'frames' : undefined} integer format={(v) => (v === 0 ? 'off' : String(v))} disabled={!!lockedReason} disabledReason={lockedReason ? null : reason} appliedWord="Saved" dirtyWord="Not saved" commitVerb="saves" send={(v: number) => onset({ autofocus_every_n: v })} />
      {@render issuesOf('autofocus_every_n')}
    </div>
    <div class="wide">
      <CommitTextField
        label="Start (UTC)"
        value={draftStartText(startT)}
        placeholder="at once"
        mono
        nullable
        maxlength={20}
        disabledReason={reason}
        hint={startHint}
        send={sendStart}
      />
      {@render issuesOf('start_at_utc')}
    </div>
    <div class="wide">
      <Checkbox label="Autofocus on filter change" size="s" checked={plan?.autofocus_on_filter_change ?? false} disabled={!!lockedReason} disabledReason={lockedReason ? null : reason} onchange={(v) => void onset({ autofocus_on_filter_change: v }).catch(() => undefined)} />
      {#if afNote}<p class="issue warn"><span class="mark" aria-hidden="true"></span>{afNote}</p>{/if}
    </div>
    <div class="wide end">
      <span class="key" id="plan-end-label">End of run</span>
      <Segmented label="End of run" size="s" options={END} value={endKnown ? (plan?.on_complete ?? 'Nothing') : 'Nothing'} disabled={!!lockedReason} disabledReason={lockedReason ? null : reason} onchange={(v) => void onset({ on_complete: v }).catch(() => undefined)} />
      {#if !endKnown}<p class="issue"><span class="mark" aria-hidden="true"></span>“{plan?.on_complete}” is not an end-of-run action: choose one</p>{/if}
      {@render issuesOf('on_complete')}
    </div>
    {#if issues.plan('base_dir').length || issues.plan(null).length}
      <div class="wide">{@render issuesOf('base_dir')}{@render issuesOf('')}</div>
    {/if}
  </div>
</Card>

<style>
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-2) var(--space-3);
    align-items: start;
  }
  .wide {
    grid-column: 1 / -1;
  }
  .end {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .key {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .issue {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    margin: 2px 0 0;
    color: var(--fg);
    font-size: var(--text-xs);
    line-height: var(--leading-tight);
  }
  .issue .mark {
    flex: none;
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
    background: var(--danger);
    transform: translateY(-1px);
  }
  .issue.warn .mark {
    /* The attention mark, a bar over a dot (BRAND 8, run/LevelMark): never a triangle,
       the check star's shape (BRAND 2.6; design review W6a). */
    width: 3px;
    height: 9px;
    border: none;
    border-radius: 0;
    background: linear-gradient(var(--warning) 0 5px, transparent 5px 7px, var(--warning) 7px 9px);
  }
</style>
