import { describe, expect, it } from 'vitest';
import { attentionApi, checkAttentionBatch, checkAttentionItem, ruleWords, timeOf } from './attention';

const WIRE = {
  id: 'hfd_rise-152',
  level: 'attention',
  rule: 'hfd_rise',
  title: 'HFD 17.5 px = 2.0× the first 20 frames',
  short: 'HFD 17.5 px · 2.0× baseline',
  detail: 'Rule: HFD above 1.5 × 8.65 px for 3 frames in a row (17.5, 17.6, 23.6 px, frames 150-152).',
  since_utc: '2026-09-25T22:16:14Z',
  frame: 152,
  run_id: 'r1',
  values: { hfd: 17.5, baseline: 8.65 },
};

describe('attention items on the wire', () => {
  it("reads the server's item (protocol.md AttentionItem)", () => {
    const a = checkAttentionItem({
      ...WIRE,
      name: 'HFD rise',
      kind: 'condition',
      cause: 'hfd_rise:IR',
      since: '2026-09-25T22:16:14Z',
      since_utc: undefined,
      raised_utc: '2026-09-25T22:16:20Z',
      action: { to: 'devices', label: 'Devices' },
      cleared_utc: null,
      cleared_reason: null,
      acked: false,
      occurrences: 2,
      sound: true,
      repeat_s: null,
    })!;
    expect(a.ruleLabel).toBe('HFD rise');
    expect(a.since).toBe(Date.parse('2026-09-25T22:16:14Z') / 1000);
    expect(a.action).toEqual({ to: 'devices', label: 'Devices' });
    expect(a).toMatchObject({ kind: 'condition', occurrences: 2, sound: true, repeatS: null, active: true, cleared: null });
    expect(checkAttentionItem({ ...WIRE, kind: 'event', cleared_utc: '2026-09-25T22:30:00Z', cleared_reason: 'acknowledged', active: false })).toMatchObject({ kind: 'event', clearedReason: 'acknowledged', active: false });
  });

  it('reads a full item and normalises times to unix seconds', () => {
    const a = checkAttentionItem(WIRE)!;
    expect(a.id).toBe('hfd_rise-152');
    expect(a.level).toBe('attention');
    expect(a.ruleLabel).toBe('HFD rise');
    expect(a.since).toBe(Date.parse('2026-09-25T22:16:14Z') / 1000);
    expect(a.frame).toBe(152);
    expect(a.active).toBe(true);
    expect(a.acked).toBe(false);
    expect(a.action).toBeNull();
    expect(a.values).toEqual({ hfd: 17.5, baseline: 8.65 });
  });

  it('refuses an item without id, level or text (never guessed)', () => {
    expect(checkAttentionItem({ ...WIRE, id: '' })).toBeNull();
    expect(checkAttentionItem({ ...WIRE, level: 'warning' })).toBeNull();
    expect(checkAttentionItem({ ...WIRE, title: undefined })).toBeNull();
    expect(checkAttentionItem(null)).toBeNull();
    expect(checkAttentionItem([WIRE])).toBeNull();
  });

  it('takes `message` for the title and the title for a missing headline', () => {
    const a = checkAttentionItem({ id: 'x', level: 'critical', rule: 'no_frame', message: 'No new frame for 140 s' })!;
    expect(a.title).toBe('No new frame for 140 s');
    expect(a.short).toBe('No new frame for 140 s');
    expect(a.ruleLabel).toBe('No frame');
    expect(a.since).toBeNull();
  });

  it('reads acknowledgement and clearing in any of the accepted forms', () => {
    expect(checkAttentionItem({ ...WIRE, acked: true })!.acked).toBe(true);
    expect(checkAttentionItem({ ...WIRE, acked_by: 'client-2' })!.acked).toBe(true);
    const a = checkAttentionItem({ ...WIRE, acked_utc: '2026-09-25T22:20:00Z' })!;
    expect(a.acked).toBe(true);
    expect(a.ackedAt).toBe(Date.parse('2026-09-25T22:20:00Z') / 1000);
    const c = checkAttentionItem({ ...WIRE, cleared_utc: '2026-09-25T22:30:00Z' })!;
    expect(c.active).toBe(false);
    expect(checkAttentionItem({ ...WIRE, active: false })!.active).toBe(false);
  });

  it('keeps a known action target and drops an unknown one', () => {
    expect(checkAttentionItem({ ...WIRE, action: { to: 'focus', label: 'Focus mode' } })!.action).toEqual({ to: 'focus', label: 'Focus mode' });
    expect(checkAttentionItem({ ...WIRE, action: { to: 'somewhere' } })!.action).toBeNull();
    expect(checkAttentionItem({ ...WIRE, action: { to: 'field' } })!.action).toEqual({ to: 'field', label: 'Field' });
  });

  it('reads one item, a replay and the REST answer', () => {
    expect(checkAttentionBatch({ type: 'attention', item: WIRE })).toMatchObject({ replace: false, revision: null, items: [{ id: 'hfd_rise-152' }] });
    const replay = checkAttentionBatch({ type: 'attention', active: [WIRE], history: [{ ...WIRE, id: 'old', level: 'info', title: 'Run started' }] })!;
    expect(replay.replace).toBe(true);
    expect(replay.items.map((a) => a.id).sort()).toEqual(['hfd_rise-152', 'old']);
    // A later view of an id wins over the history's copy.
    const both = checkAttentionBatch({ history: [{ ...WIRE, acked: false }], active: [{ ...WIRE, acked: true }] })!;
    expect(both.items).toHaveLength(1);
    expect(both.items[0].acked).toBe(true);
    expect(checkAttentionBatch({ items: [] })).toEqual({ items: [], replace: true, revision: null, sound: null, unacked: null, thresholds: null });
    expect(checkAttentionBatch({ type: 'attention' })).toBeNull();
    // The snapshot's sound and thresholds in force (protocol.md AttentionState).
    const snap = checkAttentionBatch({ active: [], history: [], counts: { critical: 0, attention: 0, info: 0, unacked: 0 }, sound: { level: 'soft', info: true, repeat_s: 0 }, thresholds: { 'alerts.hfd_factor': 1.5, 'alerts.baseline_frames': 20 }, revision: 7 })!;
    expect(snap).toMatchObject({ revision: 7, unacked: 0, sound: { level: 'soft', info: true, repeatS: 0 }, thresholds: { 'alerts.hfd_factor': 1.5, 'alerts.baseline_frames': 20 } });
  });

  it('words a rule id when the server sends no label', () => {
    expect(ruleWords('hfd_rise')).toBe('HFD rise');
    expect(ruleWords('too_few_comparisons')).toBe('Too few comparisons');
    expect(ruleWords('star-count-drop')).toBe('Star count drop');
  });

  it('reads ISO and numeric times, never invents one', () => {
    expect(timeOf(1_790_000_000)).toBe(1_790_000_000);
    expect(timeOf('nope')).toBeNull();
    expect(timeOf(Number.NaN)).toBeNull();
    expect(timeOf(undefined)).toBeNull();
  });
});

describe('attention routes', () => {
  it('lists and acknowledges through the client (the id is escaped)', async () => {
    const calls: [string, string, unknown][] = [];
    const client = {
      request: async <T,>(method: string, path: string, body?: unknown): Promise<T> => {
        calls.push([method, path, body]);
        if (method === 'GET') return { active: [WIRE], history: [], revision: 4, counts: { unacked: 1 }, sound: { level: 'soft', info: false, repeat_s: 30 } } as T;
        return { active: [{ ...WIRE, id: 'a/b', acked: true }], history: [], revision: 5 } as T;
      },
    };
    const list = await attentionApi.list(client);
    expect(list).toMatchObject({ replace: true, revision: 4, unacked: 1, sound: { level: 'soft', info: false, repeatS: 30 } });
    expect(list?.items).toHaveLength(1);
    const after = await attentionApi.ack(client, 'a/b', 'laptop');
    expect(after?.items[0].acked).toBe(true);
    await attentionApi.ackAll(client);
    expect(calls[0]).toEqual(['GET', '/api/attention', undefined]);
    expect(calls[1]).toEqual(['POST', '/api/attention/a%2Fb/ack', { by: 'laptop' }]);
    expect(calls[2]).toEqual(['POST', '/api/attention/ack-all', {}]);
  });
});
