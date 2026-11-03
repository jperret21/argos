<!--
  Settings › Plate solving (02 1.9, 1.14, W5; M30, M35, M37). The ASTAP
  status (A81: the program the solve would run, the star database and the
  -D / -d flags it passes) is re-read after every change of the three ASTAP
  keys, from any client. The database set is unavailable with the reason
  while a database folder is set (Q-C9: ASTAP ignores it then). The
  automatic-solving keys sit under Advanced (Q-C4).
-->
<script lang="ts">
  import type { AstapState } from '../../api/types';
  import { useApp } from '../../app/state.svelte';
  import Control from '../../components/Control.svelte';
  import StatusBadge from '../../components/StatusBadge.svelte';
  import SettingsBlock from '../SettingsBlock.svelte';

  interface Props {
    query?: string;
  }
  let { query = '' }: Props = $props();

  const app = useApp();
  const KEYS = [
    'astrometry.astap_path',
    'astrometry.database_path',
    'astrometry.database',
    'astrometry.search_radius_deg',
    'astrometry.downsample',
    'astrometry.use_scale_hint',
    'astrometry.grid_spacing_arcmin',
    'astrometry.live_search_radius_deg',
    'astrometry.live_resolve_s',
    'astrometry.live_resolve_arcmin',
    'astrometry.live_timeout_s',
  ];

  let astap = $state.raw<AstapState | null>(null);
  let loading = $state(false);
  let error: string | null = $state(null);

  const watched = $derived(
    [
      app.configValues?.['astrometry.astap_path'],
      app.configValues?.['astrometry.database_path'],
      app.configValues?.['astrometry.database'],
    ].join('|'),
  );

  async function refresh(): Promise<void> {
    loading = true;
    try {
      astap = await app.client.astap();
      error = null;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    void watched;
    if (app.linkOpen) void refresh();
  });

  const found = $derived(!!astap?.astap);
</script>

<div class="page">
  {#if !query}
    <section class="astap" aria-labelledby="astap-title">
      <div class="head">
        <h3 class="title" id="astap-title">ASTAP</h3>
        {#if astap}
          <StatusBadge tone={found ? 'ok' : 'error'} label={found ? 'Found' : 'Not found'} />
          {#if found}
            <StatusBadge tone={astap.database_found ? 'ok' : 'busy'} label={astap.database_found ? 'Star database found' : 'No star database'} />
          {/if}
        {/if}
        <span class="spacer"></span>
        <Control
          icon="refresh"
          label="Detect again"
          size="xs"
          variant="ghost"
          tooltip="top"
          busy={loading}
          disabledReason={app.linkOpen ? null : 'the ARGOS server is not reachable'}
          onclick={() => void refresh()}
        />
      </div>
      {#if error}
        <p class="line bad">{error}</p>
      {:else if astap}
        {#if !found || !astap.database_found}<p class="line">{astap.message}</p>{/if}
        {#if astap.astap}<p class="line"><span class="key">Program</span><span class="mono">{astap.astap}</span></p>{/if}
        {#if astap.database_dir}
          <p class="line">
            <span class="key">Database</span><span class="mono">{astap.database_dir}</span>
            <span class="muted">({astap.database_source === 'configured' ? 'the folder set below' : 'detected'})</span>
          </p>
        {/if}
        {#if astap.database_args.length}
          <p class="line"><span class="key">Solve flags</span><span class="mono">{astap.database_args.join(' ')}</span></p>
        {/if}
        {#if astap.database_ignored}
          <p class="line note">The database set is ignored while a star database folder is set (ASTAP uses -d).</p>
        {/if}
      {:else}
        <p class="line muted">Detecting ASTAP…</p>
      {/if}
    </section>
  {/if}
  <SettingsBlock title="Solver" keys={KEYS.slice(0, 3)} {query} hideEmpty={!!query} />
  <SettingsBlock title="Solving" keys={KEYS.slice(3)} {query} hideEmpty={!!query} />
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }
  .astap {
    max-width: var(--page-max-w);
    padding: var(--space-3) var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: 26px;
  }
  .title {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
  }
  .spacer {
    flex: 1;
  }
  .line {
    display: flex;
    flex-wrap: wrap;
    gap: 0 var(--space-3);
    margin: var(--space-1) 0 0;
    color: var(--fg);
    font-size: var(--text-s);
    overflow-wrap: anywhere;
  }
  .key {
    width: 84px;
    flex: none;
    color: var(--text-muted);
  }
  .mono {
    font-family: var(--font-mono);
    font-size: var(--text-s);
  }
  .muted,
  .note {
    color: var(--text-muted);
  }
  .bad {
    color: var(--fg);
  }
</style>
