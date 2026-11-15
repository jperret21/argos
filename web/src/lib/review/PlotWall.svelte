<!--
  The Review plot wall (R1 body; spec 07 E6-E9, WF-B, §2.4; README R1, M85-M88, M96;
  PROPOSAL §6 W7, promoted from src/lab/charts/charts/PlotWall.svelte).

  - One cell per star of the filter shown (targets, check stars, one per comparison) and a
    Conditions cell (D6), small multiples on ONE time axis (CurveLink): one zoom (drag,
    Ctrl / Cmd + wheel, + / −, F, double-click), one crosshair, one selected time. Plain
    wheel scrolls the wall. A star cell is the shared LightCurvePlot with one facet: the
    same markers as Observe (suspect hollow, saturated ×), U error bars and M relative flux
    for every cell at once (one CurveDisplay), the check as check − V (D10), a comparison as
    its leave-one-out Δmag from its own median (Qt's Review diagnostic).
  - 2 columns, 3 with the rail collapsed and 1200 px or more; whole rows of 200 px or more
    fill the height (six cells at 1440 × 900 with the rail open).
  - The health strip on top (frames and gaps, HFD episodes, fewer comparisons, flags).
  - Each cell's title row ends with its numbers (n; the check's mean offset and scatter
    against its median error; a comparison's vetting scatter and status word), Expand and
    the cell menu: Copy data (TSV), Save as PNG, Expand / Restore, Move earlier / later,
    Hide plot, Reset layout. The Conditions cell's metric picker sits there too.
  - Series are labelled "Name [IR]" only when two filters or more are loaded (wave 6b §8).
  - Enter opens the selected frame (R2) through `onopenframe`.
  Keys of a focused cell: F fit, + / − zoom, Shift+← / → pan, ← / → step, U, M (shared).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import LightCurvePlot from '../charts/lightcurve/LightCurvePlot.svelte';
  import { CurveView } from '../charts/lightcurve/view.svelte';
  import { browserExport, composeCanvas, fileStem, toTsv, type ExportHooks, type ExportText } from '../charts/export';
  import Control from '../components/Control.svelte';
  import Icon from '../components/Icon.svelte';
  import Menu from '../components/Menu.svelte';
  import type { MenuChoice, MenuEntry } from '../components/menu';
  import { tooltip } from '../components/tooltip';
  import { fixed, int, signed } from '../format/number';
  import ConditionsCell from './ConditionsCell.svelte';
  import HealthStrip from './HealthStrip.svelte';
  import type { WallLayoutState } from './layout.svelte';
  import type { ReviewSource } from './session.svelte';
  import { statusOk, statusWord } from './source';
  import { cellMenu, cellStats, cellTsv, defaultCells, healthOf, METRICS, metricMenu, metricSeries, metricTsv, rowHeight, wallColumns, type CellStats, type MetricId, type WallCell } from './wall';

  interface Props {
    source: ReviewSource;
    layout: WallLayoutState;
    /** The right rail is open (two columns), else three from 1200 px. */
    railOpen?: boolean;
    theme?: unknown;
    /** Feedback of the cell menu (copy, PNG): the host's toast. */
    notify?: (title: string, message?: string) => void;
    /** Enter with a selected time: open that frame (R2). */
    onopenframe?: (t: number) => void;
    /** Export route (browser now; the Tauri dialogs in wave 8). */
    exporter?: ExportHooks;
    /** The wheel names of the filter tokens ("IR"), for the labels. */
    wheel?: readonly string[];
    /** Each star cell's data push (ms) and the store's points (the large-session check). */
    onperf?: (ms: number, points: number) => void;
  }

  let { source, layout, railOpen = true, theme, notify, onopenframe, exporter = browserExport, wheel = [], onperf }: Props = $props();

  let root: HTMLDivElement;
  let width = $state(0);
  let gridH = $state(0);
  let menuFor = $state<string | null>(null);
  let menuAnchor = $state<HTMLElement | null>(null);
  let metricOpen = $state(false);
  let metricAnchor = $state<HTMLElement | null>(null);

  const version = $derived(source.version);
  const store = $derived(source.store);
  const filter = $derived.by(() => {
    void version;
    void source.display.filter;
    return source.shownFilter();
  });
  const cells: WallCell[] = $derived.by(() => {
    void version;
    return defaultCells(store, filter, { filtersLoaded: source.filters.length, wheel, conditions: source.frames.length > 0 });
  });
  const arranged = $derived(layout.arrange(cells));
  const shown = $derived(layout.expanded ? arranged.shown.filter((c) => c.id === layout.expanded) : arranged.shown);
  const starCount = $derived(cells.filter((c) => c.kind !== 'conditions').length);

  const target = $derived.by(() => {
    void version;
    return store.primary('target', null, filter);
  });
  const report = $derived.by(() => {
    void version;
    void filter;
    return source.report();
  });
  const stats = $derived.by(() => {
    void version;
    const out = new Map<string, CellStats>();
    for (const c of cells) {
      if (!c.key) continue;
      const s = store.stars.get(c.key);
      if (s) out.set(c.id, cellStats(s, report));
    }
    return out;
  });
  const lanes = $derived.by(() => {
    void version;
    return healthOf(source.wallFrames(), target, store.comparisons(filter).length, 1.5, target ? (source.extras.get(target.key) ?? null) : null);
  });
  const clickTimes = $derived.by(() => {
    void version;
    return target ? target.cols.view('t') : new Float64Array(0);
  });

  const cols = $derived(layout.expanded ? 1 : wallColumns(width, railOpen));
  const rowH = $derived(layout.expanded ? Math.max(200, gridH) : rowHeight(gridH));

  // One CurveView per cell over the shared display (global U / M / time axis / filter).
  const views = new Map<string, CurveView>();
  function viewFor(id: string): CurveView {
    let v = views.get(id);
    if (!v) {
      v = new CurveView(source.display);
      views.set(id, v);
    }
    return v;
  }

  // A new source fits again (the link was reset): nothing kept from the old one.
  $effect(() => {
    void source.store;
    untrack(() => {
      menuFor = null;
      layout.expanded = null;
    });
  });

  // -- Cell menu ---------------------------------------------------------------------------------
  const menuItems = (c: WallCell): MenuEntry[] =>
    cellMenu(
      c,
      arranged.shown.findIndex((x) => x.id === c.id),
      arranged.shown.length,
      layout.expanded === c.id,
    );

  function onMenu(c: WallCell, it: MenuChoice): void {
    menuFor = null;
    if (it.id === 'copy') void copyCell(c);
    else if (it.id === 'png') void pngCell(c);
    else if (it.id === 'expand') layout.toggleExpand(c.id);
    else if (it.id === 'earlier') layout.move(arranged.shown, c.id, -1);
    else if (it.id === 'later') layout.move(arranged.shown, c.id, 1);
    else if (it.id === 'hide') layout.setHidden(c.id, true);
    else if (it.id === 'reset') layout.reset();
  }

  const stem = (c: WallCell) => fileStem(source.info?.object || store.object || 'review', c.kind === 'conditions' ? METRICS[layout.metric].label : c.label, source.info?.startedUtc?.slice(0, 10) ?? null);

  async function copyCell(c: WallCell): Promise<void> {
    try {
      let t: { header: string[]; rows: string[][] };
      if (c.kind === 'conditions') t = metricTsv(metricSeries(source.wallFrames(), layout.metric, target), layout.metric);
      else {
        const s = c.key ? store.stars.get(c.key) : null;
        if (!s) return;
        t = cellTsv(s, source.display.flux ? 'flux' : 'mag');
      }
      notify?.(await exporter.tsv(`${stem(c)}.tsv`, toTsv(t.header, t.rows), t.rows.length), c.kind === 'conditions' ? undefined : 'Full precision, as the photometry CSV');
    } catch (e) {
      notify?.('Copy failed', e instanceof Error ? e.message : String(e));
    }
  }

  async function pngCell(c: WallCell): Promise<void> {
    const el = root?.querySelector<HTMLElement>(`[data-cell="${CSS.escape(c.id)}"]`);
    if (!el) return;
    try {
      const cs = getComputedStyle(el);
      const texts: ExportText[] = [...el.querySelectorAll('header h3, header .sub, header .stat')].map((t) => {
        const s = getComputedStyle(t);
        return { el: t, color: s.color, font: `${s.fontWeight} ${s.fontSize} ${s.fontFamily}` };
      });
      const canvas = composeCanvas(el, cs.getPropertyValue('--chart-surface').trim() || cs.backgroundColor, texts);
      notify?.(await exporter.png(`${stem(c)}.png`, canvas));
    } catch (e) {
      notify?.('PNG export failed', e instanceof Error ? e.message : String(e));
    }
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === 'Enter' && !e.metaKey && !e.ctrlKey && !e.altKey && source.link.selection.t !== null && onopenframe) {
      const t = e.target as HTMLElement | null;
      if (t && (t.closest('button, [role="menu"], input, textarea') || t.isContentEditable)) return;
      e.preventDefault();
      onopenframe(source.link.selection.t);
    }
  }

  const metricItems = $derived<MenuEntry[]>(metricMenu(layout.metric));

  function statText(c: WallCell, st: CellStats | undefined): { text: string; tip: string; status: string | null; ok: boolean } | null {
    if (!st) return null;
    // The count lives in the tooltips: the title row keeps the numbers that differ (design review).
    const n = `${int(st.n)} points`;
    if (c.kind === 'check') {
      const parts: string[] = [];
      if (st.meanOffset !== null) parts.push(`mean ${signed(st.meanOffset, 3)}`);
      if (st.scatter !== null) parts.push(`σ ${fixed(st.scatter, 3)}`);
      if (st.medianErr !== null) parts.push(`err ${fixed(st.medianErr, 3)}`);
      return {
        text: parts.join(' · '),
        tip: `Check star (${n}): mean of check − catalogue V over ${int(st.n - st.saturated)} unsaturated points; σ is the point-to-point scatter (robust second differences, as uncertainty.py); err the median formal error. A σ near err: the errors are honest.`,
        status: null,
        ok: true,
      };
    }
    if (c.kind === 'comparison') {
      const v = st.vetting;
      const sc = st.scatter !== null ? `σ ${fixed(st.scatter, 3)}` : null;
      return {
        text: sc ?? '',
        tip: v
          ? `${n}. Vetting (photometry_quality.json${report?.filter ? `, filter ${report.filter}` : ''}): ${int(v.n_valid)} valid points, scatter ${fixed(v.scatter_mag, 4)} mag, median formal error ${fixed(v.median_formal_error_mag, 4)} mag: ${statusWord(v.status)}`
          : st.scatter !== null
            ? `${n}. No vetting report for this filter: σ estimated here as uncertainty.py does (robust second differences / √6)`
            : `${n}. Fewer than 10 valid points: no scatter`,
        status: v ? statusWord(v.status) : null,
        ok: v ? statusOk(v.status) : true,
      };
    }
    if (c.kind === 'target') {
      const range = st.lo !== null && st.hi !== null ? `${fixed(st.lo, 2)}–${fixed(st.hi, 2)}` : null;
      return { text: range ?? '', tip: `${int(st.n)} points; the range of the magnitudes neither saturated nor suspect${st.suspect ? `; ${st.suspect} suspect (hollow)` : ''}${st.saturated ? `; ${st.saturated} saturated (×)` : ''}`, status: null, ok: true };
    }
    return null;
  }
</script>

{#snippet metricPicker()}
  <Control
    label="Frame metric: {METRICS[layout.metric].label}"
    size="xs"
    variant="ghost"
    tooltip="none"
    aria-haspopup="menu"
    aria-expanded={metricOpen}
    onclick={(e) => {
      metricAnchor = e.currentTarget as HTMLElement;
      metricOpen = !metricOpen;
    }}
  >
    <span class="metric">{METRICS[layout.metric].label}{METRICS[layout.metric].unit ? ` (${METRICS[layout.metric].unit})` : ''}<Icon name="disclosure" size={12} /></span>
  </Control>
{/snippet}

{#snippet tools(c: WallCell)}
  {@const st = statText(c, stats.get(c.id))}
  {#if st}
    <span class="stat num" use:tooltip={{ text: st.tip }}>{st.text}</span>
    {#if st.status}<span class="status" class:warn={!st.ok} use:tooltip={{ text: `Vetting: ${st.status}` }}><span class="word">{st.status}</span></span>{/if}
  {/if}

  <!-- The two buttons never shrink: a narrow cell gives up its numbers first (design review). -->
  <span class="btns">
    <Control icon="expand-pane" label={layout.expanded === c.id ? 'Restore the wall' : `Expand ${c.label}`} size="xs" variant="ghost" pressed={layout.expanded === c.id} layoutToggle tooltip="bottom" onclick={() => layout.toggleExpand(c.id)} />
    <Control
      icon="disclosure"
      label="Plot menu: {c.label}"
      size="xs"
      variant="ghost"
      tooltip="none"
      aria-haspopup="menu"
      aria-expanded={menuFor === c.id}
      onclick={(e) => {
        menuAnchor = e.currentTarget as HTMLElement;
        menuFor = menuFor === c.id ? null : c.id;
      }}
    />
  </span>
{/snippet}

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div class="pw" bind:this={root} bind:clientWidth={width} role="region" aria-label="Plot wall" aria-busy={source.status === 'loading'} onkeydown={onKey}>
  <div class="health">
    <HealthStrip {lanes} times={clickTimes} link={source.link} {theme} />
  </div>
  <div class="grid" bind:clientHeight={gridH} style:--cols={cols} style:--row-h="{rowH}px">
    {#if source.status === 'loading' && !cells.length}
      {#each [0, 1, 2, 3, 4, 5] as k (k)}<section class="cell skeleton" aria-hidden="true"></section>{/each}
    {:else}
      {#if !starCount && source.status !== 'loading'}
        <p class="empty" role="note">
          <Icon name="light-curve" size={20} />
          {source.kind === 'live' ? 'No point measured yet in this run.' : 'No photometry CSV in photometry/. Re-run photometry or import a CSV.'}
        </p>
      {/if}
      {#each shown as c (c.id)}
        {#snippet cellTools()}{@render tools(c)}{/snippet}
        <section class="cell" class:expanded={layout.expanded === c.id} data-cell={c.id} aria-label={c.kind === 'conditions' ? 'Conditions' : `${c.label}, ${c.kind}`}>
          {#if c.kind === 'conditions'}
            <ConditionsCell frames={source.wallFrames()} metric={layout.metric} {target} link={source.link} display={source.display} {version} {theme} headerEnd={cellTools} picker={metricPicker} />
          {:else}
            <LightCurvePlot
              {store}
              facets={[c.kind]}
              targetKey={c.kind === 'target' ? c.key : null}
              checkKey={c.kind === 'check' ? c.key : null}
              comparisonKey={c.kind === 'comparison' ? c.key : null}
              view={viewFor(c.id)}
              toolbar={false}
              link={source.link}
              wheel="modifier"
              {theme}
              titlePx={24}
              titleOf={() => c.label}
              headerEnd={cellTools}
              newestRing={source.kind === 'live'}
              {notify}
              {onperf}
              label="{c.kind === 'target' ? 'Target' : c.kind === 'check' ? 'Check star' : 'Comparison'} {c.label}"
            />
          {/if}
          {#if menuFor === c.id}
            <Menu open anchor={menuAnchor} items={menuItems(c)} label="Plot {c.label}" placement="bottom-end" minWidth={220} onselect={(it) => onMenu(c, it)} onclose={() => (menuFor = null)} />
          {/if}
        </section>
      {/each}
    {/if}
  </div>
</div>

{#if metricOpen}
  <Menu open anchor={metricAnchor} items={metricItems} label="Frame metric" placement="bottom-start" start="checked" onselect={(it) => layout.setMetric(it.id as MetricId)} onclose={() => (metricOpen = false)} />
{/if}

<style>
  .pw {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    min-width: 0;
    background: var(--chart-surface);
  }
  .health {
    height: 56px;
    flex: none;
    padding: 2px 0;
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .grid {
    position: relative;
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
    grid-auto-rows: var(--row-h);
    align-content: start;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .cell {
    position: relative;
    min-width: 0;
    min-height: 0;
    background: var(--chart-surface);
    border-right: var(--border-w) solid var(--border-soft);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .cell.skeleton {
    background: linear-gradient(var(--chart-surface), var(--chart-surface)) padding-box;
  }
  .cell.skeleton::after {
    content: '';
    position: absolute;
    inset: 28px 26px 26px 58px;
    border-left: var(--border-w) solid var(--chart-axis);
    border-bottom: var(--border-w) solid var(--chart-axis);
  }
  .empty {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
    padding: var(--space-3) var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-s);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .stat {
    flex: 0 1 auto;
    min-width: 0;
    max-width: 24ch;
    overflow: hidden;
    color: var(--text-muted);
    font-size: var(--text-2xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .status,
  .metric {
    flex: none;
  }
  .status {
    padding: 0 5px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    line-height: 16px;
    white-space: nowrap;
  }
  .status.warn {
    border-color: var(--warning);
    color: var(--fg);
  }
  .btns {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: 2px;
  }
  /* A narrow cell: the vetting word becomes a 6 px dot (the word in its tooltip), the numbers
     end in an ellipsis sooner; the buttons keep their room. */
  @container lc-cell (max-width: 560px) {
    .stat {
      max-width: 14ch;
    }
    .status {
      width: 6px;
      height: 6px;
      padding: 0;
      border: none;
      border-radius: 50%;
      background: var(--text-muted);
    }
    .status.warn {
      background: var(--warning);
    }
    .status .word {
      display: none;
    }
  }
  .metric {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    padding: 0 4px;
    color: var(--fg);
    font-size: var(--text-xs);
  }
</style>
