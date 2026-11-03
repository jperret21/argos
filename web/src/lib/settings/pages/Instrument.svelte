<!--
  Settings › Instrument (02 1.8, W4; M29, D28, Q-C1). The telescope profile
  is a read-only mirror here: it is chosen on the Connection screen, which
  checks that no equipment is connected. Sensor limits are the overrides of
  the profile for your unit (empty = the profile's value, shown as the
  placeholder); the ADC depth is the profile's (read-only, Q-C1). The
  photon-transfer calibration folder describes the sensor. Advanced: the
  access-point address, the ADC depth and the electron gain table; the
  legacy Qt copies (read-only mirrors) in a closed "Qt app compatibility"
  disclosure at the end.
-->
<script lang="ts">
  import type { ConfigValue, KeyMeta } from '../../api/types';
  import { useApp } from '../../app/state.svelte';
  import Control from '../../components/Control.svelte';
  import StatusBadge from '../../components/StatusBadge.svelte';
  import { profileSpecs, UNVALIDATED_TEXT } from '../../connection/model';
  import { int } from '../../format/number';
  import EgainTable from '../EgainTable.svelte';
  import QtCompat from '../QtCompat.svelte';
  import SettingsBlock from '../SettingsBlock.svelte';

  interface Props {
    query?: string;
  }
  let { query = '' }: Props = $props();

  const app = useApp();
  const profiles = $derived(app.profiles);
  const active = $derived(profiles?.profiles.find((p) => p.key === profiles.active) ?? null);
  const placeholders = $derived<Record<string, string>>(
    active
      ? {
          'hardware.overrides.full_well_adu': `Profile: ${int(active.full_well_adu)}`,
          'hardware.overrides.linearity_max_adu': `Profile: ${int(active.linearity_max_adu)}`,
          // Read-only: the effective depth, where it comes from (never "not set").
          'hardware.overrides.adc_bits': `${active.adc_bits} bit · from the telescope profile`,
          'hardware.overrides.ap_host': active.ap_host ? `Profile: ${active.ap_host}` : 'Not set',
        }
      : {},
  );
  const lock = $derived(
    profiles?.locked ? (profiles.locked_reason ?? 'Locked while equipment is connected') : 'Changed on the Connection screen',
  );
</script>

{#snippet egain(_key: string, _meta: KeyMeta, value: ConfigValue | undefined)}
  <EgainTable {value} />
{/snippet}

<div class="page">
  {#if !query}
    <section class="group" aria-labelledby="profile-title" data-key="hardware.profile">
      <div class="head">
        <h3 class="title" id="profile-title">Telescope profile</h3>
        <p class="caption">{lock}</p>
      </div>
      {#if active}
        <div class="profile">
          <div class="line">
            <span class="name">{active.name}</span>
            <StatusBadge tone={active.validated ? 'ok' : 'busy'} label={active.validated ? 'Validated' : 'Not validated'} />
            <span class="spacer"></span>
            <Control
              icon="nav-connection"
              label="Change on Connection"
              showLabel
              size="xs"
              variant="ghost"
              tooltip="top"
              tooltipText="The profile is chosen in the Connection screen's Instrument card (F1)"
              onclick={() => app.go('connection')}
            />
          </div>
          <p class="specs num">{profileSpecs(active)} · ADC {active.adc_bits} bit</p>
          {#if !active.validated}
            <p class="warn" role="note">{UNVALIDATED_TEXT}</p>
          {/if}
          <p class="note">Do not change it mid-series: the plate scale would move under a running curve.</p>
        </div>
      {:else}
        <p class="note">Waiting for the telescope profiles…</p>
      {/if}
    </section>
  {/if}
  <SettingsBlock
    title="Sensor limits"
    caption="Override the profile for your unit; empty uses the profile's value."
    keys={['hardware.overrides.full_well_adu', 'hardware.overrides.linearity_max_adu']}
    {placeholders}
    {query}
    hideEmpty={!!query}
  />
  <SettingsBlock
    title="Photon-transfer calibrations"
    keys={['data_paths.camera_calibration_directory']}
    {query}
    hideEmpty={!!query}
  />
  <SettingsBlock
    keys={[
      'hardware.overrides.ap_host',
      'hardware.overrides.adc_bits',
      'camera.egain_table',
      ...(query ? ['hardware.profile'] : []),
    ]}
    {placeholders}
    {query}
    hideEmpty
    customKeys={['camera.egain_table']}
    custom={egain}
  />
  <QtCompat
    keys={['camera.full_well_adu', 'camera.linearity_max_adu']}
    caption="Copies the Qt app reads (same configuration file); they follow Saturation and Linearity limit above."
    {query}
  />
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }
  .group {
    max-width: var(--page-max-w);
  }
  .head {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0 var(--space-3);
    padding-bottom: var(--space-2);
    border-bottom: var(--border-w) solid var(--border);
  }
  .title {
    margin: 0;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .caption {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .profile {
    padding: var(--space-3) 0 0 var(--space-4);
  }
  .line {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .name {
    color: var(--fg);
    font-size: var(--text-m);
    font-weight: var(--weight-medium);
  }
  .spacer {
    flex: 1;
  }
  p {
    margin: 0;
  }
  .specs {
    margin-top: var(--space-1);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .warn {
    margin-top: var(--space-2);
    padding: var(--space-1) var(--space-3);
    border-left: 2px solid var(--warning);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .note {
    margin-top: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
