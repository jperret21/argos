<!--
  Re-run photometry over saved frames (web/spec/07-review-analysis.md 1.13, 2.2 rows 1.13,
  WF-F; README M8, M50, A76, D2, Q-R1; protocol.md "Re-run photometry (A76)").

  - Every choice asks the server's plan again (never writes): the frames it found (`.fit`,
    `.fits`, `.fts`, light frames of the object only: S12, S62) and what it left out, the stars
    (the session's targets.json, or the live set), the reference (identify the first frame
    with ASTAP, the default for a saved session; or the live field solution, only offered when
    one exists, D2), the aperture rule and the parameters (read-only, "Settings ›" to change
    them), the site (no site: no airmass, no BJD_TDB), and the NEW output folder
    `<session>/photometry_rerun_<UTC>/` (never another run's files, S13).
  - The Qt message boxes become one line under the form and a disabled Start that says why
    (no frames, no target, no comparison, no live solution, ASTAP missing), in the server's
    words.
  - Start begins the `rerun` job and closes the dialog: the job strip shows "Re-running
    photometry · 37 / 195 frames · ETA …" with Cancel (honoured between frames; a cancelled
    run saves no curve, only its per-frame notes when diagnostics are on). The result opens
    as a new run of the session (the integrator).
-->
<script lang="ts">
  import { showTail } from '../../components/tail';
  import { untrack } from 'svelte';
  import Button from '../../components/Button.svelte';
  import Checkbox from '../../components/Checkbox.svelte';
  import Dialog from '../../components/Dialog.svelte';
  import FilePicker from '../../components/FilePicker.svelte';
  import type { FsLister } from '../../components/filepicker';
  import Icon from '../../components/Icon.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import Spinner from '../../components/Spinner.svelte';
  import TextField from '../../components/TextField.svelte';
  import { middleEllipsis } from '../../format/path';
  import type { JobStart, RerunBody, RerunPlan } from './api';
  import { apertureLine, framesLine, paramsLine, paramsRows, rerunBlock, rerunBody, starsLine } from './rerun';

  interface Props {
    open?: boolean;
    /** The session folder (the re-run writes its new folder inside). */
    session: string;
    sessionLabel: string;
    /** The live target set may be used (the source is the live run, D2). */
    liveTargets?: boolean;
    /** Settings diagnostics.enabled (the checkbox's start value). */
    diagnosticsDefault?: boolean;
    getPlan: (body: RerunBody, signal?: AbortSignal) => Promise<RerunPlan>;
    start: (body: RerunBody) => Promise<JobStart>;
    onstarted?: (start: JobStart) => void;
    /** Settings › Photometry (the aperture and reference parameters). */
    onsettings?: () => void;
    list: FsLister;
    /**
     * The session's header site check said mismatch (A68 `site_check`): the re-run computes
     * airmass and BJD_TDB for the Settings site, which was not where the telescope was.
     */
    siteWarning?: string | null;
    preview?: boolean;
  }

  let {
    open = $bindable(false),
    session,
    sessionLabel,
    liveTargets = false,
    diagnosticsDefault = false,
    getPlan,
    start,
    onstarted,
    onsettings,
    list,
    siteWarning = null,
    preview = false,
  }: Props = $props();

  let frames = $state('');
  let targets = $state<'session' | 'live'>('session');
  let reference = $state<'solve' | 'live'>('solve');
  let diagnostics = $state(false);

  $effect(() => {
    if (!open) return;
    untrack(() => {
      frames = '';
      targets = 'session';
      reference = 'solve';
      diagnostics = diagnosticsDefault;
      startError = null;
    });
  });

  // -- Plan ------------------------------------------------------------------------------------
  let plan = $state<RerunPlan | null>(null);
  let planError = $state<string | null>(null);
  let pending = $state(false);
  const body = $derived(rerunBody(session, { frames, targets, reference, diagnostics }));

  $effect(() => {
    if (!open) return;
    const b = body;
    const controller = new AbortController();
    pending = true;
    const timer = setTimeout(() => {
      getPlan(b, controller.signal)
        .then((p) => {
          if (controller.signal.aborted) return;
          plan = p;
          planError = null;
          // The live solution went away: fall back to identifying a frame.
          if (reference === 'live' && !p.reference.live_available) reference = 'solve';
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return;
          planError = err instanceof Error ? err.message : String(err);
        })
        .finally(() => {
          if (!controller.signal.aborted) pending = false;
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  });

  let busy = $state(false);
  let startError = $state<string | null>(null);
  const block = $derived(rerunBlock(plan, planError, pending));

  async function doStart(): Promise<void> {
    if (block || busy) return;
    busy = true;
    startError = null;
    try {
      const s = await start(body);
      open = false;
      onstarted?.(s);
    } catch (err) {
      startError = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }

  let pickerOpen = $state(false);
  const liveReason = $derived.by(() => {
    if (!plan) return planError ? 'the plan could not be read' : 'checking for a live solution…';
    return plan.reference.live_available ? null : 'No live field solution: identify the field in Observe first';
  });
</script>

<Dialog bind:open title="Re-run photometry over saved frames" subtitle={sessionLabel} size="l" {preview} initialFocus=".primary-start button">
  <div class="form">
    <span class="k">Frames</span>
    <div class="v col">
      <div class="path" use:showTail={frames}>
        <TextField
          label="Frames folder"
          hideLabel
          mono
          value={frames}
          placeholder={plan?.frames_dir ? middleEllipsis(plan.frames_dir, 40) : 'the session’s light frames'}
          oninput={(e) => (frames = (e.currentTarget as HTMLInputElement).value)}
        />
        <IconButton icon="browse" label="Choose the frames folder…" size="s" tooltip="top" onclick={() => (pickerOpen = true)} />
      </div>
      {#if plan}
        <span class="line num">{framesLine(plan)}</span>
        {#if plan.frame_names.first}
          <span class="line muted num">{middleEllipsis(plan.frame_names.first, 44)}{plan.frame_names.last && plan.frame_names.last !== plan.frame_names.first ? ` … ${middleEllipsis(plan.frame_names.last, 44)}` : ''}</span>
        {/if}
      {:else if pending}
        <span class="line muted"><Spinner size={12} /> Looking for frames…</span>
      {/if}
    </div>

    <span class="k">Stars</span>
    <div class="v col">
      {#if liveTargets}
        <Segmented
          label="Stars from"
          size="s"
          options={[
            { value: 'session', label: 'Session targets.json' },
            { value: 'live', label: 'Live target set' },
          ]}
          value={targets}
          onchange={(v: 'session' | 'live') => (targets = v)}
        />
      {/if}
      <span class="line">
        {#if plan}<span class="num">{plan.stars.object || '—'}</span> · <span class="num">{starsLine(plan.stars)}</span>{:else}<span class="muted">—</span>{/if}
        <span class="muted"> · {targets === 'live' ? 'the live target set' : 'the session’s targets.json'}</span>
      </span>
    </div>

    <span class="k">Reference</span>
    <div class="v col">
      <Segmented
        label="Reference solution"
        size="s"
        options={[
          { value: 'solve', label: 'Identify the first frame (ASTAP)' },
          { value: 'live', label: 'Live field solution', disabledReason: liveReason },
        ]}
        value={reference}
        onchange={(v: 'solve' | 'live') => {
          if (v === 'live' && liveReason) return;
          reference = v;
        }}
      />
      <span class="line muted">
        {#if reference === 'solve'}
          {plan?.reference.frame ? `ASTAP on ${middleEllipsis(plan.reference.frame, 48)}` : 'ASTAP on the first light frame in time order'}{plan && !plan.reference.astap ? ' · ASTAP is not installed' : ''}
        {:else}
          the field solution of Observe, now
        {/if}
      </span>
    </div>

    <span class="k">Aperture</span>
    <div class="v col">
      <span class="line num">{plan ? apertureLine(plan.params) : '—'}</span>
      {#if plan}
        <dl class="params" aria-label={paramsLine(plan.params, plan.site_set)}>
          {#each paramsRows(plan.params, plan.site_set) as [k, v] (k)}<div><dt>{k}</dt><dd class="num">{v}</dd></div>{/each}
        </dl>
      {/if}
      {#if onsettings}<span class="line"><button type="button" class="link" onclick={() => onsettings?.()}>Settings ›</button></span>{/if}
      {#if siteWarning && plan?.site_set}
        <span class="warn-line"><Icon name="attention" size={14} /><span>The Settings site was not where the telescope was during this run: the re-run computes airmass and BJD<sub>TDB</sub> for the Settings site, so its airmass will be wrong (the FITS header AIRMASS, the mount's, is right).</span></span>
      {/if}
    </div>

    <span class="k">Output</span>
    <div class="v col">
      <span class="line num" title={plan?.out_dir ?? ''}>{plan ? middleEllipsis(plan.out_dir, 64) : '—'}</span>
      <span class="line muted">a new folder in the session: never another run’s files; a cancelled run saves no curve{diagnostics ? ' (only its per-frame notes)' : ''}</span>
    </div>

    <span class="k"></span>
    <div class="v">
      <Checkbox label="Write diagnostics (diagnostics.jsonl)" detail="the per-frame notes: anchors, zero points, skips" checked={diagnostics} onchange={(on) => (diagnostics = on)} />
    </div>
  </div>

  {#snippet footer()}
    <div class="foot">
      <span class="reason" class:error={!!startError || !!plan?.refusal} role={startError || plan?.refusal ? 'alert' : undefined}>{startError ?? block ?? ''}</span>
      <span class="grow"></span>
      <Button label="Cancel" variant="secondary" onclick={() => (open = false)} />
      <span class="primary-start"><Button label="Start" variant="primary" {busy} disabledReason={block} onclick={() => void doStart()} /></span>
    </div>
  {/snippet}
</Dialog>

{#if pickerOpen}
  <FilePicker
    bind:open={pickerOpen}
    mode="open-folder"
    title="Folder of saved frames"
    start={frames.trim() || plan?.frames_dir || session}
    {list}
    countFits
    onchoose={(p) => {
      frames = p;
    }}
  />
{/if}

<style>
  .form {
    display: grid;
    grid-template-columns: 96px minmax(0, 1fr);
    gap: var(--space-4) var(--space-4);
    align-items: baseline;
    font-size: var(--text-s);
  }
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .v {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .v.col {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-1);
  }
  .warn-line {
    display: flex;
    align-items: flex-start;
    gap: var(--space-1);
    max-width: 100%;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .warn-line :global(svg) {
    flex: none;
    margin-top: 1px;
    color: var(--warning);
  }
  .line {
    display: inline-flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1);
    max-width: 100%;
    min-width: 0;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .muted {
    color: var(--text-muted);
  }
  .path {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
  }
  .path :global(.field) {
    flex: 1;
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
  .foot {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    min-width: 0;
  }
  .reason {
    min-width: 0;
    overflow: hidden;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .reason.error {
    color: var(--fg);
    white-space: normal;
  }
  .grow {
    flex: 1;
  }
  /* The run's parameters: a key / value grid, each value with its unit kept together. */
  .params {
    display: flex;
    flex-wrap: wrap;
    gap: 2px var(--space-3);
    margin: 0;
    font-size: var(--text-xs);
  }
  .params div {
    display: inline-flex;
    gap: 4px;
    white-space: nowrap;
  }
  .params dt {
    color: var(--text-muted);
  }
  .params dd {
    margin: 0;
    color: var(--fg);
  }
</style>
