/** Feature probe inside a worker: OffscreenCanvas contexts available off the main thread. */

const out: Record<string, boolean | string> = {};
try {
  out.offscreen = typeof OffscreenCanvas !== 'undefined';
  if (out.offscreen) {
    out.offscreen2d = !!new OffscreenCanvas(4, 4).getContext('2d');
    const gl = new OffscreenCanvas(4, 4).getContext('webgl2');
    out.offscreenWebgl2 = !!gl;
  }
} catch (e) {
  out.error = String(e);
}
(self as unknown as Worker).postMessage(out);
