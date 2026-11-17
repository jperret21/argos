<!--
  Find a place (02 1.7 #7-#10, W3; A82): an explicit online search, never
  automatic. Enter or [Search] starts the server's `site_search` job
  (OpenStreetMap Nominatim for places, Open-Meteo for the elevation, 8 s
  each); Cancel or editing the query abandons it (the job is cancelled, its
  answer dropped). The matches are a radio list with their values visible
  before choosing (Qt had a combo); [Use as default site] writes the four
  site keys in one commit, with Undo. The elevation is a terrain model:
  the caption says so (Qt configuration_page.py:895-896).
-->
<script lang="ts">
  import type { PlaceResult } from '../api/types';
  import { ApiError } from '../api/client';
  import { useApp } from '../app/state.svelte';
  import Control from '../components/Control.svelte';
  import { coordsText, currentSite, elevationText, siteChanges, siteFromPlace, siteText } from './sites';

  const app = useApp();

  let query = $state('');
  let jobId: string | null = $state(null);
  let places: PlaceResult[] = $state.raw([]);
  let chosen = $state(-1);
  let note: { tone: 'info' | 'warning' | 'error'; text: string } | null = $state.raw(null);
  let applying = $state(false);
  let searchedFor = $state('');

  const job = $derived(jobId ? app.jobs.get(jobId) : null);
  const running = $derived(!!job && (job.state === 'queued' || job.state === 'running'));
  const stage = $derived(
    running && job
      ? job.stage === 'elevation'
        ? `Elevation of the matches (${job.done} of ${job.total ?? '?'})…`
        : 'Searching OpenStreetMap Nominatim…'
      : '',
  );

  async function search(): Promise<void> {
    const q = query.trim();
    if (!q) {
      note = { tone: 'warning', text: 'Enter a city, country, or address first.' };
      return;
    }
    if (running && jobId) void app.jobs.cancel(jobId);
    places = [];
    chosen = -1;
    note = null;
    searchedFor = q;
    try {
      const answer = await app.client.startSiteSearch(q);
      app.jobs.ingest(answer.job);
      jobId = answer.job_id;
      const final = await app.waitJob(answer.job_id);
      if (jobId !== answer.job_id) return; // abandoned (a newer search or an edit)
      if (final.state === 'done') {
        const r = final.result as { places?: PlaceResult[] } | null;
        places = r?.places ?? [];
        chosen = places.length ? 0 : -1;
        note = places.length
          ? { tone: 'info', text: 'Choose a match, then use it. Elevation is terrain-modelled: edit it for a surveyed site.' }
          : { tone: 'warning', text: `No place found for “${q}”.` };
      } else if (final.state === 'failed') {
        note = { tone: 'error', text: final.error?.message ?? 'Location search failed.' };
      } else {
        note = { tone: 'info', text: 'Search cancelled.' };
      }
    } catch (err) {
      if (err instanceof ApiError && err.code === 'busy' && err.owner) {
        note = { tone: 'warning', text: 'Another place search is running (another window): wait for it, then search again.' };
      } else {
        note = { tone: 'error', text: err instanceof Error ? err.message : String(err) };
      }
    }
  }

  function cancel(): void {
    if (jobId && running) void app.jobs.cancel(jobId);
  }

  /** Editing the query abandons a running search (02 2.4 "Long work"). */
  function onInput(v: string): void {
    query = v;
    if (running && v.trim() !== searchedFor) {
      cancel();
      jobId = null;
      note = { tone: 'info', text: 'Search abandoned: the query changed.' };
    }
  }

  async function useChosen(): Promise<void> {
    const place = places[chosen];
    if (!place || applying) return;
    const before = currentSite(app.configValues);
    const next = siteFromPlace(place, before);
    applying = true;
    try {
      await app.patchConfig(siteChanges(next));
      note = { tone: 'info', text: `Default site set: ${siteText(next)}.` };
      app.undo.push({
        title: `Default site: ${next.name}`,
        detail: `Was ${siteText(before)}`,
        undo: () => app.patchConfig(siteChanges(before)),
      });
    } catch (err) {
      note = { tone: 'error', text: err instanceof Error ? err.message : String(err) };
    } finally {
      applying = false;
    }
  }
</script>

<div class="place-search">
  <div class="row">
    <label class="key" for="place-query">Find a place</label>
    <input
      id="place-query"
      class="query"
      type="text"
      autocomplete="off"
      spellcheck="false"
      placeholder="City, country, or address (e.g. Saint-Michel-l'Observatoire)"
      value={query}
      oninput={(e) => onInput(e.currentTarget.value)}
      onkeydown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          void search();
        }
      }}
    />
    {#if running}
      <Control icon="stop" label="Cancel" showLabel size="s" variant="secondary" onclick={cancel} />
    {:else}
      <Control
        icon="search"
        label="Search"
        showLabel
        size="s"
        variant="secondary"
        tooltip="top"
        tooltipText="Search online: OpenStreetMap Nominatim, then Open-Meteo for the elevation"
        disabledReason={app.linkOpen ? null : 'the ARGOS server is not reachable'}
        onclick={() => void search()}
      />
    {/if}
  </div>
  <p class="caption">
    Online, only when you press Search: OpenStreetMap Nominatim (places) and Open-Meteo (elevation). Nothing is
    written until you use a match.
  </p>

  {#if running}
    <p class="note" aria-live="polite"><span class="spin" aria-hidden="true"></span>{stage}</p>
  {:else if note}
    <p class="note tone-{note.tone}" role={note.tone === 'error' ? 'alert' : 'status'}>{note.text}</p>
  {/if}

  {#if places.length}
    <div class="matches" role="radiogroup" aria-label="Matches">
      {#each places as p, i (p.label + i)}
        <label class="match" class:chosen={i === chosen}>
          <input type="radio" name="place-match" checked={i === chosen} onchange={() => (chosen = i)} />
          <span class="radio" aria-hidden="true"></span>
          <span class="label">{p.label}</span>
          <span class="num coords">{coordsText(p.latitude, p.longitude)}</span>
          <span class="num elev">{elevationText(p.elevation_m)}</span>
        </label>
      {/each}
    </div>
    <div class="use">
      <Control
        icon="site"
        label="Use as default site"
        showLabel
        size="s"
        variant="secondary"
        busy={applying}
        disabledReason={chosen < 0 ? 'choose a match first' : null}
        onclick={() => void useChosen()}
      />
    </div>
  {/if}
</div>

<style>
  .place-search {
    max-width: var(--page-max-w);
  }
  .row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-3);
  }
  .key {
    color: var(--fg);
    font-size: var(--text-m);
    font-weight: var(--weight-medium);
  }
  .query {
    height: var(--input-h);
    min-width: 0;
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font: inherit;
    font-size: var(--text-m);
  }
  .query::placeholder {
    color: var(--text-muted);
  }
  .query:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  p {
    margin: 0;
  }
  .caption {
    margin-top: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .note {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-top: var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .note.tone-warning,
  .note.tone-error {
    color: var(--fg);
  }
  .note.tone-warning::before,
  .note.tone-error::before {
    content: '';
    flex: none;
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
    background: var(--warning);
  }
  .note.tone-error::before {
    background: var(--danger);
  }
  .spin {
    flex: none;
    width: 10px;
    height: 10px;
    border: 1.5px solid var(--fg-muted);
    border-right-color: transparent;
    border-radius: var(--radius-round);
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spin {
      animation: none;
    }
  }
  .matches {
    display: flex;
    flex-direction: column;
    margin-top: var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .match {
    position: relative;
    display: grid;
    grid-template-columns: 16px minmax(0, 1fr) auto minmax(72px, auto);
    align-items: center;
    gap: var(--space-3);
    min-height: var(--row-h);
    padding: 3px var(--space-3);
    font-size: var(--text-s);
    cursor: pointer;
  }
  .match + .match {
    border-top: var(--border-w) solid var(--border-soft);
  }
  .match:hover {
    background: var(--hover-bg);
  }
  .match input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
  .radio {
    width: 12px;
    height: 12px;
    border: 1.5px solid var(--fg-muted);
    border-radius: var(--radius-round);
  }
  /* Chosen: a filled centre inside the ring (a hard edge, no gradient). */
  .chosen .radio {
    border-color: var(--fg);
    background: var(--fg);
    box-shadow: inset 0 0 0 2px var(--bg-2);
  }
  .match:has(input:focus-visible) {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .label {
    min-width: 0;
    overflow: hidden;
    color: var(--fg);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .coords,
  .elev {
    color: var(--fg);
    text-align: right;
    white-space: nowrap;
  }
  .use {
    display: flex;
    justify-content: flex-end;
    margin-top: var(--space-2);
  }
</style>
