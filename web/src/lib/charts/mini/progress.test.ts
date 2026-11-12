import { describe, expect, it } from 'vitest';
import { coverageSegments, percentOf, progressText } from './progress';

describe('run progress', () => {
  it('splits the coverage where a frame came past the overdue limit of the cadence', () => {
    // 30 s cadence: overdue after max(60, 90) = 90 s; a 5 min pause splits the run.
    const t = [0, 30, 60, 90, 390, 420, 450];
    expect(coverageSegments(t, t.length)).toEqual([
      [0, 90],
      [390, 450],
    ]);
    expect(coverageSegments(t, 3)).toEqual([[0, 60]]);
    expect(coverageSegments([], 0)).toEqual([]);
    expect(coverageSegments([5], 1)).toEqual([[5, 5]]);
  });

  it('places a time on the bar, held to its ends', () => {
    expect(percentOf(50, 0, 200)).toBe(25);
    expect(percentOf(-10, 0, 200)).toBe(0);
    expect(percentOf(300, 0, 200)).toBe(100);
    expect(percentOf(10, 5, 5)).toBe(0);
  });

  it('says the progress in words', () => {
    expect(progressText(37, 50)).toBe('37 of 50 frames, 74 %');
    expect(progressText(37, 50, 2)).toBe('37 of 50 frames, 74 %, 2 autofocus passes');
    expect(progressText(0, 0)).toBe('0 of 0 frames, 0 %');
  });
});
