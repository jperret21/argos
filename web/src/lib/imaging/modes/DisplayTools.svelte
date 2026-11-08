<!--
  Display tools of the Framing band, in its header row (one 28 px row, no band of its
  own): the transfer function and the display rotation. Display only: the FITS data and
  every measurement keep the raw values; the rotation turns the picture, never the
  coordinates (overlays and readouts stay in frame pixels).
-->
<script lang="ts">
  import Segmented from '../../components/Segmented.svelte';
  import type { RotationMode } from '../../viewer/rotation';
  import type { StretchMode } from '../../viewer/stretch';

  interface Props {
    mode: StretchMode;
    rotation: RotationMode;
    disabled?: boolean;
    onmode: (mode: StretchMode) => void;
    onrotation: (rotation: RotationMode) => void;
  }

  let { mode, rotation, disabled = false, onmode, onrotation }: Props = $props();

  const MODES: { value: StretchMode; label: string }[] = [
    { value: 'linear', label: 'Linear' },
    { value: 'log', label: 'Log' },
    { value: 'asinh', label: 'Asinh' },
  ];
  const ROTATIONS: { value: RotationMode; label: string }[] = [
    { value: 'auto', label: 'Auto' },
    { value: '0', label: '0°' },
    { value: '90', label: '90°' },
    { value: '180', label: '180°' },
    { value: '270', label: '270°' },
  ];
</script>

<span class="tools">
  <Segmented label="Transfer function" options={MODES} value={mode} size="s" {disabled} onchange={(m) => onmode(m)} />
  <span class="k" aria-hidden="true">Rotation</span>
  <Segmented label="Display rotation (clockwise)" options={ROTATIONS} value={rotation} size="s" mono onchange={(r) => onrotation(r)} />
</span>

<style>
  .tools {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .k {
    margin-left: var(--space-2);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
</style>
