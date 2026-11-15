import { describe, expect, it } from 'vitest';
import { ELLIPSIS, middleEllipsis, middleName } from './path';

const BUNDLE = '/Users/observer/Desktop/argos-support-0.5.0-20261102T202437Z.zip';

describe('middleEllipsis', () => {
  it('leaves a path that fits alone', () => {
    expect(middleEllipsis('/tmp/a.zip', 20)).toBe('/tmp/a.zip');
  });

  it('cuts the middle and keeps the file name whole', () => {
    const s = middleEllipsis(BUNDLE, 50);
    expect(s.length).toBeLessThanOrEqual(50);
    expect(s.endsWith('/argos-support-0.5.0-20261102T202437Z.zip')).toBe(true);
    expect(s).toContain(ELLIPSIS);
    expect(s.startsWith('/')).toBe(true);
  });

  it('keeps the folder next to the name when it fits', () => {
    expect(middleEllipsis(BUNDLE, 55)).toBe(`/${ELLIPSIS}/Desktop/argos-support-0.5.0-20261102T202437Z.zip`);
    expect(middleEllipsis(BUNDLE, 63)).toBe(`/Users/${ELLIPSIS}/Desktop/argos-support-0.5.0-20261102T202437Z.zip`);
    expect(middleEllipsis('C:\\Users\\me\\Desktop\\a-long-name.zip', 30)).toBe(`C:\\${ELLIPSIS}\\Desktop\\a-long-name.zip`);
  });

  it('cuts the start of the name only when the name alone is too long', () => {
    const s = middleEllipsis(BUNDLE, 20);
    expect(s).toHaveLength(20);
    expect(s.startsWith(ELLIPSIS)).toBe(true);
    expect(s.endsWith('T202437Z.zip')).toBe(true);
  });

  it('never returns more than asked', () => {
    for (let max = 0; max < BUNDLE.length + 2; max++) {
      expect(middleEllipsis(BUNDLE, max).length, String(max)).toBeLessThanOrEqual(Math.max(0, max));
    }
  });
});

describe('middleName', () => {
  it('keeps the start and the frame number of a long file name', () => {
    expect(middleName('RR_Lyr_ir_light_e010000ms_g080_00010.fit', 32)).toBe(`RR_Lyr_ir_light_e0100${ELLIPSIS}_00010.fit`);
    expect(middleName('RR_Lyr_ir_light_e010000ms_g080_00010.fit', 32)).toHaveLength(32);
    expect(middleName('short.fit', 32)).toBe('short.fit');
  });
});
