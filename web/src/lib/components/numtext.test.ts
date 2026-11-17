import { describe, expect, it } from 'vitest';
import { groupInteger, numberRuns } from './numtext';

describe('numberRuns (numbers in Mono inside Sans text)', () => {
  it('finds grouped, decimal, signed and clock numbers', () => {
    const runs = numberRuns('Hold 0.7 s to park · 0 … 10 000 · −1.25° at 13:38:39');
    expect(runs.filter((r) => r.num).map((r) => r.text)).toEqual(['0.7', '0', '10 000', '−1.25', '13:38:39']);
    expect(runs.map((r) => r.text).join('')).toBe('Hold 0.7 s to park · 0 … 10 000 · −1.25° at 13:38:39');
  });

  it('keeps a sentence without numbers whole', () => {
    expect(numberRuns('Ready')).toEqual([{ text: 'Ready', num: false }]);
  });
});

describe('groupInteger (server sentences)', () => {
  it('groups plain integers only', () => {
    expect(groupInteger('5000')).toBe('5\u202f000');
    expect(groupInteger('12450')).toBe('12\u202f450');
    expect(groupInteger('980')).toBe('980');
    expect(groupInteger('5.70')).toBe('5.70');
    expect(groupInteger('13:38')).toBe('13:38');
  });
});
