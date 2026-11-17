<!--
  Settings › Observer & site › Default site: the position as ONE compound
  row (02 2.3 W3; design review): latitude, longitude and elevation side by
  side, about 12 characters each, under one label, instead of three
  full-height rows. Each value is still its own commit (README 3.4: one
  PATCH per commit, refused with that key's words under its field); the
  server re-checks the site against the mount only once the site has stayed
  unchanged for 2 s (protocol.md "Site check"), so a half-typed position is
  never compared or logged.

  Personal keys (meta.personal): no "Reset to the default" (0°, 0° is not a
  site). Each field carries `data-key`, so the command palette, links and
  the "About this setting" column find it like any other row.
-->
<script lang="ts">
  import type { ConfigValue, KeyMeta } from '../api/types';
  import { useApp } from '../app/state.svelte';
  import NumberField from '../components/NumberField.svelte';
  import { commitKey, decimalsFor, signedFor } from '../components/settings';

  const KEYS = ['site.latitude', 'site.longitude', 'site.elevation'] as const;

  const app = useApp();
  const meta = $derived(app.configMeta ?? {});
  const values = $derived(app.configValues ?? {});
  const present = $derived(KEYS.filter((k) => k in meta));
  const patch = (changes: Record<string, ConfigValue>) => app.patchConfig(changes);
  const num = (v: ConfigValue | undefined) => (typeof v === 'number' ? v : null);
  const short: Record<string, string> = { 'site.latitude': 'Latitude', 'site.longitude': 'Longitude', 'site.elevation': 'Elevation' };
  const width = (m: KeyMeta) => (m.unit === 'm' ? 'calc(9ch + 34px)' : 'calc(11.4ch + 34px)');
</script>

{#if present.length}
  <div class="position" role="group" aria-labelledby="site-position-label">
    <div class="label-col">
      <span class="label" id="site-position-label">Position</span>
      <p class="help">Geodetic, north and east positive. FITS SITELAT / SITELONG / SITEELEV; altitude, airmass and visibility.</p>
    </div>
    <div class="fields">
      {#each present as key (key)}
        {@const m = meta[key]}
        <div class="cell" data-key={key}>
          <NumberField
            label={short[key] ?? m.label}
            value={num(values[key])}
            unit={m.unit ?? undefined}
            min={m.min ?? -Infinity}
            max={m.max ?? Infinity}
            step={m.step ?? 1}
            decimals={decimalsFor(m)}
            signed={signedFor(key)}
            width={width(m)}
            appliedWord="Saved"
            dirtyWord="Not saved"
            commitVerb="saves"
            reserve
            send={(v) => commitKey(patch, key, v)}
          />
        </div>
      {/each}
    </div>
  </div>
{/if}

<style>
  /* The grid of a SettingField row (label | controls), so the row lines up. */
  .position {
    display: grid;
    grid-template-columns: minmax(0, 15fr) minmax(0, 17fr) 52px;
    align-items: start;
    gap: var(--space-1) var(--space-5);
    padding: 6px 0 6px var(--space-4);
  }
  @container settings (max-width: 520px) {
    .position {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  .label-col {
    min-width: 0;
    padding-top: 5px;
  }
  .label {
    color: var(--fg);
    font-size: var(--text-m);
    font-weight: var(--weight-medium);
    line-height: var(--leading-tight);
  }
  .help {
    margin: 2px 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
  }
  .fields {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-4);
    min-width: 0;
  }
  .cell {
    min-width: 0;
  }
</style>
