/**
 * Transit planning in the Source card (06 §2.3.3, A42 + A66; Q-P10, P5, P6, P7):
 * the planet (lookup), the transit the server chose (the night asked for, or the next
 * observable one), and the series it writes as the draft (with its ephemeris, S5).
 *
 * - The form (baseline, exposure, cadence, gain, filter, night) is remembered per viewer
 *   (`argos.plan.transit`, spec 2.4 Persistence); a changed baseline or night predicts again
 *   at once (fixes P5: Qt kept the 60 min window until Prepare).
 * - Prepare plans exactly the transit shown (`epoch_number`), never a later one.
 * - Nothing is computed here but words: times, altitudes and skipped transits are the
 *   server's (transit.py, airmass.py through A66).
 */

import type { ExoplanetTarget, PlanApi, PlanDoc, TransitPrediction } from '../api/plan';
import type { TransitSpans } from '../api/sequence';
import { loadPref, savePref } from '../app/prefs';
import { fixed } from '../format/number';
import { localHm, utcHm } from './model';

export interface TransitForm {
  planet: string;
  baseline_minutes: number;
  exposure_s: number;
  cadence_s: number;
  gain: number;
  filter_name: string;
  /** Night asked for (YYYY-MM-DD); '' = the next observable transit. */
  date: string;
}

/** Qt's transit form defaults (sequence_panel.py:394-425). */
export const TRANSIT_DEFAULTS: TransitForm = { planet: '', baseline_minutes: 60, exposure_s: 10, cadence_s: 13, gain: 80, filter_name: '', date: '' };

const PREF = 'argos.plan.transit';

export function isTransitForm(v: unknown): v is TransitForm {
  if (typeof v !== 'object' || v === null) return false;
  const o = v as Record<string, unknown>;
  const n = (k: string) => typeof o[k] === 'number' && Number.isFinite(o[k]);
  return typeof o.planet === 'string' && n('baseline_minutes') && n('exposure_s') && n('cadence_s') && n('gain') && typeof o.filter_name === 'string' && typeof o.date === 'string';
}

/** "YYYY-MM-DD" (a real calendar date), or '' (next observable). */
export function dateProblem(text: string): string | null {
  const t = text.trim();
  if (!t) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(t);
  if (!m) return 'Type the night as YYYY-MM-DD, or leave it empty for the next observable transit';
  const d = new Date(`${t}T12:00:00Z`);
  if (Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== t) return `${t} is not a calendar date`;
  return null;
}

/** "Coverage 01:12 → 05:02 local · 00:12 → 04:02 UTC · 3.84 h" parts. */
export function coverageText(p: TransitPrediction, offsetMin?: number): { local: string; utc: string; hours: string } {
  return {
    local: `${localHm(p.utc.coverage_start, offsetMin)} → ${localHm(p.utc.coverage_end, offsetMin)}`,
    utc: `${utcHm(p.utc.coverage_start)} → ${utcHm(p.utc.coverage_end)}`,
    hours: `${fixed(p.window.coverage_hours, 2)} h`,
  };
}

const deg = (v: number | null) => (v === null ? '—' : `${Math.round(v)}°`);

/** "start 41° · mid 63° · end 58°": coverage start, mid-transit, coverage end (named, BRAND 7). */
export function altitudeText(p: TransitPrediction): string {
  return `start ${deg(p.altitude_deg.coverage_start)} · mid ${deg(p.altitude_deg.mid)} · end ${deg(p.altitude_deg.coverage_end)}`;
}

/**
 * What limits this transit, in words (spec 2.3.3 "⚠ Mid-transit at 18° altitude; coverage
 * ends below 30°"): null when the transit and its baselines are dark and above the limit.
 */
export function transitNote(p: TransitPrediction): string | null {
  const lim = `${Math.round(p.min_alt_deg)}°`;
  if (!p.observable.transit) {
    const low = (['ingress', 'mid', 'egress'] as const).filter((k) => (p.altitude_deg[k] ?? 90) < p.min_alt_deg);
    const day = p.sun_alt_deg ? (['ingress', 'mid', 'egress'] as const).filter((k) => (p.sun_alt_deg?.[k] ?? -90) > -18) : [];
    const parts: string[] = [];
    if (low.length) parts.push(`below ${lim} at ${low.join(', ')}`);
    if (day.length) parts.push(`in twilight or daylight at ${day.join(', ')}`);
    return `The transit itself is not observable: ${parts.join('; ') || 'outside the night or below the limit'}`;
  }
  if (!p.observable.coverage) {
    const lowEnds = (['coverage_start', 'coverage_end'] as const).filter((k) => (p.altitude_deg[k] ?? 90) < p.min_alt_deg);
    const words = lowEnds.map((k) => (k === 'coverage_start' ? 'coverage starts' : 'coverage ends'));
    return words.length ? `Baseline cut: ${words.join(' and ')} below ${lim}` : 'Baseline cut: part of the coverage is outside the astronomical night';
  }
  return null;
}

/** "3 earlier transits skipped (daylight 2, below 30° 1)"; past the 20 the server lists, the
 * reasons are those of the first 20 and the line says so. Null when none was skipped. */
export function skippedText(p: TransitPrediction): string | null {
  if (!p.skipped_count) return null;
  const by = new Map<string, number>();
  for (const s of p.skipped) by.set(s.reason, (by.get(s.reason) ?? 0) + 1);
  const lim = `${Math.round(p.min_alt_deg)}°`;
  const parts = [...by].map(([r, n]) => `${r === 'below_limit' ? `below ${lim}` : r === 'daylight' ? 'daylight' : r} ${n}`);
  const n = p.skipped_count;
  const of = p.skipped.length < n ? `of the first ${p.skipped.length}: ` : '';
  return `${n} earlier transit${n === 1 ? '' : 's'} skipped${parts.length ? ` (${of}${parts.join(', ')})` : ''}`;
}

/** The spans the visibility timeline draws (unix s). */
export function spansOf(p: TransitPrediction): TransitSpans | null {
  const t = (iso: string) => Date.parse(iso) / 1000;
  const s = { coverageStart: t(p.utc.coverage_start), ingress: t(p.utc.ingress), mid: t(p.utc.mid), egress: t(p.utc.egress), coverageEnd: t(p.utc.coverage_end) };
  return Object.values(s).every(Number.isFinite) ? s : null;
}

/** The planet's facts line (spec 2.3.3): "P 2.21857567 d · duration 1.84 h · depth 2.4 % · epoch BJD_TDB". */
export function planetFacts(e: ExoplanetTarget): string {
  const parts = [`P ${fixed(e.period_days, 8)} d`];
  parts.push(e.duration_hours !== null ? `duration ${fixed(e.duration_hours, 2)} h` : 'no published duration');
  if (e.depth_percent !== null) parts.push(`depth ${fixed(e.depth_percent, e.depth_percent < 1 ? 2 : 1)} %`);
  parts.push(`epoch ${e.epoch_system || 'unknown system'}`);
  return parts.join(' · ');
}

export class TransitPlanner {
  form: TransitForm = $state(loadPref(PREF, isTransitForm, { ...TRANSIT_DEFAULTS }));
  planet: ExoplanetTarget | null = $state.raw(null);
  prediction: TransitPrediction | null = $state.raw(null);
  predicting = $state(false);
  predictError: string | null = $state(null);
  preparing = $state(false);
  prepareError: string | null = $state(null);
  private ctl: AbortController | null = null;

  constructor(private readonly api: PlanApi) {}

  set(patch: Partial<TransitForm>): void {
    this.form = { ...this.form, ...patch };
    savePref(PREF, this.form);
  }

  /** A42: find the planet, then its transit. Rejects with the server's words. */
  async lookup(q: string, signal?: AbortSignal): Promise<ExoplanetTarget> {
    const e = await this.api.exoplanetLookup(q, signal);
    this.planet = e;
    this.prediction = null;
    this.set({ planet: e.planet_name });
    void this.predict();
    return e;
  }

  /** A66 predict: that night's transit, or the next observable one; a newer call cancels this one. */
  async predict(): Promise<void> {
    const name = this.planet?.planet_name ?? this.form.planet;
    if (!name || dateProblem(this.form.date)) return;
    this.ctl?.abort();
    const ctl = new AbortController();
    this.ctl = ctl;
    this.predicting = true;
    this.predictError = null;
    try {
      const p = await this.api.transitPredict(
        { planet_name: name, baseline_minutes: this.form.baseline_minutes, ...(this.form.date ? { date: this.form.date } : {}) },
        ctl.signal,
      );
      if (ctl.signal.aborted) return;
      this.prediction = p;
      this.planet = p.planet;
    } catch (err) {
      if (ctl.signal.aborted) return;
      this.prediction = null;
      this.predictError = err instanceof Error ? err.message : String(err);
    } finally {
      if (this.ctl === ctl) this.predicting = false;
    }
  }

  /** A66 plan: the transit shown becomes the draft (its ephemeris kept for observation.json, S5). */
  async prepare(): Promise<PlanDoc> {
    const p = this.prediction;
    if (!p) throw new Error('Find a planet and its transit first.');
    this.preparing = true;
    this.prepareError = null;
    try {
      const f = this.form;
      const r = await this.api.transitPlan({
        planet_name: p.planet.planet_name,
        baseline_minutes: f.baseline_minutes,
        epoch_number: p.window.epoch_number,
        exposure_s: f.exposure_s,
        cadence_s: f.cadence_s,
        gain: f.gain,
        filter_name: f.filter_name,
      });
      if (r.prediction) this.prediction = r.prediction;
      return r.plan;
    } catch (err) {
      this.prepareError = err instanceof Error ? err.message : String(err);
      throw err;
    } finally {
      this.preparing = false;
    }
  }
}
