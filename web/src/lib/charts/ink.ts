/**
 * Design tokens resolved for canvas and WebGL drawing (uPlot, the histogram,
 * sparklines, PNG export, viewer uniforms).
 *
 * A canvas cannot use var(--x): the value is read from the computed style at
 * build time and re-read on every theme change (charts rebuild their options
 * then). Promoted from src/lab/research/tokens.ts and
 * src/lab/charts/core/palette.ts (web/lab/PROPOSAL.md section 6). Two traps the
 * research lab measured (stack-capabilities 3.7):
 *
 * 1. getPropertyValue('--selection-bg') returns the token's text with var()
 *    substituted ("color-mix(in srgb, #8d6b2b 55%, #191b1f)"), not a colour:
 *    unregistered custom properties are not computed.
 * 2. The engine serialises a computed color-mix() as "color(srgb r g b)", which
 *    "#rrggbb" / "rgb()" parsers (lib/app/theme.ts parseCssColor) miss.
 *
 * resolveColor() therefore parses the common forms itself (hex, rgb(), rgba(),
 * color(srgb …)) and hands anything else to the engine: the value becomes an
 * element's `color` (any syntax the engine knows), the computed colour is
 * parsed, and as a last resort one pixel of a 2D canvas gives sRGB bytes.
 * Results are cached per string, so draw loops stay cheap.
 */

/** sRGB bytes and alpha: r, g, b in 0..255, a in 0..1. */
export type RGBA = readonly [number, number, number, number];

const clampByte = (v: number) => Math.min(255, Math.max(0, Math.round(v)));
const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** A channel of rgb(): "216", "84.7%"; null when it is not a number. */
function rgbChannel(t: string): number | null {
  if (t.endsWith('%')) {
    const v = Number(t.slice(0, -1));
    return Number.isFinite(v) ? clampByte((v / 100) * 255) : null;
  }
  const v = Number(t);
  return Number.isFinite(v) ? clampByte(v) : null;
}

/** An alpha: "0.5", "50%"; null when it is not a number. */
function alphaChannel(t: string | undefined): number | null {
  if (t === undefined) return 1;
  const v = t.endsWith('%') ? Number(t.slice(0, -1)) / 100 : Number(t);
  return Number.isFinite(v) ? clamp01(v) : null;
}

/** Split "a, b, c / d" or "a b c / d" into channels and an optional alpha. */
function channels(body: string): { c: string[]; alpha?: string } | null {
  const [main, alpha, extra] = body.split('/');
  if (extra !== undefined) return null;
  const c = main
    .trim()
    .split(/\s*,\s*|\s+/)
    .filter(Boolean);
  const a = alpha?.trim();
  if (c.length === 4 && a === undefined) return { c: c.slice(0, 3), alpha: c[3] };
  return c.length === 3 ? { c, alpha: a } : null;
}

/**
 * Parse the colour forms a computed style produces, without the engine:
 * "#rgb", "#rgba", "#rrggbb", "#rrggbbaa", "rgb()" / "rgba()" (comma or space
 * syntax), "color(srgb r g b [/ a])" (0..1 or percentages) and "transparent".
 * Returns null for anything else (named colours, color-mix(), oklch(), …).
 */
export function parseColor(css: string): RGBA | null {
  const text = css.trim().toLowerCase();
  if (text === 'transparent') return [0, 0, 0, 0];
  let m = /^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/.exec(text);
  if (m) {
    let hex = m[1];
    if (hex.length <= 4) hex = [...hex].map((h) => h + h).join('');
    const n = (i: number) => parseInt(hex.slice(i, i + 2), 16);
    return [n(0), n(2), n(4), hex.length === 8 ? Math.round((n(6) / 255) * 1000) / 1000 : 1];
  }
  m = /^rgba?\(([^)]*)\)$/.exec(text);
  if (m) {
    const parts = channels(m[1]);
    if (!parts) return null;
    const [r, g, b] = parts.c.map(rgbChannel);
    const a = alphaChannel(parts.alpha);
    if (r === null || g === null || b === null || a === null) return null;
    return [r, g, b, a];
  }
  m = /^color\(\s*srgb\s+([^)]*)\)$/.exec(text);
  if (m) {
    const parts = channels(m[1]);
    if (!parts) return null;
    const unit = parts.c.map((t) => {
      if (t === 'none') return 0;
      const v = t.endsWith('%') ? Number(t.slice(0, -1)) / 100 : Number(t);
      return Number.isFinite(v) ? clampByte(clamp01(v) * 255) : null;
    });
    const a = parts.alpha === 'none' ? 0 : alphaChannel(parts.alpha);
    if (unit.some((v) => v === null) || a === null) return null;
    return [unit[0] as number, unit[1] as number, unit[2] as number, a];
  }
  return null;
}

/** How the engine turns a CSS colour it knows into one of the parseable forms. */
export type ColorEngine = (css: string) => RGBA | null;

let probeEl: HTMLSpanElement | null = null;
let probeCtx: CanvasRenderingContext2D | null = null;

/** The browser: computed `color` of a hidden element, then one canvas pixel. */
export const browserEngine: ColorEngine = (css) => {
  const doc = globalThis.document;
  if (!doc?.body) return null;
  if (!probeEl) {
    probeEl = doc.createElement('span');
    probeEl.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;visibility:hidden';
    probeEl.setAttribute('aria-hidden', 'true');
    doc.body.append(probeEl);
  }
  probeEl.style.color = '';
  probeEl.style.color = css;
  if (!probeEl.style.color) return null; // not a colour the engine accepts
  const computed = getComputedStyle(probeEl).color;
  const parsed = parseColor(computed);
  if (parsed) return parsed;
  if (!probeCtx) {
    const c = doc.createElement('canvas');
    c.width = c.height = 1;
    probeCtx = c.getContext('2d', { willReadFrequently: true });
  }
  if (!probeCtx) return null;
  probeCtx.clearRect(0, 0, 1, 1);
  probeCtx.fillStyle = '#000';
  probeCtx.fillStyle = computed;
  probeCtx.fillRect(0, 0, 1, 1);
  const d = probeCtx.getImageData(0, 0, 1, 1).data;
  return [d[0], d[1], d[2], Math.round((d[3] / 255) * 1000) / 1000];
};

const cache = new Map<string, RGBA>();
/** Opaque black: what an unknown token draws as (black emits no light, safe in Night Red). */
const BLACK: RGBA = [0, 0, 0, 1];

/** Any CSS colour -> sRGB bytes and alpha. Unknown values resolve to black (not cached). */
export function resolveColor(css: string, engine: ColorEngine = browserEngine): RGBA {
  const key = css.trim();
  const hit = cache.get(key);
  if (hit) return hit;
  const out = parseColor(key) ?? engine(key);
  if (!out) return BLACK;
  cache.set(key, out);
  return out;
}

/** Forget resolved colours (tests; a page that redefines its tokens at run time). */
export function clearInkCache(): void {
  cache.clear();
}

/** A resolved token colour: "rgba()" strings at any alpha, or 0..1 floats. */
export class Ink {
  readonly r: number;
  readonly g: number;
  readonly b: number;
  /** The colour's own alpha, 0..1 (1 for every palette token). */
  readonly alpha: number;
  constructor(css: string, engine?: ColorEngine) {
    [this.r, this.g, this.b, this.alpha] = resolveColor(css, engine);
  }
  /** "rgba(r, g, b, a)", `alpha` multiplied by the colour's own alpha. */
  a(alpha = 1): string {
    return `rgba(${this.r}, ${this.g}, ${this.b}, ${Math.round(alpha * this.alpha * 1000) / 1000})`;
  }
  toString(): string {
    return this.a(1);
  }
  /** 0..1 floats, for WebGL uniforms or LUTs. */
  get rgb01(): [number, number, number] {
    return [this.r / 255, this.g / 255, this.b / 255];
  }
}

/** What readInks needs from a computed style (a fake in tests). */
export type StyleSource = Pick<CSSStyleDeclaration, 'getPropertyValue'>;

/** A token's text from a computed style, trimmed ("" when undefined). */
export function cssVar(style: StyleSource, name: string): string {
  return style.getPropertyValue(name).trim();
}

/** Everything a chart draws with, resolved for the theme active on an element. */
export interface ChartInks {
  surface: Ink;
  grid: Ink;
  axis: Ink;
  text: Ink;
  reference: Ink;
  highlight: Ink;
  /** --chart-1..3: the photometric roles. */
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
  /** --chart-error-opacity. */
  errorAlpha: number;
  /** --chart-band-alpha (stability bands, fit envelopes; theme dependent). */
  bandAlpha: number;
  /** --chart-flag-alpha (hatch of a period where a rule holds). */
  flagAlpha: number;
  /** --chart-clip-alpha (histogram regions the stretch clips). */
  clipAlpha: number;
  /** --chart-twilight-0..4: washes of --fg-muted (night .. day). */
  twilight: [number, number, number, number, number];
  /** Font family lists, for a canvas `font`. */
  mono: string;
  ui: string;
}

const TWILIGHT_DEFAULT = [0, 0.035, 0.065, 0.1, 0.15] as const;

/** Resolve the chart inks from a computed style. */
export function inksFrom(style: StyleSource, engine?: ColorEngine): ChartInks {
  const raw = (n: string) => cssVar(style, n);
  const ink = (n: string) => new Ink(raw(n) || '#000', engine);
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
    bandAlpha: num('--chart-band-alpha', 0.16),
    flagAlpha: num('--chart-flag-alpha', 0.22),
    clipAlpha: num('--chart-clip-alpha', 0.5),
    twilight: TWILIGHT_DEFAULT.map((d, i) => num(`--chart-twilight-${i}`, d)) as ChartInks['twilight'],
    mono: raw('--font-mono') || 'monospace',
    ui: raw('--font-ui') || 'sans-serif',
  };
}

/** The chart inks of the theme active on `el` (call again after a theme change). */
export function readInks(el: Element): ChartInks {
  return inksFrom(getComputedStyle(el));
}

/** Canvas font for the mono face at `px` CSS pixels, scaled by the device ratio. */
export function monoFont(inks: Pick<ChartInks, 'mono'>, px: number, weight = 400, dpr = 1): string {
  return `${weight} ${Math.round(px * dpr)}px ${inks.mono}`;
}

/** Canvas font for the UI face. */
export function uiFont(inks: Pick<ChartInks, 'ui'>, px: number, weight = 400, dpr = 1): string {
  return `${weight} ${Math.round(px * dpr)}px ${inks.ui}`;
}
