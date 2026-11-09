/**
 * Wire records of live photometry (API 2, wave 5: argos/server/protocol.md "API 2 routes,
 * wave 5"; README 4.3 rows A50, A54-A58; 08 2.5). Kept next to the photometry UI that reads
 * them. The science is the server's (argos/core, identical to Qt): the client never
 * recomputes a magnitude, an error or a verdict, it only formats them.
 */

import type { PhotometryGeometry, Role, TargetSet, TargetStar } from '../field/types';

export type { Role, TargetSet, TargetStar };

/** One light-curve point: every `LcPoint` field (lightcurve.py:38-62) plus the frame's time. */
export interface LcPoint {
  /** Exposure midpoint, JD (UTC). */
  jd_utc: number;
  /** BJD_TDB of the midpoint for this star; null without a site (never a 0/0 default). */
  bjd_tdb: number | null;
  /** Differential magnitude; NaN (null on the wire) for a ratio-only point. */
  mag: number | null;
  /** Error with the systematic floor: hypot(formal_mag_err, sigma_syst). */
  mag_err: number | null;
  formal_mag_err: number | null;
  sigma_syst: number | null;
  airmass: number | null;
  fwhm: number | null;
  sky_adu: number | null;
  /** Comparisons behind `mag`. */
  comps_used: number;
  relative_flux: number | null;
  relative_flux_err: number | null;
  /** Comparisons behind `relative_flux` (the ratio path also drops suspect stars). */
  relative_comps_used: number;
  saturated: boolean;
  /** Aperture peak without PSF support (hot pixel?): recorded, never dropped. */
  suspect: boolean;
  /** Exposure midpoint, ISO 8601 UTC (server convenience). */
  t?: string | null;
  /** The frame it was measured on. */
  frame_seq?: number | null;
  /** The star's ensemble zero point on that frame (catalogue − instrumental, mean) and its rms. */
  zero_point?: number | null;
  zp_rms?: number | null;
}

/** A star's curve in the live store (`LightCurve`, keyed as Qt: AUID, else the display name). */
export interface Curve {
  key: string;
  /** The set star's key (`auid:…` / `pos:…`); null when the star left the set. */
  star_key: string | null;
  role: Role;
  name: string;
  auid: string | null;
  /** Catalogue magnitudes (VSP). */
  mags?: Record<string, number>;
  /** D10: the check star is plotted as check − this. */
  catalogue_v: number | null;
  /** The curve's current systematic floor. */
  sigma_syst: number | null;
  /** The CSV the server rewrites after every point. */
  csv?: string | null;
  points: LcPoint[];
}

export type EntryStatus = 'stable' | 'unstable' | 'noisy' | 'insufficient_data';
export type SelectionStatus = 'insufficient_data' | 'not_ready' | 'live_preview_consistent';

/** One comparison of the leave-one-out report (quality.py:61-72) and its wire extras. */
export interface QualityEntry {
  name: string;
  auid: string | null;
  n_valid: number;
  scatter_mag: number | null;
  median_formal_error_mag: number | null;
  status: EntryStatus | string;
  /** Its curve key. */
  key?: string | null;
  /** Its TargetStar key. */
  star_key?: string | null;
  /** Its newest leave-one-out point (calibrated against the other comparisons). */
  last?: { mag: number | null; mag_err: number | null; comps_used: number; jd_utc: number } | null;
}

/** The leave-one-out report (quality.py:22-98), live in and out of a sequence (A57, Q-R13). */
export interface QualityReport {
  schema?: number;
  generated_utc?: string;
  selection_status: SelectionStatus | string;
  scientific_note: string;
  criteria: { min_points: number; max_scatter_mag: number; max_formal_error_mag: number };
  comparison_stars: QualityEntry[];
}

/** Effective photometry geometry (A51 `geometry`, plus the frozen series FWHM in A54). */
export type PhotGeometry = PhotometryGeometry & { series_fwhm_px?: number | null };

export type LiveStateName = 'off' | 'waiting' | 'measured' | 'skipped';
export type LiveReason = 'no_target' | 'not_solved' | 'no_epoch' | 'no_comparison' | 'no_point';

/** WS `photometry` (the live status the Field band shows). */
export interface LiveStatus {
  state: LiveStateName | string;
  reason: LiveReason | string | null;
  /** The server's sentence (as logged), shown verbatim when present. */
  message: string | null;
  /** Measured frames and kept points since the last reset. */
  frames: number;
  points: number;
  last: {
    frame_seq: number;
    t: string;
    jd_utc: number;
    bjd_tdb: number | null;
    /** Points kept on that frame. */
    points: number;
    target: { key: string; mag: number | null; mag_err: number | null } | null;
    /** Green px. */
    aperture_px: number;
    fwhm_px: number;
    anchors: number | null;
    tracking: { rot_deg: number; dx: number; dy: number; residual_px: number } | null;
  } | null;
  revision?: number;
}

/** A54 `GET /api/photometry/live`. */
export interface LiveSnapshot {
  object_name: string;
  run_root: string | null;
  sequence_running: boolean;
  band: string | null;
  obscode: string | null;
  chart_id: string | null;
  /** X2: BJD_TDB and the star's own airmass need the Settings site. */
  site_set: boolean;
  geometry: PhotGeometry | null;
  curves: Curve[];
  quality: QualityReport | null;
  status: LiveStatus | null;
  /** +1 at every reset. */
  revision: number;
  /** The newest point / reset of the stream. */
  seq: number;
}

/** A55 WS `photometry_point`. */
export interface PointEvent {
  seq: number;
  revision: number;
  frame_seq: number;
  key: string;
  star_key: string | null;
  role: Role;
  name: string;
  auid: string | null;
  /** Position of the point in its curve. */
  index: number;
  point: LcPoint;
  /** The curve's floor after this point: every earlier bar is hypot(formal, it) (S19). */
  sigma_syst: number | null;
}

/** A56 WS `photometry_reset`. */
export interface ResetEvent {
  seq: number;
  revision: number;
  reason: 'object_changed' | 'cleared' | 'sequence_started' | string;
}

/** A50 `GET /api/field/variables`: one VSX variable of the solved field. */
export interface FieldVariable {
  /** The index A52 takes (`variable_index`). */
  index: number;
  name: string;
  var_type: string | null;
  /** "max – min" as VSX gives it. */
  mag_text: string | null;
  /** The bright end of the VSX range (the Qt filter's value). */
  brightest_mag: number | null;
  period_d: number | null;
  /** From the solved field centre. */
  sep_arcmin: number | null;
  /** Its role when it is in the target set. */
  in_set_role: Role | null;
  suspected: boolean;
  auid: string | null;
  key: string;
  ra_hours?: number | null;
  dec_deg?: number | null;
  /** Reference frame px (moved by the tracking transform). */
  x: number | null;
  y: number | null;
}

export interface FieldVariables {
  /** The field is solved and its catalogue known. */
  available: boolean;
  generation: number;
  rows: FieldVariable[];
}

/** A58 `POST /api/photometry/comparisons/recommend`. */
export type RecommendMode = 'complete' | 'replace';
export interface RecommendResult {
  added: number;
  removed: TargetStar[];
  /** The set's comparisons afterwards. */
  comparisons: TargetStar[];
  targets: TargetSet | null;
}
