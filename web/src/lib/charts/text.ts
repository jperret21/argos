/**
 * Canvas text that never inherits a stale alignment.
 *
 * uPlot (and any other drawing on a shared context) leaves its own textAlign
 * and textBaseline on the context: an axis draws with `center`, and the next
 * label drawn by a plugin lands half its width to the left (found by the
 * workspace lab, web/lab/PROPOSAL.md section 6). Every label drawn by
 * web/src/lib therefore goes through these helpers, which always set both.
 */

export type TextAlign = CanvasTextAlign;
export type TextBaseline = CanvasTextBaseline;

/** The context state a label needs; everything is set on every call. */
export interface TextStyle {
  /** A canvas font string (ink.ts monoFont / uiFont). */
  font: string;
  /** A resolved colour (ink.ts Ink, or its rgba() string). */
  fill: string | { toString(): string };
  align: TextAlign;
  baseline: TextBaseline;
}

/** The subset of CanvasRenderingContext2D the helpers use (a fake in tests). */
export type TextContext = Pick<
  CanvasRenderingContext2D,
  'font' | 'fillStyle' | 'textAlign' | 'textBaseline' | 'fillText' | 'measureText'
>;

/** Apply a full text style to the context: font, fill, align and baseline. */
export function setTextStyle(ctx: TextContext, style: TextStyle): void {
  ctx.font = style.font;
  ctx.fillStyle = String(style.fill);
  ctx.textAlign = style.align;
  ctx.textBaseline = style.baseline;
}

/** Draw one label with an explicit style (device pixels, like every canvas call). */
export function drawText(ctx: TextContext, text: string, x: number, y: number, style: TextStyle): void {
  setTextStyle(ctx, style);
  ctx.fillText(text, x, y);
}

/** Width of a label in the given font (device pixels). */
export function measureText(ctx: TextContext, text: string, font: string): number {
  ctx.font = font;
  return ctx.measureText(text).width;
}
