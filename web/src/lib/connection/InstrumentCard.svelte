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
    to Settings › Observer & site. A missing site is a science error, so it
    reads as a warning. Wave 2: the site-against-mount check under it (the
    server's verdict): a mismatch is a warning line with both altitudes and
    the angle between the directions; an agreement is one muted line.
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import Card from '../components/Card.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Select from '../components/Select.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { fixed } from '../format/number';
  import { siteCheckView } from '../settings/categories';
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
      detail: `${p.sensor} · ${fixed(p.arcsec_per_px, 2)}″/px${p.validated ? '' : ' · not validated'}`,
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
  const check = $derived(app.siteCheck);
  const checkView = $derived(siteCheckView(check));
  /** One line: "88.5° apart · mount alt 75.4°, Settings site alt 13.8°". */
  const checkLine = $derived.by(() => {
    if (!check) return null;
    if (check.state === 'mismatch') {
      const parts: string[] = [];
      if (check.separation_deg !== null) parts.push(`${fixed(check.separation_deg, 1)}° apart`);
      if (check.mount && check.expected) {
        parts.push(`mount alt ${fixed(check.mount.alt_deg, 2)}°, Settings site alt ${fixed(check.expected.alt_deg, 2)}°`);
      } else if (check.driver_site?.distance_km != null) {
        parts.push(`the mount's own site is ${fixed(check.driver_site.distance_km, 0)} km away`);
      }
      return parts.join(' · ');
    }
    if (check.state === 'ok' && check.separation_deg !== null) {
      return `Agrees with the mount (${fixed(check.separation_deg, 1)}° apart${checkView.when ? `, ${checkView.when}` : ''})`;
    }
    return null;
  });
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
        onclick={() => app.openSettings('observer_site')}
      />
    </div>

    {#if check?.state === 'mismatch'}
      <span></span>
      <p class="note warning site-check" role="alert">
        <StatusBadge variant="alert" level="attention" label="Site ≠ mount" live={false} />
        <span class="lead">The Settings site disagrees with the mount: airmass, BJD and the FITS site would be wrong.</span>
        {#if checkLine}<span class="num">{checkLine}</span>{/if}
      </p>
    {:else if checkLine}
      <span></span>
      <p class="check-ok num">{checkLine}</p>
    {/if}
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
  .site-check {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }
  .check-ok {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
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
