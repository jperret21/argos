<!--
  Catalogue layers popover (web/spec/03-observe-page.md 2.3 W2, 04 2.3 "Field overlays";
  replaces the Qt two-row overlay bar, overlay_bar.py:54, and reclaims ~76 px for the image).
  Opened by the toolbar's `catalogue` button (O), 320 px, anchored under it; closes on Esc,
  an outside press or a second O.

  - OBJECTS: Stars, Variables, Galaxies, Nebulae + clusters, Exoplanet hosts, Other objects;
    REFERENCES: VSP reference candidates, Selected stars; DISPLAY: Coordinate grid (G),
    Labels (N; L is the activity log). Each row: a token-drawn box, the layer's swatch (the
    overlay's own SVG mark in the layer's overlay token, so the popover is the legend, Night
    Red included), its name and its count (mono). Changes apply at once and are remembered per viewer.
  - Before a solve every row is unavailable with the reason "Identify the field first (S)"
    and the counts show "—"; the head offers Identify field. After a solve every row stays
    clickable even at count 0 (Qt rule, imaging_page.py:1720-1722).
  - Gaia G limit: slider 5.0 → the fetched depth, with a typed readout; filters the stars
    on the image at once, saved ONCE on release / Enter (fixes P11, P23); galaxies and
    nebulae are unaffected.
  - Busy: a spinner row "Fetching catalogues…"; failed: "Catalogues unavailable: <error>";
    loaded layers stay.
  - Footer: "Catalogue settings…" and "Field identification settings…" open the Settings
    sections as a sheet over Observe (the caller owns the sheet).
-->
<script lang="ts">
  import { fixed, int } from '../../format/number';
  import Icon from '../../components/Icon.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import Popover from '../../components/Popover.svelte';
  import Slider from '../../components/Slider.svelte';
  import Spinner from '../../components/Spinner.svelte';
  import { tooltip } from '../../components/tooltip';
  import { LAYERS, layerPath, rolePath, type DisplayToggle, type LayerId, type Visibility } from '../../viewer/overlay/layers';

  interface Props {
    open?: boolean;
    visibility: Visibility;
    /** Count per layer (null: the field is not identified). */
    counts: Partial<Record<LayerId, number | null>>;
    solved: boolean;
    solving?: boolean;
    /** Catalogue state of this field. */
    catalog?: { state: 'idle' | 'fetching' | 'ready' | 'error'; error?: string | null; warnings?: readonly string[] } | null;
    gLimit: number;
    /** The fetched Gaia depth (catalog.field_stars_mag_limit): the slider's end. */
    gMax?: number;
    onvisible?: (id: LayerId | DisplayToggle, on: boolean) => void;
    /** Live while dragging (filters the image). */
    onglimit?: (v: number) => void;
    /** Once per release / Enter: save catalog.display_mag_limit. */
    onglimitcommit?: (v: number) => void;
    onidentify?: () => void;
    oncatalogsettings?: () => void;
    onsolvesettings?: () => void;
    /** Shortcut shown in the trigger's tooltip. */
    shortcut?: string;
    /** Keys of the grid and labels toggles (the registry's: G, N). */
    gridKey?: string;
    labelsKey?: string;
    /**
     * The trigger lives elsewhere (the Observe toolbar's `catalogue` tool): no own button,
     * the popover is anchored to this element.
     */
    anchor?: HTMLElement | null;
    external?: boolean;
    /** Draw the open popover in place (gallery). */
    preview?: boolean;
  }

  let {
    open = $bindable(false),
    visibility,
    counts,
    solved,
    solving = false,
    catalog = null,
    gLimit,
    gMax = 18,
    onvisible,
    onglimit,
    onglimitcommit,
    onidentify,
    oncatalogsettings,
    onsolvesettings,
    shortcut = 'O',
    gridKey = 'G',
    labelsKey = 'N',
    anchor = null,
    external = false,
    preview = false,
  }: Props = $props();

  let trigger: HTMLElement | undefined = $state();
  const id = `catpop-${Math.random().toString(36).slice(2, 9)}`;

  const OBJECTS: LayerId[] = ['stars', 'variables', 'galaxies', 'nebulae_clusters', 'exoplanets', 'other_objects'];
  const REFERENCES: LayerId[] = ['vsp', 'selected'];
  const DISPLAY: { id: DisplayToggle; label: string; icon: string; key: string }[] = $derived([
    { id: 'grid', label: 'Coordinate grid', icon: 'sky-grid', key: gridKey },
    { id: 'labels', label: 'Labels · catalogue names', icon: 'labels', key: labelsKey },
  ]);
  const REASON = 'Identify the field first (S)';

  /** Shown layers / layers that have something (the trigger's badge). */
  const shown = $derived(solved ? [...OBJECTS, ...REFERENCES].filter((l) => visibility[l]).length : 0);
  const anyOn = $derived(solved && shown > 0);

  let g = $state(0);
  $effect.pre(() => {
    g = gLimit;
  });
</script>

{#snippet row(rid: LayerId | DisplayToggle, label: string, icon: string, right: string, help: string)}
  {@const off = !solved}
  <label class="row" class:off use:tooltip={{ text: off ? label : help, reason: off ? REASON : null, placement: 'left' }}>
    <input
      class="visually-hidden"
      type="checkbox"
      checked={visibility[rid]}
      aria-disabled={off || undefined}
      onclick={(e) => {
        if (off) e.preventDefault();
      }}
      onchange={(e) => onvisible?.(rid, (e.currentTarget as HTMLInputElement).checked)}
    />
    <span class="box" aria-hidden="true"></span>
    <span class="glyph" aria-hidden="true">
      {#if rid === 'grid' || rid === 'labels'}
        <Icon name={icon} size={16} />
      {:else if rid === 'selected'}
        <svg class="swatch" viewBox="0 0 18 18" width="18" height="18"><path class="role target" d={rolePath('target', 9, 9, 6.5)} /></svg>
      {:else}
        <svg class="swatch" viewBox="0 0 18 18" width="18" height="18"
          ><path class="mark {rid}" d={layerPath(rid as Exclude<LayerId, 'selected'>, 9, 9, rid === 'nebulae_clusters' ? 4.5 : rid === 'stars' ? 4.5 : 6.5)} /></svg
        >
      {/if}
    </span>
    <span class="name">{label}</span>
    <span class="count num">{right}</span>
  </label>
{/snippet}

{#snippet body()}
  {#if !solved}
    <div class="unsolved">
      <span class="lead"><Icon name="plate-solve" size={16} /></span>
      <p>{solving ? 'Identifying the field…' : 'Identify the field to show the catalogue layers.'}</p>
      {#if onidentify}
        <IconButton icon="plate-solve" label="Identify field" showLabel size="s" variant="secondary" busy={solving} tooltip="none" onclick={onidentify} />
      {/if}
    </div>
  {:else if catalog?.state === 'fetching'}
    <p class="status" aria-live="polite"><Spinner />Fetching catalogues…</p>
  {:else if catalog?.state === 'error'}
    <p class="status warn" role="status">Catalogues unavailable: {catalog.error ?? 'no answer'}</p>
  {/if}
  {#if solved && catalog?.warnings?.length}
    {#each catalog.warnings as w, i (i)}<p class="status note" title={w}>{w}</p>{/each}
  {/if}
  <div class="group" role="group" aria-label="Objects">
    <h3>Objects <span>n</span></h3>
    {#each OBJECTS as l (l)}
      {@render row(l, LAYERS[l].label, LAYERS[l].icon, solved ? int(counts[l] ?? 0) : '—', LAYERS[l].help)}
    {/each}
  </div>
  <div class="group" role="group" aria-label="References">
    <h3>References</h3>
    {#each REFERENCES as l (l)}
      {@render row(l, LAYERS[l].label, LAYERS[l].icon, solved ? int(counts[l] ?? 0) : '—', LAYERS[l].help)}
    {/each}
  </div>
  <div class="group" role="group" aria-label="Display">
    <h3>Display</h3>
    {#each DISPLAY as d (d.id)}
      {@render row(d.id, d.label, d.icon, d.key, d.id === 'grid' ? 'RA / Dec graticule of the solution' : 'Names next to the catalogue markers; the target set is always labelled')}
    {/each}
    <p class="hint">The target set is always labelled.</p>
  </div>
  <div class="depth">
    <Slider
      label="Gaia G ≤"
      bind:value={g}
      min={5}
      max={Math.max(gMax, 5.5)}
      step={0.1}
      minor={1}
      major={5}
      unit="mag"
      readoutWidth={88}
      format={(v) => fixed(v, 1)}
      oninput={(v) => onglimit?.(v)}
      oncommit={(v) => onglimitcommit?.(v)}
    />
    <p class="hint">Stars only; galaxies and nebulae are unaffected.</p>
  </div>
{/snippet}

{#snippet footer()}
  <div class="links">
    <IconButton icon="settings" label="Catalogue settings…" showLabel size="s" variant="ghost" tooltip="none" onclick={() => oncatalogsettings?.()} />
    <IconButton icon="plate-solve" label="Field identification settings…" showLabel size="s" variant="ghost" tooltip="none" onclick={() => onsolvesettings?.()} />
  </div>
{/snippet}

{#if preview}
  <Popover open title="Catalogue layers" preview width={320} {footer}>
    {@render body()}
  </Popover>
{:else if external}
  <Popover bind:open {anchor} title="Catalogue layers" {id} width={320} placement="bottom-end" {footer}>
    {@render body()}
  </Popover>
{:else}
  <span bind:this={trigger} class="anchor" class:dot={anyOn}>
    <IconButton
      icon="catalogue"
      label="Catalogue layers"
      {shortcut}
      variant="ghost"
      tooltip="bottom"
      pressed={open}
      layoutToggle
      busy={catalog?.state === 'fetching'}
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-controls={id}
      onclick={() => (open = !open)}
    />
  </span>
  <Popover bind:open anchor={trigger} title="Catalogue layers" {id} width={320} placement="bottom-end" {footer}>
    {@render body()}
  </Popover>
{/if}

<style>
  .anchor {
    position: relative;
    display: inline-flex;
  }
  /* The overlay's own marks, in the overlay tokens (the popover is the legend). */
  .swatch {
    display: block;
  }
  .swatch path {
    fill: none;
    stroke-width: 1.5;
  }
  .mark.stars {
    stroke: var(--overlay-field-star);
  }
  .mark.variables {
    stroke: var(--overlay-variable);
  }
  .mark.galaxies {
    stroke: var(--overlay-galaxy);
  }
  .mark.nebulae_clusters {
    stroke: var(--overlay-nebula);
  }
  .mark.exoplanets {
    stroke: var(--overlay-exoplanet);
  }
  .mark.other_objects {
    stroke: var(--overlay-other);
  }
  .mark.vsp {
    stroke: var(--role-comparison);
  }
  .role.target {
    stroke: var(--role-target);
    stroke-width: 2;
  }
  /* A dot when any layer is on (03 2.2): neutral, not brass. */
  .anchor.dot::after {
    content: '';
    position: absolute;
    top: 5px;
    right: 5px;
    width: 5px;
    height: 5px;
    border-radius: var(--radius-round);
    background: var(--fg-muted);
    pointer-events: none;
  }
  .group + .group,
  .depth {
    margin-top: var(--space-2);
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }
  h3 {
    display: flex;
    justify-content: space-between;
    margin: 0 0 var(--space-1);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .row {
    display: grid;
    grid-template-columns: 14px 18px minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-2);
    height: 26px;
    padding: 0 var(--space-1);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-s);
    cursor: pointer;
  }
  .row:hover {
    background: var(--hover-bg);
  }
  .row.off {
    color: var(--fg-disabled);
    cursor: default;
  }
  .row.off:hover {
    background: transparent;
  }
  /* The Checkbox look (BRAND 8): --fg on --toggled-bg, never brass. */
  .box {
    position: relative;
    width: 14px;
    height: 14px;
    box-sizing: border-box;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg);
  }
  input:checked + .box {
    border-color: var(--border);
    background: var(--toggled-bg);
  }
  input:checked + .box::after {
    content: '';
    position: absolute;
    left: 4px;
    top: 1px;
    width: 3px;
    height: 7px;
    border: solid var(--fg);
    border-width: 0 1.5px 1.5px 0;
    transform: rotate(45deg);
  }
  .off .box {
    border-color: var(--border-soft);
  }
  .off input:checked + .box::after {
    border-color: var(--fg-disabled);
  }
  input:focus-visible + .box {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
  .glyph {
    display: inline-flex;
    color: var(--fg-muted);
  }
  .off .glyph {
    color: var(--fg-disabled);
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    font-variant-numeric: var(--numeric);
  }
  .unsolved {
    display: grid;
    grid-template-columns: 18px minmax(0, 1fr);
    gap: var(--space-1) var(--space-2);
    align-items: center;
    margin-bottom: var(--space-2);
    padding-bottom: var(--space-2);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .unsolved p {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
  }
  .unsolved :global(button) {
    grid-column: 2;
    justify-self: start;
  }
  .lead {
    display: inline-flex;
    color: var(--fg-muted);
  }
  .status {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0 0 var(--space-2);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .status.warn {
    padding-left: var(--space-2);
    border-left: 2px solid var(--warning);
  }
  .status.note {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .hint {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .links {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
  }
  /* A failed source in one or two lines (the full text in its tooltip and the log). */
  .status.note {
    display: -webkit-box;
    overflow: hidden;
    overflow-wrap: anywhere;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
  }
</style>
