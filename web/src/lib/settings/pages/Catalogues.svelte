<!--
  Settings › Catalogues (02 1.10, 1.15, W6; M31, M36). The bundled catalogue
  (A84, offline, read-only), the identification budget shared by Gaia and
  SIMBAD, then one group per source. The Gaia depth has its presets (Bright
  ≤ 15 · Standard ≤ 18 · Deep ≤ 20 · Custom) bound both ways to the G limit
  (fixes the Qt one-way sync, 02 1.15 #7). The network permissions are
  unavailable with the reason while their source is off, and mirrored in
  Privacy & diagnostics.
-->
<script lang="ts">
  import type { EssentialCatalogue } from '../../api/types';
  import { useApp } from '../../app/state.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import { int } from '../../format/number';
  import SettingsBlock from '../SettingsBlock.svelte';

  interface Props {
    query?: string;
  }
  let { query = '' }: Props = $props();

  const app = useApp();
  let essential: EssentialCatalogue | null = $state.raw(null);
  let essentialError: string | null = $state(null);
  $effect(() => {
    if (!app.linkOpen || essential) return;
    app.client
      .essentialCatalogue()
      .then((e) => (essential = e))
      .catch((err) => (essentialError = err instanceof Error ? err.message : String(err)));
  });

  const PRESETS = [
    { value: '15', label: 'Bright ≤ 15' },
    { value: '18', label: 'Standard ≤ 18' },
    { value: '20', label: 'Deep ≤ 20' },
    { value: 'custom', label: 'Custom' },
  ];
  const gaiaG = $derived(app.configValues?.['catalog.field_stars_mag_limit']);
  const gaiaOn = $derived(app.configValues?.['catalog.field_stars_enabled'] !== false);
  const preset = $derived(
    typeof gaiaG === 'number' && [15, 18, 20].includes(gaiaG) ? String(gaiaG) : 'custom',
  );
  let presetError: string | null = $state(null);

  async function setPreset(v: string): Promise<void> {
    if (v === 'custom') return; // the G field below is the custom value
    presetError = null;
    try {
      await app.patchConfig({ 'catalog.field_stars_mag_limit': Number(v) });
    } catch (err) {
      presetError = err instanceof Error ? err.message : String(err);
    }
  }
</script>

<div class="page">
  {#if !query}
    <section class="bundled" aria-labelledby="bundled-title">
      <h3 class="title" id="bundled-title">Bundled catalogue</h3>
      {#if essential}
        <p class="line">
          <span class="name">{essential.name} {essential.version}</span>
          <span class="num">{int(essential.object_count)} objects</span>
          <span class="muted">offline, read-only, inside the application</span>
        </p>
        <p class="line muted">Source: {essential.source}</p>
      {:else if essentialError}
        <p class="line muted">{essentialError}</p>
      {:else}
        <p class="line muted">Reading the bundled catalogue…</p>
      {/if}
    </section>
  {/if}
  <SettingsBlock title="Identification budget" keys={['catalog.identification_max_objects']} {query} hideEmpty={!!query} />
  <SettingsBlock
    title="Variable stars · AAVSO VSX"
    keys={['catalog.mag_limit', 'catalog.max_results', 'catalog.include_suspected']}
    {query}
    hideEmpty={!!query}
  />
  <SettingsBlock
    title="Field stars · Gaia DR3"
    keys={['catalog.field_stars_enabled', 'catalog.field_stars_mag_limit', 'catalog.field_stars_detected_only']}
    {query}
    hideEmpty={!!query}
  />
  {#if !query}
    <div class="preset">
      <span class="preset-key">Gaia depth preset</span>
      <Segmented
        label="Gaia depth preset"
        options={PRESETS}
        value={preset}
        disabled={!gaiaOn}
        onchange={(v) => void setPreset(v)}
      />
      <span class="preset-note">
        {#if !gaiaOn}Turn on Gaia DR3 identification first{:else if presetError}{presetError}{:else if preset === 'custom'}Custom: the Gaia depth above{:else}Sets the Gaia depth above{/if}
      </span>
    </div>
  {/if}
  <SettingsBlock
    title="Context layers · local, never online"
    keys={['catalog.show_essential_objects', 'catalog.show_cached_exoplanets']}
    {query}
    hideEmpty={!!query}
  />
  <SettingsBlock
    title="Named objects · SIMBAD"
    keys={['catalog.named_objects_enabled', 'catalog.named_objects_allow_network']}
    {query}
    hideEmpty={!!query}
  />
  <SettingsBlock
    title="Exoplanet hosts · NASA Exoplanet Archive"
    keys={['catalog.exoplanet_hosts_enabled', 'catalog.exoplanet_hosts_allow_network']}
    {query}
    hideEmpty={!!query}
  />
  {#if !query}
    <p class="foot">HD stays an online or cached lookup: there is no versioned J2000 pack yet.</p>
  {/if}
</div>

<style>
  .page {
    container: catalogues / inline-size;
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }
  .bundled {
    max-width: var(--page-max-w);
    padding: var(--space-3) var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .title {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
  }
  .line {
    display: flex;
    flex-wrap: wrap;
    gap: 0 var(--space-3);
    margin: var(--space-1) 0 0;
    font-size: var(--text-s);
    color: var(--fg);
  }
  .name {
    font-weight: var(--weight-medium);
  }
  .muted {
    color: var(--text-muted);
  }
  .preset {
    display: grid;
    grid-template-columns: minmax(0, 15fr) minmax(0, 17fr) 52px;
    align-items: center;
    gap: var(--space-1) var(--space-5);
    max-width: var(--page-max-w);
    margin-top: calc(-1 * var(--space-4));
    padding-top: var(--space-3);
    border-top: var(--border-w) solid var(--border-soft);
    padding-left: var(--space-4);
  }
  .preset-key {
    color: var(--fg);
    font-size: var(--text-m);
    font-weight: var(--weight-medium);
  }
  .preset :global(.segmented),
  .preset > :global(:nth-child(2)) {
    grid-column: 2;
  }
  .preset-note {
    grid-column: 2;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  /* Narrow (the Settings sheet over Observe is 560 px): the key above the control, which
     may wrap, so no segment ever crosses the box or the sheet's edge. */
  @container catalogues (max-width: 640px) {
    .preset {
      grid-template-columns: minmax(0, 1fr);
      padding-left: var(--space-3);
    }
    .preset :global(.segmented),
    .preset > :global(:nth-child(2)),
    .preset-note {
      grid-column: 1;
    }
    .preset :global(.segmented) {
      flex-wrap: wrap;
      max-width: 100%;
    }
  }
  .foot {
    max-width: var(--page-max-w);
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
