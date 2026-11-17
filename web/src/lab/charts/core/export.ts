/**
 * Export hooks for charts (spec Q-G16: "Copy data (TSV)" per plot, a PNG of
 * the view). The lab implements them in the browser (clipboard, download
 * link); the app would route them through the Tauri dialog / fs plugins.
 * Charts call the hook; they never decide where a file goes.
 */

export interface ExportHooks {
  tsv: (name: string, text: string, rows: number) => Promise<string>;
  png: (name: string, canvas: HTMLCanvasElement) => Promise<string>;
}

/** TSV with a header row; values are written as given (already formatted). */
export function toTsv(header: string[], rows: (string | number)[][]): string {
  const clean = (v: string | number) => String(v).replace(/[\t\n\r]/g, ' ');
  return [header.map(clean).join('\t'), ...rows.map((r) => r.map(clean).join('\t'))].join('\n') + '\n';
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

export const browserExport: ExportHooks = {
  async tsv(name, text, rows) {
    try {
      await navigator.clipboard.writeText(text);
      return `Copied ${rows} rows as TSV`;
    } catch {
      download(name, new Blob([text], { type: 'text/tab-separated-values' }));
      return `Saved ${name} (${rows} rows)`;
    }
  },
  async png(name, canvas) {
    const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, 'image/png'));
    if (!blob) return 'PNG export failed';
    download(name, blob);
    return `Saved ${name} · ${canvas.width} × ${canvas.height} px · ${Math.round(blob.size / 1024)} kB`;
  },
};

/**
 * Compose the canvases of several uPlot charts (and their HTML headers,
 * redrawn as text) into one PNG-ready canvas, positioned as on screen.
 */
export function composeCanvas(
  frame: HTMLElement,
  background: string,
  texts: { el: Element; color: string; font: string }[],
): HTMLCanvasElement {
  const dpr = window.devicePixelRatio || 1;
  const box = frame.getBoundingClientRect();
  const out = document.createElement('canvas');
  out.width = Math.round(box.width * dpr);
  out.height = Math.round(box.height * dpr);
  const ctx = out.getContext('2d');
  if (!ctx) return out;
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, out.width, out.height);
  for (const c of frame.querySelectorAll('canvas')) {
    const r = c.getBoundingClientRect();
    if (r.width === 0) continue;
    ctx.drawImage(c, (r.left - box.left) * dpr, (r.top - box.top) * dpr, r.width * dpr, r.height * dpr);
  }
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
