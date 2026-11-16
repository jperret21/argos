/**
 * Re-run photometry dialog and its job, the pure part (web/spec/07-review-analysis.md 1.13,
 * WF-F; README M8, M50, A76, D2, S12, S13; protocol.md "Re-run photometry (A76)").
 *
 * The server's plan (`POST /api/review/rerun/plan`, never writes) says what a start would do;
 * this module turns it into the dialog's lines and the job's outcome into words.
 */

import { fixed, int, signed } from '../../format/number';
import type { Refusal, RerunBody, RerunParams, RerunPlan, RerunResult } from './api';

export interface RerunChoice {
  /** A frames folder typed or picked; "" = the session's. */
  frames: string;
  targets: 'session' | 'live';
  reference: 'solve' | 'live';
  diagnostics: boolean | null;
}

export function rerunBody(session: string, c: RerunChoice): RerunBody {
  const frames = c.frames.trim();
  return {
    session,
    frames: frames ? frames : null,
    targets: c.targets,
    reference: c.reference,
    reference_frame: null,
    diagnostics: c.diagnostics,
  };
}

const n = (v: number, one: string, many: string) => `${int(v)} ${v === 1 ? one : many}`;

/** "1 target · 6 comparisons · 1 check" for the object. */
export function starsLine(s: RerunPlan['stars']): string {
  return [n(s.target, 'target', 'targets'), n(s.comparison, 'comparison', 'comparisons'), n(s.check, 'check', 'checks')].join(' · ');
}

/** "195 light frames (.fit .fits .fts)" and what was left out. */
export function framesLine(p: Pick<RerunPlan, 'frames' | 'left_out'>): string {
  const bits = [`${n(p.frames, 'light frame', 'light frames')} (.fit .fits .fts)`];
  const out: string[] = [];
  if (p.left_out.calibration) out.push(`${int(p.left_out.calibration)} calibration`);
  if (p.left_out.other_object) out.push(`${int(p.left_out.other_object)} of another object`);
  if (p.left_out.outside_lights) out.push(`${int(p.left_out.outside_lights)} outside lights/`);
  if (p.left_out.duplicates) out.push(`${int(p.left_out.duplicates)} ${p.left_out.duplicates === 1 ? 'link' : 'links'} to a frame listed`);
  if (out.length) bits.push(`left out: ${out.join(', ')}`);
  return bits.join(' · ');
}

/** "2.50 × FWHM, floor 4.0 px · annulus 8.0–12.0 px" (the aperture rule the run will use). */
export function apertureLine(p: RerunParams): string {
  const bits: string[] = [];
  if (p.aperture_fwhm_mult !== null) bits.push(`${fixed(p.aperture_fwhm_mult, 2)} × FWHM${p.aperture_min_px !== null ? `, floor ${fixed(p.aperture_min_px, 1)} px` : ''}`);
  if (p.annulus_in_px !== null && p.annulus_out_px !== null) bits.push(`annulus ${fixed(p.annulus_in_px, 1)}–${fixed(p.annulus_out_px, 1)} px`);
  return bits.join(' · ') || '—';
}

/** "tracking on · e-/ADU 2.31 · read noise 3.5 e- · band TG · min 3 comparisons · site set". */
export function paramsLine(p: RerunParams, siteSet: boolean): string {
  const bits: string[] = [];
  if (p.track_apertures !== null) bits.push(`tracking ${p.track_apertures ? 'on' : 'off'}`);
  if (p.egain !== null) bits.push(`e−/ADU ${fixed(p.egain, 2)}`);
  if (p.read_noise_e !== null) bits.push(`read noise ${fixed(p.read_noise_e, 1)} e−`);
  if (p.sat_adu !== null) bits.push(`saturation ${int(p.sat_adu)} ADU`);
  if (p.band) bits.push(`band ${p.band}`);
  if (p.min_comps !== null) bits.push(`min ${n(p.min_comps, 'comparison', 'comparisons')}`);
  bits.push(siteSet ? 'site set' : 'no site: no airmass, no BJD_TDB');
  return bits.join(' · ');
}

/** paramsLine as label / value pairs (the dialog's grid: labels in the UI face, values in mono). */
export function paramsRows(p: RerunParams, siteSet: boolean): [string, string][] {
  const rows: [string, string][] = [];
  if (p.track_apertures !== null) rows.push(['Tracking', p.track_apertures ? 'on' : 'off']);
  if (p.egain !== null) rows.push(['e−/ADU', fixed(p.egain, 2)]);
  if (p.read_noise_e !== null) rows.push(['Read noise', `${fixed(p.read_noise_e, 1)}\u202fe−`]);
  if (p.sat_adu !== null) rows.push(['Saturation', `${int(p.sat_adu)}\u202fADU`]);
  if (p.band) rows.push(['Band', p.band]);
  if (p.min_comps !== null) rows.push(['Min comparisons', String(p.min_comps)]);
  rows.push(['Site', siteSet ? 'set' : 'none: no airmass, no BJD_TDB']);
  return rows;
}

/** What blocks Start, or null: the server's refusal, a failed plan, a plan not there yet. */
export function rerunBlock(plan: RerunPlan | null, planError: string | null, pending: boolean): string | null {
  if (planError) return planError;
  if (!plan) return pending ? 'Checking the frames…' : 'No plan yet.';
  if (plan.refusal) return plan.refusal.message;
  if (!plan.frames) return `No FITS files (.fit, .fits, .fts) in ${plan.frames_dir}`;
  return null;
}

export function refusalText(r: Refusal | null): string | null {
  return r ? r.message : null;
}

/** The outcome in words for the job strip and the toast. */
export function rerunResultText(r: RerunResult): string {
  const bits = [`${int(r.frames_done)} of ${int(r.frames_total)} frames`, n(r.curves.length, 'curve', 'curves')];
  if (r.frames_skipped) bits.push(`${int(r.frames_skipped)} skipped`);
  if (r.frames_unverified) bits.push(`${int(r.frames_unverified)} unverified (suspect)`);
  if (r.frames_rotation_solved) bits.push(`${int(r.frames_rotation_solved)} re-solved for rotation`);
  if (r.stars_off_centre) bits.push(`${int(r.stars_off_centre)} off-centre (suspect)`);
  if (r.frames_rotation_unsolved) bits.push(`${int(r.frames_rotation_unsolved)} not re-solved for rotation`);
  if (r.frames_no_target_point) bits.push(`${int(r.frames_no_target_point)} without a target point`);
  if (r.frames_no_detection) bits.push(`${int(r.frames_no_detection)} no detection (suspect)`);
  if (r.frames_site_wrong) bits.push(`site in Settings wrong on ${int(r.frames_site_wrong)}`);
  return `${bits.join(' · ')} → ${r.folder}/`;
}

/** "field rot +0.42° · drift 3.1 px" (said when the apertures followed the field). */
export function trackingText(r: Pick<RerunResult, 'rotation_deg' | 'shift_px'>): string | null {
  if (Math.abs(r.rotation_deg) <= 0.05 && r.shift_px <= 1) return null;
  return `field rot ${signed(r.rotation_deg, 2)}° · drift ${fixed(r.shift_px, 1)} px`;
}

/** "Check 000-BCG-523 [ir]: RMS 0.012 mag over 183 frames" lines. */
export function checkRmsLines(r: RerunResult, names: (key: string) => string = (k) => k): string[] {
  return r.check_rms.map((c) => `Check ${names(c.key)}: RMS ${fixed(c.rms_mag, 3)} mag over ${n(c.n, 'frame', 'frames')}`);
}
