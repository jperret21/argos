<!--
  Source card (06 §2.2 rows 1.5 #1-#13, §2.3.1, §2.3.3, §2.4; M72; Q-P8, Q-P10): the first card
  of the Plan rail, where planning starts.

  - Programme (Segmented, first row): Variable star, Exoplanet, Other. It decides the
    catalogue of the one search field (SourceSearch) and is remembered per viewer.
  - Variable star / Other: the name found becomes the observation's target (A39: the object
    name and the mount target; the photometry target only for a variable type, Q-P8). The
    card shows it (name, type, RA / Dec in BRAND 5, the catalogue) with a link to Observe,
    where the slew is made (it never slews from here).
  - Exoplanet: the planet (A42) and the transit the server chose (A66: the night asked for, or
    the next observable one; daylight and below-limit transits skipped, Q-P10): mid-transit
    in BJD_TDB, coverage in local and UTC times, altitudes, what limits it. A changed baseline
    or night predicts again at once (P5). "Prepare transit sequence" writes the series as the
    draft (the screen asks first when that replaces unsaved steps).
  - While a run is active the object is locked (Q-P9): the search and Prepare say why.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import type { Observation } from '../api/types';
  import Card from '../components/Card.svelte';
  import Control from '../components/Control.svelte';
  import NumberField from '../components/NumberField.svelte';
  import Segmented from '../components/Segmented.svelte';
  import Select from '../components/Select.svelte';
  import TextField from '../components/TextField.svelte';
  import { tooltip } from '../components/tooltip';
  import { formatDec, formatRA } from '../format/astro';
  import { fixed } from '../format/number';
  import { lightSlots, optionsWith, timeTitle, utcHm } from './model';
  import SourceSearch from './SourceSearch.svelte';
  import { altitudeText, coverageText, dateProblem, planetFacts, skippedText, type TransitPlanner, transitNote } from './transit.svelte';

  export type Programme = 'variable' | 'exoplanet' | 'other';

  interface Props {
    programme: Programme;
    onprogramme: (p: Programme) => void;
    /** The observation (object name, target). */
    observation: Observation | null;
    transit: TransitPlanner;
    /** Filter names for the transit series (the plan record's). */
    filters: readonly string[];
    filterSource?: string;
    /** Why the object cannot change now (a run is active). */
    lockedReason?: string | null;
    suggestNames: (q: string, signal: AbortSignal) => Promise<string[]>;
    suggestPlanets: (q: string, signal: AbortSignal) => Promise<string[]>;
    /** Find a star or an object: resolve it and make it the target. Rejects with the server's words. */
    findObject: (q: string, programme: Programme, signal: AbortSignal) => Promise<unknown>;
    /** Find a planet (A42), then its host becomes the target. */
    findPlanet: (q: string, signal: AbortSignal) => Promise<unknown>;
    onprepare: () => void;
    onobserve: () => void;
    open?: boolean;
    /** The search input (the screen's `/` key). */
    searchInput?: HTMLInputElement | null;
  }

  let {
    programme,
    onprogramme,
    observation,
    transit,
    filters,
    filterSource = 'wheel',
    lockedReason = null,
    suggestNames,
    suggestPlanets,
    findObject,
    findPlanet,
    onprepare,
    onobserve,
    open = $bindable(true),
    searchInput = $bindable(null),
  }: Props = $props();

  const PROGRAMMES = [
    { value: 'variable' as const, label: 'Variable star', icon: 'variable-star' },
    { value: 'exoplanet' as const, label: 'Exoplanet', icon: 'exoplanet' },
    { value: 'other' as const, label: 'Other', icon: 'other-objects' },
  ];
  const PLACEHOLDER: Record<Programme, string> = {
    variable: 'T CrB, RR Lyr, V404 Cyg…',
    exoplanet: 'HD 189733 b, WASP-12 b…',
    other: 'M 42, NGC 7000…',
  };

  const target = $derived(observation?.target ?? null);
  const f = $derived(transit.form);
  const p = $derived(transit.prediction);
  const planet = $derived(transit.planet);
  const cadenceShort = $derived(f.cadence_s < f.exposure_s ? `The cadence must be at least the exposure (${fixed(f.exposure_s, 2)} s)` : null);
  const dateErr = $derived(dateProblem(f.date));
  const filterOpts = $derived(
    optionsWith(lightSlots(filters), f.filter_name, `not in the ${filterSource}`),
  );
  const prepareReason = $derived(
    lockedReason ??
      (!p ? (transit.predicting ? 'the transit is being predicted' : 'find a planet and its transit first') : null) ??
      cadenceShort ??
      (!f.filter_name ? 'choose a filter' : null),
  );
  const cov = $derived(p ? coverageText(p) : null);

  // The series' filter: the first slot that passes light until the observer chooses one (S7).
  $effect(() => {
    const first = lightSlots(filters)[0];
    if (!f.filter_name && first) untrack(() => transit.set({ filter_name: first }));
  });
  const note = $derived(p ? transitNote(p) : null);
  const skipped = $derived(p ? skippedText(p) : null);

  // A changed baseline or night predicts again at once (P5); a lookup predicts by itself.
  let lastKey = '';
  $effect(() => {
    const key = `${planet?.planet_name ?? ''}|${f.baseline_minutes}|${f.date}`;
    if (!planet || key === lastKey) return;
    const first = lastKey === '';
    lastKey = key;
    if (!first) void transit.predict();
  });
</script>

<Card title="Source" icon="search" collapsible bind:open persist="argos.card.plan.source">
  {#snippet summary()}
    {programme === 'exoplanet' ? (planet?.planet_name ?? 'no planet') : (target?.name ?? 'no source')}
  {/snippet}

  <div class="body">
    <Segmented label="Programme" size="s" fill options={PROGRAMMES} value={programme} onchange={(v) => onprogramme(v)} />
    {#if programme === 'exoplanet'}
      <SourceSearch
        label="Exoplanet"
        placeholder={PLACEHOLDER.exoplanet}
        current={planet?.planet_name ?? f.planet}
        suggest={suggestPlanets}
        lookup={findPlanet}
        lookupHint="Earlier lookups, then the NASA Exoplanet Archive (up to 2 × 12 s)"
        disabledReason={lockedReason}
        bind:input={searchInput}
      />
      {#if planet}
        <div class="facts">
          <p class="title"><span class="name">{planet.planet_name}</span> <span class="muted">{`· host ${planet.host_name}`}</span></p>
          <p class="num small">{planetFacts(planet)}</p>
        </div>
      {/if}

      <div class="form">
        <span class="night" use:tooltip={{ text: 'The night (YYYY-MM-DD, its evening); empty: the next transit entirely in the dark and above the minimum altitude', placement: 'top' }}>
          <TextField label="Night" mono placeholder="next observable" value={f.date} error={dateErr} oninput={(e) => transit.set({ date: (e.currentTarget as HTMLInputElement).value.trim() })} />
        </span>
        <NumberField label="Baseline each side" value={f.baseline_minutes} unit="min" integer min={0} max={240} onchange={(v: number) => transit.set({ baseline_minutes: v })} />
        <NumberField label="Exposure" value={f.exposure_s} unit="s" decimals={2} onchange={(v: number) => transit.set({ exposure_s: v })} />
        <NumberField label="Cadence" value={f.cadence_s} unit="s" decimals={1} hint={cadenceShort} onchange={(v: number) => transit.set({ cadence_s: v })} />
        <NumberField label="Gain" value={f.gain} integer group={false} onchange={(v: number) => transit.set({ gain: v })} />
        <Select label="Filter" options={filterOpts} value={f.filter_name || null} placeholder="Choose" onchange={(v) => transit.set({ filter_name: v })} />
      </div>

      {#if transit.predicting && !p}
        <p class="muted small" role="status">Predicting the transit…</p>
      {:else if transit.predictError}
        <p class="bad small" role="alert">{transit.predictError}</p>
      {/if}
      {#if p && cov}
        <dl class="pred" aria-busy={transit.predicting || undefined}>
          <dt>Mid-transit</dt>
          <dd class="num">
            <span use:tooltip={{ text: `BJD_TDB ${p.window.mid_bjd_tdb.toFixed(6)} · ${timeTitle(p.utc.mid)}`, placement: 'top' }}>BJD {p.window.mid_bjd_tdb.toFixed(5)}</span>
            <span class="muted">(E = {p.window.epoch_number})</span>
          </dd>
          <dt>Coverage</dt>
          <dd class="num">
            <span>{cov.utc} UTC · {cov.hours}</span><br /><span class="muted">{cov.local} local</span>
          </dd>
          <dt>Night of</dt>
          <dd class="num">{p.night?.date ?? '—'}{#if p.night?.dusk_utc}<span class="muted">{` · dark ${utcHm(p.night.dusk_utc)} → ${utcHm(p.night.dawn_utc)} UTC`}</span>{/if}</dd>
          <dt>Altitude</dt>
          <dd class="num" use:tooltip={{ text: 'Altitudes without refraction', placement: 'top' }}>{altitudeText(p)}</dd>
        </dl>
        {#if note}<p class="warn small"><span class="mark" aria-hidden="true"></span>{note}</p>{/if}
        {#if skipped}<p class="muted small">{skipped}</p>{/if}
      {/if}
      <div class="actions">
        <Control icon="transit" label="Prepare transit sequence" showLabel variant="secondary" size="s" disabledReason={prepareReason} busy={transit.preparing} onclick={onprepare} />
      </div>
      {#if transit.prepareError}<p class="bad small" role="alert">{transit.prepareError}</p>{/if}
    {:else}
      <SourceSearch
        label={programme === 'variable' ? 'Variable star' : 'Object'}
        placeholder={PLACEHOLDER[programme]}
        current={target?.name ?? ''}
        suggest={suggestNames}
        lookup={(q, signal) => findObject(q, programme, signal)}
        lookupHint="Bundled catalogue, earlier lookups, then CDS Sesame online (8 s)"
        disabledReason={lockedReason}
        bind:input={searchInput}
      />
      {#if target}
        <div class="facts">
          <p class="title"><span class="name">{target.name}</span> <span class="muted">· {target.type_label || target.object_type || 'object'}</span></p>
          <p class="num small">RA {formatRA(target.ra_hours)} · Dec {formatDec(target.dec_deg)}</p>
          <p class="muted small">{target.source}{target.is_variable ? ' · photometry target' : ''}</p>
        </div>
        <div class="actions">
          <Control icon="goto" label="Slew in Observe" showLabel variant="ghost" size="s" tooltipText="Opens Observe with this target armed in the Mount card; nothing moves from here" onclick={onobserve} />
        </div>
      {:else}
        <p class="muted small">Find a source: it becomes the observation's object and the mount's target (the slew is made in Observe).</p>
      {/if}
    {/if}
  </div>
</Card>

<style>
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }
  .facts {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .facts p {
    margin: 0;
  }
  .title {
    font-size: var(--text-m);
  }
  .name {
    color: var(--fg);
    font-weight: var(--weight-semibold);
  }
  .muted {
    color: var(--text-muted);
  }
  .small {
    margin: 0;
    font-size: var(--text-s);
    line-height: var(--leading-tight);
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .bad {
    color: var(--fg);
  }
  .warn {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    color: var(--fg);
  }
  .warn .mark {
    flex: none;
    /* The attention mark, a bar over a dot (BRAND 8, run/LevelMark): never a triangle,
       the check star's shape (BRAND 2.6; design review W6a). */
    width: 3px;
    height: 9px;
    border: none;
    border-radius: 0;
    background: linear-gradient(var(--warning) 0 5px, transparent 5px 7px, var(--warning) 7px 9px);
  }
  .form {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-2) var(--space-3);
    align-items: start;
  }
  .night {
    display: block;
    min-width: 0;
  }
  .pred {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: 2px var(--space-3);
    margin: 0;
    font-size: var(--text-s);
  }
  .pred dt {
    color: var(--text-muted);
  }
  .pred dd {
    margin: 0;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .actions {
    display: flex;
    gap: var(--space-2);
  }
</style>
