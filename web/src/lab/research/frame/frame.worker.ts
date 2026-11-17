/**
 * Lab worker: synthesises a 1920 x 1080 16-bit star frame (a Seestar frame
 * after the display rotation, 2.07 Mpx) and computes its statistics, off the
 * main thread. The pixel buffer is *transferred* both ways (ping-pong): the
 * main thread uploads it to WebGL, then hands it back for the next frame, so
 * a 4 MB frame per second costs no copy and no garbage.
 *
 * In the app the frames come from the server over the WebSocket; the same
 * worker shape would decode / compute statistics there.
 */

import { gauss, prng } from '../synth';
import { frameStats } from './stats';

interface Star {
  x: number;
  y: number;
  flux: number;
}

export interface FrameRequest {
  type: 'frame';
  width: number;
  height: number;
  /** A buffer handed back for reuse (transferred), or null. */
  recycle: ArrayBuffer | null;
}

export interface FrameReply {
  type: 'frame';
  seq: number;
  width: number;
  height: number;
  buffer: ArrayBuffer;
  stats: ReturnType<typeof frameStats>;
  timings: { synth: number; stats: number };
  sky: number;
  seeing: number;
}

const NOISE_N = 1 << 20;
const rand = prng(20261101);
const noise = new Float32Array(NOISE_N);
for (let i = 0; i < NOISE_N; i++) noise[i] = gauss(rand);

let stars: Star[] = [];
let hot: Int32Array = new Int32Array(0);
let acc: Float32Array | null = null;
let seq = 0;
let lastSize = '';

function setup(w: number, h: number): void {
  const r = prng(42);
  stars = [];
  for (let i = 0; i < 1700; i++) {
    // Steep luminosity function: many faint stars, a few bright ones.
    const u = r();
    stars.push({ x: r() * w, y: r() * h, flux: 900 * Math.pow(1 - u, -1.35) });
  }
  hot = new Int32Array(260);
  for (let i = 0; i < hot.length; i++) hot[i] = Math.floor(r() * w * h);
  acc = new Float32Array(w * h);
}

function synth(req: FrameRequest): FrameReply {
  const { width: w, height: h } = req;
  const size = `${w}x${h}`;
  if (size !== lastSize) {
    setup(w, h);
    lastSize = size;
  }
  const t0 = performance.now();
  seq++;
  const a = acc!;
  const sky = 1795 + 9 * Math.sin(seq / 40);
  const sigmaSky = 26;
  const off = Math.floor(rand() * NOISE_N);
  for (let i = 0; i < a.length; i++) a[i] = sky + sigmaSky * noise[(off + i * 7) & (NOISE_N - 1)];

  // Seeing and a slow tracking drift (periodic error): stars move, truthfully.
  const seeing = 1.05 + 0.12 * Math.sin(seq / 9) + 0.04 * gauss(rand);
  const dx = 2.4 * Math.sin(seq / 23);
  const dy = 0.06 * seq;
  const two = 2 * seeing * seeing;
  const rad = Math.ceil(seeing * 3.6);
  for (const s of stars) {
    const sx = s.x + dx;
    const sy = (((s.y + dy) % h) + h) % h;
    const cx = Math.round(sx);
    const cy = Math.round(sy);
    if (cx < rad || cy < rad || cx >= w - rad || cy >= h - rad) continue;
    const peak = s.flux / (Math.PI * two);
    for (let yy = -rad; yy <= rad; yy++) {
      const fy = cy + yy - sy;
      const row = (cy + yy) * w;
      for (let xx = -rad; xx <= rad; xx++) {
        const fx = cx + xx - sx;
        a[row + cx + xx] += peak * Math.exp(-(fx * fx + fy * fy) / two);
      }
    }
  }
  for (let i = 0; i < hot.length; i++) a[hot[i]] += 3000 + (i % 7) * 2600;

  const buffer = req.recycle && req.recycle.byteLength === w * h * 2 ? req.recycle : new ArrayBuffer(w * h * 2);
  const px = new Uint16Array(buffer);
  for (let i = 0; i < a.length; i++) {
    const v = a[i];
    px[i] = v <= 0 ? 0 : v >= 65535 ? 65535 : v + 0.5;
  }
  const t1 = performance.now();
  const stats = frameStats(px, w, h, 256);
  const t2 = performance.now();
  return { type: 'frame', seq, width: w, height: h, buffer, stats, timings: { synth: t1 - t0, stats: t2 - t1 }, sky, seeing };
}

self.onmessage = (e: MessageEvent<FrameRequest>) => {
  if (e.data?.type !== 'frame') return;
  const reply = synth(e.data);
  (self as unknown as Worker).postMessage(reply, [reply.buffer, reply.stats.hist.buffer]);
};
