/**
 * Minimal WebGL2 frame renderer for the lab: R16UI texture (exact 16-bit
 * values, no float conversion on the CPU), stretch in the shader, a 256-entry
 * LUT texture for false colour, max-of-taps minification so faint stars do
 * not vanish at "fit". The app's renderer (lib/viewer/renderer.ts) does the
 * stretch part already; the LUT is what this file adds and measures.
 *
 * Night Red: only the neutral LUT is allowed (spec D30), multiplied by the
 * --viewer-tint token (#d80000), so the canvas emits red light only.
 */

export type Palette = 'neutral' | 'negative' | 'fire' | 'ice';

export interface View {
  /** Screen px (device) per image px. */
  scale: number;
  /** Image point at the centre of the viewport. */
  cx: number;
  cy: number;
}

const VS = `#version 300 es
in vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }`;

const FS = `#version 300 es
precision highp float;
precision highp usampler2D;
uniform usampler2D u_img;
uniform sampler2D u_lut;
uniform vec2 u_imgSize;
uniform vec2 u_viewSize;
uniform vec2 u_center;
uniform float u_scale;
uniform int u_taps;
uniform float u_black;
uniform float u_white;
uniform float u_mid;
uniform vec3 u_tint;
out vec4 o;

float mtf(float m, float x) { return ((m - 1.0) * x) / ((2.0 * m - 1.0) * x - m); }

void main() {
  vec2 frag = vec2(gl_FragCoord.x, u_viewSize.y - gl_FragCoord.y);
  vec2 p = u_center + (frag - 0.5 * u_viewSize) / u_scale;
  if (p.x < 0.0 || p.y < 0.0 || p.x >= u_imgSize.x || p.y >= u_imgSize.y) { o = vec4(0.0, 0.0, 0.0, 1.0); return; }
  // Max over the footprint of this screen pixel: a star never falls between taps.
  uint raw = 0u;
  float step = 1.0 / u_scale / float(u_taps);
  for (int j = 0; j < 4; j++) {
    if (j >= u_taps) break;
    for (int i = 0; i < 4; i++) {
      if (i >= u_taps) break;
      vec2 q = clamp(p + vec2(float(i), float(j)) * step, vec2(0.0), u_imgSize - 1.0);
      raw = max(raw, texelFetch(u_img, ivec2(q), 0).r);
    }
  }
  float x = clamp((float(raw) - u_black) / max(1.0, u_white - u_black), 0.0, 1.0);
  float v = clamp(mtf(u_mid, x), 0.0, 1.0);
  vec3 c = texture(u_lut, vec2(v * (255.0 / 256.0) + 0.5 / 256.0, 0.5)).rgb;
  o = vec4(c * u_tint, 1.0);
}`;

// -- Perceptual LUTs (OKLCH, no library) -----------------------------------------

/** OKLab -> gamma-encoded sRGB, 0..1 per channel, unclipped (Ottosson 2020). */
export function oklabToSrgb(L: number, a: number, b: number): [number, number, number] {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const lin = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  const enc = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
  return [enc(lin[0]), enc(lin[1]), enc(lin[2])];
}

/** OKLCH -> sRGB, chroma reduced (bisection) until the colour is inside the sRGB gamut, so lightness is never traded. */
export function oklchToSrgbInGamut(L: number, C: number, hDeg: number): [number, number, number] {
  const h = (hDeg * Math.PI) / 180;
  const inside = (c: number) => oklabToSrgb(L, c * Math.cos(h), c * Math.sin(h)).every((v) => v >= -1e-4 && v <= 1 + 1e-4);
  let lo = 0;
  let hi = C;
  if (!inside(hi)) {
    for (let k = 0; k < 24; k++) {
      const mid = (lo + hi) / 2;
      if (inside(mid)) lo = mid;
      else hi = mid;
    }
    hi = lo;
  }
  const rgb = oklabToSrgb(L, hi * Math.cos(h), hi * Math.sin(h));
  return [Math.min(1, Math.max(0, rgb[0])), Math.min(1, Math.max(0, rgb[1])), Math.min(1, Math.max(0, rgb[2]))];
}

/**
 * A false-colour ramp with OKLab lightness exactly proportional to the
 * stretched value: brighter pixel = lighter colour, everywhere, so the
 * palette adds hue without lying about intensity (a rainbow LUT does).
 */
function perceptualRamp(v: number, h0: number, h1: number, cMax: number): [number, number, number] {
  const L = v;
  const C = cMax * Math.pow(Math.sin(Math.PI * v), 0.75);
  return oklchToSrgbInGamut(L, C, h0 + (h1 - h0) * v);
}

/** 256 x RGBA8 lookup table for a palette. */
export function buildLut(palette: Palette): Uint8Array {
  const out = new Uint8Array(256 * 4);
  for (let i = 0; i < 256; i++) {
    const v = i / 255;
    let c: [number, number, number];
    switch (palette) {
      case 'negative':
        c = [1 - v, 1 - v, 1 - v];
        break;
      case 'fire': // red -> orange -> yellow -> white
        c = perceptualRamp(v, 20, 100, 0.2);
        break;
      case 'ice': // indigo -> blue -> cyan -> white
        c = perceptualRamp(v, 275, 200, 0.16);
        break;
      default:
        c = [v, v, v];
    }
    out[i * 4] = Math.round(c[0] * 255);
    out[i * 4 + 1] = Math.round(c[1] * 255);
    out[i * 4 + 2] = Math.round(c[2] * 255);
    out[i * 4 + 3] = 255;
  }
  return out;
}

export interface DrawParams {
  view: View;
  black: number;
  white: number;
  mid: number;
  tint: [number, number, number];
}

export class LabRenderer {
  readonly gl: WebGL2RenderingContext;
  private prog: WebGLProgram;
  private tex: WebGLTexture;
  private lut: WebGLTexture;
  private size = { w: 0, h: 0 };
  private loc: Record<string, WebGLUniformLocation | null> = {};

  constructor(readonly canvas: HTMLCanvasElement) {
    const gl = canvas.getContext('webgl2', { antialias: false, alpha: false, preserveDrawingBuffer: true });
    if (!gl) throw new Error('WebGL2 unavailable');
    this.gl = gl;
    const sh = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? 'shader');
      return s;
    };
    const p = gl.createProgram()!;
    gl.attachShader(p, sh(gl.VERTEX_SHADER, VS));
    gl.attachShader(p, sh(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) ?? 'link');
    this.prog = p;
    gl.useProgram(p);
    for (const n of ['u_img', 'u_lut', 'u_imgSize', 'u_viewSize', 'u_center', 'u_scale', 'u_taps', 'u_black', 'u_white', 'u_mid', 'u_tint']) {
      this.loc[n] = gl.getUniformLocation(p, n);
    }
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const a = gl.getAttribLocation(p, 'a_pos');
    gl.enableVertexAttribArray(a);
    gl.vertexAttribPointer(a, 2, gl.FLOAT, false, 0, 0);
    this.tex = gl.createTexture()!;
    this.lut = gl.createTexture()!;
    gl.uniform1i(this.loc.u_img, 0);
    gl.uniform1i(this.loc.u_lut, 1);
    this.setPalette('neutral');
  }

  setPalette(palette: Palette): void {
    const gl = this.gl;
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.lut);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 4);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, buildLut(palette));
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  }

  /** Upload a frame; returns the CPU time of the call (ms). */
  upload(px: Uint16Array, w: number, h: number): number {
    const gl = this.gl;
    const t0 = performance.now();
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.tex);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 2);
    if (w !== this.size.w || h !== this.size.h) {
      // Immutable storage once per size; later frames only refill it.
      this.tex = gl.createTexture()!;
      gl.bindTexture(gl.TEXTURE_2D, this.tex);
      gl.texStorage2D(gl.TEXTURE_2D, 1, gl.R16UI, w, h);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      this.size = { w, h };
    }
    gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, w, h, gl.RED_INTEGER, gl.UNSIGNED_SHORT, px);
    return performance.now() - t0;
  }

  /** Draw; returns the CPU time of the call (ms). GPU time is not observable portably. */
  draw(p: DrawParams): number {
    const gl = this.gl;
    const t0 = performance.now();
    const { width, height } = this.canvas;
    gl.viewport(0, 0, width, height);
    gl.useProgram(this.prog);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.tex);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.lut);
    gl.uniform2f(this.loc.u_imgSize, this.size.w, this.size.h);
    gl.uniform2f(this.loc.u_viewSize, width, height);
    gl.uniform2f(this.loc.u_center, p.view.cx, p.view.cy);
    gl.uniform1f(this.loc.u_scale, p.view.scale);
    gl.uniform1i(this.loc.u_taps, Math.max(1, Math.min(4, Math.ceil(1 / p.view.scale))));
    gl.uniform1f(this.loc.u_black, p.black);
    gl.uniform1f(this.loc.u_white, p.white);
    gl.uniform1f(this.loc.u_mid, p.mid);
    gl.uniform3f(this.loc.u_tint, p.tint[0], p.tint[1], p.tint[2]);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    return performance.now() - t0;
  }

  /** Block until the GPU has finished (1-px readPixels); returns the wait (ms). */
  sync(): number {
    const gl = this.gl;
    const t0 = performance.now();
    const px = new Uint8Array(4);
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    return performance.now() - t0;
  }

  get frameSize(): { w: number; h: number } {
    return this.size;
  }

  dispose(): void {
    this.gl.getExtension('WEBGL_lose_context')?.loseContext();
  }
}

/** Midtones balance that puts `x` (0..1, after black/white) at `target`. */
export function midtonesFor(x: number, target = 0.12): number {
  // Solve mtf(m, x) = target for m.
  if (x <= 0 || x >= 1) return 0.5;
  return (x * (target - 1)) / (2 * x * target - x - target);
}
