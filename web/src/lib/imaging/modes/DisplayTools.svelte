<!--
  Display tools of the Framing band, in its header row (one 28 px row, no band of its
  own): the transfer function. The display rotation moved into View options with the
  other display choices (wave 4, web/spec/04-viewer-and-image-tools.md 2.3, where the spec
  places it). Display only: the FITS data and every measurement keep the raw values.
-->
<script lang="ts">
  import Segmented from '../../components/Segmented.svelte';
  import type { StretchMode } from '../../viewer/stretch';

  interface Props {
    mode: StretchMode;
    disabled?: boolean;
    onmode: (mode: StretchMode) => void;
  }

  let { mode, disabled = false, onmode }: Props = $props();

  const MODES: { value: StretchMode; label: string }[] = [
    { value: 'linear', label: 'Linear' },
    { value: 'log', label: 'Log' },
    { value: 'asinh', label: 'Asinh' },
  ];
</script>

<span class="tools">
  <Segmented label="Transfer function" options={MODES} value={mode} size="s" {disabled} onchange={(m) => onmode(m)} />
</span>

<style>
  .tools {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
</style>
