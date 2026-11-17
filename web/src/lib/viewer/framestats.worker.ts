/**
 * Frame statistics worker (web/lab/PROPOSAL.md 3.4 and 6, W3): the star
 * peaks of the exposure check (framestats.ts starPeaks, 10-20 ms on a 2 Mpx
 * frame) run here, off the main thread, so live view never stutters. The
 * pixels arrive as a copy (the viewer keeps its frame for the pixel readout
 * and the GPU upload); the answer is a few numbers.
 *
 * Production code (not the lab's synthetic frame worker, which stays in
 * src/lab and never reaches the bundle).
 */

import { starPeaks, type StarPeaks } from './framestats';

export interface PeaksRequest {
  type: 'peaks';
  seq: number;
  width: number;
  height: number;
  bayer: string | null;
  pixels: Uint16Array;
}

export interface PeaksReply {
  type: 'peaks';
  seq: number;
  result: StarPeaks | null;
  ms: number;
  error?: string;
}

self.onmessage = (e: MessageEvent<PeaksRequest>) => {
  const req = e.data;
  if (req?.type !== 'peaks') return;
  const t0 = performance.now();
  let reply: PeaksReply;
  try {
    const result = starPeaks(req.pixels, req.width, req.height, { bayer: req.bayer });
    reply = { type: 'peaks', seq: req.seq, result, ms: performance.now() - t0 };
  } catch (err) {
    reply = { type: 'peaks', seq: req.seq, result: null, ms: performance.now() - t0, error: String(err) };
  }
  (self as unknown as Worker).postMessage(reply);
};
