<!--
  Settings › Appearance (02 1.11 #3, W8; M16, D15, D16, Q-G6; owner D7).
  This browser: theme (live; also the rail footer's quick toggle), density
  (Compact or Comfortable: tokens, never a zoom; the image keeps its size),
  image rotation of the viewer (display only), and Reset all layouts (Undo).
  Shared by every viewer (server configuration): the Observe display depth
  and star aperture. The Qt app's own theme and rotation (shared file
  during the transition): this browser seeded its choices from them once.
-->
<script lang="ts">
  import { useApp } from '../../app/state.svelte';
  import { THEME_LABELS, THEMES, type Theme } from '../../app/theme';
  import { DENSITIES, DENSITY_LABELS, type Density } from '../../app/viewerprefs';
  import Control from '../../components/Control.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import { ROTATION_MODES, type RotationMode } from '../../viewer/rotation';
  import PrefRow from '../PrefRow.svelte';
  import QtCompat from '../QtCompat.svelte';
  import SettingsBlock from '../SettingsBlock.svelte';

  interface Props {
    query?: string;
  }
  let { query = '' }: Props = $props();

  const app = useApp();
  const ROTATION_LABELS: Record<RotationMode, string> = { auto: 'Auto', '0': '0°', '90': '90°', '180': '180°', '270': '270°' };
  const words = (q: string, ...hay: string[]) =>
    q
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean)
      .every((w) => hay.join(' ').toLowerCase().includes(w));
  const showViewer = $derived(!query || words(query, 'theme density comfortable compact rotation layout reset night red observatory charcoal'));
</script>

<div class="page">
  {#if showViewer}
    <section class="group" aria-labelledby="viewer-title">
      <div class="head">
        <h3 class="title" id="viewer-title">This browser</h3>
        <p class="caption">Kept per viewer: another window or computer keeps its own.</p>
      </div>
      <div class="rows">
        <PrefRow id="theme" label="Theme" help="Night Red keeps every pixel red for dark adaptation. Also one click on the rail's theme button.">
          <Segmented
            label="Theme"
            options={THEMES.map((t) => ({ value: t, label: THEME_LABELS[t] }))}
            value={app.theme}
            onchange={(t) => app.setTheme(t as Theme)}
          />
        </PrefRow>
        <PrefRow
          id="density"
          label="Density"
          help="Comfortable, for reading from a step away: the Mount readouts 20 px, card values and frame statistics 16 px, table rows 28 px, log lines 24 px. Toolbars, icons and the image keep their size."
        >
          <Segmented
            label="Density"
            options={DENSITIES.map((d) => ({ value: d, label: DENSITY_LABELS[d] }))}
            value={app.density}
            onchange={(d) => app.setDensity(d as Density)}
          />
        </PrefRow>
        <PrefRow
          id="rotation"
          label="Image rotation"
          help="Auto turns portrait frames to landscape. Display only: cursor readouts, overlays and coordinates sent to the server stay in frame pixels."
        >
          <Segmented
            label="Image rotation"
            options={ROTATION_MODES.map((r) => ({ value: r, label: ROTATION_LABELS[r] }))}
            value={app.rotation}
            onchange={(r) => app.setRotation(r as RotationMode)}
          />
        </PrefRow>
        <PrefRow
          id="layouts"
          label="Layouts"
          help="Every section back to its default panels, drawer, rail and card folds. Theme, density, rotation and settings stay."
        >
          <Control icon="layout-reset" label="Reset all layouts" showLabel size="s" variant="secondary" onclick={() => app.resetAllLayouts()} />
        </PrefRow>
      </div>
    </section>
  {/if}
  <SettingsBlock
    title="Observe display"
    caption="Server configuration, shared by every viewer."
    keys={['catalog.display_mag_limit', 'imaging.star_radius_px']}
    {query}
    hideEmpty={!!query}
  />
  <QtCompat
    keys={['ui.theme.preset', 'ui.display.rotation']}
    caption="Read by the Qt app (same configuration file). This browser took its theme and rotation from them once."
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
</style>
