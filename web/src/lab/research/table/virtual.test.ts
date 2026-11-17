import { describe, expect, it } from 'vitest';
import { rowWindow, scrollToRow } from './virtual';

describe('rowWindow (lab virtual table)', () => {
  it('renders the visible rows plus overscan, never past the ends', () => {
    expect(rowWindow(0, 240, 24, 10000, 6)).toEqual({ start: 0, end: 17, offset: 0, total: 240000 });
    const w = rowWindow(2400, 240, 24, 10000, 6);
    expect(w.start).toBe(94);
    expect(w.end).toBe(117);
    expect(w.offset).toBe(94 * 24);
  });

  it('clamps an over-scrolled position and tiny tables', () => {
    expect(rowWindow(1e9, 240, 24, 100, 6).end).toBe(100);
    expect(rowWindow(0, 240, 24, 3, 6)).toEqual({ start: 0, end: 3, offset: 0, total: 72 });
    expect(rowWindow(0, 240, 24, 0)).toEqual({ start: 0, end: 0, offset: 0, total: 0 });
  });

  it('keeps the DOM size constant whatever the row count', () => {
    const a = rowWindow(5000, 600, 24, 1000);
    const b = rowWindow(5000, 600, 24, 1000000);
    expect(a.end - a.start).toBe(b.end - b.start);
  });
});

describe('scrollToRow', () => {
  it('scrolls only when the row is out of view', () => {
    expect(scrollToRow(5, 0, 240, 24)).toBe(0);
    expect(scrollToRow(20, 0, 240, 24)).toBe(21 * 24 - 240);
    expect(scrollToRow(2, 240, 240, 24)).toBe(48);
  });
});
