<!--
  Field band (promoted from src/lab/workspace/observe/bands/FieldBand.svelte, web/lab/
  PROPOSAL.md 3.1 "Comparison workspace" and 6, W4; BRAND 11.1 "Field = comparison
  candidates"). Choosing comparisons is a comparison BETWEEN stars, so it is a table linked
  to the image:

  - Candidates: the VSP comparison stars of the frame (A47 `candidates`) with the guide's
    rules as columns: V, B−V, Δ(B−V) against the target (flagged beyond 0.3), separation
    (beyond the observer's limit, Settings › Photometry), the peak on the solved frame
    ("clipped" / "non-linear" as words), SNR, Gaia sources inside the aperture (blend risk),
    status. The note line states the target, the aperture and the rules in words (BRAND 7:
    no rule only in a tooltip); a flag most rows share is said there once instead of
    underlining almost every row. Ensemble: the set's comparisons and check. Sorting re-orders rows with a flip (--duration-fast, BRAND 9; zero under
    reduced motion); values never animate.
  - Variables (VSX) and Stars (Gaia, up to the catalogue budget): virtual tables (constant
    DOM whatever the count).
  - Hovering or focusing a row rings its star on the image (the field store's hover link);
    hovering a marker on the image marks its row. Click or Enter selects the star on the
    image (its card and ring, A49) and puts it in the Inspector, as the Variables and Stars
    lists do.
  - Below 150 px the band is one summary row (BRAND 11.1).
-->
<script lang="ts">
  import { type Snippet, untrack } from 'svelte';
  import { flip } from 'svelte/animate';
  import { loadPref, savePref } from '../../app/prefs';
  import { reducedMotion } from '../../components/motion.svelte';
  import NumText from '../../components/NumText.svelte';
  import type { Column } from '../../components/table';
  import VirtualTable from '../../components/VirtualTable.svelte';
  import { fixed, int, signed } from '../../format/number';
  import type { LayerId, Marker } from '../../viewer/overlay/layers';
  import { candidateRows, commonFlags, ensembleRows, ensembleSummary, maxSepArcmin, sortCandidates, MAX_DELTA_BV, type CandidateKey, type CandidateRow } from './candidates';
  import { markerRowId, type FieldStore } from './field.svelte';
  import RoleGlyph from './RoleGlyph.svelte';

  interface Props {
    field: FieldStore;
    compact?: boolean;
    /** The ADC's top code of the frame on screen (65 520 for 12-bit data), for "clipped". */
    topCode?: number | null;
    /** A star of a list was picked (click / Enter): the caller may select it on the image. */
    onlistpick?: (layer: LayerId, marker: Marker) => void;
    /** A candidate row was picked (click / Enter): the caller selects it on the image. */
    onrowpick?: (row: CandidateRow) => void;
    /** The open list (remembered per viewer). */
    tab?: 'candidates' | 'ensemble' | 'variables' | 'stars';
    /** The live photometry status (W5), at the right of the tab row; `true` in the summary row. */
    live?: Snippet<[boolean]>;
  }

  type Tab = 'candidates' | 'ensemble' | 'variables' | 'stars';
  const isTab = (v: unknown): v is Tab => v === 'candidates' || v === 'ensemble' || v === 'variables' || v === 'stars';

  let { field, compact = false, topCode = null, onlistpick, onrowpick, tab = $bindable(loadPref('argos.field.tab', isTab, 'candidates')), live }: Props = $props();
  $effect(() => {
    const t = tab;
    untrack(() => savePref('argos.field.tab', t));
  });

  const limits = $derived(field.layers?.limits ?? null);
  const maxSep = $derived(maxSepArcmin(limits));
  const COLS: { key: CandidateKey; label: string; num: boolean; title: string }[] = $derived([
    { key: 'role', label: 'Role', num: false, title: 'Role in the set (shape as on the image)' },
    { key: 'name', label: 'Star', num: false, title: 'AUID (VSP label when there is none)' },
    { key: 'v', label: 'V', num: true, title: 'V magnitude (VSP)' },
    { key: 'bv', label: 'B−V', num: true, title: 'Colour index (VSP B − V)' },
    { key: 'dbv', label: 'Δ(B−V)', num: true, title: `Colour difference with the target (keep within ${MAX_DELTA_BV} mag)` },
    { key: 'sep', label: 'Sep ′', num: true, title: `Separation from the target, arcmin (keep within ${maxSep}′, Settings › Photometry)` },
    { key: 'peak', label: 'Peak ADU', num: true, title: 'Brightest pixel on the solved frame ("clipped" at the ADC top code)' },
    { key: 'snr', label: 'SNR', num: true, title: 'Signal-to-noise in the photometry aperture' },
    { key: 'nbr', label: 'Nbr', num: true, title: 'Gaia sources inside the aperture at most 3 mag fainter (blend risk)' },
    { key: 'status', label: 'Status', num: false, title: 'The rules this star breaks, in words' },
  ]);

  /** The observer's sort; until one, Δ(B−V), or Sep when the target's B−V is unknown. */
  let chosenKey: CandidateKey | null = $state(null);
  let asc = $state(true);
  const dur = $derived(reducedMotion() ? 0 : 120);

  const top = $derived(topCode ?? 65535);
  const setStars = $derived(field.targets?.stars ?? []);
  const candRows = $derived(candidateRows(field.candidates, 'candidates', top, { limits, stars: setStars }));
  const ensRows = $derived(ensembleRows(field.candidates, setStars, top, limits));
  const shown = $derived(tab === 'ensemble' ? ensRows : candRows);
  const sortKey: CandidateKey = $derived(chosenKey ?? (shown.some((r) => r.dbv !== null) ? 'dbv' : 'sep'));
  const rows = $derived(sortCandidates(shown, sortKey, asc));
  const summary = $derived(ensembleSummary(field.candidates, setStars, limits));
  /** Flags most rows share: said once in the note, not underlined on every row. */
  const common = $derived(commonFlags(shown));
  const warn = (r: CandidateRow, flag: string) => r.flags.includes(flag) && !common.has(flag);

  /** The note line: the target's context and the rules, in words (BRAND 7). */
  const targetStar = $derived(setStars.find((s) => s.role === 'target') ?? null);
  const targetBv = $derived.by(() => {
    const m = targetStar?.mags ?? null;
    const b = m?.B ?? m?.b;
    const v = m?.V ?? m?.v;
    return typeof b === 'number' && typeof v === 'number' ? b - v : null;
  });
  const apertureArcsec = $derived.by(() => {
    const scale = field.field?.solution?.scale_arcsec_px;
    return field.apertureR && typeof scale === 'number' ? field.apertureR * scale : null;
  });
  const FLAG_TEXT: Record<string, (n: number, of: number) => string> = {
    far: (n, of) => `${n} of ${of} beyond ${int(maxSep)}′`,
    'not detected': (n, of) => `${n} of ${of} not detected`,
    'blend risk': (n, of) => `${n} of ${of} blended`,
    colour: (n, of) => `${n} of ${of} Δ(B−V) > ${MAX_DELTA_BV}`,
    clipped: (n, of) => `${n} of ${of} clipped`,
    'non-linear': (n, of) => `${n} of ${of} non-linear`,
    'variable?': (n, of) => `${n} of ${of} in VSX`,
  };
  const commonText = $derived([...common].map(([f, n]) => FLAG_TEXT[f]?.(n, shown.length) ?? `${n} of ${shown.length} ${f}`));
  /** Target context first, then what most rows share, then the rules (the line may cut there). */
  const contextText = $derived(
    [
      targetStar ? `Target ${targetStar.display_name ?? targetStar.name ?? ''}` : 'No target: Sep from the field centre',
      targetStar ? (targetBv === null ? 'B−V unknown' : `B−V ${fixed(targetBv, 2)}`) : null,
      field.apertureR ? `aperture ${fixed(field.apertureR, 1)} px${apertureArcsec ? ` (${int(apertureArcsec)}″)` : ''}` : null,
    ]
      .filter(Boolean)
      .join(' · '),
  );
  const rulesText = $derived(`flags: Δ(B−V) > ${MAX_DELTA_BV} · Sep > ${int(maxSep)}′ · clipped · blended · VSX`);
  const variables = $derived(field.layersAvailable ? (field.layers?.layers.variables ?? []) : []);
  const stars = $derived(field.layersAvailable ? (field.layers?.layers.stars ?? []) : []);

  /** The row marked from the image: candidates by set key, the virtual lists by marker id. */
  const hotKey = $derived(field.hover && field.hover.source === 'image' ? field.hover.key : null);
  const hotId = $derived(field.hover && field.hover.source === 'image' ? (field.hover.id ?? null) : null);

  function sortBy(k: CandidateKey): void {
    if (sortKey === k) asc = !asc;
    else asc = true;
    chosenKey = k;
  }

  /** Click / Enter on a candidate: the Inspector, and the star selected on the image. */
  function pick(r: CandidateRow): void {
    field.inspect(r.key);
    onrowpick?.(r);
  }

  /** A marker's row key in the virtual lists (the image hover sends the same id). */
  const mKey = (layer: LayerId) => (m: Marker) => markerRowId(layer, m);

  function hover(r: CandidateRow | null): void {
    if (!r || r.x === null || r.y === null) return field.setHover(null, 'candidates');
    field.setHover({ source: 'candidates', key: r.key, points: [{ x: r.x, y: r.y }], reference: true });
  }
  function markerHover(layer: LayerId, m: Marker | null): void {
    if (!m) return field.setHover(null, 'list');
    field.setHover({ source: 'list', key: m.key ?? null, id: mKey(layer)(m), points: [{ x: m.x, y: m.y }], reference: true });
  }

  function rowKey(e: KeyboardEvent, i: number, r: CandidateRow): void {
    const go = (j: number) => {
      const el = (e.currentTarget as HTMLElement).parentElement?.children[j] as HTMLElement | undefined;
      el?.focus();
    };
    if (e.key === 'ArrowDown') go(Math.min(rows.length - 1, i + 1));
    else if (e.key === 'ArrowUp') go(Math.max(0, i - 1));
    else if (e.key === 'Home') go(0);
    else if (e.key === 'End') go(rows.length - 1);
    else if (e.key === 'Enter' || e.key === ' ') pick(r);
    else return;
    e.preventDefault();
  }

  const focusKey = $derived(rows.find((r) => r.key === field.inspected)?.key ?? rows[0]?.key ?? null);

  // -- Virtual lists ----------------------------------------------------------------------------
  const num = (v: number | null | undefined, d: number) => (v === null || v === undefined || !Number.isFinite(v) ? '—' : fixed(v, d));
  const VAR_COLS: Column<Marker>[] = [
    { id: 'name', label: 'Name', value: (m) => m.name ?? m.label ?? '', width: 'minmax(120px, 1.4fr)' },
    { id: 'type', label: 'Type', value: (m) => m.var_type ?? '', width: '90px', title: 'VSX variability type' },
    { id: 'mag', label: 'Range', value: (m) => m.mag_text ?? '', width: 'minmax(110px, 1fr)', title: 'Magnitude range (VSX)' },
    { id: 'period', label: 'Period d', numeric: true, value: (m) => m.period_d ?? null, format: (m) => num(m.period_d, 4), width: '96px' },
    { id: 'sep', label: 'Sep ′', numeric: true, value: (m) => m.sep_arcmin ?? null, format: (m) => num(m.sep_arcmin, 1), width: '72px', title: 'From the field centre, arcmin' },
  ];
  const STAR_COLS: Column<Marker>[] = [
    { id: 'name', label: 'Star', value: (m) => m.name || m.label || '', format: (m) => m.name || m.label || 'Gaia DR3', width: 'minmax(140px, 1.4fr)' },
    { id: 'g', label: 'G', numeric: true, value: (m) => m.g_mag ?? null, format: (m) => num(m.g_mag, 2), width: '72px', title: 'Gaia G magnitude' },
    { id: 'bprp', label: 'BP−RP', numeric: true, value: (m) => (m.bp_mag != null && m.rp_mag != null ? m.bp_mag - m.rp_mag : null), format: (m) => (m.bp_mag != null && m.rp_mag != null ? fixed(m.bp_mag - m.rp_mag, 2) : '—'), width: '80px', title: 'Gaia colour' },
    { id: 'det', label: 'On frame', value: (m) => (m.detected === undefined ? '' : m.detected ? 'detected' : ''), width: '90px', title: 'A source was detected there on the solved frame' },
  ];
  let varSel: string | null = $state(null);
  let starSel: string | null = $state(null);
</script>

{#if compact}
  <div class="row-compact">
    <span class="k">Ensemble</span>
    <span class="grp"><NumText text={`${summary.comparisons} comparison${summary.comparisons === 1 ? '' : 's'}${summary.check ? ` · check ${summary.check}` : ' · no check star'}${summary.flagged ? ` · ${summary.flagged} flagged` : ''}`} /></span>
    <span class="div" aria-hidden="true"></span>
    <span class="k">Candidates</span><span class="num">{summary.candidates}</span>
    {#if live}<span class="live-slot">{@render live(true)}</span>{/if}
  </div>
{:else}
  <div class="wrap">
    <div class="tabs" role="tablist" aria-label="Field lists">
      {#each [
        { id: 'candidates', label: 'Candidates', n: candRows.length },
        { id: 'ensemble', label: 'Ensemble', n: ensRows.length },
        { id: 'variables', label: 'Variables', n: variables.length },
        { id: 'stars', label: 'Stars', n: stars.length },
      ] as t (t.id)}
        <button type="button" role="tab" aria-selected={tab === t.id} class:on={tab === t.id} onclick={() => (tab = t.id as Tab)}>
          {t.label} <span class="n num">{field.layersAvailable ? int(t.n) : '—'}</span>
        </button>
      {/each}
      {#if live}<span class="live-slot">{@render live(false)}</span>{/if}
    </div>
    {#if field.layersAvailable && (tab === 'candidates' || tab === 'ensemble')}
      <p class="note" title="{contextText} · {commonText.join(' · ')} · {rulesText}">
        <span>{contextText}</span>{#each commonText as t (t)}<span class="sep" aria-hidden="true">·</span><span class="common">{t}</span>{/each}<span class="sep" aria-hidden="true">·</span><span>{rulesText}</span>
      </p>
    {/if}
    {#if !field.layersAvailable}
      <p class="empty">{field.solving ? 'Identifying the field…' : 'Identify the field (S) to list the comparison candidates, the variables and the Gaia stars of the frame.'}</p>
    {:else if tab === 'variables'}
      <VirtualTable
        label="VSX variables in the field"
        columns={VAR_COLS}
        rows={variables}
        rowKey={mKey('variables')}
        bind:selected={varSel}
        highlight={hotId}
        empty="No VSX variable in this field."
        onhover={(m) => markerHover('variables', m)}
        onactivate={(m) => onlistpick?.('variables', m)}
      />
    {:else if tab === 'stars'}
      <VirtualTable
        label="Gaia stars in the field"
        columns={STAR_COLS}
        rows={stars}
        rowKey={mKey('stars')}
        bind:selected={starSel}
        highlight={hotId}
        empty="No Gaia star in this field (Settings ▸ Catalogues: Gaia depth)."
        onhover={(m) => markerHover('stars', m)}
        onactivate={(m) => onlistpick?.('stars', m)}
      />
    {:else if !rows.length}
      <p class="empty">
        {tab === 'ensemble'
          ? 'No comparison or check star in the set yet: click a star on the image to give it a role.'
          : 'No VSP comparison star detected in this frame. Choose comparisons on the image, or check Settings ▸ Catalogues (VSP).'}
      </p>
    {:else}
      <div class="scroll">
        <table role="grid" aria-label={tab === 'ensemble' ? 'Ensemble: comparisons and check' : 'Comparison candidates'} aria-rowcount={rows.length + 1}>
          <thead>
            <tr>
              {#each COLS as c (c.key)}
                <th class:num={c.num} aria-sort={sortKey === c.key ? (asc ? 'ascending' : 'descending') : 'none'}>
                  <button type="button" tabindex="-1" onclick={() => sortBy(c.key)} title={c.title}>
                    {c.label}{#if sortKey === c.key}<svg class="arrow" class:up={asc} viewBox="0 0 10 10" aria-hidden="true"><path d="M2.5 3.75 5 6.25 7.5 3.75" /></svg>{/if}
                  </button>
                </th>
              {/each}
            </tr>
          </thead>
          <tbody onpointerleave={() => hover(null)}>
            {#each rows as r, i (r.key)}
              <tr
                animate:flip={{ duration: dur }}
                class:hov={hotKey === r.key || (field.hover?.source === 'candidates' && field.hover.key === r.key)}
                class:sel={field.inspected === r.key}
                class:flag={r.flags.length > 0}
                tabindex={r.key === focusKey ? 0 : -1}
                aria-selected={field.inspected === r.key}
                onpointerenter={() => hover(r)}
                onfocus={() => hover(r)}
                onblur={() => hover(null)}
                onclick={() => pick(r)}
                onkeydown={(e) => rowKey(e, i, r)}
              >
                <td class="role"><RoleGlyph role={r.role} label={r.role ?? 'candidate'} /></td>
                <td class="name">{r.name}</td>
                <td class="num">{r.v === null ? '—' : fixed(r.v, 2)}</td>
                <td class="num">{r.bv === null ? '—' : fixed(r.bv, 2)}</td>
                <td class="num" class:warn={warn(r, 'colour')}>{r.dbv === null ? '—' : signed(r.dbv, 2)}</td>
                <td class="num" class:warn={warn(r, 'far')}>{r.sep === null ? '—' : fixed(r.sep, 1)}</td>
                <td class="num" class:warn={warn(r, 'clipped') || warn(r, 'non-linear')}>{r.peak === null ? '—' : r.clipped ? 'clipped' : int(r.peak)}</td>
                <td class="num">{r.snr === null ? '—' : int(r.snr)}</td>
                <td class="num" class:warn={warn(r, 'blend risk')}>{r.nbr === null ? '—' : r.nbr}</td>
                <td class="status">{r.status}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>
{/if}

<style>
  .live-slot {
    display: inline-flex;
    min-width: 0;
    margin-left: auto;
  }
  .wrap {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .wrap > :global(.vt) {
    flex: 1;
  }
  .tabs {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    height: 30px;
    padding: 0 var(--space-2);
    flex: none;
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .tabs button {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 24px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font: inherit;
    font-size: var(--text-s);
    cursor: pointer;
  }
  .tabs button:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .tabs button.on {
    background: var(--toggled-bg);
    border-color: var(--border);
    color: var(--fg);
  }
  .tabs button:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .n {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  /* The target's context and the rules, in words (BRAND 7): one line under the tabs. */
  .note {
    flex: none;
    margin: 0;
    padding: 2px var(--space-3);
    overflow: hidden;
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: 18px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .note .common {
    color: var(--fg);
  }
  .note .sep {
    padding: 0 0.45em;
  }
  .scroll {
    flex: 1;
    min-height: 0;
    overflow: auto;
  }
  table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: var(--text-s);
  }
  th {
    position: sticky;
    top: 0;
    z-index: 1;
    height: 26px;
    padding: 0;
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg-2);
    text-align: left;
  }
  /* The shared Table's header (README 3.5): sentence case, --text-xs, muted. */
  th button {
    width: 100%;
    height: 100%;
    padding: 0 var(--space-3);
    border: none;
    background: transparent;
    color: var(--text-muted);
    font: inherit;
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    text-align: inherit;
    white-space: nowrap;
    cursor: pointer;
  }
  th button:hover,
  th[aria-sort='ascending'] button,
  th[aria-sort='descending'] button {
    color: var(--fg);
  }
  th.num {
    text-align: right;
  }
  .arrow {
    width: 10px;
    height: 10px;
    margin-left: 2px;
    vertical-align: -1px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.25;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .arrow.up {
    transform: rotate(180deg);
  }
  td {
    height: var(--row-h, 24px);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg);
    white-space: nowrap;
  }
  td.num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
    text-align: right;
  }
  td.name {
    font-family: var(--font-mono);
  }
  td.status {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  /* A rule broken: underlined in --warning, and the word in Status (never colour alone). */
  td.warn {
    text-decoration: underline;
    text-decoration-color: var(--warning);
    text-decoration-thickness: 2px;
    text-underline-offset: 3px;
  }
  tr {
    cursor: pointer;
    outline: none;
  }
  tbody tr:hover,
  tr.hov {
    background: var(--hover-bg);
  }
  tr.sel {
    background: var(--toggled-bg);
  }
  tr.sel td:first-child {
    box-shadow: inset 2px 0 0 var(--accent);
  }
  tr:focus-visible td {
    box-shadow: inset 0 var(--focus-ring-w) 0 var(--focus-ring), inset 0 calc(-1 * var(--focus-ring-w)) 0 var(--focus-ring);
  }
  tr.flag td.status {
    color: var(--fg);
  }
  .role :global(svg) {
    display: block;
  }
  .empty {
    margin: 0;
    padding: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .row-compact {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 100%;
    padding: 0 var(--space-3);
    color: var(--fg);
    font-size: var(--text-s);
  }
  /* Between the summary's key-value groups (the rest of the row's rule). */
  .row-compact .div {
    width: 1px;
    height: 14px;
    background: var(--border-soft);
    flex: none;
  }
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
</style>
