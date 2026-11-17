<!--
  The light curve's tools, outside the plot (wave 5 carry-over, wave 6b): in the drawer's tab
  row next to the ensemble verdict, and in the Run band's header. One row, right-aligned; it
  measures its width and drops the least needed tools first (curveToolsLayout): − / + (the
  keys and the wheel always zoom), then the time axis turns into one button that cycles UTC,
  JD, BJD, then U and M (their keys stay), then Copy. The zoom state is always named (BRAND
  10: Whole run, Following, Zoom kept), with Fit and Follow beside it.

  S49: when the curves name two filters or more, a filter key leads the row: one curve per
  star and filter, never mixed in one series.
-->
<script lang="ts">
  import { filterLabel } from '../../format/filter';
  import IconButton from '../../components/IconButton.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import { tooltip } from '../../components/tooltip';
  import { int } from '../../format/number';
  import { AXIS_LABEL, curveToolsLayout, zoomText, type CurveView } from './view.svelte';

  interface Props {
    view: CurveView;
    /** 'drawer': with Copy data (TSV); 'band': the Run band's header (no Copy). */
    variant?: 'drawer' | 'band';
    /** Right-aligned in a tab row or a header (default); left in the plot's own row. */
    align?: 'start' | 'end';
  }

  let { view, variant = 'drawer', align = 'end' }: Props = $props();

  let width = $state(0);
  const filterW = $derived(view.filters.length > 1 ? 24 + view.filters.length * 34 : 0);
  const L = $derived(width > 0 ? curveToolsLayout(width, { copy: variant === 'drawer', filterW }) : curveToolsLayout(9999, { copy: variant === 'drawer', filterW }));
  const off = $derived(!view.attached || !view.anyData);
  const AXES = $derived([
    { value: 'utc' as const, label: 'UTC' },
    { value: 'jd' as const, label: 'JD' },
    { value: 'bjd' as const, label: 'BJD', disabledReason: view.bjdOk ? null : 'BJD_TDB needs the observing site (Settings › Site) on every point' },
  ]);
  // The filter's name (IR, LP), never the file-name token (S49 in the UI).
  const FILTERS = $derived(view.filters.map((f) => ({ value: f, label: filterLabel(f) })));
  const modeTip = $derived(
    view.mode === 'fit' ? 'The whole run is in view; new frames widen it' : view.mode === 'follow' ? 'The right edge follows the newest frame' : 'New frames never move this view',
  );
</script>

<div class="ct" class:start={align === 'start'} bind:clientWidth={width} role="toolbar" aria-label="Light curve tools" data-curve-tools={variant}>
  {#if view.filters.length > 1}
    <span class="filter" use:tooltip={{ text: 'One curve per star and filter (S49): the filter drawn' }}>
      <span class="k" aria-hidden="true">Filter</span>
      <Segmented
        label="Filter drawn"
        size="s"
        options={FILTERS}
        bind:value={() => view.shownFilter ?? view.filters[0], (f) => (view.display.filter = f)}
      />
    </span>
    <span class="sep" aria-hidden="true"></span>
  {/if}
  {#if L.axis === 'segmented'}
    <Segmented label="Time axis" size="s" options={AXES} bind:value={view.display.axis} />
    <span class="sep" aria-hidden="true"></span>
  {:else if L.axis === 'cycle'}
    <button
      type="button"
      class="cycle num"
      aria-label="Time axis: {AXIS_LABEL[view.display.axis]}. Press for the next"
      use:tooltip={{ text: `Time axis ${AXIS_LABEL[view.display.axis]}: press for ${view.display.axis === 'utc' ? 'JD' : view.display.axis === 'jd' && view.bjdOk ? 'BJD' : 'UTC'}` }}
      onclick={() => view.cycleAxis()}>{AXIS_LABEL[view.display.axis]}</button
    >
    <span class="sep" aria-hidden="true"></span>
  {/if}
  {#if L.steps}
    <IconButton icon="zoom-out" label="Zoom out time" shortcut="-" size="s" variant="ghost" tooltip="top" onclick={() => view.zoomOut()} disabled={off} />
    <IconButton icon="zoom-in" label="Zoom in time" shortcut="+" size="s" variant="ghost" tooltip="top" onclick={() => view.zoomIn()} disabled={off} />
  {/if}
  <IconButton icon="zoom-fit" label="Fit the whole run" shortcut="F" size="s" variant="ghost" tooltip="top" onclick={() => view.fit()} disabled={off} />
  <IconButton icon="live" label="Follow the newest frame" shortcut="End" size="s" variant="ghost" tooltip="top" pressed={view.mode === 'follow'} layoutToggle onclick={() => view.follow()} disabled={off} />
  <span class="chip" class:kept={view.mode === 'manual'} data-zoom-state={view.mode} aria-live="polite" use:tooltip={{ text: modeTip, shortcut: ['F', 'End'] }}>
    {zoomText(view.mode, view.span)}{#if L.hint && view.mode !== 'fit'}<span class="hint">· <kbd>F</kbd></span>{/if}
  </span>
  {#if view.newer > 0}
    <button type="button" class="newer num" onclick={() => view.follow()} use:tooltip={{ text: 'Frames after this view: follow the newest', shortcut: ['End'] }}>{int(view.newer)} newer ›</button>
  {/if}
  {#if L.toggles}
    <span class="sep" aria-hidden="true"></span>
    <IconButton icon="error-bars" label="Error bars" shortcut="U" size="s" variant="ghost" tooltip="top" pressed={view.display.errors} layoutToggle onclick={() => (view.display.errors = !view.display.errors)} />
    <IconButton
      icon="relative-flux"
      label="Relative flux (median-normalised)"
      shortcut="M"
      size="s"
      variant="ghost"
      tooltip="top"
      pressed={view.display.flux}
      layoutToggle
      onclick={() => (view.display.flux = !view.display.flux)}
    />
  {/if}
  {#if L.copy}
    <IconButton icon="copy" label="Copy data (TSV)" size="s" variant="ghost" tooltip="top" onclick={() => view.copy()} disabledReason={off ? 'No point to copy yet' : null} />
  {/if}
</div>

<style>
  .ct {
    display: flex;
    flex: 1 1 0;
    align-items: center;
    justify-content: flex-end;
    gap: 2px;
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
  }
  .ct.start {
    justify-content: flex-start;
  }
  .sep {
    width: 1px;
    height: 16px;
    margin: 0 var(--space-1);
    background: var(--border-soft);
    flex: none;
  }
  .filter {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    flex: none;
  }
  .filter .k {
    color: var(--text-muted);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .cycle {
    height: 22px;
    min-width: 36px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-xs);
    cursor: pointer;
    flex: none;
  }
  .cycle:hover {
    background: var(--hover-bg);
  }
  .cycle:focus-visible,
  .newer:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -1px;
  }
  /* A label (the zoom state's name), not a button. */
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    height: 20px;
    margin-left: var(--space-1);
    padding: 0 var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-xs);
    flex: none;
  }
  .chip.kept {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .chip .hint {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    color: var(--text-muted);
  }
  kbd {
    padding: 0 3px;
    border: var(--border-w) solid var(--border);
    border-radius: 3px;
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    line-height: 13px;
  }
  .newer {
    height: 20px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-xs);
    flex: none;
    cursor: pointer;
  }
  .newer:hover {
    background: var(--hover-bg);
  }
</style>
