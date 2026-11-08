<!--
  A canvas sparkline (mini/spark.ts; promoted from src/lab/charts/mini, web/lab/PROPOSAL.md
  section 6, W3), neutral inks unless the caller passes another: conditions are not
  photometric roles. Redraws when `version` changes (new data, a clock tick) or the
  theme changes (`theme`), so Night Red holds on the canvas. role="img" with a text
  alternative: the chart never holds information found nowhere else.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { readInks, type ChartInks } from '../ink';
  import { drawSpark, sizeCanvas, type SparkSpec } from './spark';

  interface Props {
    spec: (ink: ChartInks) => SparkSpec | null;
    width: number;
    height: number;
    /** Any value that changes when the data does. */
    version: unknown;
    /** The theme (or anything that changes with the tokens). */
    theme?: unknown;
    label: string;
  }

  let { spec, width, height, version, theme, label }: Props = $props();
  let canvas: HTMLCanvasElement;
  let ink: ChartInks | null = null;

  $effect(() => {
    void theme;
    untrack(() => {
      ink = readInks(canvas);
      draw();
    });
  });

  $effect(() => {
    void version;
    void width;
    void height;
    untrack(draw);
  });

  function draw(): void {
    if (!canvas || !ink) return;
    const ctx = sizeCanvas(canvas, width, height);
    const s = spec(ink);
    if (ctx && s) drawSpark(ctx, width, height, s, ink);
  }
</script>

<span class="spark" role="img" aria-label={label}>
  <canvas bind:this={canvas} style:width="{width}px" style:height="{height}px" aria-hidden="true"></canvas>
</span>

<style>
  .spark,
  canvas {
    display: block;
    flex: none;
  }
</style>
