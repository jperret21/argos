/**
 * Field overlay layers (README 4.3 A47 `field_layers`; web/spec/04-viewer-and-image-tools.md
 * 2.2 rows 1.4 and 2.4 "Overlay drawing"): what each layer is, how it is drawn, which
 * marker a pointer is on, and where labels go without overlapping. Pure, tested.
 *
 * Shapes match the icons of the same layers (fixes 04 P18, P19) and the BRAND 6.8 role
 * frames: target circle, comparison square, check upright triangle; Gaia stars small
 * circles, variables large circles (suspected dashed), galaxies tilted ellipses (star-atlas
 * symbol), nebulae and clusters a circle with four outward ticks (a shape no other layer
 * uses), exoplanet hosts a dot with an orbit, other objects diamonds, VSP references a plus.
 * The selection is four corner brackets (a viewfinder) and a list's hover the same brackets
 * in the foreground ink, so neither borrows the target's circle. Sizes are CSS px (constant
 * at any zoom), from the Qt viewer's diameters (argos/ui/widgets/fits_viewer.py:205-231,
 * 748-830).
 */

import { formatDec, formatRA } from '../../format/astro';
import type { Point, Size } from './project';

/** Catalogue and set layers, in drawing order (bottom first). */
export const LAYER_IDS = [
  'stars',
  'other_objects',
  'galaxies',
  'nebulae_clusters',
  'exoplanets',
  'variables',
  'vsp',
  'selected',
] as const;
export type LayerId = (typeof LAYER_IDS)[number];

/** Rows of the Catalogue layers popover that are not marker layers. */
export type DisplayToggle = 'grid' | 'labels';

export type Role = 'target' | 'comparison' | 'check';
export const ROLES: readonly Role[] = ['target', 'comparison', 'check'];

/**
 * One marker of A47 (protocol.md "Layers (A47)"), in frame px of the REFERENCE solve (numpy
 * convention, un-rotated): the tracking transform (A48) moves it onto the frame on screen.
 */
export interface Marker {
  /** Stable within a generation. */
  id?: string;
  x: number;
  y: number;
  /** "" when Qt drew no label (generic survey ids are never labels). */
  label?: string | null;
  /** Qt's tooltip text, lines joined by \n. */
  tooltip?: string | null;
  kind?: string;
  /** The TargetStar key the star has (or would have) in the set. */
  key?: string | null;
  ra_hours?: number;
  dec_deg?: number;
  /** Gaia G (stars only): the display depth filters on it client-side. */
  g_mag?: number | null;
  /** VSX "suspected" variables are dashed. */
  suspected?: boolean | null;
  /** Selected set only. */
  role?: Role | string | null;
  detected?: boolean;
  /** Variables: the index A52 takes (`variable_index`), and VSX fields. */
  index?: number;
  name?: string | null;
  var_type?: string | null;
  mag_text?: string | null;
  period_d?: number | null;
  auid?: string | null;
  sep_arcmin?: number | null;
  bp_mag?: number | null;
  rp_mag?: number | null;
}

export type LayerMarkers = Partial<Record<LayerId, readonly Marker[]>>;

export interface LayerMeta {
  id: LayerId;
  /** Popover row label (03 W2 wording). */
  label: string;
  /** Icon id of the popover row (04 2.2). */
  icon: string;
  /** Section of the popover. */
  group: 'objects' | 'references';
  /** Shown automatically on the first solve of a field (03 2.4, Qt imaging_page.py:1735-1769). */
  autoShow: boolean;
  /** Hit-test priority, lower wins (Qt imaging_page.py:793-967, 04 2.4). */
  priority: number;
  /** Tooltip when the layer has nothing to say yet. */
  help: string;
}

export const LAYERS: Record<LayerId, LayerMeta> = {
  stars: { id: 'stars', label: 'Stars (Gaia DR3 + SIMBAD)', icon: 'field-stars', group: 'objects', autoShow: true, priority: 6, help: 'Gaia stars down to the display depth' },
  variables: { id: 'variables', label: 'Variables (VSX)', icon: 'variable-star', group: 'objects', autoShow: true, priority: 1, help: 'AAVSO VSX variables in the field; suspected ones dashed' },
  galaxies: { id: 'galaxies', label: 'Galaxies', icon: 'galaxy', group: 'objects', autoShow: true, priority: 4, help: 'Galaxies (SIMBAD)' },
  nebulae_clusters: { id: 'nebulae_clusters', label: 'Nebulae + clusters', icon: 'nebula', group: 'objects', autoShow: true, priority: 4, help: 'Nebulae and star clusters (SIMBAD)' },
  exoplanets: { id: 'exoplanets', label: 'Exoplanet hosts', icon: 'exoplanet', group: 'objects', autoShow: true, priority: 5, help: 'Stars with known exoplanets' },
  other_objects: { id: 'other_objects', label: 'Other objects', icon: 'other-objects', group: 'objects', autoShow: true, priority: 3, help: 'Other SIMBAD objects' },
  vsp: { id: 'vsp', label: 'VSP references, detected', icon: 'comparison-star', group: 'references', autoShow: false, priority: 2, help: 'AAVSO VSP comparison stars detected on the solved frame (the Candidates tab lists every VSP star of the frame)' },
  selected: { id: 'selected', label: 'Selected stars', icon: 'target-star', group: 'references', autoShow: true, priority: 0, help: 'Target, comparison and check stars of the set' },
};

export type Visibility = Record<LayerId | DisplayToggle, boolean>;

/** Before any field: everything the first solve shows, labels and VSP off (03 2.4). */
export function defaultVisibility(): Visibility {
  const v = { grid: true, labels: false } as Visibility;
  for (const id of LAYER_IDS) v[id] = LAYERS[id].autoShow;
  return v;
}

export function isVisibility(v: unknown): v is Partial<Visibility> {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) return false;
  return Object.values(v as Record<string, unknown>).every((x) => typeof x === 'boolean');
}

/** The Gaia display depth filters stars only (04 1.4 #11: galaxies and nebulae unaffected). */
export function passesDepth(layer: LayerId, m: Marker, gLimit: number | null): boolean {
  if (layer !== 'stars' || gLimit === null || !Number.isFinite(gLimit)) return true;
  return m.g_mag == null || !Number.isFinite(m.g_mag) || m.g_mag <= gLimit;
}

/** Stars shown at a depth (for the popover count of the Stars row). */
export function countWithin(markers: readonly Marker[] | undefined, gLimit: number | null): number {
  if (!markers) return 0;
  let n = 0;
  for (const m of markers) if (passesDepth('stars', m, gLimit)) n++;
  return n;
}

// -- Marker geometry (CSS px) ---------------------------------------------------------------

/** Radius of each layer's symbol, CSS px (Qt diameters / 2, 04 2.4). */
export const RADIUS: Record<Exclude<LayerId, 'selected'>, number> = {
  stars: 9,
  variables: 14,
  galaxies: 14,
  nebulae_clusters: 15,
  exoplanets: 13,
  other_objects: 12,
  vsp: 10,
};

/**
 * Role markers: the photometry aperture on screen, never smaller than the role's floor so the
 * set stands out of the catalogue circles (Qt draws the target 34 px and comparison / check
 * 30 px at 3 px, against variables 30 px at 2 px: fits_viewer.py:637, 803-807).
 */
export const ROLE_FLOOR: Record<Role, number> = { target: 17, comparison: 15, check: 15 };

export function roleRadius(aperturePx: number | null | undefined, scale: number, role: Role = 'target'): number {
  const ap = aperturePx && aperturePx > 0 && scale > 0 ? aperturePx * scale : 0;
  return Math.min(64, Math.max(ROLE_FLOOR[role], ap));
}

/** Variables drawn smaller when this many are on screen (they would hide the image). */
export const DENSE_VARIABLES = 60;
export const DENSE_VARIABLE_RADIUS = 9;

const f = (v: number) => (Math.round(v * 10) / 10).toString();

/** A circle as two arcs (one path can hold thousands, 1 DOM node per layer). */
export function circlePath(x: number, y: number, r: number): string {
  return `M${f(x - r)} ${f(y)}a${f(r)} ${f(r)} 0 1 0 ${f(2 * r)} 0a${f(r)} ${f(r)} 0 1 0 ${f(-2 * r)} 0`;
}

/** Square of the same visual weight as a circle of radius r (area-matched, 0.886 r half-side). */
export function squarePath(x: number, y: number, r: number): string {
  const h = r * 0.886;
  return `M${f(x - h)} ${f(y - h)}h${f(2 * h)}v${f(2 * h)}h${f(-2 * h)}z`;
}

/** Upright equilateral triangle (point up on screen, whatever the display rotation). */
export function trianglePath(x: number, y: number, r: number): string {
  const t = r * 1.347;
  return `M${f(x)} ${f(y - t)}L${f(x + t * 0.866)} ${f(y + t * 0.5)}L${f(x - t * 0.866)} ${f(y + t * 0.5)}z`;
}

export function diamondPath(x: number, y: number, r: number): string {
  return `M${f(x)} ${f(y - r)}L${f(x + r)} ${f(y)}L${f(x)} ${f(y + r)}L${f(x - r)} ${f(y)}z`;
}

/** Four corner brackets around (x, y) at half-size r (the selection, a list's hover). */
export function bracketPath(x: number, y: number, r: number): string {
  const l = Math.max(4, r * 0.4);
  const c = [
    [-1, -1],
    [1, -1],
    [1, 1],
    [-1, 1],
  ];
  return c
    .map(([sx, sy]) => `M${f(x + sx * r)} ${f(y + sy * (r - l))}V${f(y + sy * r)}H${f(x + sx * (r - l))}`)
    .join('');
}

/** A circle with four short outward ticks (nebulae and clusters). */
export function nebulaPath(x: number, y: number, r: number): string {
  const t = 4;
  return `${circlePath(x, y, r)}M${f(x)} ${f(y - r)}v${f(-t)}M${f(x + r)} ${f(y)}h${f(t)}M${f(x)} ${f(y + r)}v${f(t)}M${f(x - r)} ${f(y)}h${f(-t)}`;
}

export function plusPath(x: number, y: number, r: number): string {
  return `M${f(x - r)} ${f(y)}h${f(2 * r)}M${f(x)} ${f(y - r)}v${f(2 * r)}`;
}

/** Ellipse tilted by `deg` (screen, clockwise), drawn with two arcs. */
export function ellipsePath(x: number, y: number, rx: number, ry: number, deg: number): string {
  const a = (deg * Math.PI) / 180;
  const ux = Math.cos(a) * rx;
  const uy = Math.sin(a) * rx;
  return `M${f(x - ux)} ${f(y - uy)}a${f(rx)} ${f(ry)} ${f(deg)} 1 0 ${f(2 * ux)} ${f(2 * uy)}a${f(rx)} ${f(ry)} ${f(deg)} 1 0 ${f(-2 * ux)} ${f(-2 * uy)}`;
}

export function rolePath(role: Role, x: number, y: number, r: number): string {
  return role === 'target' ? circlePath(x, y, r) : role === 'comparison' ? squarePath(x, y, r) : trianglePath(x, y, r);
}

/** The symbol of a catalogue layer at (x, y), screen px (`r` overrides the layer's radius). */
export function layerPath(layer: Exclude<LayerId, 'selected'>, x: number, y: number, r: number = RADIUS[layer]): string {
  switch (layer) {
    case 'galaxies':
      return ellipsePath(x, y, r, r * 0.5, -30);
    case 'exoplanets':
      // A host dot ring and its orbit (the `exoplanet` icon).
      return `${circlePath(x, y, 4)}${ellipsePath(x, y, r, r * 0.42, -20)}`;
    case 'other_objects':
      return diamondPath(x, y, r);
    case 'vsp':
      return plusPath(x, y, r);
    case 'nebulae_clusters':
      return nebulaPath(x, y, r);
    default:
      return circlePath(x, y, r);
  }
}

// -- Hit test --------------------------------------------------------------------------------

/** A marker placed on the stage. */
export interface Placed {
  layer: LayerId;
  index: number;
  marker: Marker;
  /** Stage px. */
  sx: number;
  sy: number;
}

/**
 * The marker under the pointer: within `tol` CSS px of its centre (04 2.4: 10 screen px,
 * fixes P9), the highest-priority layer first, then the nearest. Null when none.
 */
export function hitTest(placed: readonly Placed[], p: Point, tol = 10): Placed | null {
  let best: Placed | null = null;
  let bestPrio = Infinity;
  let bestD = Infinity;
  const t2 = tol * tol;
  for (const m of placed) {
    const dx = m.sx - p.x;
    const dy = m.sy - p.y;
    const d = dx * dx + dy * dy;
    if (d > t2) continue;
    const prio = LAYERS[m.layer].priority;
    if (prio < bestPrio || (prio === bestPrio && d < bestD)) {
      best = m;
      bestPrio = prio;
      bestD = d;
    }
  }
  return best;
}

// -- Label placement (screen px, after each zoom: fixes 04 P27) -----------------------------

/** Plex Mono 11 px advance (0.6 em) and the label box height. */
export const LABEL_CHAR_W = 6.6;
export const LABEL_H = 13;

export interface LabelRequest {
  id: string;
  text: string;
  /** Anchor (the marker centre) and the marker radius, stage px. */
  x: number;
  y: number;
  r: number;
}

export interface PlacedLabel {
  id: string;
  text: string;
  /** Text baseline origin. */
  x: number;
  y: number;
  anchor: 'start' | 'end' | 'middle';
}

export interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

const overlaps = (a: Box, b: Box) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

/**
 * Greedy de-overlap: requests in priority order (the caller sorts), each tries right, left,
 * above, below its marker and takes the first spot that stays on the stage and touches no
 * label already placed; a label with no free spot is dropped (its marker still shows and
 * its tooltip still names it). At most `max` labels.
 */
export function placeLabels(reqs: readonly LabelRequest[], stage: Size, max = 250, obstacles: readonly Box[] = []): PlacedLabel[] {
  // The HUD (chips, compass, scale bar, readout) is an obstacle like any placed label.
  const placed: Box[] = [...obstacles];
  const out: PlacedLabel[] = [];
  const seen: { text: string; x: number; y: number }[] = [];
  for (const q of reqs) {
    if (out.length >= max) break;
    const text = q.text.trim();
    if (!text) continue;
    // One source in two layers (the set's target is also a VSX variable): one label.
    if (seen.some((o) => o.text === text && Math.abs(o.x - q.x) < 4 && Math.abs(o.y - q.y) < 4)) continue;
    seen.push({ text, x: q.x, y: q.y });
    const w = text.length * LABEL_CHAR_W + 2;
    const gap = q.r + 4;
    const cands: { box: Box; x: number; y: number; anchor: PlacedLabel['anchor'] }[] = [
      { box: { x0: q.x + gap, y0: q.y - LABEL_H / 2, x1: q.x + gap + w, y1: q.y + LABEL_H / 2 }, x: q.x + gap, y: q.y + 4, anchor: 'start' },
      { box: { x0: q.x - gap - w, y0: q.y - LABEL_H / 2, x1: q.x - gap, y1: q.y + LABEL_H / 2 }, x: q.x - gap, y: q.y + 4, anchor: 'end' },
      { box: { x0: q.x - w / 2, y0: q.y - gap - LABEL_H, x1: q.x + w / 2, y1: q.y - gap }, x: q.x, y: q.y - gap - 3, anchor: 'middle' },
      { box: { x0: q.x - w / 2, y0: q.y + gap, x1: q.x + w / 2, y1: q.y + gap + LABEL_H }, x: q.x, y: q.y + gap + LABEL_H - 3, anchor: 'middle' },
    ];
    for (const c of cands) {
      const b = c.box;
      if (b.x0 < 0 || b.y0 < 0 || b.x1 > stage.width || b.y1 > stage.height) continue;
      if (placed.some((o) => overlaps(o, b))) continue;
      placed.push(b);
      out.push({ id: q.id, text, x: c.x, y: c.y, anchor: c.anchor });
      break;
    }
  }
  return out;
}

/**
 * Qt's label rule (`_short_marker_label`, fits_viewer.py:46-51): a name longer than 18
 * characters becomes its first 11 + "…" + its last 6.
 */
export function shortLabel(text: string): string {
  const t = text.trim();
  return t.length > 18 ? `${t.slice(0, 11)}…${t.slice(-6)}` : t;
}

/** The marker's short text for its label: the server's label (generic ids already blanked). */
export function markerLabel(m: Marker): string {
  return shortLabel(m.label ?? '');
}

/**
 * A grid label in the UI's coordinate format at the grid's precision (BRAND 5): the server
 * sends Qt's compact "19h28m00.0s" / "+42°30'00.0\"" text; seconds that are zero are dropped
 * ("19h 28m", "+42° 30′").
 */
export function gridLabelText(text: string, axis: 'ra' | 'dec' | string | undefined): string {
  const nums = (text.match(/\d+(?:\.\d+)?/g) ?? []).map(Number);
  if (nums.length < 2) return text;
  const neg = /^[-−]/.test(text.trim());
  const [a, b, c = 0] = nums;
  if (axis === 'ra' || /h/.test(text)) {
    const hours = a + b / 60 + c / 3600;
    const full = formatRA(hours);
    return Math.round(c) % 60 === 0 ? full.replace(/ \d+\.\ds$/, '') : full.replace(/\.\ds$/, 's');
  }
  const deg = (neg ? -1 : 1) * (a + b / 60 + c / 3600);
  const full = formatDec(deg);
  return Math.round(c) % 60 === 0 ? full.replace(/ \d+″$/, '') : full;
}

/** One fact of a marker's identity popover. */
export interface TipRow {
  k: string;
  v: string;
}

/**
 * The identity popover of a marker (BRAND 7): the star's name as the title, the facts as a key
 * and value grid, RA and Dec in the UI's format, empty rows left out. Built from the server's
 * tooltip lines ("key␣␣value") and the marker's own fields.
 */
export function tipContent(layer: LayerId, m: Marker): { title: string; kind: string; rows: TipRow[] } {
  const lines = (m.tooltip ?? '').split('\n').map((l) => l.trim()).filter(Boolean);
  const title = (m.name || m.label || m.auid || (m as { source_id?: string }).source_id || lines[1] || lines[0] || '').trim();
  const rows: TipRow[] = [];
  for (const line of lines.slice(1)) {
    if (line === title || /^RA\s/.test(line)) continue;
    const i = line.indexOf('  ');
    if (i > 0) {
      const k = line.slice(0, i).trim();
      const v = line.slice(i).trim();
      if (v && v !== '—' && !(k.startsWith('Gaia DR3 source') && v === title)) rows.push({ k, v });
    } else if (/^AUID\s/.test(line)) {
      rows.push({ k: 'AUID', v: line.slice(5).trim() });
    } else if (line !== lines[0]) {
      rows.push({ k: '', v: line });
    }
  }
  if (typeof m.ra_hours === 'number' && typeof m.dec_deg === 'number') {
    rows.push({ k: 'RA', v: formatRA(m.ra_hours) }, { k: 'Dec', v: formatDec(m.dec_deg) });
  }
  return { title: title || LAYERS[layer].label, kind: lines[0] ?? LAYERS[layer].label, rows };
}

/** Stable id of a marker within its layer. */
export function markerId(layer: LayerId, index: number, m: Marker): string {
  return m.id ? `${layer}:${m.id}` : `${layer}#${index}`;
}

/** The role of a set marker, when it is one of the three. */
export function asRole(v: unknown): Role | null {
  return v === 'target' || v === 'comparison' || v === 'check' ? v : null;
}
