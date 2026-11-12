<!--
  Steps table (06 §2.2 rows 1.4 #1-#15, §2.3.1-2.3.2, README 3.5): the only editable table.

  - One row per step with explicit editors: On (checkbox), Type and Filter (token-drawn menus,
    never a native select), Exposure, Gain, Count, Interval, Cadence, Dither
    (NumberField: Enter / blur / a pause after steps sends one value; the wheel acts only on a
    focused field, 06 P27), and the Duration the server derives.
  - Nothing is clamped or substituted: an unknown type or filter is listed as it is and
    flagged; a value out of range is kept and the server's issue outlines the cell, with the
    words under the row (06 P11, P30).
  - Selection is explicit (06 P19): a click on the row (or on its number), or the focus in one
    of its fields. Keys on a focused row: ↑ ↓ Home End move, Insert adds, Mod+D duplicates,
    Delete removes (Undo toast), Alt+↑↓ moves, Space toggles On. Rows are reordered by
    dragging their number.
  - While a run is active the cells are plain values (Q-P9) and each row says its progress:
    done n/N, the active one, waiting, skipped.
-->
<script lang="ts">
  import { tick } from 'svelte';
  import { DARK_SLOT, FRAME_TYPES, type PlanStep } from '../api/plan';
  import NumberField from '../components/NumberField.svelte';
  import Select from '../components/Select.svelte';
  import { tooltip } from '../components/tooltip';
  import { fixed, int } from '../format/number';
  import { duration } from '../format/time';
  import { FIELD_LABELS, type IssueIndex, issueText, isKnownType, optionsWith, type RowRun, type StepCommand, stepKeyCommand, usesFilter } from './model';

  /** Optional columns (the column menu): Interval, Cadence, Dither (Q-P5: hidden by default). */
  export type OptionalColumn = 'interval_s' | 'cadence_s' | 'dither_every' | 'duration';

  interface Props {
    steps: readonly PlanStep[];
    /** Stable keys of the rows (the store's ids), so an editor follows its step on a move. */
    keys?: readonly (string | number)[];
    /** Derived seconds per step (A59), in plan order. */
    perStep: readonly number[];
    issues: IssueIndex;
    selected: number | null;
    /** The wheel's names (or the profile's while the wheel is offline). */
    wheel: readonly string[];
    /** Where the names come from, for an unknown name's note ("not in the wheel"). */
    wheelSource?: string;
    columns: ReadonlySet<OptionalColumn>;
    /** A run is active: values only, with each row's progress. */
    locked?: boolean;
    progress?: readonly RowRun[] | null;
    /** Index of the step the run is on. */
    active?: number | null;
    onedit: (i: number, patch: Partial<PlanStep>) => Promise<unknown>;
    oncommand: (cmd: StepCommand) => void;
    onreorder: (from: number, to: number) => void;
    onselect: (i: number | null) => void;
    /** An issue's field asks for the focus (the issue list). */
    focusRequest?: { step: number; field: string | null; n: number } | null;
  }

  let {
    steps,
    keys,
    perStep,
    issues,
    selected,
    wheel,
    wheelSource = 'wheel',
    columns,
    locked = false,
    progress = null,
    active = null,
    onedit,
    oncommand,
    onreorder,
    onselect,
    focusRequest = null,
  }: Props = $props();

  const uid = `steps-${Math.random().toString(36).slice(2, 8)}`;
  const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);
  let body: HTMLTableSectionElement | undefined = $state();

  const typeOptions = $derived((t: string) => optionsWith(FRAME_TYPES, t, 'not a frame type: choose one'));
  const filterOptions = (f: string) =>
    optionsWith(wheel, f, `not in the ${wheelSource}`).map((o) =>
      o.value.toLowerCase() === DARK_SLOT.toLowerCase() ? { ...o, detail: 'opaque slot: no light reaches the sensor' } : o,
    );

  /**
   * Columns in order; `w` is the CSS width. Locked (a run), the cells are plain values, so the
   * columns narrow and Duration gives way to the Run column: at 1280 px the Run column was
   * clipped (design review W6a).
   */
  const w = (edit: number, plain: number): string => `${locked ? plain : edit}px`;
  const cols = $derived(
    [
      { id: 'n', label: '#', w: '40px', title: 'Step number: drag to reorder' },
      { id: 'enabled', label: 'On', w: '34px', title: 'Step included in the run' },
      { id: 'frame_type', label: 'Type', w: w(86, 64) },
      { id: 'filter_name', label: 'Filter', w: w(100, 84), title: 'Wheel slot; Dark and Bias use the opaque slot' },
      { id: 'exposure_s', label: 'Exp s', w: w(112, 72), num: true, title: 'Exposure, seconds' },
      { id: 'gain', label: 'Gain', w: w(76, 52), num: true },
      { id: 'count', label: 'Count', w: w(76, 56), num: true, title: 'Frames per pass' },
      ...(columns.has('interval_s') ? [{ id: 'interval_s', label: 'Interval s', w: w(82, 76), num: true, title: 'Idle wait after each frame; not used when a cadence is set' }] : []),
      ...(columns.has('cadence_s') ? [{ id: 'cadence_s', label: 'Cadence s', w: w(82, 76), num: true, title: 'Start-to-start period (empty = off); at least the exposure' }] : []),
      ...(columns.has('dither_every') ? [{ id: 'dither_every', label: 'Dither', w: w(80, 56), num: true, title: 'Nudge the mount every N frames of the run (0 = off)' }] : []),
      ...(columns.has('duration') && !progress ? [{ id: 'duration', label: 'Duration', w: '76px', num: true, title: 'Count × period, from the server (filter moves and autofocus not counted)' }] : []),
      ...(progress ? [{ id: 'run', label: 'Run', w: '92px', title: 'Progress of this pass' }] : []),
    ] as { id: string; label: string; w: string; num?: boolean; title?: string }[],
  );

  /** Issues of a cell, with the step's own (no field) on the # cell. */
  const cellIssues = (i: number, field: string) => issues.field(i, field);
  const rowMessages = (i: number) => issues.step(i);

  // -- Selection and keys ----------------------------------------------------------------------

  async function focusRow(i: number | null): Promise<void> {
    await tick();
    if (i === null) return;
    body?.querySelector<HTMLElement>(`tr[data-row="${i}"]`)?.focus();
  }

  function onRowKey(e: KeyboardEvent, i: number): void {
    if (e.target !== e.currentTarget) return; // an editor keeps its keys
    const cmd = stepKeyCommand(e, mac);
    if (!cmd) return;
    e.preventDefault();
    e.stopPropagation();
    const last = steps.length - 1;
    if (cmd === 'prev' || cmd === 'next' || cmd === 'first' || cmd === 'last') {
      const to = cmd === 'prev' ? Math.max(0, i - 1) : cmd === 'next' ? Math.min(last, i + 1) : cmd === 'first' ? 0 : last;
      onselect(to);
      void focusRow(to);
      return;
    }
    if (selected !== i) onselect(i);
    if (cmd === 'toggle') {
      if (!locked) void onedit(i, { enabled: !steps[i].enabled }).catch(() => undefined);
      return;
    }
    oncommand(cmd);
    void tick().then(() => focusRow(selected));
  }

  function onRowPointer(e: MouseEvent, i: number): void {
    const t = e.target as Element | null;
    if (t?.closest?.('button, input, [role="combobox"], [role="checkbox"]')) return;
    onselect(i);
  }

  /** The row whose tab stop is live: the selection, else the first row. */
  const focusIndex = $derived(selected !== null && selected < steps.length ? selected : 0);

  // -- Reorder by dragging the number -------------------------------------------------------------

  let drag: { from: number; to: number; pointer: number } | null = $state(null);

  function dragDown(e: PointerEvent, i: number): void {
    if (locked || e.button !== 0 || steps.length < 2) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    drag = { from: i, to: i, pointer: e.pointerId };
    onselect(i);
  }

  function dragMove(e: PointerEvent): void {
    if (!drag || e.pointerId !== drag.pointer || !body) return;
    const rows = [...body.querySelectorAll<HTMLElement>('tr[data-row]')];
    let to = rows.length - 1;
    for (let k = 0; k < rows.length; k++) {
      const r = rows[k].getBoundingClientRect();
      if (e.clientY < r.top + r.height / 2) {
        to = k > drag.from ? k - 1 : k;
        break;
      }
    }
    drag = { ...drag, to: Math.max(0, Math.min(rows.length - 1, to)) };
  }

  function dragUp(e: PointerEvent): void {
    if (!drag || e.pointerId !== drag.pointer) return;
    const { from, to } = drag;
    drag = null;
    if (to !== from) {
      onreorder(from, to);
      void focusRow(to);
    }
  }

  // -- The issue list asks for a field ----------------------------------------------------------------

  $effect(() => {
    const r = focusRequest;
    if (!r || !body) return;
    void tick().then(() => {
      const row = body?.querySelector<HTMLElement>(`tr[data-row="${r.step}"]`);
      const cell = r.field ? row?.querySelector<HTMLElement>(`[data-field="${r.field}"] input, [data-field="${r.field}"] button`) : null;
      (cell ?? row)?.focus();
    });
  });

  const fmtSecs = (v: number) => fixed(v, 2);
  const fmtTenth = (v: number) => fixed(v, 1);
</script>

{#snippet edge(i: number, field: string)}
  {@const list = cellIssues(i, field)}
  {#if list.length}
    <span class="edge" class:warn={list.every((x) => x.level === 'warning')} aria-hidden="true"></span>
  {/if}
{/snippet}

<div class="wrap" class:dragging={!!drag}>
  <table class="grid" role="grid" aria-label="Steps" aria-rowcount={steps.length + 1} aria-readonly={locked || undefined} aria-describedby="{uid}-keys">
    <colgroup>
      {#each cols as c (c.id)}<col style:width={c.w} />{/each}
      <col />
    </colgroup>
    <thead>
      <tr>
        {#each cols as c (c.id)}
          <th scope="col" class:num={c.num}>
            <span use:tooltip={{ text: c.title ?? '', placement: 'top', disabled: !c.title }}>{c.label}</span>
          </th>
        {/each}
        <th aria-hidden="true"></th>
      </tr>
    </thead>
    <tbody bind:this={body}>
      {#each steps as s, i (keys?.[i] ?? i)}
        {@const row = progress?.[i] ?? null}
        {@const msgs = rowMessages(i)}
        {@const filterUsed = usesFilter(s.frame_type)}
        {@const label = `Step ${i + 1}`}
        <tr
          data-row={i}
          class:selected={selected === i}
          class:off={!s.enabled}
          class:problem={msgs.some((x) => x.level === 'error')}
          class:active={active === i && !!progress}
          class:drop-before={drag && drag.to === i && drag.to < drag.from}
          class:drop-after={drag && drag.to === i && drag.to > drag.from}
          aria-selected={selected === i}
          aria-describedby={msgs.length ? `${uid}-m${i}` : undefined}
          tabindex={i === focusIndex ? 0 : -1}
          onkeydown={(e) => onRowKey(e, i)}
          onclick={(e) => onRowPointer(e, i)}
          onfocusin={(e) => {
            if (e.target !== e.currentTarget && selected !== i) onselect(i);
          }}
        >
          <td class="n">
            <span
              class="handle"
              class:grab={!locked && steps.length > 1}
              role="presentation"
              onpointerdown={(e) => dragDown(e, i)}
              onpointermove={dragMove}
              onpointerup={dragUp}
              onpointercancel={() => (drag = null)}
            >{i + 1}</span>
          </td>
          <td data-field="enabled">
            <button
              type="button"
              class="check"
              role="checkbox"
              aria-checked={s.enabled}
              aria-label="{label}: included in the run"
              aria-disabled={locked || undefined}
              tabindex="-1"
              onclick={() => {
                if (!locked) void onedit(i, { enabled: !s.enabled }).catch(() => undefined);
              }}
              use:tooltip={{ text: s.enabled ? 'Included (Space)' : 'Skipped (Space)', placement: 'top', reason: locked ? 'Locked while a run is scheduled or running' : null }}
            ><span class="box" aria-hidden="true"></span></button>
          </td>
          <td data-field="frame_type" class="cell">
            {@render edge(i, 'frame_type')}
            {#if locked}
              <span class="val" class:flag={!isKnownType(s.frame_type)}>{s.frame_type}</span>
            {:else}
              <Select label="{label} type" hideLabel options={typeOptions(s.frame_type)} value={s.frame_type} onchange={(v) => void onedit(i, { frame_type: v }).catch(() => undefined)} />
            {/if}
          </td>
          <td data-field="filter_name" class="cell">
            {@render edge(i, 'filter_name')}
            {#if !filterUsed}
              <span class="val muted" use:tooltip={{ text: `${s.frame_type} frames use the opaque slot (${DARK_SLOT}); the filter is not used`, placement: 'top' }}>Dark slot</span>
            {:else if locked}
              <span class="val">{s.filter_name || '—'}</span>
            {:else}
              <Select label="{label} filter" hideLabel options={filterOptions(s.filter_name)} value={s.filter_name || null} placeholder="Choose" onchange={(v) => void onedit(i, { filter_name: v }).catch(() => undefined)} />
            {/if}
          </td>
          <td data-field="exposure_s" class="cell num">
            {@render edge(i, 'exposure_s')}
            {#if locked}<span class="val">{fmtSecs(s.exposure_s)}</span>{:else}
              <NumberField label="{label} exposure" hideLabel value={s.exposure_s} unit="s" decimals={2} step={1} appliedWord="Saved" dirtyWord="Not saved" commitVerb="saves" send={(v: number) => onedit(i, { exposure_s: v })} />
            {/if}
          </td>
          <td data-field="gain" class="cell num">
            {@render edge(i, 'gain')}
            {#if locked}<span class="val">{int(s.gain)}</span>{:else}
              <NumberField label="{label} gain" hideLabel value={s.gain} integer appliedWord="Saved" dirtyWord="Not saved" commitVerb="saves" send={(v: number) => onedit(i, { gain: v })} />
            {/if}
          </td>
          <td data-field="count" class="cell num">
            {@render edge(i, 'count')}
            {#if locked}<span class="val">{int(s.count)}</span>{:else}
              <NumberField label="{label} count" hideLabel value={s.count} integer appliedWord="Saved" dirtyWord="Not saved" commitVerb="saves" send={(v: number) => onedit(i, { count: v })} />
            {/if}
          </td>
          {#if columns.has('interval_s')}
            <td data-field="interval_s" class="cell num">
              {@render edge(i, 'interval_s')}
              <!-- With a cadence the interval is unused, but a stored value out of range stays
                   visible and editable where its issue points (design review W6a). -->
              {#if s.cadence_s !== null && !cellIssues(i, 'interval_s').length}
                <span class="val muted" use:tooltip={{ text: 'A cadence is set: the interval is not used (start-to-start period instead)', placement: 'top' }}>—</span>
              {:else if locked}<span class="val">{fmtTenth(s.interval_s)}</span>{:else}
                <NumberField label="{label} interval" hideLabel value={s.interval_s} unit="s" decimals={1} appliedWord="Saved" dirtyWord="Not saved" commitVerb="saves" send={(v: number) => onedit(i, { interval_s: v })} />
              {/if}
            </td>
          {/if}
          {#if columns.has('cadence_s')}
            <td data-field="cadence_s" class="cell num">
              {@render edge(i, 'cadence_s')}
              {#if locked}<span class="val">{s.cadence_s === null ? '—' : fmtTenth(s.cadence_s)}</span>{:else}
                <NumberField label="{label} cadence" hideLabel value={s.cadence_s} nullable placeholder="off" unit="s" decimals={1} appliedWord="Saved" dirtyWord="Not saved" commitVerb="saves" send={(v: number | null) => onedit(i, { cadence_s: v })} />
              {/if}
            </td>
          {/if}
          {#if columns.has('dither_every')}
            <td data-field="dither_every" class="cell num">
              {@render edge(i, 'dither_every')}
              {#if locked}<span class="val">{s.dither_every ? int(s.dither_every) : 'off'}</span>{:else}
                <NumberField label="{label} dither every N frames" hideLabel value={s.dither_every} integer format={(v) => (v === 0 ? 'off' : String(v))} appliedWord="Saved" dirtyWord="Not saved" commitVerb="saves" send={(v: number) => onedit(i, { dither_every: v })} />
              {/if}
            </td>
          {/if}
          {#if columns.has('duration') && !progress}
            <td class="num ro">
              <span class="val" class:muted={!s.enabled}>{s.enabled && perStep[i] !== undefined ? duration(perStep[i]) : '—'}</span>
            </td>
          {/if}
          {#if progress}
            <td class="run">
              {#if row?.kind === 'active'}
                <span class="state on"><span class="dot" aria-hidden="true"></span><span class="num">{row.done}/{row.total}</span></span>
              {:else if row?.kind === 'done'}
                <span class="state">done <span class="num">{row.done}/{row.total}</span></span>
              {:else if row?.kind === 'skipped'}
                <span class="state muted">skipped</span>
              {:else if row}
                <span class="state muted">waiting <span class="num">0/{row.total}</span></span>
              {/if}
            </td>
          {/if}
          <td class="fill" aria-hidden="true"></td>
        </tr>
        {#if msgs.length}
          <tr class="msgrow" aria-hidden="true">
            <td></td>
            <td colspan={cols.length} id="{uid}-m{i}">
              {#each msgs as m (m.code + (m.field ?? ''))}
                <span class="msg" class:warn={m.level === 'warning'}>
                  <span class="mark" aria-hidden="true"></span><span class="visually-hidden">{m.field ? `${FIELD_LABELS[m.field] ?? m.field}: ` : ''}</span>{issueText(m)}
                </span>
              {/each}
            </td>
          </tr>
        {/if}
      {/each}
    </tbody>
  </table>
  <p class="visually-hidden" id="{uid}-keys">
    On a step row: arrows move, Insert adds, {mac ? 'Command' : 'Control'}+D duplicates, Delete removes, Alt+arrows move the step, Space includes or skips it.
  </p>
</div>

<style>
  .wrap {
    /* Editors fit the 24 px rows (README 3.5). */
    --input-h: 22px;
    min-height: 0;
  }
  .grid {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    table-layout: fixed;
    font-size: var(--text-s);
    color: var(--fg);
  }
  th {
    position: sticky;
    top: 0;
    z-index: 2;
    height: var(--row-h, 24px);
    padding: 0 var(--space-2);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    text-align: left;
    white-space: nowrap;
  }
  /* Unitless numbers (gain, count, dither): no room kept for a unit, so an out-of-range value
     typed there (never clamped) stays readable in full. */
  td[data-field='gain'] :global(input),
  td[data-field='count'] :global(input),
  td[data-field='dither_every'] :global(input) {
    padding-right: var(--space-2);
  }
  th.num {
    text-align: right;
  }
  td {
    position: relative;
    height: calc(var(--input-h) + 4px);
    padding: 0 var(--space-1);
    border-bottom: var(--border-w) solid var(--border-soft);
    white-space: nowrap;
    vertical-align: middle;
  }
  td.num,
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
    text-align: right;
  }
  /* The editors keep their own value alignment; cells only size them. */
  .cell :global(.field),
  .cell :global(.nf) {
    width: 100%;
  }
  .val {
    display: block;
    padding: 0 var(--space-2);
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .muted {
    color: var(--text-muted);
  }
  .flag {
    text-decoration: underline wavy var(--danger);
  }

  tbody tr {
    outline: none;
  }
  tbody tr:not(.msgrow):hover {
    background: var(--hover-bg);
  }
  tr.off td:not(.n):not([data-field='enabled']) .val,
  tr.off td.ro .val {
    color: var(--fg-disabled);
  }
  /* Selection: one brass mark (BRAND 3); a problem's edge stays outermost. */
  tr.selected {
    background: var(--toggled-bg);
  }
  tr.selected td:first-child {
    box-shadow: inset 2px 0 0 var(--accent);
  }
  tr.problem td:first-child {
    box-shadow: inset 2px 0 0 var(--danger);
  }
  tr.selected.problem td:first-child {
    box-shadow:
      inset 2px 0 0 var(--danger),
      inset 4px 0 0 var(--accent);
  }
  /* The step the run is on: neutral bar and fill (run progress is not brass, BRAND 8). */
  tr.active {
    background: var(--surface);
  }
  tr.active td:first-child {
    box-shadow: inset 3px 0 0 var(--fg);
  }
  tbody tr:focus-visible td {
    box-shadow:
      inset 0 var(--focus-ring-w) 0 var(--focus-ring),
      inset 0 calc(-1 * var(--focus-ring-w)) 0 var(--focus-ring);
  }
  tr.drop-before td {
    box-shadow: inset 0 2px 0 var(--fg);
  }
  tr.drop-after td {
    box-shadow: inset 0 -2px 0 var(--fg);
  }

  /* Row number: the drag handle. */
  .n {
    color: var(--text-muted);
    font-family: var(--font-mono);
    text-align: right;
  }
  .handle {
    display: inline-block;
    min-width: 24px;
    padding: 0 var(--space-1);
    border-radius: var(--radius-s);
    text-align: right;
    user-select: none;
    touch-action: none;
  }
  .handle.grab {
    cursor: grab;
  }
  .handle.grab:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .dragging,
  .dragging .handle {
    cursor: grabbing;
  }

  /* On: a token-drawn box (Checkbox's look). */
  .check {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 22px;
    padding: 0;
    border: 0;
    background: transparent;
    cursor: pointer;
  }
  .check .box {
    position: relative;
    width: 14px;
    height: 14px;
    border: var(--border-w) solid var(--fg-muted);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .check[aria-checked='true'] .box {
    border-color: var(--fg);
    background: var(--toggled-bg);
  }
  .check[aria-checked='true'] .box::after {
    content: '';
    position: absolute;
    left: 4px;
    top: 1px;
    width: 4px;
    height: 8px;
    border: solid var(--fg);
    border-width: 0 1.5px 1.5px 0;
    transform: rotate(45deg);
  }
  .check[aria-disabled='true'] {
    cursor: default;
  }
  .check[aria-disabled='true'] .box {
    border-color: var(--border-soft);
  }
  .check:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }

  /* A cell with an issue: --danger edge around its editor (warning: --warning, dashed). */
  .edge {
    position: absolute;
    inset: 1px 2px;
    border: var(--border-w) solid var(--danger);
    border-radius: var(--radius-s);
    pointer-events: none;
    z-index: 1;
  }
  .edge.warn {
    border-style: dashed;
    border-color: var(--warning);
  }

  .run .state {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: 0 var(--space-2);
    color: var(--fg);
  }
  .run .state.muted {
    color: var(--text-muted);
  }
  .run .dot {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
    background: var(--fg);
  }

  /* Issue words under the row (spec 2.4 "Invalid cell"). */
  .msgrow td {
    height: auto;
    padding: 2px var(--space-2) 4px;
    border-bottom: var(--border-w) solid var(--border-soft);
    white-space: normal;
  }
  .msg {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-1);
    margin-right: var(--space-4);
    color: var(--fg);
    font-size: var(--text-xs);
    line-height: var(--leading-tight);
  }
  .msg .mark {
    flex: none;
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
    background: var(--danger);
    transform: translateY(-1px);
  }
  .msg.warn .mark {
    /* The attention mark, a bar over a dot (BRAND 8, run/LevelMark): never a triangle,
       the check star's shape (BRAND 2.6; design review W6a). */
    width: 3px;
    height: 9px;
    border: none;
    border-radius: 0;
    background: linear-gradient(var(--warning) 0 5px, transparent 5px 7px, var(--warning) 7px 9px);
  }
  .fill {
    padding: 0;
  }
</style>
