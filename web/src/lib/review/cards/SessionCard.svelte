<!--
  Rail card "Session" (07 E2 summary fields, E12 metadata; README M81, M91), folded by
  default: what was observed, when, with what (frames by filter, curves by role), the
  summary of session.json (P20), the problems met reading it, and the metadata read-only
  with a Copy (TSV) (fixes 07 P11: the Qt table was editable). Imported files say what
  they lack (07 WF-G).
-->
<script lang="ts">
  import Card from '../../components/Card.svelte';
  import Control from '../../components/Control.svelte';
  import { int } from '../../format/number';
  import { toTsv } from '../../charts/export';
  import type { SessionInfo, SourceKind } from '../session.svelte';

  interface Props {
    info: SessionInfo | null;
    kind: SourceKind | null;
    lights: number;
    missing: number;
    curves: { target: number; check: number; comparison: number };
    filters: readonly string[];
    problems: readonly string[];
    oncopy?: (tsv: string, rows: number) => void;
  }
  let { info, kind, lights, missing, curves, filters, problems, oncopy }: Props = $props();

  const frameFilters = $derived(
    Object.entries(info?.filters ?? {})
      .map(([f, n]) => `${f || '—'} ${int(n)}`)
      .join(' · '),
  );
  function copy(): void {
    if (!info) return;
    const rows = [['folder', info.folder], ['object', info.object], ['started_utc', info.startedUtc ?? ''], ['software', info.software ?? ''], ...info.metadata];
    oncopy?.(toTsv(['key', 'value'], rows), rows.length);
  }
</script>

<Card title="Session" icon="metadata" collapsible open={false} persist="review.session">
  {#snippet summary()}{info?.folder ?? ''}{/snippet}
  {#if info}
    <dl class="kv">
      <dt>Object</dt><dd>{info.object || '—'}</dd>
      <dt>Source</dt><dd class="num path" title={info.path}>{kind === 'import' ? `Imported · ${info.folder}` : kind === 'live' ? 'Live run (read-only)' : info.folder}</dd>
      {#if info.startedUtc}<dt>Started</dt><dd class="num">{info.startedUtc.replace('T', ' ').slice(0, 19)} UTC</dd>{/if}
      {#if kind === 'session'}
        <dt>Lights</dt><dd class="num">{int(lights)}{missing ? ` · ${int(missing)} FITS missing` : ''}</dd>
        {#if frameFilters}<dt>Filters</dt><dd class="num">{frameFilters}</dd>{/if}
      {/if}
      <dt>Curves</dt><dd class="num">{curves.target} T · {curves.check} K · {curves.comparison} C{filters.length > 1 ? ` · ${filters.length} filters` : ''}</dd>
      {#if info.software}<dt>Software</dt><dd>{info.software}</dd>{/if}
      {#each info.summary.filter((r) => r.known) as r (r.label)}<dt>{r.label}</dt><dd class="num">{r.value}</dd>{/each}
    </dl>
    {#if info.summary.some((r) => !r.known)}
      <details class="meta">
        <summary>More <span class="num">{info.summary.filter((r) => !r.known).length}</span></summary>
        <dl class="kv num">
          {#each info.summary.filter((r) => !r.known) as r (r.label)}<dt>{r.label}</dt><dd>{r.value}</dd>{/each}
        </dl>
      </details>
    {/if}
    {#if kind === 'import'}<p class="note">No frames and no quality report for an imported file.</p>{/if}
    {#if problems.length}
      <ul class="problems" aria-label="Problems reading the session">
        {#each problems as p (p)}<li>{p}</li>{/each}
      </ul>
    {/if}
    {#if info.metadata.length}
      <details class="meta">
        <summary>Metadata <span class="num">{info.metadata.length}</span></summary>
        <dl class="kv num">
          {#each info.metadata as [k, v] (k)}<dt>{k}</dt><dd>{v}</dd>{/each}
        </dl>
      </details>
    {/if}
    <div class="act"><Control icon="copy" label="Copy the session's metadata (TSV)" size="s" variant="ghost" tooltip="bottom" onclick={copy} /></div>
  {:else}
    <p class="note">No session open.</p>
  {/if}
</Card>

<style>
  .kv {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 3px var(--space-3);
    margin: 0;
    font-size: var(--text-xs);
  }
  .kv dt {
    color: var(--text-muted);
    font-family: var(--font-ui);
  }
  .kv dd {
    margin: 0;
    color: var(--fg);
    overflow-wrap: anywhere;
  }
  .path {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .note {
    margin: var(--space-2) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .problems {
    margin: var(--space-2) 0 0;
    padding-left: var(--space-4);
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .meta {
    margin-top: var(--space-2);
    font-size: var(--text-xs);
  }
  .meta summary {
    color: var(--text-muted);
    cursor: pointer;
  }
  .meta .kv {
    margin-top: var(--space-1);
    max-height: 180px;
    overflow-y: auto;
  }
  .act {
    margin-top: var(--space-2);
    display: flex;
    justify-content: flex-end;
  }
</style>
