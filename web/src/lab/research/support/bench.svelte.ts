/**
 * Micro-benchmarks run in the engine that opens the page. Medians of a few
 * runs; numbers are for comparison between approaches in one engine, not
 * absolute promises (headless Chrome draws WebGL on the CPU, SwiftShader).
 */

import uPlot from 'uplot';
import { markers } from '../curve/plugins';
import { LabRenderer } from '../frame/gl';
import { frameStats } from '../frame/stats';
import { prng } from '../synth';

export interface BenchResult {
  id: string;
  label: string;
  ms: number;
  detail?: string;
}

const median = (a: number[]) => {
  const s = [...a].sort((x, y) => x - y);
  return s[Math.floor(s.length / 2)];
};

function hiddenHost(w: number, h: number): HTMLDivElement {
  const el = document.createElement('div');
  el.style.cssText = `position:absolute;left:-20000px;top:0;width:${w}px;height:${h}px`;
  document.body.append(el);
  return el;
}

/** setData -> draw hook, with the light-curve markers plugin (circles + error bars). */
async function uplotDraw(xs: ArrayLike<number>, ys: ArrayLike<number>, errs: ArrayLike<number>, runs = 5): Promise<number> {
  const host = hiddenHost(1100, 320);
  let resolveDraw: (() => void) | null = null;
  const u = new uPlot(
    {
      width: 1100,
      height: 320,
      legend: { show: false },
      scales: { x: { time: false }, y: { dir: -1 } },
      series: [{}, { stroke: '#b48e2c', paths: () => null, points: { show: false } }],
      plugins: [
        markers({
          shape: 'circle',
          color: () => '#b48e2c',
          errorAlpha: () => 0.55,
          errors: () => errs,
          showErrors: () => true,
          latest: () => '#e8e5df',
        }),
      ],
      hooks: { draw: [() => resolveDraw?.()] },
    },
    [[], []],
    host,
  );
  const times: number[] = [];
  for (let r = 0; r < runs; r++) {
    const done = new Promise<void>((res) => (resolveDraw = res));
    const t0 = performance.now();
    u.setData([xs as number[], ys as number[]], true);
    await done;
    times.push(performance.now() - t0);
  }
  u.destroy();
  host.remove();
  return median(times);
}

function series(n: number): { xs: Float64Array; ys: Float64Array; errs: Float64Array } {
  const r = prng(n);
  const xs = new Float64Array(n);
  const ys = new Float64Array(n);
  const errs = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    xs[i] = i;
    ys[i] = 9.8 + 0.4 * Math.sin(i / 300) + 0.01 * (r() - 0.5);
    errs[i] = 0.005 + 0.01 * r();
  }
  return { xs, ys, errs };
}

export async function runBench(onProgress?: (r: BenchResult[]) => void): Promise<BenchResult[]> {
  const out: BenchResult[] = [];
  const push = (r: BenchResult) => {
    out.push(r);
    onProgress?.([...out]);
  };
  const pause = () => new Promise((r) => setTimeout(r, 30));

  // 1. uPlot draw time vs point count (typed arrays).
  for (const n of [1000, 10000, 100000]) {
    const s = series(n);
    push({ id: `uplot-${n}`, label: `uPlot setData → drawn, ${n.toLocaleString('en-GB')} pts + error bars`, ms: await uplotDraw(s.xs, s.ys, s.errs) });
    await pause();
  }

  // 2. Same draw, data held in Svelte $state (deep proxy) vs $state.raw.
  {
    const n = 10000;
    const s = series(n);
    const proxied = $state({ xs: Array.from(s.xs), ys: Array.from(s.ys), errs: Array.from(s.errs) });
    const raw = $state.raw({ xs: Array.from(s.xs), ys: Array.from(s.ys), errs: Array.from(s.errs) });
    const tp = await uplotDraw(proxied.xs, proxied.ys, proxied.errs);
    const tr = await uplotDraw(raw.xs, raw.ys, raw.errs);
    push({ id: 'proxy-uplot', label: 'uPlot draw, 10 000 pts from $state (deep proxy)', ms: tp });
    push({ id: 'raw-uplot', label: 'uPlot draw, 10 000 pts from $state.raw', ms: tr, detail: `${(tp / tr).toFixed(1)}× faster` });
    await pause();
    // Plain reads: sum 100 000 numbers through the proxy vs a raw array.
    const big = Array.from({ length: 100000 }, (_, i) => i * 0.5);
    const p = $state({ v: big.slice() });
    const t0 = performance.now();
    let a = 0;
    for (let k = 0; k < 5; k++) for (let i = 0; i < p.v.length; i++) a += p.v[i];
    const t1 = performance.now();
    let b = 0;
    for (let k = 0; k < 5; k++) for (let i = 0; i < big.length; i++) b += big[i];
    const t2 = performance.now();
    push({ id: 'proxy-read', label: 'Read 100 000 numbers × 5 through $state proxy', ms: t1 - t0, detail: a === b ? 'same sum' : 'sum differs' });
    push({ id: 'raw-read', label: 'Read 100 000 numbers × 5, raw array', ms: t2 - t1 });
    await pause();
  }

  // 3. Frame statistics of a 1920 x 1080 u16 frame (what the worker does), on this thread.
  {
    const w = 1920;
    const h = 1080;
    const px = new Uint16Array(w * h);
    const r = prng(1);
    for (let i = 0; i < px.length; i++) px[i] = 1790 + ((r() * 60) | 0);
    for (let k = 0; k < 900; k++) {
      const c = ((r() * (h - 40) + 20) | 0) * w + ((r() * (w - 40) + 20) | 0);
      px[c] = 20000;
      px[c - 1] = px[c + 1] = px[c - w] = px[c + w] = 9000;
    }
    const t0 = performance.now();
    const s = frameStats(px, w, h);
    push({ id: 'stats-2mpx', label: 'frameStats 2.07 Mpx (median, MAD, histogram, stars, HFD)', ms: performance.now() - t0, detail: `${s.stars} stars` });
    await pause();

    // 4. WebGL2 upload + draw + forced sync of the same frame.
    try {
      const canvas = document.createElement('canvas');
      canvas.width = 1100;
      canvas.height = 620;
      const gl = new LabRenderer(canvas);
      const times: number[] = [];
      for (let k = 0; k < 5; k++) {
        const t0g = performance.now();
        gl.upload(px, w, h);
        gl.draw({ view: { scale: 0.57, cx: w / 2, cy: h / 2 }, black: 1780, white: 65535, mid: 0.002, tint: [1, 1, 1] });
        gl.sync();
        times.push(performance.now() - t0g);
      }
      gl.dispose();
      push({ id: 'gl-upload', label: 'WebGL2 R16UI upload + draw, 2.07 Mpx, synced', ms: median(times) });
    } catch (e) {
      push({ id: 'gl-upload', label: 'WebGL2 upload', ms: NaN, detail: String(e) });
    }
    await pause();
  }

  // 5. Canvas 2D sparkline, 120 points, 1000 draws.
  {
    const c = document.createElement('canvas');
    c.width = 240;
    c.height = 56;
    const ctx = c.getContext('2d')!;
    const vals = Array.from({ length: 120 }, (_, i) => Math.sin(i / 9));
    const t0 = performance.now();
    for (let k = 0; k < 1000; k++) {
      ctx.clearRect(0, 0, 240, 56);
      ctx.beginPath();
      for (let i = 0; i < 120; i++) ctx.lineTo(i * 2, 28 - vals[i] * 24);
      ctx.stroke();
    }
    push({ id: 'sparkline', label: 'Canvas 2D sparkline (120 pts), per draw', ms: (performance.now() - t0) / 1000 });
  }

  // 5b. Path2D with 10 000 triangles (check-star markers), with and without
  // closePath(): quadratic in Chromium 156 (4.4 s at 50 000), linear in WebKit.
  {
    const c = document.createElement('canvas');
    c.width = 1000;
    c.height = 400;
    const ctx = c.getContext('2d')!;
    const tri = (close: boolean) => {
      const t0 = performance.now();
      const p = new Path2D();
      for (let i = 0; i < 10000; i++) {
        const x = (i * 7) % 1000;
        const y = (i * 13) % 400;
        p.moveTo(x, y - 4);
        p.lineTo(x + 3.5, y + 2);
        p.lineTo(x - 3.5, y + 2);
        if (close) p.closePath();
      }
      ctx.fill(p);
      ctx.getImageData(0, 0, 1, 1);
      return performance.now() - t0;
    };
    const closed = tri(true);
    const open = tri(false);
    push({ id: 'path2d-close', label: 'Path2D, 10 000 triangles with closePath(), filled', ms: closed });
    push({ id: 'path2d-open', label: 'Path2D, 10 000 triangles without closePath()', ms: open, detail: `${(closed / Math.max(open, 0.001)).toFixed(0)}× faster` });
    await pause();
  }

  // 6. Number formatting, 10 000 values: cached Intl vs toFixed.
  {
    const nf = new Intl.NumberFormat('en-GB', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
    const t0 = performance.now();
    let len = 0;
    for (let i = 0; i < 10000; i++) len += nf.format(9 + i / 7777).length;
    const t1 = performance.now();
    for (let i = 0; i < 10000; i++) len += (9 + i / 7777).toFixed(3).length;
    const t2 = performance.now();
    push({ id: 'intl', label: 'Intl.NumberFormat (cached) × 10 000', ms: t1 - t0, detail: `toFixed: ${(t2 - t1).toFixed(2)} ms` });
  }
  return out;
}
