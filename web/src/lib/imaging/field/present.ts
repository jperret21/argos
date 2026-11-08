/**
 * Words and places of the field UI, as data (web/spec/03-observe-page.md 2.4 "Field states",
 * 04 2.3 star card; PROPOSAL 9 motion rules). Pure, tested.
 */

import { fixed, MINUS } from '../../format/number';
import type { Point, Size } from '../../viewer/overlay/project';
import type { CatalogState, FieldState, FieldTransform, Selection, SelectionKind, TargetSet } from './types';

// -- The field chip of the HUD (03 2.4) --------------------------------------------------------

export interface FieldChip {
  text: string;
  /** neutral: a state; busy: a spinner leads; warn: --warning edge and the word. */
  tone: 'neutral' | 'busy' | 'warn';
  /** Tooltip: what the chip summarises. */
  title: string;
}

const signedDeg = (v: number) => `${v < 0 ? MINUS : ''}${fixed(Math.abs(v), 1)}°`;

/**
 * "Field not identified" · "Identifying field…" · "Identified · 1.19″/px · PA 12.3° · Δtarget
 * 2.4′" (+ " · Auto", + " · Catalogues…") · "Identified · tracking lost" · "Identification
 * failed, last solution kept" · "Field moved: identify again". Text, never colour alone.
 */
export function fieldChip(field: FieldState | null, catalog: CatalogState | null = null, transform: FieldTransform | null = null): FieldChip {
  const s = field?.state ?? 'none';
  const auto = field?.auto ? ' · Auto' : '';
  if (s === 'solving') return { text: `Identifying field…${auto}`, tone: 'busy', title: 'ASTAP is solving the frame on screen' };
  if (s === 'invalidated') return { text: 'Field moved: identify again', tone: 'warn', title: field?.message ?? 'The field was cleared' };
  const sol = field?.solution;
  if (s === 'failed' && sol) return { text: 'Identification failed, last solution kept', tone: 'warn', title: field?.message ?? field?.last_attempt?.message ?? '' };
  if (s === 'failed') return { text: `Field not identified${auto}`, tone: 'warn', title: field?.message ?? field?.last_attempt?.message ?? 'The last attempt failed' };
  if (s !== 'solved' || !sol) return { text: `Field not identified${auto}`, tone: 'neutral', title: 'Identify the field (S) to see catalogues and give stars roles' };
  if (transform?.tracking === 'lost') {
    return {
      text: `Identified · tracking lost${auto}`,
      tone: 'warn',
      title: 'No anchor star found on the newest frames: the overlays stand where the field was last seen. Identify the field again (S) if it does not come back.',
    };
  }
  const parts: string[] = ['Identified'];
  if (sol.scale_arcsec_px != null) parts.push(`${fixed(sol.scale_arcsec_px, 2)}″/px`);
  if (sol.rotation_deg != null) parts.push(`PA ${signedDeg(sol.rotation_deg)}`);
  if (sol.delta_target_arcmin != null) parts.push(`Δtarget ${fixed(sol.delta_target_arcmin, 1)}′`);
  const fetching = catalog?.state === 'fetching' ? ' · Catalogues…' : '';
  const pa =
    sol.rotation_deg != null
      ? '\nPA: the position angle of the sensor frame as ASTAP reports it (CROTA2, east of north), not of the display, which the auto rotation may turn.'
      : '';
  return {
    text: `${parts.join(' · ')}${auto}${fetching}`,
    tone: fetching ? 'busy' : 'neutral',
    title: `${sol.summary ?? 'Plate solution of the field'}${pa}`,
  };
}

/** Why Identify field cannot act now (03 2.4), or null. */
export function identifyReason(hasFrame: boolean, field: FieldState | null): string | null {
  if (!hasFrame) return 'No frame yet: take a frame or open a FITS image first';
  if (field?.state === 'solving') return 'A solve is running';
  return null;
}

/**
 * M50, pre-checks only (03 1.14 #1-#3, replacing the three Qt boxes of `_on_rerun_subs`,
 * imaging_page.py:2262-2273, in their order): why photometry on saved subs cannot start, or
 * null. The Re-run button itself comes with live photometry and Review (W5, W7); it shows
 * this reason as its unavailable reason.
 */
export function photometryProblem(field: FieldState | null, targets: TargetSet | null): string | null {
  const s = field?.state;
  if (!field?.solution || !(s === 'solved' || s === 'failed' || s === 'solving')) return 'identify the field first';
  const stars = targets?.stars ?? [];
  if (!stars.some((x) => x.role === 'target')) return 'assign a target star first';
  if (!stars.some((x) => x.role === 'comparison')) {
    return 'the target set has no comparison stars: identify the field and wait for the catalogue, or assign Comparison from the image';
  }
  return null;
}

// -- Star card --------------------------------------------------------------------------------

/** The icon of what was clicked (the layer's icon: same shape as its marker). */
export function kindIcon(kind: SelectionKind | string | null | undefined): string {
  switch (kind) {
    case 'target':
      return 'target-star';
    case 'variable':
      return 'variable-star';
    case 'vsp':
      return 'comparison-star';
    case 'simbad':
      return 'other-objects';
    case 'deep_sky':
      return 'galaxy';
    case 'exoplanet':
      return 'exoplanet';
    case 'gaia':
    case 'point_identity':
      return 'field-stars';
    default:
      return 'crosshair';
  }
}

/** GCVS / VSX variability types in words (the card's facts line; the code stays in the details). */
const VSX_TYPES: [RegExp, string][] = [
  [/^EA/, 'eclipsing (Algol)'],
  [/^EB/, 'eclipsing (β Lyrae)'],
  [/^EW/, 'eclipsing (W UMa)'],
  [/^E/, 'eclipsing'],
  [/^RR/, 'RR Lyrae'],
  [/^HADS/, 'high-amplitude δ Scuti'],
  [/^DSCT/, 'δ Scuti'],
  [/^SXPHE/, 'SX Phoenicis'],
  [/^GDOR/, 'γ Doradus'],
  [/^(DCEP|CEP|CW)/, 'Cepheid'],
  [/^M$/, 'Mira'],
  [/^SR/, 'semi-regular'],
  [/^L/, 'irregular'],
  [/^ROT/, 'rotational'],
  [/^BY/, 'BY Draconis'],
  [/^RS/, 'RS CVn'],
  [/^ELL/, 'ellipsoidal'],
  [/^(UG|NL|CV)/, 'cataclysmic'],
  [/^(YSO|INS|IN)/, 'young stellar object'],
  [/^ACV/, 'α² CVn'],
  [/^(VAR|S$|MISC)/, 'unclassified variable'],
];

export function vsxTypeWord(type: string | null | undefined): string | null {
  const t = (type ?? '').trim().toUpperCase();
  if (!t) return null;
  const first = t.split(/[/|:+ ]/)[0];
  for (const [re, word] of VSX_TYPES) if (re.test(first)) return word;
  return null;
}

const KIND_WORD: Partial<Record<SelectionKind, string>> = {
  target: 'in the set',
  variable: 'VSX variable',
  vsp: 'VSP comparison',
  simbad: 'SIMBAD object',
  deep_sky: 'deep-sky object',
  exoplanet: 'exoplanet host',
  gaia: 'Gaia DR3 star',
  point_identity: 'identified point',
  measured: 'measured star',
};

/**
 * The star card's two lines (BRAND 7, PROPOSAL 3.1): the identity alone as the title (the
 * server's "Kind · name" without the kind) and a facts line built from the fields, never raw
 * rows: "V 7.90 · B−V 0.69 · 27.4′ from target · VSP comparison". A star listed by two
 * catalogues names both ("KIC 7201168 · VSP 000-BJW-666").
 */
export function cardText(
  sel: Selection,
  opts: { target?: { ra_hours: number; dec_deg: number } | null; alias?: string | null } = {},
): { title: string; facts: string } {
  const p = sel.pending_star;
  const parts = sel.title.split(' · ');
  const bare = parts.length > 1 ? parts.slice(1).join(' · ') : sel.title;
  const named = p?.name?.trim() || bare;
  const title = opts.alias && opts.alias !== named ? `${named} · ${opts.alias}` : named;
  const row = (k: string) => sel.rows.find((r) => r.key === k)?.value ?? null;
  const facts: string[] = [];
  const mags = p?.mags ?? {};
  const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
  const v = num(mags.V);
  const b = num(mags.B);
  const g = num(mags.G);
  if (v !== null) facts.push(`V ${fixed(v, 2)}`);
  else if (g !== null) facts.push(`G ${fixed(g, 2)}`);
  else if (sel.kind === 'variable' && row('Max')) facts.push(`${row('Max')} – ${row('Min') ?? '?'}`);
  if (v !== null && b !== null) facts.push(`B−V ${fixed(b - v, 2)}`);
  const m = sel.measurement;
  if (sel.kind === 'measured' && m) {
    if (m.fwhm_arcsec != null) facts.push(`FWHM ${fixed(m.fwhm_arcsec, 1)}″`);
    if (m.snr != null) facts.push(`SNR ${fixed(m.snr, 0)}`);
  }
  const t = opts.target;
  const ra = p?.ra_hours ?? (typeof p?.ra_deg === 'number' ? p.ra_deg / 15 : null);
  if (t && p && typeof ra === 'number' && typeof p.dec_deg === 'number' && sel.role !== 'target') {
    const d2r = Math.PI / 180;
    const c = Math.sin(p.dec_deg * d2r) * Math.sin(t.dec_deg * d2r) + Math.cos(p.dec_deg * d2r) * Math.cos(t.dec_deg * d2r) * Math.cos((ra - t.ra_hours) * 15 * d2r);
    const sep = (Math.acos(Math.min(1, Math.max(-1, c))) / d2r) * 60;
    facts.push(`${fixed(sep, 1)}′ from target`);
  }
  const type = sel.kind === 'variable' ? vsxTypeWord(row('Type')) : null;
  // The pressed role button already says the role: the kind only for a star with none.
  const word = sel.role ? (facts.length ? null : `${sel.role} of the set`) : type ? `${type} (VSX)` : (KIND_WORD[sel.kind] ?? null);
  if (word) facts.push(word);
  return { title, facts: facts.join(' · ') };
}

/** -1: beside the star; 0..3: top-left, top-right, bottom-left, bottom-right. */
export type Dock = -1 | 0 | 1 | 2 | 3;
export const CORNER_NAMES = ['top left', 'top right', 'bottom left', 'bottom right'] as const;

export function isDock(v: unknown): v is Dock {
  return v === -1 || v === 0 || v === 1 || v === 2 || v === 3;
}

/** Space kept free for the HUD chip row (top) and the cursor readout (bottom right). */
export interface Margins {
  top: number;
  bottom: number;
  side: number;
}
export const CARD_MARGINS: Margins = { top: 44, bottom: 12, side: 12 };

/** Beside the star, flipped to stay inside the stage; never over the star itself. */
export function besideStar(at: { x: number; y: number; r: number }, card: Size, bounds: Size, m: Margins = CARD_MARGINS): Point {
  const gap = at.r + 14;
  const right = at.x + gap;
  const x = right + card.width > bounds.width - m.side ? at.x - gap - card.width : right;
  const y = at.y - card.height / 2;
  return {
    x: Math.max(m.side, Math.min(bounds.width - m.side - card.width, x)),
    y: Math.max(m.top, Math.min(bounds.height - m.bottom - card.height, y)),
  };
}

export function cornerPos(c: 0 | 1 | 2 | 3, card: Size, bounds: Size, m: Margins = CARD_MARGINS): Point {
  return {
    x: c % 2 === 0 ? m.side : Math.max(m.side, bounds.width - card.width - m.side),
    y: c < 2 ? m.top : Math.max(m.top, bounds.height - card.height - m.bottom),
  };
}

export function nearestCorner(p: Point, card: Size, bounds: Size, m: Margins = CARD_MARGINS): 0 | 1 | 2 | 3 {
  let best: 0 | 1 | 2 | 3 = 2;
  let d = Infinity;
  for (const c of [0, 1, 2, 3] as const) {
    const q = cornerPos(c, card, bounds, m);
    const dd = Math.hypot(q.x - p.x, q.y - p.y);
    if (dd < d) {
      d = dd;
      best = c;
    }
  }
  return best;
}

/** Arrow keys on the card's grip move between corners; Home puts it back beside the star. */
export function dockKey(dock: Dock, key: string): Dock | null {
  if (key === 'Home') return -1;
  const c = dock === -1 ? 2 : dock;
  switch (key) {
    case 'ArrowLeft':
      return c === 1 ? 0 : c === 3 ? 2 : c;
    case 'ArrowRight':
      return c === 0 ? 1 : c === 2 ? 3 : c;
    case 'ArrowUp':
      return c === 2 ? 0 : c === 3 ? 1 : c;
    case 'ArrowDown':
      return c === 0 ? 2 : c === 1 ? 3 : c;
    default:
      return null;
  }
}
