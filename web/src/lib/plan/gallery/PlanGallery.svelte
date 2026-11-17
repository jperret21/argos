<!--
  Component gallery, wave 6a, the Plan screen (development only, part of /?gallery=1): the
  Steps table (plan, issues kept as typed, running and locked, empty, the dither column), the
  issue list, the Source card (variable star, exoplanet transit, lookup refusal, locked), the
  Run options card (plain, issues, locked), the Presets and Save popovers (list, empty,
  refusal, the replace confirmation), the Target set card and the source search with its
  suggestions, on deterministic data (fixtures.ts). The first table is live on an in-memory
  plan with the server's rules for range and cadence, so editing, the keys and the issues
  can be tried. Sections are [data-gallery="w6-plan-<name>"] for element screenshots.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { PlanApi, type PlanIssue, type PlanStep, type SequencePlan } from '../../api/plan';
  import { STARS } from '../../imaging/photometry/gallery/fixtures';
  import IssueList from '../IssueList.svelte';
  import { indexIssues, type StepCommand } from '../model';
  import { PlanStore } from '../plan.svelte';
  import PresetsPopover from '../PresetsPopover.svelte';
  import RunOptionsCard from '../RunOptionsCard.svelte';
  import SavePresetPopover from '../SavePresetPopover.svelte';
  import SourceCard from '../SourceCard.svelte';
  import SourceSearch from '../SourceSearch.svelte';
  import StepsTable, { type OptionalColumn } from '../StepsTable.svelte';
  import TargetSetCard from '../TargetSetCard.svelte';
  import { TRANSIT_DEFAULTS, TransitPlanner } from '../transit.svelte';
  import { BAD_ISSUES, BAD_STEPS, DOC, ISSUES_BAD, ISSUES_OK, OBSERVATION, PER_STEP, PLAN, PLAN_BAD, PLANET_ONLY, PREDICTION, PRESETS, PROGRESS, STEPS, WHEEL } from './fixtures';

  const noop = () => undefined;
  const none = async () => [] as string[];
  const never = () => new Promise<never>(() => undefined);
  const COLS = new Set<OptionalColumn>(['interval_s', 'cadence_s', 'duration']);
  const COLS_DITHER = new Set<OptionalColumn>(['interval_s', 'cadence_s', 'dither_every', 'duration']);

  // -- A live table on an in-memory plan (the server's range and cadence rules) ------------------
  function issuesOf(p: SequencePlan): PlanIssue[] {
    const out: PlanIssue[] = [];
    p.steps.forEach((s, i) => {
      if (s.exposure_s < 0.01 || s.exposure_s > 600) out.push({ step: i, field: 'exposure_s', code: 'out_of_range', level: 'error', message: `Exposure ${s.exposure_s} s is outside the camera range 0.01-600 s.` });
      if (s.gain < 0 || s.gain > 600) out.push({ step: i, field: 'gain', code: 'out_of_range', level: 'error', message: `Gain ${s.gain} is outside 0-600.` });
      if (s.count < 1 || s.count > 9999) out.push({ step: i, field: 'count', code: 'out_of_range', level: 'error', message: `Count ${s.count} is outside 1-9999.` });
      if (s.cadence_s !== null && s.cadence_s < s.exposure_s) out.push({ step: i, field: 'cadence_s', code: 'cadence_short', level: 'error', message: `Cadence ${s.cadence_s} s is shorter than the ${s.exposure_s} s exposure.` });
      if (s.cadence_s !== null && s.interval_s > 0) out.push({ step: i, field: 'interval_s', code: 'interval_ignored', level: 'warning', message: 'A cadence is set: the interval is not used.' });
    });
    return out;
  }
  let revision = 1;
  const live = new PlanStore(
    new PlanApi({
      request: async <T,>(method: string, _path: string, body?: unknown): Promise<T> => {
        const plan = method === 'PUT' ? (body as SequencePlan) : PLAN;
        return { ...DOC, plan, derived: { ...DOC.derived, per_step_s: PER_STEP(plan.steps) }, issues: issuesOf(plan), revision: ++revision } as T;
      },
    }),
  );
  void live.load();
  const liveIssues = $derived(indexIssues(live.doc?.issues ?? []));
  function liveCommand(cmd: StepCommand): void {
    if (cmd === 'add') live.add(WHEEL);
    else if (cmd === 'duplicate') live.duplicate();
    else if (cmd === 'remove') live.remove();
    else if (cmd === 'up') live.move(-1);
    else if (cmd === 'down') live.move(1);
  }

  // -- Transit planners frozen in a state ----------------------------------------------------------
  const quiet = new PlanApi({ request: never });
  function planner(state: Partial<Pick<TransitPlanner, 'planet' | 'prediction' | 'predictError' | 'predicting'>>): TransitPlanner {
    const t = new TransitPlanner(quiet);
    untrack(() => {
      t.form = { ...TRANSIT_DEFAULTS, planet: 'HD 189733 b', filter_name: 'IR' };
      Object.assign(t, state);
    });
    return t;
  }
  const tPredicted = planner({ planet: PLANET_ONLY, prediction: PREDICTION });
  const tEmpty = planner({});
  const tRefused = planner({ planet: PLANET_ONLY, predictError: 'No transit of HD 189733 b is observable from this site above 30° in the next 366 days.' });
  const blank = planner({});
  untrack(() => (blank.form = { ...TRANSIT_DEFAULTS }));

  const stepsOf = (s: readonly PlanStep[]) => s;
</script>

<section data-gallery="w6-plan-steps" id="w6-plan-steps">
  <h2>Steps table <span>explicit editors (On, Type and Filter as token-drawn menus, NumberFields), Duration from the server, the selection one brass edge, the active run row neutral; nothing clamped: a value out of range stays and the server's issue outlines its cell, with the words under the row</span></h2>
  <div class="row top">
    <figure class="centre">
      <div class="table-demo">
        {#if live.doc}
          <StepsTable steps={live.steps} keys={live.ids} perStep={live.doc.derived.per_step_s} issues={liveIssues} selected={live.selected} wheel={WHEEL} columns={COLS} onedit={(i, p) => live.editStep(i, p)} oncommand={liveCommand} onreorder={(f, t) => live.reorder(f, t)} onselect={(i) => (live.selected = i)} />
        {/if}
      </div>
      <IssueList issues={live.doc?.issues ?? []} onfocus={noop} />
      <figcaption>live: type 900 in an exposure, or a cadence under the exposure; Insert, {navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'}+D, Delete, Alt+↑↓ and Space on a focused row; drag a row by its number</figcaption>
    </figure>
  </div>
  <div class="row top">
    <figure class="centre">
      <div class="table-demo tall"><StepsTable steps={stepsOf(BAD_STEPS)} perStep={PER_STEP(BAD_STEPS)} issues={ISSUES_BAD} selected={1} wheel={WHEEL} columns={COLS} onedit={async () => undefined} oncommand={noop} onreorder={noop} onselect={noop} /></div>
      <IssueList issues={BAD_ISSUES} notes={['Planning metadata not restored: use Prepare transit for tonight’s window.']} onfocus={noop} />
      <figcaption>issues: 9999 s kept as typed (out of range), a cadence shorter than its exposure, a filter the wheel does not have (listed, flagged, never replaced), Light on the opaque slot (warning, dashed)</figcaption>
    </figure>
  </div>
  <div class="row top">
    <figure class="centre">
      <div class="table-demo"><StepsTable steps={STEPS} perStep={PER_STEP(STEPS)} issues={ISSUES_OK} selected={null} wheel={WHEEL} columns={COLS} locked progress={PROGRESS} active={1} onedit={async () => undefined} oncommand={noop} onreorder={noop} onselect={noop} /></div>
      <figcaption>running (locked, Q-P9): plain values, step 1 done 30/30, step 2 active 7/10 (neutral bar), the Dark step skipped</figcaption>
    </figure>
  </div>
  <div class="row top">
    <figure class="centre">
      <div class="table-demo short"><StepsTable steps={STEPS.slice(0, 2)} perStep={PER_STEP(STEPS)} issues={ISSUES_OK} selected={0} wheel={WHEEL} columns={COLS_DITHER} onedit={async () => undefined} oncommand={noop} onreorder={noop} onselect={noop} /></div>
      <figcaption>the column menu with Dither shown (hidden by default, Q-P5: it moves the mount between frames)</figcaption>
    </figure>
    <figure>
      <p class="empty-demo">No steps. Add a step (Insert) or open a preset.</p>
      <figcaption>empty plan: Start is disabled with “Add a step or open a preset”</figcaption>
    </figure>
  </div>
</section>

<section data-gallery="w6-plan-source" id="w6-plan-source">
  <h2>Source card <span>programme, one search field (catalogue by programme), the target found; the transit: mid-transit in BJD_TDB (5 decimals, 6 on hover), coverage local and UTC, altitudes, what limits it, the transits skipped (Q-P10)</span></h2>
  <div class="row top">
    <figure class="rail"><SourceCard programme="variable" onprogramme={noop} observation={OBSERVATION} transit={blank} filters={WHEEL} suggestNames={none} suggestPlanets={none} findObject={never} findPlanet={never} onprepare={noop} onobserve={noop} /><figcaption>variable star found: the observation's target, a link to Observe (it never slews from here)</figcaption></figure>
    <figure class="rail"><SourceCard programme="exoplanet" onprogramme={noop} observation={OBSERVATION} transit={tPredicted} filters={WHEEL} suggestNames={none} suggestPlanets={none} findObject={never} findPlanet={never} onprepare={noop} onobserve={noop} /><figcaption>exoplanet: the next observable transit, its coverage end below 30° said in words, 3 earlier transits skipped</figcaption></figure>
    <figure class="rail"><SourceCard programme="exoplanet" onprogramme={noop} observation={null} transit={tRefused} filters={WHEEL} suggestNames={none} suggestPlanets={none} findObject={never} findPlanet={never} onprepare={noop} onobserve={noop} /><figcaption>no observable transit: the server's words, Prepare disabled with the reason</figcaption></figure>
  </div>
  <div class="row top">
    <figure class="rail"><SourceCard programme="other" onprogramme={noop} observation={null} transit={tEmpty} filters={WHEEL} suggestNames={none} suggestPlanets={none} findObject={never} findPlanet={never} onprepare={noop} onobserve={noop} /><figcaption>other object, nothing found yet</figcaption></figure>
    <figure class="rail"><SourceCard programme="variable" onprogramme={noop} observation={OBSERVATION} transit={blank} filters={WHEEL} lockedReason="Locked while the sequence runs" suggestNames={none} suggestPlanets={none} findObject={never} findPlanet={never} onprepare={noop} onobserve={noop} /><figcaption>locked while a run is active (Q-P9): the search says why</figcaption></figure>
    <figure class="rail">
      <div class="search-demo"><SourceSearch label="Variable star" placeholder="T CrB, RR Lyr…" current="" suggest={none} lookup={never} pin={{ text: 'RR', names: ['RR Lyr', 'RR Tau', 'RR Boo', 'RR Cet'], active: 1 }} /></div>
      <div class="search-demo"><SourceSearch label="Exoplanet" placeholder="HD 189733 b…" current="" suggest={none} lookup={never} pin={{ text: 'HD 189733 c', error: 'No planet named “HD 189733 c” in the NASA Exoplanet Archive.' }} /></div>
      <div class="search-demo"><SourceSearch label="Exoplanet" placeholder="HD 189733 b…" current="" suggest={none} lookup={never} pin={{ text: 'WASP-12 b', looking: true }} /></div>
      <figcaption>the search: suggestions (token-drawn, ↑ ↓), a refusal in the server's words, a lookup in progress (read-only, spinning glyph)</figcaption>
    </figure>
  </div>
</section>

<section data-gallery="w6-plan-options" id="w6-plan-options">
  <h2>Run options card <span>object shared with Observe, repeat, autofocus, end of run; each issue under its field, the value kept</span></h2>
  <div class="row top">
    <figure class="rail"><RunOptionsCard plan={PLAN} issues={ISSUES_OK} focuser onset={async () => undefined} /><figcaption>plain: park at the end</figcaption></figure>
    <figure class="rail"><RunOptionsCard plan={PLAN_BAD} issues={ISSUES_BAD} focuser={false} onset={async () => undefined} /><figcaption>issues: repeat 0 kept and flagged, no object (warning), autofocus without a focuser said</figcaption></figure>
    <figure class="rail"><RunOptionsCard plan={PLAN} issues={ISSUES_OK} focuser lockedReason="Locked while the sequence runs" onset={async () => undefined} /><figcaption>locked while a run is active</figcaption></figure>
  </div>
</section>

<section data-gallery="w6-plan-presets" id="w6-plan-presets">
  <h2>Presets and Save <span>the server's list (Qt's files), a file Qt cannot read listed with its reason, Open file… and Save as file… (FilePicker), the overwrite asked in place</span></h2>
  <div class="row top">
    <figure><PresetsPopover preview presets={PRESETS} directory="~/Argos/sequences" onopen={noop} ondelete={noop} onfile={noop} /><figcaption>list</figcaption></figure>
    <figure><PresetsPopover preview presets={PRESETS} filter="transit" onopen={noop} ondelete={noop} onfile={noop} /><figcaption>filtered</figcaption></figure>
    <figure><PresetsPopover preview presets={PRESETS} openReason="Locked while the sequence runs" onopen={noop} ondelete={noop} onfile={noop} /><figcaption>during a run: opening refused with the reason, deleting stays</figcaption></figure>
  </div>
  <div class="row top">
    <figure><PresetsPopover preview presets={[]} onopen={noop} ondelete={noop} onfile={noop} /><figcaption>empty</figcaption></figure>
    <figure><SavePresetPopover preview suggested="T CrB nightly" onsave={async () => undefined} onfile={noop} /><figcaption>Save…</figcaption></figure>
    <figure><SavePresetPopover preview suggested="T CrB nightly" pin={{ name: 'T CrB nightly', replace: true }} onsave={async () => undefined} onfile={noop} /><figcaption>the preset exists (409 file_exists): replace asked in place</figcaption></figure>
    <figure><SavePresetPopover preview suggested="" pin={{ name: 'a/b', error: 'A preset name cannot contain / \\ : * ? " < > |.' }} onsave={async () => undefined} onfile={noop} /><figcaption>a name refused in the server's words</figcaption></figure>
  </div>
</section>

<section data-gallery="w6-plan-targets" id="w6-plan-targets">
  <h2>Target set card <span>TargetSetList (D24): roles as shapes, counts in the header, Copy TSV, Pick in field; editable during a run</span></h2>
  <div class="row top">
    <figure class="rail tall"><TargetSetCard stars={STARS} object="XX Cyg" onremove={noop} onpick={noop} onfield={noop} oncopy={noop} /><figcaption>a set: target, comparisons folded, check</figcaption></figure>
    <figure class="rail"><TargetSetCard stars={[]} object="T CrB" onremove={noop} onpick={noop} onfield={noop} oncopy={noop} /><figcaption>empty: what to do</figcaption></figure>
  </div>
</section>

<style>
  section {
    padding: var(--space-5) var(--space-6);
    border-bottom: var(--border-w) solid var(--border);
  }
  h2 {
    margin: 0 0 var(--space-4);
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  h2 span {
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-regular);
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-5);
  }
  .row + .row {
    margin-top: var(--space-5);
  }
  .row.top {
    align-items: flex-start;
  }
  figure {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
  }
  figcaption {
    color: var(--text-muted);
    font-size: var(--text-xs);
    max-width: 900px;
  }
  .rail {
    width: 400px;
    padding: var(--space-4);
    background: var(--bg-2);
  }
  .rail.tall {
    height: 420px;
  }
  .centre {
    width: 928px;
  }
  .table-demo {
    height: 168px;
    overflow: auto;
    border: var(--border-w) solid var(--border-soft);
    background: var(--bg);
  }
  .table-demo.tall {
    height: 236px;
  }
  .table-demo.short {
    height: 96px;
  }
  .empty-demo {
    width: 320px;
    margin: 0;
    padding: var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    background: var(--bg);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .search-demo {
    margin-bottom: var(--space-2);
  }
  .search-demo:first-child {
    margin-bottom: 190px;
  }
</style>
