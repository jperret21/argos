/**
 * "Save view as PNG…" (web/spec/04-viewer-and-image-tools.md 2.2 row 1.2 #5,
 * Q9: PNG only): the picture as drawn (FitsViewer.snapshot(), device px) with
 * the SVG overlays of the stage drawn over it (field markers, grid, region
 * box, crosshair), at screen resolution. The HUD chips are not part of it.
 *
 * SVG drawn through an <img> cannot see the page's CSS, so every element's
 * computed paint (stroke, fill, widths, dashes, opacity, font) is written
 * inline on a clone first: the export looks like the screen in every theme.
 */

const PAINT = [
  'fill',
  'fill-opacity',
  'stroke',
  'stroke-width',
  'stroke-opacity',
  'stroke-dasharray',
  'stroke-linecap',
  'stroke-linejoin',
  'opacity',
  'paint-order',
  'font-family',
  'font-size',
  'font-weight',
  'text-anchor',
  'dominant-baseline',
  'visibility',
  'display',
] as const;

function inlineStyles(src: Element, dst: Element): void {
  const cs = getComputedStyle(src);
  const style = PAINT.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(';');
  dst.setAttribute('style', style);
  for (let i = 0; i < src.children.length; i++) {
    const d = dst.children[i];
    if (d) inlineStyles(src.children[i], d);
  }
}

function svgImage(svg: SVGSVGElement): Promise<HTMLImageElement | null> {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  inlineStyles(svg, clone);
  const r = svg.getBoundingClientRect();
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.setAttribute('width', String(r.width));
  clone.setAttribute('height', String(r.height));
  const text = new XMLSerializer().serializeToString(clone);
  const url = URL.createObjectURL(new Blob([text], { type: 'image/svg+xml' }));
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    img.src = url;
  });
}

/**
 * Compose the picture, the bitmap overlays (`canvas[data-overlay]`) and every visible SVG
 * layer of `stage`. `picture` is
 * the viewer's snapshot (device px of `viewerEl`). Resolves to a PNG blob.
 */
export async function composeView(stage: HTMLElement, viewerEl: HTMLElement, picture: HTMLCanvasElement): Promise<Blob | null> {
  const sr = stage.getBoundingClientRect();
  const vr = viewerEl.getBoundingClientRect();
  const scale = picture.width / Math.max(1, vr.width);
  const out = document.createElement('canvas');
  out.width = Math.round(sr.width * scale);
  out.height = Math.round(sr.height * scale);
  const ctx = out.getContext('2d');
  if (!ctx) return null;
  ctx.drawImage(picture, (vr.left - sr.left) * scale, (vr.top - sr.top) * scale);
  // Bitmap overlays (the catalogue layers' canvas), under the SVG ones.
  for (const c of Array.from(stage.querySelectorAll<HTMLCanvasElement>('canvas[data-overlay]'))) {
    const r = c.getBoundingClientRect();
    if (r.width > 32 && r.height > 32 && getComputedStyle(c).display !== 'none') {
      ctx.globalAlpha = Number(getComputedStyle(c).opacity) || 1;
      ctx.drawImage(c, (r.left - sr.left) * scale, (r.top - sr.top) * scale, r.width * scale, r.height * scale);
      ctx.globalAlpha = 1;
    }
  }
  const layers = Array.from(stage.querySelectorAll<SVGSVGElement>('svg')).filter((s) => {
    // Overlays only: not icons inside chips or buttons, nothing hidden.
    if (s.closest('button, [role="dialog"], [data-hud], .loupe')) return false;
    const r = s.getBoundingClientRect();
    return r.width > 32 && r.height > 32 && getComputedStyle(s).display !== 'none';
  });
  for (const svg of layers) {
    const img = await svgImage(svg);
    if (!img) continue;
    const r = svg.getBoundingClientRect();
    ctx.drawImage(img, (r.left - sr.left) * scale, (r.top - sr.top) * scale, r.width * scale, r.height * scale);
  }
  return new Promise((resolve) => out.toBlob((b) => resolve(b), 'image/png'));
}

/** File name: argos_view_<seq>_<UTC>.png. */
export function viewFileName(seq: number | null, now = new Date()): string {
  const t = now.toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
  return `argos_view_${seq !== null ? `${seq}_` : ''}${t}.png`;
}

/** Hand a blob to the browser as a download (the desktop build will use a save dialog, W8). */
export function download(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
