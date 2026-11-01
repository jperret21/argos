<!--
  Instrument card (02 2.2 / 2.3 W1, Qt connection_page.py:122-169, M22):
  the telescope profile, its derived specs, validated or not, the caveats,
  the server's profile-mismatch notes and the observing site (read-only,
  Q-C10).

  - The profile is chosen here only (D28): a token-drawn Select, locked with
    the server's reason while any device holds the link (it sets plate
    scale, sensor geometry and FITS metadata). The server stays the guard
    (409 busy, shown verbatim).
  - Unvalidated profiles say so in one wording (Q-C2) with their caveats.
  - Site: name, coordinates (5 decimals, signed) and elevation, with a link
    to Settings (Observer & site, wave 2). A missing site is a science
    error, so it reads as a warning.
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import Card from '../components/Card.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Select from '../components/Select.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { profileSpecs, siteSummary, UNVALIDATED_TEXT } from './model';

  const app = useApp();

  const LOCK_REASON =
    'Disconnect the equipment before changing the telescope: it sets plate scale, sensor geometry and FITS metadata.';

  const profiles = $derived(app.profiles);
  const active = $derived(profiles?.profiles.find((p) => p.key === profiles.active) ?? null);
  const options = $derived(
    (profiles?.profiles ?? []).map((p) => ({
      value: p.key,
      label: p.name,
      detail: `${p.sensor} · ${p.arcsec_per_px.toFixed(2)}″/px${p.validated ? '' : ' · not validated'}`,
      detailMono: true,
    })),
  );
  const lockReason = $derived.by(() => {
    if (!app.linkOpen) return 'the ARGOS server is not reachable';
    if (app.equipment.anyLinked) return LOCK_REASON;
    if (app.busy.profile) return 'changing the profile';
    return null;
  });
  const mismatch = $derived(app.devices?.camera?.warnings ?? []);
  const site = $derived(siteSummary(app.configValues));
</script>

<Card title="Instrument" icon="mount" dense>
  {#snippet status()}
    {#if active}
      <StatusBadge tone={active.validated ? 'ok' : 'busy'} label={active.validated ? 'Validated' : 'Not validated'} />
    {/if}
  {/snippet}

  <div class="grid">
    <span class="key" aria-hidden="true">Telescope</span>
    <div class="value">
      <Select
        label="Telescope"
        hideLabel
        {options}
        value={profiles?.active ?? null}
        placeholder={profiles ? 'Choose the telescope' : 'Loading the profiles…'}
        disabledReason={profiles ? lockReason : 'waiting for the server'}
        onchange={(key) => app.setProfile(key)}
      />
    </div>

    {#if active}
      <span class="key" aria-hidden="true">Optics</span>
      <p class="specs num" aria-label="Profile specifications">{profileSpecs(active)}</p>
    {/if}

    {#if active && !active.validated}
      <span></span>
      <div class="note warning" role="note">
        <p class="lead">{UNVALIDATED_TEXT}</p>
        {#if active.caveats.length}
          <ul>
            {#each active.caveats as c (c)}<li>{c}</li>{/each}
          </ul>
        {/if}
      </div>
    {/if}

    {#each mismatch as w (w)}
      <span></span>
      <p class="note warning" role="status">{w}</p>
    {/each}

    <span class="key site-key" class:missing={site.missing} aria-hidden="true">Site</span>
    <div class="site">
      <span class="site-value">
        {#if site.missing}
          <span>No observing site set: FITS site keywords and airmass would be wrong.</span>
        {:else}
          <span>{site.name}</span>
          <span class="num">{site.coords} · {site.elevation}</span>
        {/if}
      </span>
      <IconButton
        icon="nav-configuration"
        label="Settings"
        showLabel
        size="s"
        variant="ghost"
        tooltip="top"
        tooltipText="Observer & site are set in Settings (F5)"
        onclick={() => app.go('configuration')}
      />
    </div>
  </div>
</Card>

<style>
  .grid {
    display: grid;
    grid-template-columns: 64px minmax(0, 1fr);
    align-items: center;
    gap: var(--space-2) var(--space-3);
    font-size: var(--text-s);
  }

  .key {
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  .value {
    min-width: 0;
  }

  .specs {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
    line-height: var(--leading-normal);
  }

  .note {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-left: 2px solid var(--warning);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-s);
    line-height: var(--leading-normal);
  }
  .note .lead {
    margin: 0;
  }
  .note ul {
    margin: var(--space-1) 0 0;
    padding-left: var(--space-5);
    color: var(--text-muted);
  }

  .site {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-width: 0;
  }
  .site-value {
    display: flex;
    flex: 1;
    flex-wrap: wrap;
    gap: 0 var(--space-3);
    min-width: 0;
    color: var(--fg);
  }
  .site :global(.icon-button) {
    height: 26px;
  }
  /* A missing site is a science error: the attention ring beside the key (the words say it),
     the same mark as the Link card's setup line and the rail's Settings entry. */
  .site-key.missing::after {
    content: '';
    display: inline-block;
    width: 7px;
    height: 7px;
    margin-left: var(--space-2);
    border-radius: var(--radius-round);
    box-shadow: inset 0 0 0 1.5px var(--warning);
    vertical-align: middle;
  }
</style>
