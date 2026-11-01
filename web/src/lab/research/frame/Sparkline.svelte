<!--
  Sparkline / mini histogram on a Canvas 2D: no library, ~0.05 ms per draw
  for 120 points. Colours are tokens resolved at draw time (tokens.ts) and
  redrawn on a theme change, so Night Red holds. The last value is a dot,
  never an animated pulse: data does not move to attract the eye.

  Accessible name: `label` + the latest value (the visible text next to it
  carries the number; the canvas is role="img").
-->
<script lang="ts">
  import { env } from '../env.svelte';
  import { chartPalette } from '../tokens';

  interface Props {
    values: ArrayLike<number>;
    label: string;
    kind?: 'line' | 'bars';
    height?: number;
    /** Token for the mark colour. */
    tone?: '--fg-muted' | '--chart-1' | '--chart-2' | '--chart-3';
    /** Vertical markers at fractions of the width (histogram levels). */
    marks?: number[];
    /** Fixed y range; auto otherwise. */
    range?: [number, number];
  }

  let { values, label, kind = 'line', height = 28, tone = '--fg-muted', marks = [], range }: Props = $props();

  let canvas: HTMLCanvasElement;
  let width = $state(0);

  function draw(): void {
    if (!canvas || width <= 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const pal = chartPalette(canvas);
    const toneColor = tone === '--fg-muted' ? pal.fgMuted : tone === '--chart-1' ? pal.target : tone === '--chart-2' ? pal.comparison : pal.check;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const n = values.length;
    if (!n) return;
    let lo = Infinity;
    let hi = -Infinity;
    for (let i = 0; i < n; i++) {
      const v = values[i];
      if (!Number.isFinite(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    if (range) [lo, hi] = range;
    if (!(hi > lo)) {
      hi = lo + 1;
      lo -= 1;
    }
    const pad = 2;
    const y = (v: number) => pad + (height - 2 * pad) * (1 - (v - lo) / (hi - lo));
    if (kind === 'bars') {
      const bw = width / n;
      ctx.fillStyle = toneColor;
      // Log counts: the sky peak and the star tail on one strip.
      const lmax = Math.log10(Math.max(1, hi) + 1);
      for (let i = 0; i < n; i++) {
        const c = values[i];
        if (!(c > 0)) continue;
        const hgt = ((height - pad) * Math.log10(c + 1)) / lmax;
        ctx.fillRect(i * bw, height - hgt, Math.max(1, bw - 0.25), hgt);
      }
      ctx.strokeStyle = pal.accent;
      ctx.lineWidth = 1.5;
      for (const m of marks) {
        const x = Math.round(Math.min(1, Math.max(0, m)) * width) + 0.5;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      return;
    }
    const dx = width / Math.max(1, n - 1);
    ctx.strokeStyle = toneColor;
    ctx.lineWidth = 1.25;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < n; i++) {
      const v = values[i];
      if (!Number.isFinite(v)) {
        started = false;
        continue;
      }
      const px = i * dx;
      if (started) ctx.lineTo(px, y(v));
      else ctx.moveTo(px, y(v));
      started = true;
    }
    ctx.stroke();
    const last = values[n - 1];
    if (Number.isFinite(last)) {
      ctx.fillStyle = pal.fg;
      ctx.beginPath();
      ctx.arc((n - 1) * dx - 1.5, y(last), 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  $effect(() => {
    // Redraw on data, size or theme.
    void values;
    void width;
    void env.theme;
    void marks;
    draw();
  });

  $effect(() => {
    const ro = new ResizeObserver((e) => {
      width = Math.floor(e[e.length - 1].contentRect.width);
    });
    ro.observe(canvas);
    return () => ro.disconnect();
  });
</script>

<span class="wrap" role="img" aria-label={label}>
  <canvas bind:this={canvas} class="spark" style:height="{height}px" aria-hidden="true"></canvas>
</span>

<style>
  .wrap {
    display: block;
    min-width: 0;
  }
  .spark {
    display: block;
    width: 100%;
    min-width: 0;
  }
</style>
