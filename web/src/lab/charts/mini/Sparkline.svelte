<!--
  A canvas sparkline (mini/spark.ts) that redraws when `version` changes
  (new data, new clock tick) or the theme changes. role="img" with a text
  alternative: the chart never holds information found nowhere else.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { env } from '../env.svelte';
  import { readInks, type ChartInks } from '../core/palette';
  import { drawSpark, sizeCanvas, type SparkSpec } from './spark';

  interface Props {
    spec: (ink: ChartInks) => SparkSpec | null;
    width: number;
    height: number;
    version: unknown;
    label: string;
  }

  let { spec, width, height, version, label }: Props = $props();
  let canvas: HTMLCanvasElement;
  let ink: ChartInks | null = null;

  $effect(() => {
    void env.theme;
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
