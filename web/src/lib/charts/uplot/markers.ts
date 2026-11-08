/**
 * Shape-coded markers for canvas plots (BRAND 2 principle 6, 10). Promoted
 * from src/lab/charts/core/uplot/markers.ts (the shapes; the light-curve
 * marker plugin comes with wave 5).
 *
 * Role shapes: target circle, comparison square, check triangle, all of equal
 * area so no role looks heavier; `dot` is a neutral sample (V-curve,
 * conditions). Shapes are added to a shared Path2D (one fill or stroke call
 * whatever the point count); never closePath() on a shared Path2D, it is
 * quadratic in Chromium (lab/research/stack-capabilities 3.1).
 */

export type Shape = 'circle' | 'square' | 'triangle' | 'dot';

type PathLike = Pick<Path2D, 'moveTo' | 'lineTo' | 'arc' | 'rect'>;

export function addShape(p: PathLike, shape: Shape, x: number, y: number, r: number): void {
  if (shape === 'circle' || shape === 'dot') {
    p.moveTo(x + r, y);
    p.arc(x, y, r, 0, Math.PI * 2);
  } else if (shape === 'square') {
    const s = r * 0.886; // same area as the circle
    p.rect(x - s, y - s, 2 * s, 2 * s);
  } else {
    const s = r * 1.347; // same area, centroid on the point
    p.moveTo(x, y - s);
    p.lineTo(x + s * 0.866, y + s * 0.5);
    p.lineTo(x - s * 0.866, y + s * 0.5);
    p.lineTo(x, y - s); // explicit, instead of closePath()
  }
}

/** A vertical error bar with 3 px caps, snapped to the pixel grid (device px). */
export function addErrorBar(p: PathLike, x: number, yLo: number, yHi: number, cap: number): void {
  const xr = Math.round(x) + 0.5;
  p.moveTo(xr, yLo);
  p.lineTo(xr, yHi);
  p.moveTo(xr - cap, Math.round(yLo) + 0.5);
  p.lineTo(xr + cap, Math.round(yLo) + 0.5);
  p.moveTo(xr - cap, Math.round(yHi) + 0.5);
  p.lineTo(xr + cap, Math.round(yHi) + 0.5);
}
