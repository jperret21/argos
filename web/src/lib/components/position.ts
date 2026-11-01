/**
 * Placement of floating layers (popovers, menus, select lists) next to their
 * anchor, inside the viewport: flip to the other side when there is no room,
 * then clamp. Pure, so it is tested without a browser.
 */

export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

export type Side = 'bottom' | 'top' | 'right' | 'left';
export type Align = 'start' | 'end' | 'center';
export type Placement = Side | `${Side}-${Exclude<Align, 'center'>}`;

export interface PlaceOptions {
  anchor: Box;
  floating: { width: number; height: number };
  viewport: { width: number; height: number };
  placement?: Placement;
  /** Distance between anchor and layer. */
  gap?: number;
  /** Minimum distance to the viewport edges. */
  margin?: number;
}

export interface PlaceResult {
  x: number;
  y: number;
  side: Side;
}

const OPPOSITE: Record<Side, Side> = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' };

export function placeFloating(o: PlaceOptions): PlaceResult {
  const gap = o.gap ?? 4;
  const margin = o.margin ?? 8;
  const [sideRaw, alignRaw] = (o.placement ?? 'bottom-start').split('-') as [Side, Align | undefined];
  const align: Align = alignRaw ?? 'center';
  const a = o.anchor;
  const f = o.floating;
  const vw = o.viewport.width;
  const vh = o.viewport.height;
  const room: Record<Side, number> = {
    bottom: vh - margin - (a.top + a.height + gap),
    top: a.top - gap - margin,
    right: vw - margin - (a.left + a.width + gap),
    left: a.left - gap - margin,
  };
  const need = (s: Side) => (s === 'top' || s === 'bottom' ? f.height : f.width);
  let side = sideRaw;
  if (room[side] < need(side) && room[OPPOSITE[side]] > room[side]) side = OPPOSITE[side];

  let x: number;
  let y: number;
  if (side === 'top' || side === 'bottom') {
    y = side === 'bottom' ? a.top + a.height + gap : a.top - gap - f.height;
    x = align === 'start' ? a.left : align === 'end' ? a.left + a.width - f.width : a.left + a.width / 2 - f.width / 2;
  } else {
    x = side === 'right' ? a.left + a.width + gap : a.left - gap - f.width;
    y = align === 'start' ? a.top : align === 'end' ? a.top + a.height - f.height : a.top + a.height / 2 - f.height / 2;
  }
  x = Math.min(Math.max(margin, x), Math.max(margin, vw - margin - f.width));
  y = Math.min(Math.max(margin, y), Math.max(margin, vh - margin - f.height));
  return { x: Math.round(x), y: Math.round(y), side };
}
