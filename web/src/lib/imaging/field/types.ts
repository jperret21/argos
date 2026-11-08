/**
 * Wire records of field identification, catalogue layers, selection and the target set
 * (API 2, wave 4: argos/server/protocol.md "API 2 routes, wave 4"; README 4.3 rows
 * A32-A33, A43-A49, A51-A53). Positions are frame px, numpy convention, un-rotated
 * (`x_frame = 2 · x_green + 0.5`); radii carry their unit. Kept next to the field UI that
 * reads them; `api/types.ts` stays the home of the earlier waves' records.
 */

import type { LayerId, Marker, Role } from '../../viewer/overlay/layers';
import type { RigidTransform } from '../../viewer/overlay/project';

export type { LayerId, Marker, Role, RigidTransform };

// -- A43-A45 field ---------------------------------------------------------------------------

export type FieldStateName = 'none' | 'solving' | 'solved' | 'failed' | 'invalidated';
export type InvalidationReason = 'slew' | 'mount_moved' | 'geometry' | 'file_opened' | 'center';

export interface FieldSolution {
  ra_hours: number;
  dec_deg: number;
  /** Per FRAME px (ASTAP's green scale ÷ 2). */
  scale_arcsec_px: number | null;
  rotation_deg: number | null;
  mirrored?: boolean | null;
  delta_target_arcmin: number | null;
  target_name?: string | null;
  frame_seq: number;
  frame_origin?: string;
  /** [h, w], frame px. */
  frame_shape?: [number, number];
  mode?: 'manual' | 'auto';
  solved_utc?: string;
  summary?: string;
}

/** TAN WCS of the reference solve: crval degrees, crpix FITS 1-based frame px, cd degrees per frame px. */
export interface FieldWcs {
  ctype?: [string, string];
  crval: [number, number];
  crpix: [number, number];
  cd: [[number, number], [number, number]];
  frame_shape?: [number, number];
}

export interface GridLabel {
  x: number;
  y: number;
  text: string;
  axis?: 'ra' | 'dec';
}

export interface FieldGrid {
  /** Polylines of the RA / Dec graticule, frame px of the reference solve (broken off-frame). */
  lines: readonly (readonly (readonly [number, number])[])[];
  labels: readonly GridLabel[];
  centre?: { x: number; y: number; label: string } | null;
}

export interface TargetReticle {
  x: number;
  y: number;
  name?: string | null;
  ra_hours?: number;
  dec_deg?: number;
}

export interface FieldState {
  state: FieldStateName;
  auto: boolean;
  auto_source?: 'observer' | 'sequence' | null;
  solving?: { mode: 'manual' | 'auto'; job_id: string | null; frame_seq: number; started_utc: string } | null;
  /** Why the field was invalidated. */
  reason: InvalidationReason | string | null;
  /** The failure or invalidation sentence (as logged). */
  message?: string | null;
  generation?: number;
  /** The last good solution (a failed attempt keeps it). */
  solution: FieldSolution | null;
  wcs: FieldWcs | null;
  grid: FieldGrid | null;
  target_reticle: TargetReticle | null;
  last_attempt?: { mode: 'manual' | 'auto'; outcome: 'solved' | 'failed' | 'cancelled'; message: string; t: string } | null;
  /** A solution, a connected mount and a target: Centre target can act. */
  center_available?: boolean;
  revision?: number;
}

// -- A46 catalog -----------------------------------------------------------------------------

export type CatalogStateName = 'idle' | 'fetching' | 'ready' | 'error';

export interface CatalogState {
  state: CatalogStateName;
  generation?: number;
  counts: Partial<Record<'variables' | 'comparisons' | 'field_stars' | 'named_objects' | 'exoplanet_hosts', number>>;
  warnings: readonly string[];
  /** The service's words (state "error"). */
  error?: string | null;
  fetched_utc?: string | null;
  revision?: number;
}

// -- A47 field_layers, A48 field_transform ---------------------------------------------------

/** A VSP comparison candidate of the field (PROPOSAL 7, the Field band). */
export interface Candidate {
  key: string;
  auid: string | null;
  /** VSP chart label. */
  label: string | null;
  chart_id?: string | null;
  /** Reference-solve frame px. */
  x: number | null;
  y: number | null;
  ra_hours?: number;
  dec_deg?: number;
  v_mag: number | null;
  b_mag?: number | null;
  b_minus_v: number | null;
  /** Minus the target's B − V (null when the target has no VSP B − V). */
  delta_b_minus_v: number | null;
  /** From the first target, else the field centre. */
  sep_arcmin: number | null;
  peak_adu: number | null;
  snr: number | null;
  /** Peak at or above the linearity / full-well threshold (`sat_adu`). */
  saturated: boolean | null;
  /**
   * Gaia sources within the aperture at most 3 mag fainter (blend risk); null when the held
   * Gaia list cannot say (none, or not complete to the candidate's m + 3).
   */
  neighbours_in_aperture: number | null;
  /** The VSX entry at the candidate's position: a known or suspected variable. */
  vsx?: CandidateVsx | null;
  detected?: boolean;
  role: Role | string | null;
  measured_seq?: number | null;
  /** Free status from the run (W5: leave-one-out). */
  status?: string | null;
}

export interface CandidateVsx {
  name: string;
  var_type?: string | null;
  suspected?: boolean;
  max_mag?: string | null;
  min_mag?: string | null;
  sep_arcsec?: number;
}

/** The observer's comparison rules (Settings › Photometry) the band flags with. */
export interface CandidateLimits {
  comparison_max_separation_arcmin: number;
  comparison_max_delta_mag: number;
  comparison_min_snr: number;
  /** The G the held Gaia list is complete to (null: no Gaia list). */
  gaia_depth_g: number | null;
}

export interface FieldLayers {
  generation: number;
  revision?: number;
  /** The field is solved. */
  available: boolean;
  frame_shape?: [number, number] | null;
  display_mag_limit?: number;
  /** Photometry aperture radius, frame px. */
  aperture_r_px?: number;
  layers: Partial<Record<LayerId, readonly Marker[]>>;
  counts: Partial<Record<LayerId, number>>;
  candidates: readonly Candidate[];
  limits?: CandidateLimits | null;
}

export interface FieldTransform extends RigidTransform {
  generation: number;
  frame_seq?: number | null;
  anchors?: number;
  residual_px?: number | null;
  anchor_source?: 'target_set' | 'detected' | null;
  lost_frames?: number;
  /** Lock health: lost = no consistent anchor (the transform is the last good one). */
  tracking?: 'ok' | 'degraded' | 'lost' | null;
}

// -- A49 selection ---------------------------------------------------------------------------

export type SelectionKind =
  | 'target'
  | 'variable'
  | 'vsp'
  | 'simbad'
  | 'deep_sky'
  | 'exoplanet'
  | 'gaia'
  | 'point_identity'
  | 'measured'
  | 'none';

export interface SelectionRow {
  key: string;
  value: string;
}

export interface SelectionRing {
  x: number;
  y: number;
  r_px: number;
  aperture: 'photometry' | 'star';
  /** "reference": a catalogue position of the reference solve (the tracking moves it); "frame": measured on the frame. */
  space?: 'reference' | 'frame';
}

export interface PendingStar {
  ra_deg: number;
  dec_deg: number;
  ra_hours?: number;
  auid?: string | null;
  name?: string | null;
  source?: string | null;
  mags?: Record<string, number | null> | null;
  chart_id?: string | null;
}

export interface Measurement {
  x: number;
  y: number;
  fwhm_px: number | null;
  hfd_px: number | null;
  fwhm_arcsec: number | null;
  hfd_arcsec: number | null;
  eccentricity: number | null;
  snr: number | null;
  peak_adu: number | null;
  sky_adu: number | null;
  ra_hours: number | null;
  dec_deg: number | null;
}

export interface Selection {
  id: number;
  seq?: number;
  kind: SelectionKind;
  title: string;
  rows: readonly SelectionRow[];
  ring: SelectionRing | null;
  pending_star: PendingStar | null;
  /** Its key / role in the set. */
  key: string | null;
  role: Role | null;
  roles_enabled: boolean;
  roles_reason: string | null;
  removable: boolean;
  identifying: boolean;
  measurement?: Measurement | null;
}

export type SelectionStateName = 'identifying' | 'resolved' | 'no_match' | 'failed' | 'tracking';

export interface SelectionEvent {
  id: number | null;
  state?: SelectionStateName;
  selection: Selection | null;
  message?: string | null;
}

export interface SelectRequest {
  x: number;
  y: number;
  seq?: number | null;
  tol_px?: number;
}

// -- A51-A53 targets -------------------------------------------------------------------------

export interface TargetStar {
  key: string;
  role: Role;
  name: string;
  display_name?: string;
  ra_deg?: number;
  dec_deg: number;
  ra_hours: number;
  auid: string | null;
  source: string | null;
  mags: Record<string, number | null> | null;
  chart_id: string | null;
  note: string | null;
  /** Reference frame px when solved and in frame. */
  x?: number | null;
  y?: number | null;
}

export interface PhotometryGeometry {
  /** Green px (the science code's radii). */
  aperture_px: number | null;
  annulus_in_px: number | null;
  annulus_out_px: number | null;
  /** Frame px. */
  aperture_r_px?: number | null;
  annulus_in_r_px?: number | null;
  annulus_out_r_px?: number | null;
  fwhm_px: number | null;
  fwhm_source: 'frame' | 'default' | string | null;
}

export interface TargetSet {
  /** The set's key (D11), "Unknown" when empty. */
  object_name: string;
  /** <sessions_path>/targets/<object>.json */
  path?: string;
  stars: readonly TargetStar[];
  summary: Record<string, unknown> | null;
  geometry: PhotometryGeometry | null;
  revision?: number;
  /** DELETE /api/targets/{key}: the star as it was (Undo = POST with `star`). */
  removed?: TargetStar;
}

export type SetRoleRequest = { role: Role } & ({ selection: number } | { star: PendingStar } | { variable_index: number });
