/**
 * Design tokens for canvas and WebGL code.
 *
 * A canvas cannot use var(--x): the value must be read at draw time and
 * re-read on a theme change. Two traps, both measured in the lab (see
 * stack-capabilities.md):
 *
 * 1. getPropertyValue('--selection-bg') returns the token text with var()
 *    substituted ("color-mix(in srgb, #8d6b2b 55%, #191b1f)"), not a colour:
 *    unregistered custom properties are not computed.
 * 2. Parsers written for "#rrggbb" / "rgb()" (lib/app/theme.ts parseCssColor)
 *    miss "color(srgb ...)", "oklch(...)" and "color-mix(...)".
 *
 * resolveColor() asks the engine instead: the value goes through an element's
 * `color` (any CSS colour syntax the engine knows), then one pixel of a 2D
 * canvas gives sRGB bytes. Cached per string, so draw loops stay cheap.
 */

const cache = new Map<string, [number, number, number, number]>();
let probeEl: HTMLSpanElement | null = null;
let probeCtx: CanvasRenderingContext2D | null = null;

export function cssVar(el: Element, name: string): string {
  return getComputedStyle(el).getPropertyValue(name).trim();
}

/** Any CSS colour -> [r, g, b, a] bytes (a 0..255), via the engine. */
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
  const computed = getComputedStyle(probeEl).color; // "rgb()", or "color(srgb ...)" for color-mix
  let out: [number, number, number, number] = [0, 0, 0, 0];
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

export function rgba(css: string, alpha = 1): string {
  const [r, g, b] = resolveColor(css);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** 0..1 RGB for WebGL uniforms. */
export function rgb01(css: string): [number, number, number] {
  const [r, g, b] = resolveColor(css);
  return [r / 255, g / 255, b / 255];
}

/** The chart palette of the theme active on `el`, resolved for canvas. */
export interface ChartPalette {
  surface: string;
  grid: string;
  axis: string;
  text: string;
  reference: string;
  highlight: string;
  target: string;
  comparison: string;
  check: string;
  errorAlpha: number;
  accent: string;
  fg: string;
  fgMuted: string;
  textMuted: string;
  danger: string;
  warning: string;
  border: string;
  borderSoft: string;
  bg2: string;
  mono: string;
  viewerTint: string;
}

export function chartPalette(el: Element): ChartPalette {
  const css = getComputedStyle(el);
  const v = (n: string) => rgba(css.getPropertyValue(n).trim() || '#000');
  return {
    surface: v('--chart-surface'),
    grid: v('--chart-grid'),
    axis: v('--chart-axis'),
    text: v('--chart-text'),
    reference: v('--chart-reference'),
    highlight: v('--chart-highlight'),
    target: v('--chart-1'),
    comparison: v('--chart-2'),
    check: v('--chart-3'),
    errorAlpha: Number(css.getPropertyValue('--chart-error-opacity')) || 0.55,
    accent: v('--accent'),
    fg: v('--fg'),
    fgMuted: v('--fg-muted'),
    textMuted: v('--text-muted'),
    danger: v('--danger'),
    warning: v('--warning'),
    border: v('--border'),
    borderSoft: v('--border-soft'),
    bg2: v('--bg-2'),
    mono: css.getPropertyValue('--font-mono').trim() || 'monospace',
    viewerTint: v('--viewer-tint'),
  };
}

/** "rgba(r, g, b, a)" with another alpha. */
export function withAlpha(rgbaCss: string, alpha: number): string {
  return rgbaCss.replace(/rgba\(([^,]+),([^,]+),([^,]+),[^)]+\)/, `rgba($1,$2,$3, ${alpha})`);
}
