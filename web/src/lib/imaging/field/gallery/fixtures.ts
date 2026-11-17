/**
 * Deterministic synthetic field for the wave 4 gallery (development only): a portrait frame
 * (540 × 960, turned landscape by the display) with Gaussian stars on a noisy sky, the A47
 * layers of that field (reference-solve positions), a small tracking transform (the frame's
 * stars are drawn where the transform puts them, so the overlay only lines up when it is
 * applied), candidates, a target set and selections in each state. Not a real field; names
 * are synthetic.
 */

import type { DecodedFrame } from '../../../api/frames';
import type { Marker } from '../../../viewer/overlay/layers';
import { applyTransform } from '../../../viewer/overlay/project';
import type { Candidate, FieldLayers, FieldState, FieldTransform, SelectionEvent, TargetSet, TargetStar } from '../types';

export const W = 540;
export const H = 960;

function prng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const TRANSFORM: FieldTransform = { generation: 4, frame_seq: 212, dx: 5.5, dy: -3.25, rot_deg: 0.6, cx: W / 2, cy: H / 2, anchors: 4, residual_px: 0.21, anchor_source: 'target_set', lost_frames: 0 };

interface Src {
  x: number;
  y: number;
  g: number;
}

const rnd = prng(20261108);
const field: Src[] = Array.from({ length: 260 }, () => ({ x: 6 + rnd() * (W - 12), y: 6 + rnd() * (H - 12), g: 8.5 + 9 * Math.pow(rnd(), 0.55) }));

/** Named positions (reference px). */
export const TARGET = { x: 292, y: 452, g: 7.9 };
const COMPS = [
  { key: 'c101', auid: '000-BBC-101', label: '84', x: 210, y: 380, g: 8.6, v: 8.42, bv: 0.31, dbv: 0.05, sep: 4.1, peak: 41203, snr: 512, sat: false, nbr: 0, role: 'comparison' },
  { key: 'c102', auid: '000-BBC-102', label: '91', x: 360, y: 610, g: 9.3, v: 9.11, bv: 0.52, dbv: 0.26, sep: 7.9, peak: 23950, snr: 388, sat: false, nbr: 0, role: 'comparison' },
  { key: 'c103', auid: '000-BBC-103', label: '95', x: 150, y: 700, g: 9.7, v: 9.52, bv: 0.71, dbv: 0.45, sep: 11.6, peak: 16110, snr: 301, sat: false, nbr: 1, role: 'comparison' },
  { key: 'k104', auid: '000-BBC-104', label: '102', x: 420, y: 250, g: 10.4, v: 10.2, bv: 0.36, dbv: 0.1, sep: 9.3, peak: 8420, snr: 190, sat: false, nbr: 0, role: 'check' },
  { key: 'c105', auid: '000-BBC-105', label: '73', x: 95, y: 220, g: 7.4, v: 7.31, bv: 0.12, dbv: -0.14, sep: 14.2, peak: 65535, snr: null, sat: true, nbr: 0, role: null },
  { key: 'c106', auid: '000-BBC-106', label: '104', x: 470, y: 820, g: 10.6, v: 10.41, bv: 0.29, dbv: 0.03, sep: 27.4, peak: 6900, snr: 151, sat: false, nbr: 0, role: null },
  { key: 'c107', auid: '000-BBC-107', label: '88', x: 330, y: 150, g: 8.9, v: 8.83, bv: 0.4, dbv: 0.14, sep: 12.8, peak: 52800, snr: 470, sat: true, nbr: 2, role: null },
  { key: 'c108', auid: null, label: '110', x: 60, y: 520, g: 11.2, v: 11.02, bv: null, dbv: null, sep: 9.8, peak: 3910, snr: 92, sat: false, nbr: 0, role: null },
] as const;

const VARS = [
  { x: TARGET.x, y: TARGET.y, name: 'RR Lyr', var_type: 'RRAB', mag_text: '7.06 – 8.12 V', period_d: 0.566868, sep: 0.2, suspected: false },
  { x: 120, y: 470, name: 'V0123 Lyr', var_type: 'EA', mag_text: '11.2 – 12.0 V', period_d: 2.345, sep: 7.1, suspected: false },
  { x: 440, y: 520, name: 'NSV 11960', var_type: 'VAR', mag_text: '12.4 – 12.9 p', period_d: null, sep: 6.4, suspected: true },
];

const all: Src[] = [...field, TARGET, ...COMPS.map((c) => ({ x: c.x, y: c.y, g: c.g })), ...VARS.slice(1).map((v) => ({ x: v.x, y: v.y, g: 11.5 }))];

/** The frame on screen: every source where the tracking transform puts it. */
export function syntheticFrame(seq = 212): DecodedFrame {
  const px = new Uint16Array(W * H);
  const noise = prng(7);
  for (let i = 0; i < px.length; i++) px[i] = 1800 + Math.round((noise() + noise() + noise() - 1.5) * 14);
  const sigma = 1.7;
  for (const s of all) {
    const p = applyTransform(TRANSFORM, s.x, s.y);
    const peak = Math.min(70000, 62000 * Math.pow(10, -0.4 * (s.g - 7.6)));
    const r = Math.ceil(sigma * 4);
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        const x = Math.round(p.x) + dx;
        const y = Math.round(p.y) + dy;
        if (x < 0 || y < 0 || x >= W || y >= H) continue;
        const ex = x - p.x;
        const ey = y - p.y;
        const v = peak * Math.exp(-(ex * ex + ey * ey) / (2 * sigma * sigma));
        const i = y * W + x;
        px[i] = Math.min(65535, px[i] + Math.round(v));
      }
    }
  }
  return {
    header: {
      seq,
      width: W,
      height: H,
      channels: 1,
      dtype: 'uint16',
      pixel_offset: 0,
      exposure_s: 2,
      timestamp: '2026-11-08T22:40:00Z',
      source: 'file',
      stats: { min: 1750, max: 65535, median: 1800, mad: 9, mean: 1830 },
    },
    pixels: px,
    byteLength: px.byteLength,
  };
}

const m = (x: number, y: number, extra: Partial<Marker> = {}): Marker => ({ x, y, label: '', tooltip: '', ...extra });

const stars: Marker[] = field.map((s, i) =>
  m(s.x, s.y, { id: `g${i}`, kind: 'gaia', g_mag: Math.round(s.g * 100) / 100, bp_mag: s.g + 0.4, rp_mag: s.g - 0.3, tooltip: `Gaia DR3 star\nG ${s.g.toFixed(2)}`, detected: s.g < 15 }),
);

export const TARGET_STARS: TargetStar[] = [
  { key: 'rr-lyr', role: 'target', name: 'RR Lyr', display_name: 'RR Lyr', ra_hours: 19.4428, dec_deg: 42.784, auid: '000-BBC-100', source: 'vsx', mags: { V: 7.6 }, chart_id: 'X12345AB', note: null, x: TARGET.x, y: TARGET.y },
  ...COMPS.filter((c) => c.role).map(
    (c): TargetStar => ({ key: c.key, role: c.role as 'comparison' | 'check', name: c.auid ?? c.label, ra_hours: 19.44, dec_deg: 42.8, auid: c.auid, source: 'vsp', mags: { V: c.v }, chart_id: 'X12345AB', note: null, x: c.x, y: c.y }),
  ),
  { key: 'gaia-extra', role: 'comparison', name: 'Gaia DR3 2125…', display_name: 'Gaia 2125…', ra_hours: 19.45, dec_deg: 42.7, auid: null, source: 'gaia', mags: { V: 10.9 }, chart_id: null, note: null, x: field[3].x, y: field[3].y },
];

export const CANDIDATES: Candidate[] = COMPS.map((c) => ({
  key: c.key,
  auid: c.auid,
  label: c.label,
  x: c.x,
  y: c.y,
  v_mag: c.v,
  b_minus_v: c.bv,
  delta_b_minus_v: c.dbv,
  sep_arcmin: c.sep,
  peak_adu: c.peak,
  snr: c.snr,
  saturated: c.sat,
  neighbours_in_aperture: c.nbr,
  detected: true,
  role: c.role,
}));

export const LAYERS: FieldLayers = {
  generation: 4,
  revision: 1,
  available: true,
  frame_shape: [H, W],
  display_mag_limit: 16.5,
  aperture_r_px: 9.5,
  layers: {
    stars,
    variables: VARS.map((v, i) => m(v.x, v.y, { id: `v${i}`, kind: 'variable', index: i, name: v.name, label: v.name, var_type: v.var_type, mag_text: v.mag_text, period_d: v.period_d, sep_arcmin: v.sep, suspected: v.suspected, key: i === 0 ? 'rr-lyr' : null, tooltip: `Variable star\n${v.name}\nType ${v.var_type} · ${v.mag_text}${v.period_d ? `\nPeriod ${v.period_d} d` : ''}` })),
    galaxies: [m(80, 860, { id: 'gx1', kind: 'deep_sky', label: 'PGC 1000001', tooltip: 'Galaxy\nPGC 1000001 (synthetic)' }), m(500, 90, { id: 'gx2', kind: 'deep_sky', label: 'PGC 1000002', tooltip: 'Galaxy\nPGC 1000002' })],
    nebulae_clusters: [m(250, 900, { id: 'nb1', kind: 'deep_sky', label: 'Cl Synth 1', tooltip: 'Open cluster\nCl Synth 1' })],
    exoplanets: [m(380, 330, { id: 'ex1', kind: 'exoplanet', label: 'Synth-1 b', tooltip: 'Exoplanet host\nSynth-1 (1 planet)' })],
    other_objects: [m(180, 560, { id: 'o1', kind: 'simbad', label: 'HD 900001', tooltip: 'SIMBAD star\nHD 900001 · K0' })],
    vsp: COMPS.map((c) => m(c.x, c.y, { id: `vsp-${c.key}`, kind: 'vsp', key: c.key, tooltip: `VSP reference ${c.label}\nV ${c.v}` })),
    selected: TARGET_STARS.map((s) => m(s.x ?? 0, s.y ?? 0, { id: `sel-${s.key}`, kind: 'target', key: s.key, role: s.role, label: s.role === 'target' ? s.name : (s.auid?.slice(-3) ?? s.display_name ?? ''), tooltip: `${s.role}\n${s.name}` })),
  },
  counts: { stars: stars.filter((s) => (s.g_mag ?? 0) <= 16.5).length, variables: 3, galaxies: 2, nebulae_clusters: 1, exoplanets: 1, other_objects: 1, vsp: COMPS.length, selected: TARGET_STARS.length },
  candidates: CANDIDATES,
};

/** A graticule tilted by the field rotation (straight lines are enough at this scale). */
function grid(): FieldState['grid'] {
  const a = (12 * Math.PI) / 180;
  const ux = Math.cos(a);
  const uy = Math.sin(a);
  const lines: [number, number][][] = [];
  const labels: { x: number; y: number; text: string; axis: 'ra' | 'dec' }[] = [];
  for (let k = -3; k <= 3; k++) {
    const ox = W / 2 + k * 150 * ux;
    const oy = H / 2 + k * 150 * uy;
    lines.push([[ox - uy * -700, oy + ux * -700], [ox - uy * 700, oy + ux * 700]].map(([x, y]) => [x, y] as [number, number]));
    labels.push({ x: ox - uy * -440, y: oy + ux * -440, text: `19h 26m ${String(30 + k * 6).padStart(2, '0')}s`, axis: 'ra' });
  }
  for (let k = -4; k <= 4; k++) {
    const ox = W / 2 - k * 150 * uy;
    const oy = H / 2 + k * 150 * ux;
    lines.push([[ox - ux * 600, oy - uy * 600], [ox + ux * 600, oy + uy * 600]].map(([x, y]) => [x, y] as [number, number]));
    labels.push({ x: ox + ux * 250, y: oy + uy * 250, text: `+42° ${String(47 - k * 3).padStart(2, '0')}′`, axis: 'dec' });
  }
  return { lines, labels, centre: { x: W / 2, y: H / 2, label: 'RA 19h 26m 30s  Dec +42° 47′' } };
}

export const SOLVED: FieldState = {
  state: 'solved',
  auto: false,
  auto_source: null,
  solving: null,
  reason: null,
  message: null,
  generation: 4,
  solution: { ra_hours: 19.4417, dec_deg: 42.7833, scale_arcsec_px: 1.19, rotation_deg: 12.3, delta_target_arcmin: 0.4, target_name: 'RR Lyr', frame_seq: 212, frame_shape: [H, W], mode: 'manual', solved_utc: '2026-11-08T22:39:51Z', summary: 'Solved — RA 19.4417h  Dec 42.7833°  1.19″/px  rot 12.3°  Δtarget 0.4′' },
  wcs: null,
  grid: grid(),
  target_reticle: { x: TARGET.x, y: TARGET.y, name: 'RR Lyr' },
  center_available: true,
};

export const UNSOLVED: FieldState = { ...SOLVED, state: 'none', solution: null, grid: null, target_reticle: null, center_available: false };
export const SOLVING: FieldState = { ...UNSOLVED, state: 'solving', solving: { mode: 'manual', job_id: 'j1', frame_seq: 212, started_utc: '2026-11-08T22:39:40Z' } };
export const FAILED_KEPT: FieldState = { ...SOLVED, state: 'failed', message: 'ASTAP: no solution found (blind search exhausted)' };
export const MOVED: FieldState = { ...UNSOLVED, state: 'invalidated', reason: 'mount_moved', message: 'Mount pointing changed outside ARGOS — stale astrometry overlays cleared.' };

export const TARGETS: TargetSet = {
  object_name: 'RR Lyr',
  path: '/sessions/targets/RR_Lyr.json',
  stars: TARGET_STARS,
  summary: null,
  geometry: { aperture_px: 4.75, annulus_in_px: 8, annulus_out_px: 12, aperture_r_px: 9.5, annulus_in_r_px: 16, annulus_out_r_px: 24, fwhm_px: 1.9, fwhm_source: 'frame' },
};

const ring = (x: number, y: number) => ({ x, y, r_px: 9.5, aperture: 'photometry' as const });

export const SEL_VARIABLE: SelectionEvent = {
  id: 11,
  state: 'resolved',
  message: null,
  selection: {
    id: 11,
    seq: 212,
    kind: 'variable',
    title: 'Variable · RR Lyr',
    rows: [
      { key: 'Type', value: 'RRAB' },
      { key: 'Range', value: 'max 7.06 · min 8.12 V' },
      { key: 'Period', value: '0.566868 d' },
      { key: 'AUID', value: '000-BBC-100' },
    ],
    ring: ring(TARGET.x, TARGET.y),
    pending_star: { ra_deg: 291.64, dec_deg: 42.78, name: 'RR Lyr' },
    key: 'rr-lyr',
    role: 'target',
    roles_enabled: true,
    roles_reason: null,
    removable: true,
    identifying: false,
  },
};

export const SEL_IDENTIFYING: SelectionEvent = {
  id: 12,
  state: 'identifying',
  message: null,
  selection: { ...SEL_VARIABLE.selection!, id: 12, kind: 'measured', title: 'Measured star', rows: [{ key: 'FWHM', value: 'FWHM 2.84 px · 3.4″' }, { key: 'SNR', value: 'SNR 212' }], key: null, role: null, removable: false, identifying: true, ring: ring(150, 300) },
};

export const SEL_NO_WCS: SelectionEvent = {
  id: 13,
  state: 'resolved',
  message: null,
  selection: { ...SEL_IDENTIFYING.selection!, id: 13, title: 'Manual image measurement', rows: [{ key: 'FWHM', value: 'FWHM 2.84 px' }, { key: 'Peak', value: 'peak 41 203 ADU' }], identifying: false, roles_enabled: false, roles_reason: 'Identify the field first' },
};

export const SEL_NO_MATCH: SelectionEvent = {
  id: 14,
  state: 'no_match',
  message: 'No Gaia or SIMBAD source within 10″; measured star kept.',
  selection: { ...SEL_IDENTIFYING.selection!, id: 14, title: 'Measured star', identifying: false, pending_star: { ra_deg: 291.6, dec_deg: 42.7 } },
};

export const SEL_COMPARISON: SelectionEvent = {
  id: 15,
  state: 'resolved',
  message: null,
  selection: { ...SEL_VARIABLE.selection!, id: 15, kind: 'vsp', title: 'VSP · 000-BBC-102', rows: [{ key: 'V', value: 'V 9.11' }, { key: 'B−V', value: 'B−V 0.52' }], key: 'c102', role: 'comparison', ring: ring(360, 610) },
};

/** Many Gaia rows for the virtual list (the 5 000 budget). */
export function manyStars(n = 5000): Marker[] {
  const r = prng(99);
  return Array.from({ length: n }, (_, i) => m(r() * W, r() * H, { id: `big${i}`, g_mag: Math.round((9 + 9 * r()) * 100) / 100, bp_mag: 12, rp_mag: 11.2, detected: r() > 0.4, name: i % 37 === 0 ? `HD ${900000 + i}` : null }));
}
