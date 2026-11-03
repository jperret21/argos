<!--
  Settings › Photometry (02 W8; Q-C4, Q-C8): apertures, comparison
  selection, the AAVSO band of every report and the error model. The
  config-only keys of the Qt app sit under Advanced. Changing the aperture
  geometry while a sequence runs will be refused by the server from W6
  (409 run_active, Q-R10).
-->
<script lang="ts">
  import SettingsBlock from '../SettingsBlock.svelte';

  interface Props {
    query?: string;
  }
  let { query = '' }: Props = $props();
</script>

<div class="page">
  <SettingsBlock
    title="Apertures"
    caption="Green-plane pixels."
    keys={['photometry.aperture_fwhm_mult', 'photometry.aperture_min_px', 'photometry.annulus_in_px', 'photometry.annulus_out_px']}
    {query}
    hideEmpty={!!query}
  />
  <SettingsBlock
    title="Comparison stars"
    keys={[
      'photometry.auto_comparisons',
      'photometry.comparison_min_snr',
      'photometry.comparison_max_delta_mag',
      'photometry.comparison_max_separation_arcmin',
    ]}
    {query}
    hideEmpty={!!query}
  />
  <SettingsBlock
    title="Reports and errors"
    keys={[
      'photometry.default_band',
      'photometry.systematic_floor_mag',
      'photometry.track_apertures',
      'photometry.read_noise_e',
      'photometry.min_comparisons',
      'photometry.comparison_validation_min_points',
      'photometry.comparison_validation_max_scatter_mag',
      'photometry.comparison_validation_max_formal_error_mag',
    ]}
    {query}
    hideEmpty={!!query}
  />
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }
</style>
