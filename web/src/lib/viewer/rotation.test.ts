import { describe, expect, it } from 'vitest';
import {
  displaySize,
  displayToFrame,
  effectiveTurns,
  frameToDisplay,
  overlayMatrix,
  type Turns,
} from './rotation';

// numpy.rot90(np.arange(15).reshape(3, 5), -k).tolist() (what the Qt viewer shows).
const NUMPY_ROT90: Record<1 | 2 | 3, number[][]> = {
  1: [[10, 5, 0], [11, 6, 1], [12, 7, 2], [13, 8, 3], [14, 9, 4]],
  2: [[14, 13, 12, 11, 10], [9, 8, 7, 6, 5], [4, 3, 2, 1, 0]],
  3: [[4, 9, 14], [3, 8, 13], [2, 7, 12], [1, 6, 11], [0, 5, 10]],
};

const W = 5;
const H = 3;
const frame = (x: number, y: number) => y * W + x; // np.arange(15).reshape(3, 5)

function rendered(k: Turns): number[][] {
  const d = displaySize(W, H, k);
  const rows: number[][] = [];
  for (let v = 0; v < d.height; v++) {
    const row: number[] = [];
    for (let u = 0; u < d.width; u++) {
      const p = displayToFrame(u, v, W, H, k);
      row.push(frame(p.x, p.y));
    }
    rows.push(row);
  }
  return rows;
}

describe('display rotation', () => {
  it('auto turns portrait frames a quarter turn clockwise, like the Qt viewer', () => {
    expect(effectiveTurns('auto', 1080, 1920)).toBe(1);
    expect(effectiveTurns('auto', 1920, 1080)).toBe(0);
    expect(effectiveTurns('auto', 100, 100)).toBe(0);
    expect(effectiveTurns('270', 1920, 1080)).toBe(3);
    expect(effectiveTurns('0', 1080, 1920)).toBe(0);
  });

  it.each([1, 2, 3] as const)('k=%i shows numpy.rot90(frame, -k)', (k) => {
    expect(rendered(k)).toEqual(NUMPY_ROT90[k]);
  });

  it('k=0 is the identity', () => {
    expect(rendered(0)).toEqual([
      [0, 1, 2, 3, 4],
      [5, 6, 7, 8, 9],
      [10, 11, 12, 13, 14],
    ]);
  });

  it.each([0, 1, 2, 3] as const)('frameToDisplay inverts displayToFrame (k=%i)', (k) => {
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const d = frameToDisplay(x, y, W, H, k);
        expect(displayToFrame(d.u, d.v, W, H, k)).toEqual({ x, y });
      }
    }
  });

  it.each([0, 1, 2, 3] as const)('the overlay matrix equals frameToDisplay (k=%i)', (k) => {
    const [a, b, c, d, e, f] = overlayMatrix(W, H, k).slice(7, -1).split(' ').map(Number);
    for (const [x, y] of [
      [0, 0],
      [4, 2],
      [1.25, 0.5],
    ]) {
      const want = frameToDisplay(x, y, W, H, k);
      expect(a * x + c * y + e).toBeCloseTo(want.u, 12);
      expect(b * x + d * y + f).toBeCloseTo(want.v, 12);
    }
  });
});
