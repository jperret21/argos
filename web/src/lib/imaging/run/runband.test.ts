import { describe, expect, it } from 'vitest';
import type { RunBaseline } from '../../api/attention';
import { afText, baselineFrom, baselineMedian, curveRules, latestFinite, metricThreshold, miniLayout, miniWidth, miniWindow, pastThreshold, pickBaseline, ruleKey, ruleSetting, runCounts, runItems, runStarted, runSuggestion, type RunAttention } from './runband';

const item = (p: Partial<RunAttention> & Pick<RunAttention, 'id' | 'rule'>): RunAttention => ({ level: 'attention', since: 1000, active: true, ...p });

describe('Run band: the rules it draws (read-only, the server decides)', () => {
  it('keeps the run on screen: its run id, else raised since it started', () => {
    const items = [item({ id: 'a', rule: 'hfd_rise', runId: 'r1' }), item({ id: 'b', rule: 'hfd_rise', runId: 'r0' }), item({ id: 'c', rule: 'disk', since: 2000 })];
    expect(runItems(items, { run_id: 'r1', started_t: 500 }).map((a) => a.id)).toEqual(['a', 'c']);
    expect(runItems(items, { run_id: null, started_t: 1500 }).map((a) => a.id)).toEqual(['c']);
    expect(runItems(items, null)).toEqual([]);
  });

  it('draws the quality rules on the curve, from the frame where they fired, open while they hold', () => {
    const spans = curveRules([
      item({ id: 'x', rule: 'no_frame', since: 10 }),
      item({ id: 'h', rule: 'hfd_rise', ruleLabel: 'HFD rise', since: 300 }),
      item({ id: 's', rule: 'star_drop', since: 100, active: false, cleared: 250 }),
      item({ id: 'n', rule: 'comps_low', since: null }),
    ]);
    expect(spans).toEqual([
      { id: 's', from: 100, to: 250, label: 'Star count drop' },
      { id: 'h', from: 300, to: null, label: 'HFD rise' },
    ]);
  });

  it('reads the alerts settings with or without their prefix, else the defaults', () => {
    expect(ruleSetting({ hfd_factor: 2 }, 'hfd_factor')).toBe(2);
    expect(ruleSetting({ 'alerts.star_factor': 0.5 }, 'star_factor')).toBe(0.5);
    expect(ruleSetting(null, 'baseline_frames')).toBe(20);
  });

  it('"Change rule…" opens Settings › Alerts on the rule’s own key', () => {
    expect(ruleKey('hfd_rise')).toBe('alerts.hfd_factor');
    expect(ruleKey('star_drop')).toBe('alerts.star_factor');
    expect(ruleKey('comps_low')).toBe('alerts.comparisons_min');
    expect(ruleKey('run_error')).toBe('alerts.sound');
  });

  it('baseline = median of the first B finite values of the run (functional-spaces 4.10)', () => {
    const t = [0, 1, 2, 3, 4, 5, 6];
    const v = [9, 2, NaN, 3, 4, 100, 1];
    expect(baselineMedian(t, v, 7, 1, 3)).toBe(3); // 2, 3, 4
    expect(baselineMedian(t, v, 7, 1, 4)).toBe(3.5); // 2, 3, 4, 100
    expect(baselineMedian(t, v, 7, 5, 3)).toBeNull(); // only 2 values after t = 5
  });

  it('the drawn threshold: the server’s number when its item has one, else factor × baseline', () => {
    const t = Float64Array.from({ length: 30 }, (_, i) => 100 + i);
    const hfd = Float64Array.from({ length: 30 }, (_, i) => (i < 20 ? 2 + (i % 2) * 0.2 : 4));
    const rule = metricThreshold('hfd', [], { hfd_factor: 1.5, baseline_frames: 20 }, { t, v: hfd, n: 30 }, 100)!;
    expect(rule.source).toBe('rule');
    expect(rule.value).toBeCloseTo(1.5 * 2.1, 12);
    expect(rule.text).toBe('rule 1.5 × 2.10 px = 3.15 px');
    const srv = metricThreshold('hfd', [item({ id: 'h', rule: 'hfd_rise', values: { threshold: 3.2 } })], null, { t, v: hfd, n: 30 }, 100)!;
    expect(srv).toEqual({ value: 3.2, source: 'server', text: 'rule 3.20 px' });
    // The server's own values (attention.py hfd_rise / star_drop): baseline × factor, per filter.
    const real = metricThreshold('hfd', [item({ id: 'h2', rule: 'hfd_rise', values: { hfd_px: 23.6, baseline_px: 8.65, ratio: 2.73, factor: 1.5, filter: 'ir' } })], null, { t, v: hfd, n: 30 }, 100)!;
    expect(real.source).toBe('server');
    expect(real.value).toBeCloseTo(12.975, 12);
    expect(real.text).toBe('rule 1.5 × 8.65 px = 12.98 px');
    const stars = metricThreshold('stars', [item({ id: 's', rule: 'star_drop', values: { stars: 40, baseline: 120, ratio: 0.33, factor: 0.7, filter: 'ir' } })], null, { t, v: hfd, n: 30 }, 100)!;
    expect(stars).toEqual({ value: 84, source: 'server', text: 'rule 0.7 × 120 = 84' });
    // Before B subs, no line (the server cannot fire yet either).
    expect(metricThreshold('stars', [], null, { t, v: hfd, n: 10 }, 100)).toBeNull();
    expect(pastThreshold('hfd', 4, rule)).toBe(true);
    expect(pastThreshold('stars', 100, { value: 120, source: 'rule', text: '' })).toBe(true);
    expect(pastThreshold('hfd', null, rule)).toBe(false);
  });

  it('draws the server’s baseline for the run, carried from an earlier run (owner decisions 2026-11-14, 2026-11-15)', () => {
    const t = Float64Array.from({ length: 3 }, (_, i) => 100 + i);
    const hfd = Float64Array.from([9.7, 11.7, 11.4]);
    const RUN_A = Date.UTC(2026, 7, 29, 5, 1, 48) / 1000;
    const fromA = { frames: 20, carried: true, runId: '20260829T050148Z', runT: RUN_A };
    const own = { frames: 20, carried: false, runId: 'r2', runT: RUN_A + 3600 };
    const ir: RunBaseline = { filter: 'IR', hfdPx: 6.55, stars: 1986, hfdFrom: fromA, starsFrom: fromA };
    const lp: RunBaseline = { filter: 'LP', hfdPx: 9, stars: 700, hfdFrom: own, starsFrom: own };
    expect(pickBaseline([ir], null)).toBe(ir); // the only one, the filter not known
    expect(pickBaseline([ir], 'ir')).toBe(ir);
    expect(pickBaseline([ir], 'LP')).toBeNull(); // IR's line on LP subs before the fix
    expect(pickBaseline([ir, lp], 'LP')).toBe(lp);
    expect(pickBaseline([ir, lp], null)).toBeNull();
    expect(pickBaseline([], 'IR')).toBeNull();
    expect(baselineFrom(ir.hfdFrom)).toBe('baseline from the run of 05:01 UTC');
    expect(baselineFrom(lp.hfdFrom)).toBeNull(); // the run's own
    // Each line names its own baseline's origin: the HFD carried, the star count the run's own.
    const mixed: RunBaseline = { ...ir, starsFrom: own, stars: 900 };
    expect(metricThreshold('stars', [], null, { t, v: hfd, n: 3 }, null, mixed)!.text).toBe('rule 0.7 × 900 = 630');
    // 3 subs only: the run's own subs give no line, the carried baseline does (the server judges them).
    expect(metricThreshold('hfd', [], { hfd_factor: 1.5 }, { t, v: hfd, n: 3 }, 100)).toBeNull();
    const th = metricThreshold('hfd', [], { hfd_factor: 1.5 }, { t, v: hfd, n: 3 }, 100, ir)!;
    expect(th.source).toBe('server');
    expect(th.value).toBeCloseTo(9.825, 12);
    expect(th.text).toBe('rule 1.5 × 6.55 px = 9.82 px · baseline from the run of 05:01 UTC');
    const stars = metricThreshold('stars', [], null, { t, v: hfd, n: 3 }, null, lp)!;
    expect(stars.value).toBeCloseTo(490, 9);
    expect(stars).toMatchObject({ source: 'server', text: 'rule 0.7 × 700 = 490' });
    // The item's values say the same origin.
    const values = { hfd_px: 11.1, baseline_px: 6.55, factor: 1.5, baseline_origin: 'earlier_run', baseline_run_utc: '2026-08-29T05:01:48.000Z' };
    const fromItem = metricThreshold('hfd', [item({ id: 'h3', rule: 'hfd_rise', values })], null, { t, v: hfd, n: 3 }, 100, null)!;
    expect(fromItem.text).toBe('rule 1.5 × 6.55 px = 9.82 px · baseline from the run of 05:01 UTC');
  });
});

describe('Run band: mini charts and layout', () => {
  it('the newest finite value', () => {
    expect(latestFinite([1, 2, NaN], 3)).toBe(2);
    expect(latestFinite([NaN], 1)).toBeNull();
  });

  it('the sparklines follow the curve’s view, else the run to now', () => {
    expect(miniWindow([10, 20], 0, 0, 100)).toEqual([10, 20]);
    expect(miniWindow(null, 50, 40, 400)).toEqual([50, 400]);
    expect(miniWindow(null, null, 40, 60)).toEqual([40, 100]); // at least a minute
    expect(miniWindow(null, null, null, 60)).toBeNull();
  });

  it('two-line rows in a full band, one line below; the column only where the curve keeps room', () => {
    expect(miniLayout(263)).toEqual({ kind: 'stack', sparkH: 26 });
    expect(miniLayout(180).kind).toBe('row');
    expect(miniWidth(948)).toBe(216);
    expect(miniWidth(788)).toBe(184);
    expect(miniWidth(500)).toBe(0);
  });

  it('autofocus sweep in words', () => {
    expect(afText({ done: 4, total: 9 })).toBe('Autofocus · 4 of 9');
    expect(afText({ done: 12, total: 9 })).toBe('Autofocus · 9 of 9');
    expect(afText(null)).toBeNull();
  });
});

describe('Run mode is proposed when a run starts, never switched to (D1)', () => {
  it('fires on the transition into a running run only', () => {
    expect(runStarted(null, { state: 'running', run_id: 'a' })).toBe(true);
    expect(runStarted({ state: 'waiting', run_id: 'a' }, { state: 'running', run_id: 'a' })).toBe(true);
    expect(runStarted({ state: 'scheduled', run_id: 'a' }, { state: 'running', run_id: 'a' })).toBe(true);
    expect(runStarted({ state: 'running', run_id: 'a' }, { state: 'paused', run_id: 'a' })).toBe(false);
    expect(runStarted({ state: 'paused', run_id: 'a' }, { state: 'running', run_id: 'a' })).toBe(false);
    expect(runStarted({ state: 'running', run_id: 'a' }, { state: 'running', run_id: 'b' })).toBe(true);
    expect(runStarted({ state: 'running', run_id: 'a' }, { state: 'idle', run_id: null })).toBe(false);
    expect(runStarted(null, null)).toBe(false);
  });

  it('keeps the ended run’s n / N (the record goes back to 0 / 0 when idle)', () => {
    const last_result = { frames_saved: 30, frames_total: 30 } as never;
    expect(runCounts({ state: 'running', frames_done: 12, frames_total: 30, last_result: null }, 12)).toEqual({ done: 12, total: 30 });
    expect(runCounts({ state: 'idle', frames_done: 0, frames_total: 0, last_result }, 30)).toEqual({ done: 30, total: 30 });
    expect(runCounts({ state: 'idle', frames_done: 0, frames_total: 0, last_result: null }, 0)).toEqual({ done: 0, total: 0 });
    expect(runCounts(null, 7)).toEqual({ done: 7, total: 0 });
  });

  it('says what started, in the chip’s few words', () => {
    expect(runSuggestion({ object_name: 'RR Lyr', frames_total: 195 })).toBe('Run started · RR Lyr · 195 frames');
    expect(runSuggestion({ object_name: '', frames_total: 1 })).toBe('Run started · 1 frame');
    expect(runSuggestion({ object_name: null, frames_total: 0 })).toBe('Run started');
  });
});
