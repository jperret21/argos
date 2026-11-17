<!--
  Sparkline or mini histogram on a Canvas 2D (no library). Colours are tokens
  resolved at draw time and redrawn on a theme change, so Night Red holds.
  The last value is a dot (static); a threshold is a dashed line; points over
  it are ticked so a rule that holds is visible even at 120 x 24 px.

  kind 'hist': log-count bars of a binned histogram with level marks (the
  HUD's mini histogram), marks in brass: they ARE the display levels (BRAND 8
  counts them in the brass budget).
-->
<script lang="ts">
  import { resolveColor } from '../../research/tokens';
  import { env } from '../model/env.svelte';

  interface Props {
    values: ArrayLike<number>;
    label: string;
    kind?: 'line' | 'hist';
    height?: number;
    /** Horizontal threshold (line kind). */
    threshold?: number | null;
    /** Level marks as fractions of the width (hist kind). */
    marks?: readonly number[];
    /** Fixed y range. */
    range?: [number, number];
    /** Thicker strokes for the Watch view. */
    bold?: boolean;
  }

  let { values, label, kind = 'line', height = 24, threshold = null, marks = [], range, bold = false }: Props = $props();

  let canvas: HTMLCanvasElement;
  let width = $state(0);

  function token(name: string): string {
    const css = getComputedStyle(canvas).getPropertyValue(name).trim();
    const [r, g, b, a] = resolveColor(css || '#000');
    return `rgba(${r}, ${g}, ${b}, ${a / 255})`;
  }

  function draw(): void {
    if (!canvas || width <= 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const n = values.length;
    if (!n) return;
    const muted = token('--fg-muted');
    const fg = token('--fg');
    if (kind === 'hist') {
      let max = 0;
      for (let i = 0; i < n; i++) max = Math.max(max, values[i]);
      const lmax = Math.log10(max + 1) || 1;
      const bw = width / n;
      ctx.fillStyle = muted;
      ctx.globalAlpha = 0.85;
      for (let i = 0; i < n; i++) {
        const c = values[i];
        if (!(c > 0)) continue;
        const h = ((height - 1) * Math.log10(c + 1)) / lmax;
        ctx.fillRect(i * bw, height - h, Math.max(1, bw - 0.5), h);
      }
      ctx.globalAlpha = 1;
      ctx.strokeStyle = token('--accent');
      ctx.lineWidth = 1.5;
      for (const m of marks) {
        const x = Math.round(Math.min(1, Math.max(0, m)) * (width - 2)) + 1;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      return;
    }
    let lo = Infinity;
    let hi = -Infinity;
    for (let i = 0; i < n; i++) {
      const v = values[i];
      if (!Number.isFinite(v)) continue;
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
    if (threshold !== null) {
      lo = Math.min(lo, threshold);
      hi = Math.max(hi, threshold);
    }
    if (range) [lo, hi] = range;
    if (!(hi > lo)) {
      hi = lo + 1;
      lo -= 1;
    }
    const pad = bold ? 4 : 2.5;
    const y = (v: number) => pad + (height - 2 * pad) * (1 - (v - lo) / (hi - lo));
    const dx = (width - pad * 2) / Math.max(1, n - 1);
    if (threshold !== null) {
      ctx.strokeStyle = token('--warning');
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 2]);
      ctx.beginPath();
      ctx.moveTo(0, Math.round(y(threshold)) + 0.5);
      ctx.lineTo(width, Math.round(y(threshold)) + 0.5);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    ctx.strokeStyle = muted;
    ctx.lineWidth = bold ? 2.5 : 1.25;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const v = values[i];
      if (!Number.isFinite(v)) continue;
      ctx.lineTo(pad + i * dx, y(v));
    }
    ctx.stroke();
    const last = values[n - 1];
    if (Number.isFinite(last)) {
      ctx.fillStyle = fg;
      ctx.beginPath();
      ctx.arc(pad + (n - 1) * dx, y(last), bold ? 4.5 : 2.25, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  $effect(() => {
    void values;
    void width;
    void height;
    void env.theme;
    void marks;
    void threshold;
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
  <canvas bind:this={canvas} style:height="{height}px" aria-hidden="true"></canvas>
</span>

<style>
  .wrap {
    display: block;
    min-width: 0;
  }
  canvas {
    display: block;
    width: 100%;
    min-width: 0;
  }
</style>
