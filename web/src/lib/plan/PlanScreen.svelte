<!--
  Plan screen (06 §2.1-2.4; M68-M77; Q-P1 to Q-P10): built like Observe, rail | centre |
  right rail, no heading row (the rail label and the section's aria-label name it).

  - Toolbar (one 44 px row): [bookmark Presets ▾] [save Save…] · readiness chip (Preflight
    popover) · transport [Start sequence ▾] [Pause | Resume] [Stop] (lib/run) · [arrange].
  - Run strip under the toolbar while a run is engaged, and its outcome after it (lib/run).
  - Centre: the Steps region (totals and end time from the server's derived values, the row
    actions, the column menu, the editable table, the issue list) over the Visibility region
    (the target's altitude over the night with the planned run and a transit's coverage; it
    folds to one 28 px line).
  - Right rail (420 px): Source, Run options, Target set cards, each folding (per viewer);
    the Panels popover shows or hides them and the Visibility region.
  - Locked while a run is active (Q-P9): steps, Run options, Source, preset open; the target
    set and preset saving stay available.
  - Keys: `/` focuses the source search; Mod+S opens Save…; the Steps rows have their own
    (Insert, Mod+D, Delete, Alt+↑↓, Space). No key starts, pauses or stops a run.
-->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import type { PlanIssue, PlanStep } from '../api/plan';
  import { isBoolean, loadPref, savePref } from '../app/prefs';
  import { SectionLayout } from '../app/layout.svelte';
  import { useApp } from '../app/state.svelte';
  import VisibilityTimeline from '../charts/VisibilityTimeline.svelte';
  import ConfirmDialog from '../components/ConfirmDialog.svelte';
  import Button from '../components/Button.svelte';
  import Control from '../components/Control.svelte';
  import FilePicker from '../components/FilePicker.svelte';
  import { ANY_FILTER, type FileFilter } from '../components/filepicker';
  import Icon from '../components/Icon.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Menu from '../components/Menu.svelte';
  import type { MenuEntry } from '../components/menu';
  import PanelsPopover from '../components/PanelsPopover.svelte';
  import { tooltip } from '../components/tooltip';
  import { duration } from '../format/time';
  import type { TargetStar } from '../imaging/field/types';
  import ReadinessChip from '../run/ReadinessChip.svelte';
  import { endAt, isEngaged, startBlock, stateChip } from '../run/run';
  import RunStrip from '../run/RunStrip.svelte';
  import RunTransport from '../run/RunTransport.svelte';
  import LogDrawer from '../shell/LogDrawer.svelte';
  import IssueList from './IssueList.svelte';
  import { frameWord, indexIssues, issueText, LOCKED_REASON, planBlock, rowProgress, type StepCommand, timeTitle, utcHm } from './model';
  import PresetsPopover from './PresetsPopover.svelte';
  import RunOptionsCard from './RunOptionsCard.svelte';
  import SavePresetPopover from './SavePresetPopover.svelte';
  import { planSession } from './session.svelte';
  import SourceCard, { type Programme } from './SourceCard.svelte';
  import StepsTable, { type OptionalColumn } from './StepsTable.svelte';
  import TargetSetCard from './TargetSetCard.svelte';
  import { spansOf } from './transit.svelte';

  const app = useApp();
  const session = planSession(app);
  const store = session.store;
  const transit = session.transit;
  const run = session.run;
  const field = app.field;

  const PLAN_FILTER: FileFilter = { label: 'Sequence preset (.json)', ext: ['.json'] };
  const OPTIONAL: readonly { id: OptionalColumn; label: string; detail?: string }[] = [
    { id: 'interval_s', label: 'Interval' },
    { id: 'cadence_s', label: 'Cadence' },
    { id: 'dither_every', label: 'Dither', detail: 'Moves the mount between frames: for EQ mounts with guiding' },
    { id: 'duration', label: 'Duration' },
  ];
  const isColumns = (v: unknown): v is OptionalColumn[] => Array.isArray(v) && v.every((c) => OPTIONAL.some((o) => o.id === c));
  const isProgramme = (v: unknown): v is Programme => v === 'variable' || v === 'exoplanet' || v === 'other';

  const layout = new SectionLayout('sequencer', {
    panels: { source: true, options: true, targets: true, visibility: true },
    extraKeys: ['argos.card.plan.source', 'argos.card.plan.options', 'argos.card.plan.targets', 'argos.plan.visibility-open', 'argos.plan.columns'],
  });

  // -- Per-viewer choices ----------------------------------------------------------------------
  let programme: Programme = $state(loadPref('argos.plan.programme', isProgramme, 'variable'));
  // Q-P5: the dithering column is hidden by default.
  let columns: OptionalColumn[] = $state(loadPref('argos.plan.columns', isColumns, ['interval_s', 'cadence_s', 'duration']));
  let visOpen = $state(loadPref('argos.plan.visibility-open', isBoolean, true));
  const columnSet = $derived(new Set(columns));

  $effect(() => {
    void layout.generation;
    untrack(() => {
      columns = loadPref('argos.plan.columns', isColumns, ['interval_s', 'cadence_s', 'duration']);
      visOpen = loadPref('argos.plan.visibility-open', isBoolean, true);
    });
  });
  // Settings › "Reset all layouts" (app.layoutGeneration) resets this screen too.
  let seenGeneration = app.layoutGeneration;
  $effect(() => {
    const g = app.layoutGeneration;
    if (g !== seenGeneration) {
      seenGeneration = g;
      untrack(() => layout.reset());
    }
  });

  // -- Server state ------------------------------------------------------------------------------
  onMount(() => {
    void session.refresh();
  });
  // A link that comes back: read the draft and the presets again.
  let wasStale = untrack(() => app.stale);
  $effect(() => {
    const st = app.stale;
    if (wasStale && !st) void untrack(() => session.refresh());
    wasStale = st;
  });

  // Observe changed the object (or a Find did): the draft follows it on its next read (A59).
  $effect(() => {
    const name = app.observation?.object_name;
    untrack(() => {
      if (name && store.doc && !store.pending && !store.locked && name !== store.doc.plan.object_name) void store.load();
    });
  });

  // The preflight follows the plan (its checks read the draft): `preflightKey` below re-reads it
  // after a change settles (plan revision, run state, devices; one request per change).

  const doc = $derived(store.doc);
  const plan = $derived(doc?.plan ?? null);
  const steps = $derived(plan?.steps ?? []);
  const issues = $derived(indexIssues(doc?.issues ?? []));
  const seq = $derived(run.state);
  const locked = $derived(store.locked);
  const lockedReason = $derived(locked ? LOCKED_REASON : null);
  const engaged = $derived(isEngaged(seq));
  const now = $derived(app.clock / 1000);
  const wheel = $derived(doc?.filters.names ?? []);
  const progress = $derived(plan ? rowProgress(plan, seq) : null);
  const observation = $derived(app.observation);
  const targetStars = $derived(field.targets?.stars ?? []);

  // Start: the run store's rule (an engaged run, a preflight block), then the plan's own.
  const planReason = $derived(planBlock(doc));
  const startReason = $derived(
    app.stale ? 'the ARGOS server is not reachable' : (startBlock(seq, run.preflight?.checks ?? null, doc?.issues.filter((i) => i.level === 'error').map((i) => ({ ...i, message: issueText(i) })) ?? []) ?? (planReason ? planReason[0].toUpperCase() + planReason.slice(1) : null)),
  );

  // -- Totals line (A59 derived) -----------------------------------------------------------------
  const totals = $derived.by(() => {
    if (!doc) return null;
    const d = doc.derived;
    const enabled = steps.filter((s) => s.enabled && s.count > 0).length;
    const scheduled = !!plan?.start_at_utc && !!d.start_utc && Date.parse(d.start_utc) > Date.now();
    return {
      steps: `${steps.length} step${steps.length === 1 ? '' : 's'}${enabled !== steps.length ? ` (${enabled} on)` : ''}`,
      frames: `${d.total_frames} ${frameWord(d.total_frames)}`,
      estimate: `≈ ${duration(d.estimate_s)}`,
      start: scheduled ? `${utcHm(d.start_utc)} UTC` : null,
      startTitle: scheduled ? timeTitle(d.start_utc) : '',
      end: d.end_utc && d.total_frames ? `${utcHm(d.end_utc)} UTC` : null,
      endTitle: d.end_utc ? `${timeTitle(d.end_utc)} · a floor: filter moves and autofocus are not counted` : '',
    };
  });

  // -- Row actions -------------------------------------------------------------------------------
  const sel = $derived(store.selected);
  const noSel = $derived(sel === null || sel >= steps.length ? 'select a step first' : null);
  const rowReason = (extra: string | null = null) => lockedReason ?? (doc ? null : 'the plan is not loaded yet') ?? extra;

  function failed(what: string): (err: unknown) => void {
    return (err) => app.reportError(what, err);
  }

  function command(cmd: StepCommand): void {
    if (locked || !doc) return;
    switch (cmd) {
      case 'add':
        store.add(wheel)?.catch(failed('Add a step'));
        break;
      case 'duplicate':
        store.duplicate()?.catch(failed('Duplicate the step'));
        break;
      case 'remove':
        removeSelected();
        break;
      case 'up':
        store.move(-1)?.catch(failed('Move the step'));
        break;
      case 'down':
        store.move(1)?.catch(failed('Move the step'));
        break;
    }
  }

  const stepWords = (s: PlanStep) => `${s.count} × ${s.exposure_s} s ${s.frame_type}${s.frame_type === 'Light' || s.frame_type === 'Flat' ? ` ${s.filter_name}` : ''}`;

  function removeSelected(): void {
    const r = store.remove();
    if (!r) return;
    r.done.then(
      () => app.undo.push({ title: `Removed step ${r.at + 1}`, detail: stepWords(r.removed), undo: () => store.restore(r.removed, r.at) }),
      failed('Remove the step'),
    );
  }

  function edit(i: number, patch: Partial<PlanStep>): Promise<unknown> {
    return store.editStep(i, patch);
  }

  let focusRequest: { step: number; field: string | null; n: number } | null = $state(null);
  let optionsOpen = $state(true);
  let sourceOpen = $state(true);
  let searchInput: HTMLInputElement | null = $state(null);

  function focusIssue(i: PlanIssue): void {
    if (i.step !== null) {
      // An issue in a hidden optional column (an imported Dither, Q-P5) shows the column first.
      const hidden = OPTIONAL.find((o) => o.id === i.field && !columnSet.has(o.id));
      if (hidden) {
        columns = OPTIONAL.map((o) => o.id).filter((x) => x === hidden.id || columnSet.has(x));
        savePref('argos.plan.columns', columns);
        app.toast('info', `${hidden.label} column shown`);
      }
      store.selected = i.step;
      focusRequest = { step: i.step, field: i.field, n: (focusRequest?.n ?? 0) + 1 };
    } else if (i.field && i.field !== 'steps') {
      optionsOpen = true;
      layout.setVisible('options', true);
    }
  }

  // -- Column menu -------------------------------------------------------------------------------
  let colMenuOpen = $state(false);
  let colButton: HTMLElement | null = $state(null);
  const colItems = $derived<MenuEntry[]>([
    { kind: 'header', label: 'Columns' },
    ...OPTIONAL.map((o) => ({ kind: 'checkbox' as const, id: o.id, label: o.label, detail: o.detail, checked: columnSet.has(o.id) })),
  ]);
  function toggleColumn(id: string): void {
    const c = id as OptionalColumn;
    columns = columnSet.has(c) ? columns.filter((x) => x !== c) : OPTIONAL.map((o) => o.id).filter((x) => x === c || columnSet.has(x));
    savePref('argos.plan.columns', columns);
  }

  // -- Replace confirmation (preset, file, transit) ------------------------------------------------
  let replaceAsk: { title: string; message: string; confirm: string; run: () => Promise<unknown> } | null = $state(null);

  function replacing(what: string, action: () => Promise<unknown>, confirm = 'Replace'): void {
    if (!store.unsaved) {
      void action();
      return;
    }
    const n = steps.length;
    replaceAsk = {
      title: 'Replace the current plan?',
      message: `${what} replaces the ${n} step${n === 1 ? '' : 's'} of the plan, which no preset or file holds. Save it first to keep it.`,
      confirm,
      run: action,
    };
  }

  // -- Presets -----------------------------------------------------------------------------------
  let presetsOpen = $state(false);
  let preflightOpen = $state(false);
  let saveOpen = $state(false);
  let saveTrigger: HTMLElement | null = $state(null);
  let presetBusy: string | null = $state(null);
  let picker: 'open' | 'save' | null = $state(null);

  function openPreset(name: string): void {
    replacing(`Opening “${name}”`, async () => {
      presetBusy = name;
      try {
        await store.importPlan({ preset: name });
        presetsOpen = false;
        app.log.push('info', `Plan: preset “${name}” opened`, { source: 'web', topic: 'sequence' });
      } catch (err) {
        app.reportError('Open the preset', err);
      } finally {
        presetBusy = null;
      }
    });
  }

  async function deletePreset(name: string): Promise<void> {
    presetBusy = name;
    try {
      const plan = await store.deletePreset(name);
      app.undo.push({ title: `Deleted the preset “${name}”`, undo: () => store.restorePreset(name, plan) });
    } catch (err) {
      app.reportError('Delete the preset', err);
    } finally {
      presetBusy = null;
    }
  }

  async function savePreset(name: string, overwrite: boolean): Promise<void> {
    await store.savePreset(name, overwrite);
    app.toast('info', `Preset “${name}” saved`, store.presetsDir ?? '');
  }

  /** The FilePicker's choice; a string answer stays in the dialog (the server's words). */
  async function chooseFile(path: string): Promise<unknown> {
    try {
      if (picker === 'open') {
        await store.importPlan({ path });
        app.log.push('info', `Plan: opened ${path}`, { source: 'web', topic: 'sequence' });
      } else {
        // The picker asked "Replace?" for an existing .json; without a suffix the server adds one.
        const written = await store.exportFile(path, /\.json$/i.test(path));
        app.toast('info', 'Plan saved as a file', written);
      }
      picker = null;
      return undefined;
    } catch (err) {
      return err instanceof Error ? err.message : String(err);
    }
  }

  // -- Source ------------------------------------------------------------------------------------
  function setProgramme(p: Programme): void {
    programme = p;
    savePref('argos.plan.programme', p);
  }

  async function findObject(q: string, prog: Programme, signal: AbortSignal): Promise<void> {
    const r = await app.resolveName(q, signal);
    if (signal.aborted) return;
    await app.setTarget({ name: r.name, ra_hours: r.ra_hours, dec_deg: r.dec_deg, object_type: r.object_type, source: r.source, programme: prog });
    app.log.push('info', `Plan: ${r.name} is the observation's target${r.is_variable ? ' and its photometry target' : ''}`, { source: 'web', topic: 'sequence' });
  }

  async function findPlanet(q: string, signal: AbortSignal): Promise<void> {
    const e = await transit.lookup(q, signal);
    if (signal.aborted) return;
    // The telescope points at the host star, never the planet (sequencer_page.py:238-247).
    await app.setTarget({ name: e.host_name, ra_hours: e.ra_hours, dec_deg: e.dec_deg, object_type: 'Exoplanet host', source: e.source, programme: 'exoplanet' });
  }

  function prepareTransit(): void {
    replacing(
      'The transit sequence',
      async () => {
        try {
          const d = await transit.prepare();
          store.adopt(d);
          const st = d.plan.steps[0];
          app.log.push('info', `Plan: transit sequence prepared, ${st?.count ?? 0} light frames at ${st?.cadence_s ?? '?'} s cadence`, { source: 'web', topic: 'sequence' });
        } catch {
          /* the card shows the server's words */
        }
      },
      'Replace with the transit',
    );
  }

  // -- Target set --------------------------------------------------------------------------------
  let removingKey: string | null = $state(null);
  let confirmRemove: TargetStar | null = $state(null);

  function askRemove(s: TargetStar): void {
    if (engaged) confirmRemove = s;
    else void removeStar(s);
  }
  async function removeStar(s: TargetStar): Promise<void> {
    if (removingKey) return;
    removingKey = s.key;
    try {
      const { undo } = await field.remove(app.client, s.key);
      const name = s.display_name || s.name || s.auid || s.key;
      if (undo) app.undo.push({ title: `Removed from the target set: ${name}`, group: 'roles', undo: () => undo.run() });
    } catch (err) {
      app.reportError('Remove from the set', err);
    } finally {
      removingKey = null;
    }
  }
  function openInObserve(s: TargetStar | null): void {
    app.go('imaging');
    if (s && field.candidates.some((c) => c.key === s.key)) field.inspect(s.key);
  }
  function pickInField(): void {
    app.go('imaging');
    app.observe.setMode('field');
    app.observe.setDrawer({ drawerOpen: true, drawerTab: 'variables' });
  }
  async function copyTsv(tsv: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(tsv);
      app.toast('info', 'Target set copied', `${targetStars.length} rows as TSV`);
    } catch {
      app.toast('warning', 'Copy refused by the browser');
    }
  }

  // -- Visibility --------------------------------------------------------------------------------
  const visTarget = $derived.by(() => {
    if (programme === 'exoplanet' && transit.planet) return { ra_hours: transit.planet.ra_hours, dec_deg: transit.planet.dec_deg, name: transit.planet.host_name };
    const t = observation?.target;
    return t ? { ra_hours: t.ra_hours, dec_deg: t.dec_deg, name: t.name } : null;
  });
  const visNight = $derived(programme === 'exoplanet' ? (transit.prediction?.night?.date ?? null) : null);
  $effect(() => {
    const t = visTarget;
    const n = visNight;
    if (!layout.visible('visibility') || !visOpen) return;
    void untrack(() => session.loadVisibility(t, n));
  });
  const runSpan = $derived.by(() => {
    let span: { start: number; end: number } | null = null;
    if (seq && engaged && seq.started_t !== null) {
      const end = endAt(seq, now);
      span = end !== null ? { start: seq.started_t, end } : null;
    } else if (seq && seq.state === 'waiting' && seq.start_at_t !== null && doc) {
      // Scheduled from the transport (Start at…): the run starts then, whatever the draft says.
      span = { start: seq.start_at_t, end: seq.start_at_t + doc.derived.estimate_s };
    } else {
      const d = doc?.derived;
      if (d?.start_utc && d.end_utc && d.total_frames) span = { start: Date.parse(d.start_utc) / 1000, end: Date.parse(d.end_utc) / 1000 };
    }
    // Another night on the plot (a transit's): the planned run is not on it.
    const v = session.vis;
    if (span && v && (span.end < v.t[0] || span.start > v.t[v.t.length - 1])) return null;
    return span;
  });
  const transitSpan = $derived(programme === 'exoplanet' && transit.prediction ? spansOf(transit.prediction) : null);
  const showNow = $derived(!visNight || (session.vis !== null && now >= session.vis.t[0] && now <= session.vis.t[session.vis.t.length - 1]));

  function setVisOpen(v: boolean): void {
    visOpen = v;
    savePref('argos.plan.visibility-open', v);
  }

  // -- The palette (W6a): "Open a sequence preset…", "Check the run before starting" ------------
  $effect(() => {
    const req = app.planRequest;
    if (!req) return;
    untrack(() => {
      app.planRequest = null;
      if (req === 'presets') presetsOpen = true;
      else {
        preflightOpen = true;
        void run.loadPreflight(app.client);
      }
    });
  });

  // The preflight follows the plan and the equipment: checked again (debounced) after each
  // accepted plan revision, a device change or a run's state change, never per keystroke.
  const preflightKey = $derived(
    `${doc?.revision ?? ''}|${seq?.state ?? ''}|${Object.values(app.devices ?? {})
      .map((d) => (d && typeof d === 'object' && 'state' in d ? String(d.state) : ''))
      .join(',')}`,
  );
  let preflightSeen = '';
  $effect(() => {
    const key = preflightKey;
    if (key === preflightSeen) return;
    const t = setTimeout(() => {
      preflightSeen = key;
      void run.loadPreflight(app.client);
    }, 600);
    return () => clearTimeout(t);
  });

  // -- Keys --------------------------------------------------------------------------------------
  $effect(() => {
    const offs = [
      app.shortcuts.handle('plan.search', () => {
        sourceOpen = true;
        layout.setVisible('source', true);
        queueMicrotask(() => searchInput?.focus());
      }),
      app.shortcuts.handle('plan.save', () => (saveOpen = true)),
    ];
    return () => offs.forEach((f) => f());
  });

  const shown = (id: string) => layout.visible(id);
</script>

<div class="plan" style:grid-template-rows="auto auto minmax(0, 1fr) {app.logOpen ? '216px' : '0px'}">
  <div class="toolbar" role="toolbar" aria-label="Plan">
    <PresetsPopover
      bind:open={presetsOpen}
      presets={store.presets}
      directory={store.presetsDir}
      error={store.presetsError}
      openReason={lockedReason}
      busy={presetBusy}
      onshow={() => void store.loadPresets()}
      onopen={openPreset}
      ondelete={(n) => void deletePreset(n)}
      onfile={() => {
        presetsOpen = false;
        replacing('Opening a file', async () => (picker = 'open'));
      }}
    />
    <SavePresetPopover
      bind:open={saveOpen}
      bind:trigger={saveTrigger}
      suggested={store.baseline && !store.baseline.name.includes('/') ? store.baseline.name : (plan?.object_name ?? '')}
      onsave={savePreset}
      onfile={() => {
        saveOpen = false;
        picker = 'save';
      }}
    />
    <span class="grow"></span>
    <ReadinessChip bind:open={preflightOpen} running={engaged ? stateChip(seq).label : false} items={run.preflight?.checks ?? null} error={run.preflightError} onrefresh={() => void run.loadPreflight(app.client)} />
    <RunTransport
      {seq}
      {now}
      {startReason}
      suggestedStart={programme === 'exoplanet' && transit.prediction ? Date.parse(transit.prediction.utc.coverage_start) / 1000 : null}
      draftStartAt={plan?.start_at_utc ? Date.parse(plan.start_at_utc) / 1000 : null}
      onstart={(at) => run.start(at, app.client)}
      onpause={() => run.pause(app.client)}
      onresume={() => run.resume(app.client)}
      onstop={() => run.stop(app.client)}
      onerror={(m) => app.toast('error', 'Sequence refused', m)}
    />
    <span class="divider" aria-hidden="true"></span>
    <PanelsPopover
      section="Plan"
      {layout}
      groups={[
        { title: 'Right rail', panels: [{ id: 'source', label: 'Source' }, { id: 'options', label: 'Run options' }, { id: 'targets', label: 'Target set' }] },
        { title: 'Centre', panels: [{ id: 'visibility', label: 'Visibility' }] },
      ]}
      onreset={() => app.toast('info', 'Plan layout restored')}
    />
  </div>

  <div class="strip">
    <RunStrip {seq} {now} frameTimes={run.frameTimes} lastSaved={run.lastSaved} showOutcome={run.outcomeVisible} ondismiss={() => run.dismissOutcome()} onlog={() => app.setLogOpen(true)} />
  </div>

  <div class="workspace">
    <div class="center" class:vis-open={shown('visibility') && visOpen}>
      <section class="steps" aria-label="Steps">
        <div class="region-head">
          <span class="title"><Icon name="nav-sequencer" size={16} /><span class="caps">Steps</span></span>
          {#if totals}
            <span class="totals num" aria-live="polite">
              <span>{totals.steps}</span><span class="dot">·</span><span>{totals.frames}</span><span class="dot">·</span><span use:tooltip={{ text: 'Estimate from the server: exposure + interval + 3 s per frame, or the cadence; filter moves and autofocus not counted', placement: 'bottom' }}>{totals.estimate}</span>
              {#if totals.start}<span class="dot">·</span><span use:tooltip={{ text: totals.startTitle, placement: 'bottom' }}>starts {totals.start}</span>{/if}
              {#if totals.end && !engaged}<span class="dot">·</span><span use:tooltip={{ text: totals.endTitle, placement: 'bottom' }}>ends ≈ {totals.end}</span>{/if}
              {#if store.pending}<span class="muted"> · saving…</span>{/if}
            </span>
          {/if}
          {#if locked}<span class="lock" role="status" use:tooltip={{ text: 'Steps, run options, the source and opening a preset wait for the end of the run; the target set and saving a preset stay available (Q-P9)', placement: 'bottom' }}>Locked while a run is scheduled or running</span>{/if}
          <span class="grow"></span>
          <div class="row-actions" role="group" aria-label="Step actions">
            <IconButton icon="add" label="Add a step" size="s" variant="ghost" tooltip="bottom" shortcut="Insert" disabledReason={rowReason()} onclick={() => command('add')} />
            <IconButton icon="duplicate" label="Duplicate the step" size="s" variant="ghost" tooltip="bottom" shortcut="Mod+D" disabledReason={rowReason(noSel)} onclick={() => command('duplicate')} />
            <IconButton icon="remove" label="Remove the step" size="s" variant="ghost" tooltip="bottom" shortcut="Delete" disabledReason={rowReason(noSel)} onclick={() => command('remove')} />
            <IconButton icon="move-up" label="Move the step up" size="s" variant="ghost" tooltip="bottom" shortcut="Alt+ArrowUp" disabledReason={rowReason(noSel ?? (sel === 0 ? 'already the first step' : null))} onclick={() => command('up')} />
            <IconButton icon="move-down" label="Move the step down" size="s" variant="ghost" tooltip="bottom" shortcut="Alt+ArrowDown" disabledReason={rowReason(noSel ?? (sel === steps.length - 1 ? 'already the last step' : null))} onclick={() => command('down')} />
            <span class="anchor" bind:this={colButton}>
              <Control label="Columns" showLabel size="s" variant="ghost" tooltip="none" aria-haspopup="menu" aria-expanded={colMenuOpen} onclick={() => (colMenuOpen = !colMenuOpen)} />
            </span>
            <Menu bind:open={colMenuOpen} anchor={colButton} items={colItems} label="Columns" keepOpenOnCheck onselect={(it) => toggleColumn(it.id)} placement="bottom-end" />
          </div>
        </div>
        <div class="table-scroll">
          {#if store.loadError && !doc}
            <p class="empty bad" role="alert">The plan could not be read: {store.loadError}</p>
          {:else if !doc}
            <p class="empty">Reading the plan…</p>
          {:else if !steps.length}
            <div class="empty">
              <span>No steps yet.</span>
              <Button label="Add a step" size="s" disabledReason={rowReason()} onclick={() => command('add')} />
              <Button label="Open a preset…" size="s" disabledReason={lockedReason} onclick={() => (presetsOpen = true)} />
            </div>
          {:else}
            <StepsTable
              {steps}
              keys={store.ids}
              perStep={doc.derived.per_step_s}
              {issues}
              selected={store.selected}
              {wheel}
              wheelSource={doc.filters.source === 'wheel' ? 'wheel' : doc.filters.source === 'profile' ? "profile's slots" : 'default slots'}
              columns={columnSet}
              {locked}
              {progress}
              active={seq?.step_index ?? null}
              onedit={edit}
              oncommand={command}
              onreorder={(from, to) => store.reorder(from, to)?.catch(failed('Move the step'))}
              onselect={(i) => (store.selected = i)}
              {focusRequest}
            />
          {/if}
        </div>
        <IssueList issues={doc?.issues ?? []} notes={doc?.notes ?? []} onfocus={focusIssue} />
      </section>

      {#if shown('visibility')}
        <section class="visibility" class:folded={!visOpen} aria-label="Visibility">
          {#if visOpen}
            <VisibilityTimeline
              vis={session.vis}
              empty={session.visEmpty}
              target={visTarget?.name ?? null}
              run={runSpan}
              transit={transitSpan}
              frames={run.frameTimes}
              nFrames={run.frameTimes.length}
              now={showNow ? now : null}
              theme={app.theme}
              onsite={() => {
                app.settingsCategory = 'observer_site';
                app.go('configuration');
              }}
            />
            <span class="fold"><Control icon="disclosure" label="Fold the visibility" size="xs" variant="ghost" tooltip="left" onclick={() => setVisOpen(false)} /></span>
          {:else}
            <button type="button" class="folded-line" aria-expanded="false" onclick={() => setVisOpen(true)}>
              <span class="chev" aria-hidden="true"><Icon name="disclosure" size={12} /></span>
              <Icon name="visibility" size={16} /><span class="caps">Visibility</span>
              <span class="muted">{visTarget?.name ?? 'no source'}{session.vis?.peak ? ` · peak ${Math.round(session.vis.peak.alt)}°` : ''}</span>
            </button>
          {/if}
        </section>
      {/if}
    </div>

    <aside class="rail" aria-label="Plan panels">
      {#if shown('source')}
        <SourceCard
          bind:open={sourceOpen}
          bind:searchInput
          {programme}
          onprogramme={setProgramme}
          {observation}
          {transit}
          filters={wheel}
          filterSource={doc?.filters.source ?? 'wheel'}
          {lockedReason}
          suggestNames={(q, signal) => app.suggestNames(q, signal)}
          suggestPlanets={(q, signal) => session.api.exoplanetSuggest(q, signal)}
          {findObject}
          {findPlanet}
          onprepare={prepareTransit}
          onobserve={() => app.go('imaging')}
        />
      {/if}
      {#if shown('options')}
        <RunOptionsCard bind:open={optionsOpen} {plan} {issues} {lockedReason} focuser={app.devices?.focuser?.state === 'connected' || app.devices?.focuser?.state === 'busy'} onset={(p) => store.setOptions(p)} />
      {/if}
      {#if shown('targets')}
        <TargetSetCard
          stars={targetStars}
          object={field.targets?.object_name ?? observation?.object_name ?? null}
          removing={removingKey}
          onremove={askRemove}
          onpick={(s) => openInObserve(s)}
          onfield={pickInField}
          oncopy={(t) => void copyTsv(t)}
        />
      {/if}
      {#if !shown('source') && !shown('options') && !shown('targets')}
        <p class="rail-empty">Every card is hidden: show them again from Panels at the right of the toolbar.</p>
      {/if}
    </aside>
  </div>

  {#if app.logOpen}<LogDrawer label="Plan drawer" />{/if}
</div>

<FilePicker
  open={picker !== null}
  mode={picker === 'save' ? 'save-file' : 'open-file'}
  title={picker === 'save' ? 'Save the plan as a file' : 'Open a plan file'}
  start={store.presetsDir}
  list={app.listFiles}
  filters={[PLAN_FILTER, ANY_FILTER]}
  defaultName={`${(plan?.object_name || 'plan').replace(/[\\/:*?"<>|]+/g, '_')}.json`}
  onchoose={chooseFile}
  onclose={() => (picker = null)}
/>

<ConfirmDialog
  open={replaceAsk !== null}
  title={replaceAsk?.title ?? ''}
  message={replaceAsk?.message}
  confirmLabel={replaceAsk?.confirm ?? 'Replace'}
  cancelLabel="Keep the plan"
  destructive
  onconfirm={async () => {
    const a = replaceAsk;
    replaceAsk = null;
    if (a) await a.run();
  }}
  oncancel={() => (replaceAsk = null)}
/>

<ConfirmDialog
  open={confirmRemove !== null}
  title="Remove {confirmRemove?.display_name || confirmRemove?.name || 'the star'} during the run?"
  message="The ensemble of every following frame changes (its zero point for a comparison). Undo puts the star back."
  confirmLabel="Remove from the set"
  cancelLabel="Keep it"
  destructive
  onconfirm={() => {
    const s = confirmRemove;
    confirmRemove = null;
    if (s) void removeStar(s);
  }}
  oncancel={() => (confirmRemove = null)}
/>

<style>
  .plan {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    height: 100%;
    min-width: 0;
    min-height: 0;
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: var(--toolbar-h);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg);
    min-width: 0;
  }
  .grow {
    flex: 1;
  }
  .strip {
    min-width: 0;
  }
  .divider {
    width: 1px;
    height: 20px;
    background: var(--border-soft);
  }
  .workspace {
    display: grid;
    grid-template-columns: minmax(0, 1fr) var(--rail-w);
    min-height: 0;
  }
  .center {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    border-right: var(--border-w) solid var(--border);
  }
  .steps {
    display: flex;
    flex-direction: column;
    flex: 1 1 auto;
    min-height: 0;
  }
  /* With the timeline open, Steps takes its content (at least about 6 rows) and the timeline
     the rest: no dead band under a short plan (design review W6a, BRAND 11.1). */
  .center.vis-open .steps {
    flex: 0 1 auto;
  }
  .center.vis-open .table-scroll {
    min-height: 180px;
  }
  .region-head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: 36px;
    padding: 0 var(--space-2) 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    font-size: var(--text-s);
    color: var(--fg);
    min-width: 0;
  }
  .title {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--fg-muted);
  }
  .caps {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .totals {
    display: inline-flex;
    gap: var(--space-1);
    white-space: nowrap;
    overflow: hidden;
    min-width: 0;
  }
  .totals .dot,
  .muted {
    color: var(--text-muted);
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .lock {
    flex: none;
    padding: 1px var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .row-actions {
    display: inline-flex;
    align-items: center;
    gap: 2px;
  }
  .anchor {
    display: inline-flex;
  }
  .table-scroll {
    flex: 1 1 auto;
    min-height: 0;
    overflow: auto;
  }
  .empty {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-3);
    margin: 0;
    padding: var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .empty.bad {
    color: var(--fg);
  }
  .visibility {
    position: relative;
    flex: 1 1 240px;
    min-height: 240px;
    border-top: var(--border-w) solid var(--border);
  }
  .visibility.folded {
    flex: none;
    min-height: 0;
    height: 28px;
  }
  .fold {
    position: absolute;
    top: 1px;
    right: var(--space-1);
    z-index: 4;
  }
  /* Room for the fold button at the end of the timeline's own header line. */
  .visibility :global(.vis > .head) {
    padding-right: 36px;
  }
  .folded-line {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    height: 100%;
    padding: 0 var(--space-3);
    border: 0;
    background: var(--bg-2);
    color: var(--fg-muted);
    font: inherit;
    font-size: var(--text-xs);
    text-align: left;
    cursor: pointer;
  }
  .folded-line:hover {
    background: var(--hover-bg);
  }
  .folded-line:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .chev {
    display: inline-flex;
    transform: rotate(-90deg);
  }
  .rail {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-height: 0;
    min-width: 0;
    padding: var(--space-4);
    background: var(--bg-2);
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .rail-empty {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
    line-height: var(--leading-relaxed);
  }
</style>
