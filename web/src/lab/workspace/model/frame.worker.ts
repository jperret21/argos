/**
 * Synthetic 16-bit frames for the workspace lab, off the main thread.
 *
 * A sky with a mild gradient and Gaussian read + photon-like noise, the
 * field's stars as Gaussian PSFs whose width follows the night model's HFD
 * (for a Gaussian, HFD = FWHM = 2.3548 sigma), clipped at 65 535 like a
 * 16-bit sensor, and a few hot pixels. The pixel buffer is transferred to
 * the main thread (no copy). The worker also MEASURES what the HUD shows from
 * these pixels: the sky median, the frame's peak, each named star's peak and
 * the clipped-pixel count, so the readouts are true for the picture on screen.
 */

interface InitMsg {
  type: 'init';
  width: number;
  height: number;
  /** [x, y, v, id] per star. */
  stars: Float32Array;
  zeroPoint: number;
}

interface RenderMsg {
  type: 'render';
  seq: number;
  hfd: number;
  sky: number;
  noise: number;
  /** Magnitude overrides by star id (the variable target). */
  mags: Record<number, number>;
  /** 1 = clear; < 1 dims every star (a cloud). */
  transparency: number;
  seed: number;
  /** Ids whose peak ADU is measured. */
  measure: number[];
}

let W = 0;
let H = 0;
let stars: Float32Array<ArrayBufferLike> = new Float32Array(0);
let zp = 23;
let acc = new Float32Array(0);

function xorshift(seed: number): () => number {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13;
    s >>>= 0;
    s ^= s >>> 17;
    s ^= s << 5;
    s >>>= 0;
    return s / 4294967296;
  };
}

function render(m: RenderMsg) {
  const t0 = performance.now();
  const n = W * H;
  if (acc.length !== n) acc = new Float32Array(n);
  acc.fill(0);
  const sigma = Math.max(0.6, m.hfd / 2.3548);
  const r = Math.ceil(3.6 * sigma);
  const g = new Float32Array(2 * r + 1);
  // Exact pixel-integrated Gaussian would be nicer; sampling at centres is
  // fine above sigma 0.6 px and keeps the loop cheap.
  for (let k = 0; k < stars.length; k += 4) {
    const x = stars[k];
    const y = stars[k + 1];
    const id = stars[k + 3];
    const v = m.mags[id] ?? stars[k + 2];
    const flux = Math.pow(10, -0.4 * (v - zp)) * m.transparency;
    const peak = flux / (2 * Math.PI * sigma * sigma);
    if (peak < 0.5) continue;
    const ix = Math.round(x);
    const iy = Math.round(y);
    const fx = x - ix;
    const fy = y - iy;
    for (let j = -r; j <= r; j++) g[j + r] = Math.exp(-((j - fx) ** 2) / (2 * sigma * sigma));
    for (let j = -r; j <= r; j++) {
      const yy = iy + j;
      if (yy < 0 || yy >= H) continue;
      const gy = Math.exp(-((j - fy) ** 2) / (2 * sigma * sigma)) * peak;
      if (gy < 0.05) continue;
      const row = yy * W;
      for (let i = -r; i <= r; i++) {
        const xx = ix + i;
        if (xx < 0 || xx >= W) continue;
        acc[row + xx] += gy * g[i + r];
      }
    }
  }

  const out = new Uint16Array(n);
  const rand = xorshift(m.seed * 2654435761);
  const hist = new Uint32Array(65536);
  let min = 65535;
  let max = 0;
  let sum = 0;
  let clipped = 0;
  for (let y = 0; y < H; y++) {
    // Light-pollution gradient: +40 ADU from the top row to the bottom row.
    const grad = (40 * y) / H;
    const row = y * W;
    for (let x = 0; x < W; x++) {
      const signal = acc[row + x];
      // Sum of 4 uniforms ~ normal (fast); photon noise grows with the signal.
      const u = rand() + rand() + rand() + rand() - 2;
      const sd = Math.sqrt(m.noise * m.noise + signal * 0.35);
      let v = m.sky + grad + signal + u * 1.732 * sd;
      if (v < 0) v = 0;
      if (v >= 65535) {
        v = 65535;
        clipped++;
      }
      const q = v | 0;
      out[row + x] = q;
      hist[q]++;
      if (q < min) min = q;
      if (q > max) max = q;
      sum += q;
    }
  }
  // A few hot pixels, fixed positions (a real sensor's are).
  const hot = xorshift(4242);
  for (let k = 0; k < 24; k++) {
    const p = Math.floor(hot() * n);
    out[p] = 65535;
    clipped++;
  }

  // Median and MAD from the exact histogram.
  const half = n / 2;
  let cum = 0;
  let med = 0;
  for (let i = 0; i < 65536; i++) {
    cum += hist[i];
    if (cum >= half) {
      med = i;
      break;
    }
  }
  const dev = new Uint32Array(65536);
  for (let i = 0; i < 65536; i++) if (hist[i]) dev[Math.abs(i - med)] += hist[i];
  cum = 0;
  let mad = 0;
  for (let i = 0; i < 65536; i++) {
    cum += dev[i];
    if (cum >= half) {
      mad = i;
      break;
    }
  }

  const peaks: Record<number, number> = {};
  for (const id of m.measure) {
    for (let k = 0; k < stars.length; k += 4) {
      if (stars[k + 3] !== id) continue;
      const cx = Math.round(stars[k]);
      const cy = Math.round(stars[k + 1]);
      const rr = Math.max(3, Math.ceil(sigma));
      let p = 0;
      for (let y = Math.max(0, cy - rr); y <= Math.min(H - 1, cy + rr); y++) {
        for (let x = Math.max(0, cx - rr); x <= Math.min(W - 1, cx + rr); x++) {
          const q = out[y * W + x];
          if (q > p) p = q;
        }
      }
      peaks[id] = p;
    }
  }

  const ms = performance.now() - t0;
  (self as unknown as Worker).postMessage(
    {
      type: 'frame',
      seq: m.seq,
      buffer: out.buffer,
      stats: { min, max, median: med, mad, mean: sum / n },
      peaks,
      clipped,
      ms,
    },
    [out.buffer],
  );
}

self.onmessage = (e: MessageEvent<InitMsg | RenderMsg>) => {
  const m = e.data;
  if (m.type === 'init') {
    W = m.width;
    H = m.height;
    stars = m.stars;
    zp = m.zeroPoint;
  } else if (m.type === 'render') {
    render(m);
  }
};
