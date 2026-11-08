/**
 * WebGL2 renderer of 16-bit frames (no Svelte, no DOM besides the canvas).
 *
 * - upload(): raw uint16 -> R16UI / RGB16UI texture (see shaders.ts for why).
 *   The texture is allocated once per size/format (texStorage2D) and refilled
 *   with texSubImage2D, so live frames of a constant size never reallocate.
 * - draw(): one full-screen triangle; stretch, pan and zoom are uniforms, so a
 *   slider move or a wheel tick never re-uploads the image.
 * - Context loss (GPU reset, driver update, too many contexts) is handled: the
 *   GL objects are rebuilt on "webglcontextrestored" and the last frame is
 *   re-uploaded from the reference kept here (no copy).
 * - Wave 4: the palette LUT (texture unit 1, uploaded when the palette
 *   changes), the CFA preview and the saturation highlight are uniforms too.
 */

import { buildLut, LUT_SIZE, paletteCode, type Palette } from './palettes/lut';
import { FRAGMENT_SHADER, MAX_TAPS, VERTEX_SHADER } from './shaders';
import type { StretchMode, StretchParams } from './stretch';
import type { ViewState } from './view';

export interface FrameData {
  width: number;
  height: number;
  channels: 1 | 3;
  /** width*height*channels samples, row 0 = top. */
  pixels: Uint16Array;
}

export interface DrawOptions {
  view: ViewState;
  stretch: StretchParams;
  nightTint: boolean;
  /** Display rotation, clockwise quarter turns (viewer/rotation.ts); default 0. */
  rotation?: 0 | 1 | 2 | 3;
  /** Full-scale colour, 0..1 RGB (the --viewer-tint token); default white. */
  tint?: readonly [number, number, number];
  /** Device px per CSS px actually used by the canvas backing store. */
  dpr: number;
  /** Display palette (palettes/lut.ts); default neutral. Night Red forces the luminance in red. */
  palette?: Palette;
  /** CFA preview (palettes/cfa.ts previewCode); default 0, the samples as delivered. */
  preview?: PreviewUniforms;
  /** Saturation highlight on raw samples; null or absent: off. */
  saturation?: { threshold: number; colour: readonly [number, number, number] } | null;
}

/** Uniforms of a CFA preview. */
export interface PreviewUniforms {
  /** 0 as delivered, 1 CFA colour, 2 / 3 / 4 the R / G / B plane. */
  code: number;
  /** Cell sites [x, y] of R, B, G1, G2 (any for code 0). */
  r: readonly [number, number];
  b: readonly [number, number];
  g1: readonly [number, number];
  g2: readonly [number, number];
  /** Display balance of the colour preview. */
  gains: readonly [number, number, number];
}

const MODE_INDEX: Record<StretchMode, number> = { linear: 0, log: 1, asinh: 2 };

type UniformName =
  | 'u_image'
  | 'u_size'
  | 'u_rot'
  | 'u_channels'
  | 'u_viewportH'
  | 'u_offset'
  | 'u_scale'
  | 'u_taps'
  | 'u_black'
  | 'u_white'
  | 'u_midtones'
  | 'u_mode'
  | 'u_nightTint'
  | 'u_tint'
  | 'u_preview'
  | 'u_rb'
  | 'u_gg'
  | 'u_gains'
  | 'u_palette'
  | 'u_lut'
  | 'u_satOn'
  | 'u_satThreshold'
  | 'u_satColour';

const UNIFORMS: UniformName[] = [
  'u_image',
  'u_size',
  'u_rot',
  'u_channels',
  'u_viewportH',
  'u_offset',
  'u_scale',
  'u_taps',
  'u_black',
  'u_white',
  'u_midtones',
  'u_mode',
  'u_nightTint',
  'u_tint',
  'u_preview',
  'u_rb',
  'u_gg',
  'u_gains',
  'u_palette',
  'u_lut',
  'u_satOn',
  'u_satThreshold',
  'u_satColour',
];

export class WebGLUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'WebGLUnavailableError';
  }
}

interface GLState {
  gl: WebGL2RenderingContext;
  program: WebGLProgram;
  vao: WebGLVertexArrayObject;
  uniforms: Record<UniformName, WebGLUniformLocation | null>;
  texture: WebGLTexture | null;
  /** Allocated texture geometry, to decide between reallocate and refill. */
  texW: number;
  texH: number;
  texChannels: number;
  /** Palette LUT (unit 1) and the palette it holds (null: not uploaded yet). */
  lut: WebGLTexture | null;
  lutPalette: Palette | null;
}

function compile(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new WebGLUnavailableError('createShader failed');
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS) && !gl.isContextLost()) {
    const log = gl.getShaderInfoLog(shader) ?? '';
    gl.deleteShader(shader);
    throw new WebGLUnavailableError(`shader compile error: ${log}`);
  }
  return shader;
}

export class ImageRenderer {
  readonly canvas: HTMLCanvasElement;
  private state: GLState | null = null;
  private frame: FrameData | null = null;
  private lost = false;
  private readonly fencePixel = new Uint8Array(4);
  private readonly onRestored: () => void;
  private readonly handleLost = (e: Event) => {
    e.preventDefault(); // tell the browser we want the context back
    this.lost = true;
    this.state = null;
  };
  private readonly handleRestored = () => {
    this.lost = false;
    try {
      this.init();
      if (this.frame) this.upload(this.frame);
      this.onRestored();
    } catch (err) {
      console.error('[viewer] WebGL restore failed', err);
    }
  };

  /** Throws WebGLUnavailableError when WebGL2 is not available. */
  constructor(canvas: HTMLCanvasElement, onRestored: () => void = () => {}) {
    this.canvas = canvas;
    this.onRestored = onRestored;
    canvas.addEventListener('webglcontextlost', this.handleLost);
    canvas.addEventListener('webglcontextrestored', this.handleRestored);
    this.init();
  }

  get isContextLost(): boolean {
    return this.lost;
  }

  get maxTextureSize(): number {
    return this.state ? (this.state.gl.getParameter(this.state.gl.MAX_TEXTURE_SIZE) as number) : 0;
  }

  private init(): void {
    const gl = this.canvas.getContext('webgl2', {
      alpha: true,
      premultipliedAlpha: true,
      antialias: false,
      depth: false,
      stencil: false,
      preserveDrawingBuffer: false,
    });
    if (!gl) throw new WebGLUnavailableError('WebGL2 is not available in this browser');

    const vs = compile(gl, gl.VERTEX_SHADER, VERTEX_SHADER);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
    const program = gl.createProgram();
    if (!program) throw new WebGLUnavailableError('createProgram failed');
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    gl.deleteShader(vs);
    gl.deleteShader(fs);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS) && !gl.isContextLost()) {
      throw new WebGLUnavailableError(`program link error: ${gl.getProgramInfoLog(program) ?? ''}`);
    }
    const vao = gl.createVertexArray();
    if (!vao) throw new WebGLUnavailableError('createVertexArray failed');

    const uniforms = {} as Record<UniformName, WebGLUniformLocation | null>;
    for (const name of UNIFORMS) uniforms[name] = gl.getUniformLocation(program, name);

    // Rows of 16-bit samples are tightly packed: with the default alignment of
    // 4, any odd width (2-byte rows not a multiple of 4) would be read skewed.
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.disable(gl.BLEND);
    gl.disable(gl.DEPTH_TEST);

    this.state = { gl, program, vao, uniforms, texture: null, texW: 0, texH: 0, texChannels: 0, lut: null, lutPalette: null };
  }

  /** Upload the palette's LUT to texture unit 1 when it changed (normalised RGBA8: filterable). */
  private bindLut(s: GLState, palette: Palette): void {
    const { gl } = s;
    gl.activeTexture(gl.TEXTURE1);
    if (!s.lut) {
      s.lut = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, s.lut);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      s.lutPalette = null;
    } else {
      gl.bindTexture(gl.TEXTURE_2D, s.lut);
    }
    if (s.lutPalette !== palette) {
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, 4);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, LUT_SIZE, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, buildLut(palette));
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
      s.lutPalette = palette;
    }
    gl.activeTexture(gl.TEXTURE0);
  }

  /**
   * Upload a frame. Returns the time spent (ms). With `sync`, waits for the
   * GPU (see fence()) so the timing includes the actual transfer; only for
   * measurements, it stalls the pipeline.
   */
  upload(frame: FrameData, sync = false): number {
    this.frame = frame;
    const s = this.state;
    if (!s || this.lost) return 0;
    const { gl } = s;
    const t0 = performance.now();
    const max = gl.getParameter(gl.MAX_TEXTURE_SIZE) as number;
    if (frame.width > max || frame.height > max) {
      throw new WebGLUnavailableError(
        `frame ${frame.width}x${frame.height} exceeds MAX_TEXTURE_SIZE ${max}`,
      );
    }
    const rgb = frame.channels === 3;
    const internal = rgb ? gl.RGB16UI : gl.R16UI;
    const format = rgb ? gl.RGB_INTEGER : gl.RED_INTEGER;

    gl.activeTexture(gl.TEXTURE0);
    const sameGeometry =
      s.texture !== null &&
      s.texW === frame.width &&
      s.texH === frame.height &&
      s.texChannels === frame.channels;
    if (!sameGeometry) {
      if (s.texture) gl.deleteTexture(s.texture);
      const tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      // Integer textures must use NEAREST (anything else makes them
      // incomplete and they sample as zero); filtering is done in the shader.
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texStorage2D(gl.TEXTURE_2D, 1, internal, frame.width, frame.height);
      s.texture = tex;
      s.texW = frame.width;
      s.texH = frame.height;
      s.texChannels = frame.channels;
    } else {
      gl.bindTexture(gl.TEXTURE_2D, s.texture);
    }
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texSubImage2D(
      gl.TEXTURE_2D,
      0,
      0,
      0,
      frame.width,
      frame.height,
      format,
      gl.UNSIGNED_SHORT,
      frame.pixels,
    );
    if (sync) this.fence(gl);
    return performance.now() - t0;
  }

  /** Resize the drawing buffer (device px). Returns true when it changed. */
  resize(width: number, height: number): boolean {
    const w = Math.max(1, Math.round(width));
    const h = Math.max(1, Math.round(height));
    if (this.canvas.width === w && this.canvas.height === h) return false;
    this.canvas.width = w;
    this.canvas.height = h;
    return true;
  }

  /** Draw with the current texture. Returns the time spent (ms), see upload(). */
  draw(opts: DrawOptions, sync = false): number {
    const s = this.state;
    if (!s || this.lost) return 0;
    const { gl, uniforms: u } = s;
    const t0 = performance.now();
    const W = gl.drawingBufferWidth;
    const H = gl.drawingBufferHeight;
    gl.viewport(0, 0, W, H);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    if (!s.texture || !this.frame) return performance.now() - t0;

    const scale = opts.view.scale * opts.dpr; // device px per image px
    const taps = scale >= 1 ? 1 : Math.min(MAX_TAPS, Math.ceil(1 / scale));

    gl.useProgram(s.program);
    gl.bindVertexArray(s.vao);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, s.texture);
    gl.uniform1i(u.u_image, 0);
    gl.uniform2i(u.u_size, s.texW, s.texH);
    gl.uniform1i(u.u_rot, opts.rotation ?? 0);
    gl.uniform1i(u.u_channels, s.texChannels);
    gl.uniform1f(u.u_viewportH, H);
    gl.uniform2f(u.u_offset, opts.view.tx * opts.dpr, opts.view.ty * opts.dpr);
    gl.uniform1f(u.u_scale, scale);
    gl.uniform1i(u.u_taps, taps);
    gl.uniform1f(u.u_black, opts.stretch.black);
    gl.uniform1f(u.u_white, opts.stretch.white);
    gl.uniform1f(u.u_midtones, opts.stretch.midtones);
    gl.uniform1i(u.u_mode, MODE_INDEX[opts.stretch.mode]);
    gl.uniform1i(u.u_nightTint, opts.nightTint ? 1 : 0);
    const [tr, tg, tb] = opts.tint ?? [1, 1, 1];
    gl.uniform3f(u.u_tint, tr, tg, tb);
    // CFA preview: only for a raw mosaic (1 channel) or the planes of an RGB frame.
    const pv = opts.preview;
    const code = pv ? pv.code : 0;
    gl.uniform1i(u.u_preview, code);
    if (pv) {
      gl.uniform4i(u.u_rb, pv.r[0], pv.r[1], pv.b[0], pv.b[1]);
      gl.uniform4i(u.u_gg, pv.g1[0], pv.g1[1], pv.g2[0], pv.g2[1]);
      gl.uniform3f(u.u_gains, pv.gains[0], pv.gains[1], pv.gains[2]);
    }
    const palette = opts.palette ?? 'neutral';
    const pcode = paletteCode(palette);
    gl.uniform1i(u.u_palette, pcode);
    gl.uniform1i(u.u_lut, 1);
    if (pcode === 2) this.bindLut(s, palette);
    const sat = opts.saturation;
    gl.uniform1i(u.u_satOn, sat ? 1 : 0);
    if (sat) {
      gl.uniform1f(u.u_satThreshold, sat.threshold);
      // Night Red: a clipped core is a black hole, never another colour (BRAND 4.3).
      const [sr, sg, sb] = opts.nightTint ? [0, 0, 0] : sat.colour;
      gl.uniform3f(u.u_satColour, sr, sg, sb);
    }
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindVertexArray(null);
    if (sync) this.fence(gl);
    return performance.now() - t0;
  }

  /**
   * Block until the GPU has executed everything queued so far. A 1-pixel
   * readPixels is a real fence in Chrome and WebKit; gl.finish() is not
   * (Chrome returns before the GPU process has run the commands).
   */
  private fence(gl: WebGL2RenderingContext): void {
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, this.fencePixel);
  }

  /** Drop the frame and its texture (screen goes blank on next draw). */
  clear(): void {
    this.frame = null;
    const s = this.state;
    if (s?.texture) {
      s.gl.deleteTexture(s.texture);
      s.texture = null;
      s.texW = s.texH = s.texChannels = 0;
    }
  }

  dispose(): void {
    this.canvas.removeEventListener('webglcontextlost', this.handleLost);
    this.canvas.removeEventListener('webglcontextrestored', this.handleRestored);
    const s = this.state;
    if (s && !s.gl.isContextLost()) {
      if (s.texture) s.gl.deleteTexture(s.texture);
      if (s.lut) s.gl.deleteTexture(s.lut);
      s.gl.deleteVertexArray(s.vao);
      s.gl.deleteProgram(s.program);
    }
    this.state = null;
    this.frame = null;
  }
}
