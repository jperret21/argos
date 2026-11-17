import { describe, expect, it } from 'vitest';
import { buildNight, FOCUS_LOSS_FRAME, medianCadence } from './night';
import { evaluate, firstRun, silenceLimit } from './rules';

describe('synthetic night', () => {
  const night = buildNight();

  it('has the real run aggregates: 195 frames, cadence about 51.5 s', () => {
    expect(night).toHaveLength(195);
    expect(medianCadence(night)).toBeGreaterThan(51);
    expect(medianCadence(night)).toBeLessThan(52);
  });

  it('never has two frames in a row with fewer than 3 comparisons before the loss', () => {
    const i = firstRun(night.slice(0, FOCUS_LOSS_FRAME - 1), (r) => r.compsUsed < 3, 2);
    expect(i).toBe(-1);
  });
});

describe('attention rules', () => {
  const night = buildNight();

  it('fires the HFD rule on the third bad frame after the focus loss (frame 150)', () => {
    const items = evaluate(night, { now: night[194].t + 5, running: true });
    const hfd = items.find((a) => a.rule === 'HFD rise');
    expect(hfd?.frame).toBe(FOCUS_LOSS_FRAME + 2);
    expect(hfd?.level).toBe('attention');
  });

  it('raises no HFD item before the loss', () => {
    const before = night.slice(0, FOCUS_LOSS_FRAME + 1);
    const items = evaluate(before, { now: before[before.length - 1].t + 5, running: true });
    expect(items.some((a) => a.rule === 'HFD rise')).toBe(false);
  });

  it('raises no star-count or comparison alarm on this night (as replayed on the real run)', () => {
    const items = evaluate(night, { now: night[194].t + 5, running: true });
    expect(items.some((a) => a.rule === 'Star count drop')).toBe(false);
    expect(items.some((a) => a.rule === 'Comparisons used')).toBe(false);
  });

  it('flags silence only past max(2 x cadence, cadence + 60 s), and only while running', () => {
    const part = night.slice(0, 40);
    const limit = silenceLimit(part);
    expect(limit).toBeGreaterThan(110);
    const last = part[part.length - 1].t;
    expect(evaluate(part, { now: last + limit - 1, running: true }).some((a) => a.level === 'critical')).toBe(false);
    expect(evaluate(part, { now: last + limit + 1, running: true }).some((a) => a.level === 'critical')).toBe(true);
    expect(evaluate(part, { now: last + limit + 1, running: false }).some((a) => a.level === 'critical')).toBe(false);
  });

  it('sorts critical first, then attention, then info', () => {
    const items = evaluate(night, { now: night[194].t + 500, running: true });
    const ranks = items.map((a) => a.level);
    expect(ranks[0]).toBe('critical');
    expect(ranks[ranks.length - 1]).toBe('info');
  });
});
