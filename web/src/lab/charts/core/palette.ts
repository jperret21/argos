/**
 * Design tokens for canvas drawing (uPlot, sparklines, PNG export).
 *
 * A canvas cannot use var(--x): values are read at build time from the
 * element's computed style and re-read on every theme change (charts rebuild
 * their options then). Two traps measured by the research lab
 * (stack-capabilities 3.7): custom properties come back unresolved
 * ("color-mix(in srgb, ...)"), and computed colour-mix serialises as
 * "color(srgb ...)". resolveColor() therefore asks the engine: the value is
 * set as an element's colour, one canvas pixel is painted and read back.
 * Cached per string, so draw loops stay cheap.
 */

const cache = new Map<string, [number, number, number, number]>();
let probeEl: HTMLSpanElement | null = null;
let probeCtx: CanvasRenderingContext2D | null = null;

export function resolveColor(css: string): [number, number, number, number] {
  const hit = cache.get(css);
  if (hit) return hit;
  if (!probeEl) {
    probeEl = document.createElement('span');
    probeEl.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;visibility:hidden';
    document.body.append(probeEl);
  }
  if (!probeCtx) {
    const c = document.createElement('canvas');
    c.width = c.height = 1;
    probeCtx = c.getContext('2d', { willReadFrequently: true });
  }
  probeEl.style.color = '';
  probeEl.style.color = css;
  const computed = getComputedStyle(probeEl).color;
  let out: [number, number, number, number] = [0, 0, 0, 255];
  if (probeCtx) {
    probeCtx.clearRect(0, 0, 1, 1);
    probeCtx.fillStyle = '#000';
    probeCtx.fillStyle = computed;
    probeCtx.fillRect(0, 0, 1, 1);
    const d = probeCtx.getImageData(0, 0, 1, 1).data;
    out = [d[0], d[1], d[2], d[3]];
  }
  cache.set(css, out);
  return out;
}

/** A resolved token colour: build "rgba()" strings at any alpha. */
export class Ink {
  readonly r: number;
  readonly g: number;
  readonly b: number;
  constructor(css: string) {
    [this.r, this.g, this.b] = resolveColor(css);
  }
  /** "rgba(r, g, b, a)". */
  a(alpha = 1): string {
    return `rgba(${this.r}, ${this.g}, ${this.b}, ${alpha})`;
  }
  toString(): string {
    return this.a(1);
  }
  /** 0..1 floats, for WebGL or LUTs. */
  get rgb01(): [number, number, number] {
    return [this.r / 255, this.g / 255, this.b / 255];
  }
}

/** Everything a chart draws with, resolved for the theme active on `el`. */
export interface ChartInks {
  surface: Ink;
  grid: Ink;
  axis: Ink;
  text: Ink;
  reference: Ink;
  highlight: Ink;
  target: Ink;
  comparison: Ink;
  check: Ink;
  fg: Ink;
  fgMuted: Ink;
  textMuted: Ink;
  accent: Ink;
  warning: Ink;
  danger: Ink;
  success: Ink;
  border: Ink;
  borderSoft: Ink;
  bg: Ink;
  bg2: Ink;
  viewerTint: Ink;
  errorAlpha: number;
  /** Font family list of the mono face (for canvas `font`). */
  mono: string;
  ui: string;
  /** Lab-proposed tokens (see lab.css, "--lab-" prefix). */
  lab: {
    bandAlpha: number;
    twilight: number[];
    clipAlpha: number;
  };
  theme: string;
}

export function readInks(el: Element): ChartInks {
  const css = getComputedStyle(el);
  const raw = (n: string) => css.getPropertyValue(n).trim();
  const ink = (n: string) => new Ink(raw(n) || '#000');
  const num = (n: string, d: number) => {
    const v = Number.parseFloat(raw(n));
    return Number.isFinite(v) ? v : d;
  };
  return {
    surface: ink('--chart-surface'),
    grid: ink('--chart-grid'),
    axis: ink('--chart-axis'),
    text: ink('--chart-text'),
    reference: ink('--chart-reference'),
    highlight: ink('--chart-highlight'),
    target: ink('--chart-1'),
    comparison: ink('--chart-2'),
    check: ink('--chart-3'),
    fg: ink('--fg'),
    fgMuted: ink('--fg-muted'),
    textMuted: ink('--text-muted'),
    accent: ink('--accent'),
    warning: ink('--warning'),
    danger: ink('--danger'),
    success: ink('--success'),
    border: ink('--border'),
    borderSoft: ink('--border-soft'),
    bg: ink('--bg'),
    bg2: ink('--bg-2'),
    viewerTint: ink('--viewer-tint'),
    errorAlpha: num('--chart-error-opacity', 0.55),
    mono: raw('--font-mono') || 'monospace',
    ui: raw('--font-ui') || 'sans-serif',
    lab: {
      bandAlpha: num('--lab-chart-band-alpha', 0.16),
      twilight: [0, 1, 2, 3, 4].map((i) => num(`--lab-chart-twilight-${i}`, [0, 0.03, 0.06, 0.1, 0.15][i])),
      clipAlpha: num('--lab-chart-clip-alpha', 0.5),
    },
    theme: document.documentElement.getAttribute('data-theme') ?? 'observatory',
  };
}

/** Canvas font string for the mono face at `px` CSS pixels (scaled by the device ratio). */
export function monoFont(inks: ChartInks, px: number, weight = 400, dpr = 1): string {
  return `${weight} ${Math.round(px * dpr)}px ${inks.mono}`;
}
