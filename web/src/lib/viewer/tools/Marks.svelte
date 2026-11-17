<!--
  Marks on the image for stars a list hovers (the W3 leftover "hovering an exposure-check
  row marks its star on the image"): screen-space, placed from FitsViewer's geometry, so
  they keep their size at any zoom and follow the display rotation. The same mark as every
  list hover (FieldOverlay): four corner brackets in the foreground ink over a black halo
  (a hover is not a selection: no brass); nothing takes the pointer.
-->
<script lang="ts">
  import { bracketPath } from '../overlay/layers';
  import { frameToScreen, type ViewerGeometry } from './geometry';

  interface Props {
    geometry: ViewerGeometry | null;
    /** Frame px (numpy convention) of the stars to ring. */
    points: readonly { x: number; y: number }[] | null;
    stage: { width: number; height: number };
    /** Half-size of the brackets, CSS px. */
    r?: number;
  }

  let { geometry, points, stage, r = 14 }: Props = $props();
  const rings = $derived(geometry && points ? points.map((p) => frameToScreen(geometry, p.x, p.y)) : []);
</script>

{#if rings.length}
  <svg class="marks" width={stage.width} height={stage.height} aria-hidden="true" data-marks={rings.length}>
    {#each rings as c, i (i)}
      <path class="halo" d={bracketPath(c.x, c.y, r)} />
      <path class="ring" d={bracketPath(c.x, c.y, r)} />
    {/each}
  </svg>
{/if}

<style>
  .marks {
    position: absolute;
    inset: 0;
    z-index: 2;
    overflow: visible;
    pointer-events: none;
  }
  path {
    fill: none;
    stroke-linecap: square;
  }
  .halo {
    stroke: var(--viewer-bg);
    stroke-width: 3.5;
  }
  .ring {
    stroke: var(--fg);
    stroke-width: 1.5;
  }
</style>
