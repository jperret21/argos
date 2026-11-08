/**
 * What the Conditions timeline shows (decision D6): the chosen metrics (up to
 * three small multiples, BRAND 10) and the time window (whole session to
 * now, or a zoom the observer kept). Shared by the timeline and its tools in
 * the drawer header, remembered per viewer (`argos.conditions.metrics`).
 *
 * Merges the metric chips of src/lab/charts/charts/ConditionsTimeline.svelte
 * and the trend of src/lab/workspace/charts/Trend.svelte (one implementation).
 * Conditions are not photometric roles: neutral inks, never the role colours.
 */

import { loadPref, savePref } from '../app/prefs';
import type { Column } from './conditions';

export type MetricId = 'focus' | 'stars' | 'sky' | 'peak' | 'airmass' | 'sensor' | 'focuser';

export interface MetricDef {
  label: string;
  unit: string;
  /** One or two columns (two share one unit: HFD and FWHM in px). */
  cols: Column[];
  /** Names of the columns, for the readout. */
  names: string[];
  digits: number;
  /** Smallest y span drawn, so noise is never blown up to full height. */
  minSpan: number;
  /** Larger values lower (airmass: 1.0 at the top, like altitude). */
  invert?: boolean;
  sub: string;
}

export const METRICS: Record<MetricId, MetricDef> = {
  focus: { label: 'Focus', unit: 'px', cols: ['hfd', 'fwhm'], names: ['HFD', 'FWHM'], digits: 2, minSpan: 0.5, sub: 'HFD and FWHM (green plane), px' },
  stars: { label: 'Stars', unit: '', cols: ['stars'], names: ['Stars'], digits: 0, minSpan: 20, sub: 'stars detected per frame' },
  sky: { label: 'Sky', unit: 'ADU', cols: ['sky'], names: ['Sky'], digits: 0, minSpan: 20, sub: 'median background, ADU' },
  peak: { label: 'Peak', unit: 'ADU', cols: ['peak'], names: ['Peak'], digits: 0, minSpan: 500, sub: 'brightest raw pixel, ADU (full scale 65 535)' },
  airmass: { label: 'Airmass', unit: '', cols: ['airmassMount'], names: ['Airmass'], digits: 3, minSpan: 0.02, invert: true, sub: 'from the mount altitude (as FITS AIRMASS) · 1.0 at the top' },
  sensor: { label: 'Sensor', unit: '°C', cols: ['sensorC'], names: ['Sensor'], digits: 1, minSpan: 1, sub: 'sensor temperature, °C' },
  focuser: { label: 'Focuser', unit: 'steps', cols: ['focuser'], names: ['Focuser'], digits: 0, minSpan: 20, sub: 'focuser position, steps' },
};

export const METRIC_ORDER: MetricId[] = ['focus', 'stars', 'sky', 'peak', 'airmass', 'sensor', 'focuser'];
export const MAX_FACETS = 3;
export const METRICS_KEY = 'argos.conditions.metrics';

const isMetricList = (v: unknown): v is MetricId[] =>
  Array.isArray(v) && v.length >= 1 && v.length <= MAX_FACETS && v.every((m) => METRIC_ORDER.includes(m as MetricId));

export class ConditionsView {
  metrics: MetricId[] = $state(['focus', 'stars', 'sky']);
  /** A zoom the observer chose (kept while frames arrive), or null: the session to now. */
  zoom: [number, number] | null = $state.raw(null);
  private readonly persist: boolean;

  constructor(initial: MetricId[] = ['focus', 'stars', 'sky'], persist = true) {
    this.persist = persist;
    this.metrics = persist ? loadPref(METRICS_KEY, isMetricList, initial) : [...initial];
  }

  /** Add or remove a metric (at least one, at most three, in the fixed order). */
  toggle(id: MetricId): string | null {
    const i = this.metrics.indexOf(id);
    if (i >= 0) {
      if (this.metrics.length === 1) return 'One plot at least';
      this.metrics = this.metrics.filter((m) => m !== id);
    } else {
      if (this.metrics.length >= MAX_FACETS) return 'Three plots at most: hide one first';
      this.metrics = METRIC_ORDER.filter((m) => m === id || this.metrics.includes(m));
    }
    if (this.persist) savePref(METRICS_KEY, this.metrics);
    return null;
  }

  /** F: back to the whole session, running to now. */
  fit(): void {
    this.zoom = null;
  }

  setZoom(a: number, b: number): void {
    if (!(b > a) || !Number.isFinite(a) || !Number.isFinite(b)) return;
    this.zoom = [a, b];
  }
}
