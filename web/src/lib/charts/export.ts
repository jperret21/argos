/**
 * Export hooks for charts (Q-G16, README 3.13: "Copy data (TSV)" per plot, a
 * PNG of the view). Promoted from src/lab/charts/core/export.ts (web/lab/
 * PROPOSAL.md section 6, W7). The browser route is here (clipboard, a download
 * link); the desktop app routes the same hooks through the Tauri dialog and fs
 * plugins in wave 8. A chart calls a hook; it never decides where a file goes.
 *
 * - toTsv: a header row, then one row per point; tabs and line breaks inside a
 *   value become spaces, so a pasted table always has the columns it says.
 * - composeCanvas: the canvases of a region (a wall cell, every cell) and its
 *   HTML labels redrawn as text, at the device ratio, on the plot surface: what
 *   the observer sees, as one PNG.
 */

export interface ExportHooks {
  /** Copy a TSV table (clipboard, else a .tsv download); resolves to the sentence to show. */
  tsv: (name: string, text: string, rows: number) => Promise<string>;
  /** Save a canvas as PNG; resolves to the sentence to show. */
  png: (name: string, canvas: HTMLCanvasElement) => Promise<string>;
}

const clean = (v: string | number): string => String(v).replace(/[\t\n\r]+/g, ' ');

/** TSV with a header row; values are written as given (format them before). */
export function toTsv(header: readonly string[], rows: readonly (readonly (string | number)[])[]): string {
  return [header.map(clean).join('\t'), ...rows.map((r) => r.map(clean).join('\t'))].join('\n') + '\n';
}

/**
 * A file name from words ("XX Cyg · target" → "XX_Cyg_target"): letters,
 * digits, dot, dash and underscore only, never empty.
 */
export function fileStem(...parts: (string | null | undefined)[]): string {
  const s = parts
    .filter((p): p is string => !!p && p.trim() !== '')
    .map((p) =>
      p
        .normalize('NFKD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^A-Za-z0-9._-]+/g, '_')
        .replace(/^_+|_+$/g, ''),
    )
    .filter(Boolean)
    .join('_');
  return s || 'plot';
}

function download(name: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.style.display = 'none';
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`;

export const browserExport: ExportHooks = {
  async tsv(name, text, rows) {
    try {
      await navigator.clipboard.writeText(text);
      return `Copied ${plural(rows, 'row')} as TSV`;
    } catch {
      download(name, new Blob([text], { type: 'text/tab-separated-values' }));
      return `Saved ${name} (${plural(rows, 'row')})`;
    }
  },
  async png(name, canvas) {
    const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, 'image/png'));
    if (!blob) throw new Error('The browser could not encode the PNG');
    download(name, blob);
    return `Saved ${name} · ${canvas.width} × ${canvas.height} px · ${Math.round(blob.size / 1024)} kB`;
  },
};

/** A text of the region redrawn on the PNG (a cell title, a value). */
export interface ExportText {
  el: Element;
  color: string;
  /** CSS font with a px size ("500 11px IBM Plex Sans"); scaled to the device ratio. */
  font: string;
}

/**
 * Compose the canvases of `frame` (uPlot draws on canvases) and its HTML
 * texts into one PNG-ready canvas, positioned as on screen, on `background`.
 */
export function composeCanvas(frame: HTMLElement, background: string, texts: readonly ExportText[], dpr = window.devicePixelRatio || 1): HTMLCanvasElement {
  const box = frame.getBoundingClientRect();
  const out = document.createElement('canvas');
  out.width = Math.max(1, Math.round(box.width * dpr));
  out.height = Math.max(1, Math.round(box.height * dpr));
  const ctx = out.getContext('2d');
  if (!ctx) return out;
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, out.width, out.height);
  for (const c of frame.querySelectorAll('canvas')) {
    const r = c.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    ctx.drawImage(c, (r.left - box.left) * dpr, (r.top - box.top) * dpr, r.width * dpr, r.height * dpr);
  }
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  for (const t of texts) {
    const r = t.el.getBoundingClientRect();
    if (r.width === 0) continue;
    ctx.font = t.font.replace(/(\d+(?:\.\d+)?)px/, (_m, px) => `${Number(px) * dpr}px`);
    ctx.fillStyle = t.color;
    ctx.fillText(t.el.textContent?.replace(/\s+/g, ' ').trim() ?? '', (r.left - box.left) * dpr, (r.top - box.top + r.height / 2) * dpr);
  }
  return out;
}
