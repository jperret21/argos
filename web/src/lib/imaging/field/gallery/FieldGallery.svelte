<!--
  Component gallery, wave 4, field and overlays (development only, part of /?gallery=1):
  the field overlay on a real FitsViewer (synthetic frame, tracking applied), the hover link
  between the candidates table and the image, the star card, the Catalogue layers popover,
  the Field band, the Inspector and the virtual table, each in its states, on deterministic
  synthetic data (fixtures.ts). Sections are [data-gallery="w4-<name>"] for element
  screenshots. A click on the live image plays the server's part (A49) from the fixtures.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import type { Theme } from '../../../app/theme';
  import IconButton from '../../../components/IconButton.svelte';
  import Segmented from '../../../components/Segmented.svelte';
  import VirtualTable from '../../../components/VirtualTable.svelte';
  import type { Column } from '../../../components/table';
  import { fixed } from '../../../format/number';
  import FieldOverlay, { type SelectAt } from '../../../viewer/overlay/FieldOverlay.svelte';
  import type { Marker } from '../../../viewer/overlay/layers';
  import { applyTransform, placeRing, type ScreenMap } from '../../../viewer/overlay/project';
  import FitsViewer from '../../../viewer/FitsViewer.svelte';
  import { effectiveTurns, type RotationMode } from '../../../viewer/rotation';
  import { autoStf, histogram16 } from '../../../viewer/stretch';
  import { candidateRows } from '../candidates';
  import CatalogPopover from '../CatalogPopover.svelte';
  import { FieldStore } from '../field.svelte';
  import FieldBand from '../FieldBand.svelte';
  import InspectorCard from '../InspectorCard.svelte';
  import { fieldChip } from '../present';
  import StarCard from '../StarCard.svelte';
  import type { FieldState, SelectionEvent } from '../types';
  import {
    CANDIDATES,
    FAILED_KEPT,
    H,
    LAYERS,
    manyStars,
    MOVED,
    SEL_COMPARISON,
    SEL_IDENTIFYING,
    SEL_NO_MATCH,
    SEL_NO_WCS,
    SEL_VARIABLE,
    SOLVED,
    SOLVING,
    syntheticFrame,
    TARGETS,
    TRANSFORM,
    UNSOLVED,
    W,
  } from './fixtures';

  let theme = $state<Theme>('observatory');
  onMount(() => {
    const read = () => (theme = (document.documentElement.dataset.theme as Theme) || 'observatory');
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  });
  const TINTS: Record<Theme, [number, number, number]> = { observatory: [1, 1, 1], charcoal: [1, 1, 1], 'night-red': [0.847, 0, 0] };

  const mem = () => {
    const d = new Map<string, string>();
    return { getItem: (k: string) => d.get(k) ?? null, setItem: (k: string, v: string) => void d.set(k, v) };
  };
  function store(f: FieldState, opts: { layers?: boolean; transform?: boolean; targets?: boolean; sel?: SelectionEvent | null } = {}): FieldStore {
    const s = new FieldStore({ storage: mem() });
    s.ingest('field', f);
    s.ingest('catalog', { state: 'ready', counts: {}, warnings: [] });
    if (opts.layers !== false && f.solution) s.ingest('field_layers', LAYERS);
    if (opts.transform !== false && f.solution) s.ingest('field_transform', TRANSFORM);
    if (opts.targets !== false) s.ingest('targets', TARGETS);
    if (opts.sel) s.ingest('selection', opts.sel);
    return s;
  }

  // -- Live: viewer + overlay + card + band, one store ------------------------------------------
  const frame = syntheticFrame();
  const levels = { ...autoStf(histogram16(frame.pixels)), mode: 'linear' as const };
  const live = store(SOLVED);
  live.inspect('c102');
  live.inspect('c101');
  let rotation: RotationMode = $state('auto');
  let tracking = $state(true);
  let rect = $state<{ left: number; top: number; width: number; height: number } | null>(null);
  let stageW = $state(0);
  let stageH = $state(0);
  let lastClick = $state('click a star, a marker or the sky');
  const turns = $derived(effectiveTurns(rotation, W, H));
  const map: ScreenMap | null = $derived(rect ? { rect, frame: { width: W, height: H }, turns } : null);
  let popOpen = $state(false);

  /** The server's part of A49, from the fixtures: a marker opens its card, the sky measures. */
  function onselect(at: SelectAt): void {
    const hit = at.hit;
    lastClick = `x ${fixed(at.x, 1)} · y ${fixed(at.y, 1)} · tol ${fixed(at.tol_px, 1)} px${hit ? ` · ${hit.layer}` : ''}`;
    let ev: SelectionEvent;
    if (hit?.layer === 'selected' || hit?.layer === 'variables') ev = hit.marker.key === 'rr-lyr' ? SEL_VARIABLE : { ...SEL_COMPARISON, selection: { ...SEL_COMPARISON.selection!, title: hit.marker.label || 'Star', ring: { x: hit.marker.x, y: hit.marker.y, r_px: 9.5, aperture: 'photometry' } } };
    else ev = { ...SEL_NO_MATCH, id: Date.now(), selection: { ...SEL_NO_MATCH.selection!, ring: { x: at.x, y: at.y, r_px: 9.5, aperture: 'star' } } };
    // As the server: a catalogue hit's ring is a reference position, a measured star's is on the frame.
    const s = ev.selection!;
    live.ingest('selection', { ...ev, selection: { ...s, ring: { ...s.ring!, space: hit ? 'reference' : 'frame' } } });
  }

  const sel = $derived(live.selection?.selection ?? null);
  const cardAt = $derived.by(() => {
    if (!map || !sel?.ring) return null;
    return placeRing(map, tracking ? live.activeTransform : null, sel.ring);
  });
  let busyRole = $state<'target' | 'comparison' | 'check' | 'remove' | null>(null);
  function fakeRole(r: 'target' | 'comparison' | 'check' | 'remove'): void {
    busyRole = r;
    setTimeout(() => {
      busyRole = null;
      const s = live.selection?.selection;
      if (s) live.ingest('selection', { ...live.selection!, selection: { ...s, role: r === 'remove' ? null : r, removable: r !== 'remove' } });
    }, 700);
  }

  const inspectedRow = $derived(candidateRows(CANDIDATES, 'candidates').find((r) => r.key === live.inspected) ?? null);
  const inspectAt = $derived(inspectedRow && inspectedRow.x !== null && inspectedRow.y !== null ? applyTransform(TRANSFORM, inspectedRow.x, inspectedRow.y, { width: W, height: H }) : null);
  const historyRows = $derived(live.history.map((k) => ({ key: k, label: candidateRows(CANDIDATES, 'candidates').find((r) => r.key === k)?.name.slice(-3) ?? k })));

  // -- Stills -------------------------------------------------------------------------------------
  const chips = [SOLVED, { ...SOLVED, auto: true }, SOLVING, FAILED_KEPT, MOVED, UNSOLVED].map((f) => fieldChip(f, f === SOLVED ? null : { state: 'idle', counts: {}, warnings: [] }));
  const counts = LAYERS.counts;
  const unsolvedStore = store(UNSOLVED);
  const many = $state.raw(manyStars());
  const STAR_COLS: Column<Marker>[] = [
    { id: 'id', label: 'Star', value: (m) => m.name ?? '', format: (m) => m.name ?? `Gaia DR3 ${m.id}`, width: 'minmax(140px, 1fr)' },
    { id: 'g', label: 'G', numeric: true, value: (m) => m.g_mag ?? null, format: (m) => fixed(m.g_mag ?? NaN, 2), width: '72px' },
    { id: 'det', label: 'On frame', value: (m) => (m.detected ? 'detected' : ''), width: '90px' },
  ];
  let manySel: string | null = $state('big42');
  const noop = () => {};
</script>

<section data-gallery="w4-overlay" id="w4-overlay">
  <h2>Field overlay <span>screen space over the real viewer: layers follow the tracking transform and the display rotation; hover a marker (stroke +1 px, identity after 500 ms); click to select (A49); hover a candidates row to ring its star</span></h2>
  <div class="controls">
    <IconButton icon="labels" label="Labels" shortcut="L" pressed={live.visibility.labels} variant="ghost" onclick={() => live.toggle('labels')} />
    <IconButton icon="sky-grid" label="Coordinate grid" shortcut="G" pressed={live.visibility.grid} variant="ghost" onclick={() => live.toggle('grid')} />
    <CatalogPopover
      bind:open={popOpen}
      visibility={live.visibility}
      counts={counts}
      solved
      catalog={{ state: 'ready' }}
      gLimit={live.depth ?? 16.5}
      onvisible={(id, on) => live.setVisible(id, on)}
      onglimit={(v) => (live.gLimit = v)}
    />
    <Segmented label="Rotation" options={[{ value: 'auto', label: 'Auto' }, { value: '0', label: '0°' }, { value: '180', label: '180°' }]} bind:value={rotation} />
    <IconButton icon="plate-solve-auto" label={tracking ? 'Tracking transform applied' : 'Tracking transform ignored'} showLabel size="s" variant="secondary" pressed={tracking} onclick={() => (tracking = !tracking)} />
    <span class="result num" data-testid="w4-click">{lastClick}</span>
  </div>
  <div class="live">
    <div class="stage" bind:clientWidth={stageW} bind:clientHeight={stageH}>
      <FitsViewer {frame} {rotation} stretch={levels} autoStretch={false} nightTint={theme === 'night-red'} tint={TINTS[theme]} label="Synthetic field" onrect={(r) => (rect = r)} />
      <FieldOverlay
        {rect}
        frame={{ width: W, height: H }}
        {turns}
        stage={{ width: stageW, height: stageH }}
        markers={live.layers?.layers}
        transform={tracking ? live.activeTransform : null}
        visibility={live.visibility}
        gLimit={live.depth}
        grid={live.field?.grid}
        reticle={live.field?.target_reticle}
        ring={sel?.ring}
        mark={live.listMark}
        hotKey={live.hover?.source === 'candidates' ? live.hover.key : null}
        apertureR={live.apertureR}
        {onselect}
        onhover={(h) => live.hoverMarker(h)}
      />
      {#if sel}
        <StarCard
          selection={sel}
          phase={live.selection?.state}
          message={live.selection?.message}
          at={cardAt}
          bounds={{ width: stageW, height: stageH }}
          persist={false}
          {busyRole}
          onrole={(r) => fakeRole(r)}
          onremove={() => fakeRole('remove')}
          onclose={() => live.clearSelection(null)}
          oninspect={noop}
        />
      {/if}
    </div>
    <div class="side">
      <div class="band-demo"><FieldBand field={live} tab="candidates" /></div>
      <div class="insp-demo">
        <InspectorCard row={inspectedRow} {frame} at={inspectAt} {levels} {turns} apertureR={9.5} annulusIn={16} annulusOut={24} scaleArcsec={1.19} history={historyRows} onpick={(k) => live.inspect(k)} {theme} />
      </div>
    </div>
  </div>
</section>

<section data-gallery="w4-chips" id="w4-chips">
  <h2>Field state chip <span>text for the HUD chip after the frame chips (03 2.4); never colour alone</span></h2>
  <div class="row">
    {#each chips as c, i (i)}
      <span class="chip" class:warn={c.tone === 'warn'} title={c.title}>{c.text}</span>
    {/each}
  </div>
</section>

<section data-gallery="w4-popover" id="w4-popover">
  <h2>Catalogue layers popover <span>320 px; replaces the two-row overlay bar; counts in mono; rows unavailable with the reason before a solve; G limit saved once per release</span></h2>
  <div class="row top">
    <figure><CatalogPopover preview visibility={live.visibility} {counts} solved catalog={{ state: 'ready' }} gLimit={16.5} /><figcaption>solved, catalogues ready</figcaption></figure>
    <figure><CatalogPopover preview visibility={live.visibility} {counts} solved catalog={{ state: 'fetching' }} gLimit={16.5} /><figcaption>fetching</figcaption></figure>
    <figure><CatalogPopover preview visibility={live.visibility} {counts} solved catalog={{ state: 'error', error: 'VizieR did not answer (timeout 20 s)' }} gLimit={14} /><figcaption>catalogues failed, layers kept</figcaption></figure>
    <figure><CatalogPopover preview visibility={unsolvedStore.visibility} counts={{}} solved={false} gLimit={18} onidentify={noop} /><figcaption>field not identified</figcaption></figure>
  </div>
</section>

<section data-gallery="w4-starcard" id="w4-starcard">
  <h2>Star card <span>compact: identity, one line, role shapes as buttons (pressed = current role); drag settles in a corner (spring); details in the Inspector</span></h2>
  <div class="row top">
    <figure><StarCard still persist={false} selection={SEL_VARIABLE.selection!} phase="resolved" at={null} bounds={{ width: 600, height: 400 }} oninspect={noop} /><figcaption>variable, target of the set</figcaption></figure>
    <figure><StarCard still persist={false} selection={SEL_COMPARISON.selection!} phase="resolved" at={null} bounds={{ width: 600, height: 400 }} busyRole="check" /><figcaption>comparison, check being set</figcaption></figure>
    <figure><StarCard still persist={false} selection={SEL_IDENTIFYING.selection!} phase="identifying" at={null} bounds={{ width: 600, height: 400 }} /><figcaption>identifying (A49)</figcaption></figure>
    <figure><StarCard still persist={false} selection={SEL_NO_MATCH.selection!} phase="no_match" message={SEL_NO_MATCH.message} at={null} bounds={{ width: 600, height: 400 }} /><figcaption>no catalogue match</figcaption></figure>
    <figure><StarCard still persist={false} selection={SEL_NO_WCS.selection!} phase="resolved" at={null} bounds={{ width: 600, height: 400 }} /><figcaption>field not identified: roles unavailable</figcaption></figure>
  </div>
</section>

<section data-gallery="w4-band" id="w4-band">
  <h2>Field band <span>candidates linked to the image; Δ(B−V), separation, peak, blend flagged by an underline AND a word; virtual Variables / Stars lists; one row below 150 px</span></h2>
  <div class="row top">
    <figure class="wide"><div class="band-demo"><FieldBand field={store(SOLVED)} tab="ensemble" /></div><figcaption>ensemble (a Gaia comparison has no VSP values)</figcaption></figure>
    <figure class="wide"><div class="band-demo"><FieldBand field={store(SOLVED)} tab="variables" /></div><figcaption>variables (VSX, virtual rows)</figcaption></figure>
  </div>
  <div class="row top">
    <figure class="wide"><div class="band-demo short"><FieldBand field={store(SOLVED)} compact /></div><figcaption>below 150 px: one row</figcaption></figure>
    <figure class="wide"><div class="band-demo"><FieldBand field={unsolvedStore} tab="candidates" /></div><figcaption>field not identified</figcaption></figure>
  </div>
</section>

<section data-gallery="w4-inspector" id="w4-inspector">
  <h2>Inspector <span>aperture thumbnail in the viewer tint (red only in Night Red), aperture solid, annulus dashed; values in Readouts; last five stars</span></h2>
  <div class="row top">
    <figure class="insp-demo"><InspectorCard row={candidateRows(CANDIDATES, 'candidates').find((r) => r.key === 'c107') ?? null} {frame} at={applyTransform(TRANSFORM, 330, 150, { width: W, height: H })} {levels} turns={1} apertureR={9.5} annulusIn={16} annulusOut={24} scaleArcsec={1.19} {theme} /><figcaption>non-linear peak, blend risk</figcaption></figure>
    <figure class="insp-demo"><InspectorCard row={candidateRows(CANDIDATES, 'candidates').find((r) => r.key === 'c108') ?? null} frame={null} at={null} apertureR={9.5} {theme} /><figcaption>no B−V, no frame</figcaption></figure>
    <figure class="insp-demo"><InspectorCard row={null} /><figcaption>empty</figcaption></figure>
  </div>
</section>

<section data-gallery="w4-virtual" id="w4-virtual">
  <h2>Virtual table <span>5 000 Gaia rows, constant DOM; one tab stop, arrows / PageUp / PageDown / Home / End; sort by header</span></h2>
  <div class="virt-demo">
    <VirtualTable label="5 000 synthetic Gaia stars" columns={STAR_COLS} rows={many} rowKey={(m) => m.id ?? ''} bind:selected={manySel} />
  </div>
</section>

<style>
  section {
    padding: var(--space-5) 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  h2 {
    margin: 0 0 var(--space-4);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  h2 span {
    margin-left: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-regular);
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-5);
  }
  .row.top {
    align-items: flex-start;
  }
  .row + .row {
    margin-top: var(--space-5);
  }
  figure {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
    margin: 0;
  }
  figcaption {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .controls {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-3);
  }
  .result {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .live {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 460px;
    gap: var(--space-4);
  }
  .stage {
    position: relative;
    height: 460px;
    border: var(--border-w) solid var(--border);
    background: var(--viewer-bg);
  }
  .side {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .band-demo {
    width: 100%;
    height: 236px;
    border: var(--border-w) solid var(--border);
    background: var(--bg);
  }
  .band-demo.short {
    height: 40px;
  }
  .wide {
    width: 640px;
  }
  .insp-demo {
    width: 420px;
    padding: var(--space-3);
    border: var(--border-w) solid var(--border);
    background: var(--bg-2);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    height: 22px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .chip.warn {
    border-left: 2px solid var(--warning);
  }
  .virt-demo {
    width: 520px;
    height: 260px;
    border: var(--border-w) solid var(--border);
  }
</style>
