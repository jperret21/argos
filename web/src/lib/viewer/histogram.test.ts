import { describe, expect, it } from 'vitest';
import { binHistogram, displayRange, quantizationStep } from './histogram';
import { histogram16 } from './stretch';

// Expected values produced by the Python core (numpy 1.26.4):
//   argos.core.imaging.stretch.quantization_step / _histogram_edges, then
//   numpy.histogram, with the preview range [min, percentile 99.8]
//   (argos/workers/preview_processor.py). Generator script:
//   scratchpad webui/integration/hist_ref.py (same arrays as below).

function caseA(): Uint16Array {
  const v: number[] = [];
  for (let i = 0; i < 5000; i++) v.push(1800 + ((i * 7919) % 997) + ((i * 104729) % 13));
  return Uint16Array.from([...v, 60000, 65535, 30000]);
}

function caseB(): Uint16Array {
  const v: number[] = [];
  for (let i = 0; i < 5000; i++) v.push(16 * (((i * 7919) % 211) + 100));
  return Uint16Array.from([...v, 1601, 1703, 2005]);
}

function weighted(counts: Float64Array): number {
  let s = 0;
  counts.forEach((c, i) => (s += i * c));
  return s;
}

describe('binHistogram matches the Qt preview binning', () => {
  it('continuous data: 128 uniform bins over [min, p99.8]', () => {
    const h = histogram16(caseA());
    expect(displayRange(h)).toEqual({ lo: 1800, hi: 2803 });
    const b = binHistogram(h);
    expect(b.step).toBe(1);
    expect(b.counts.length).toBe(128);
    expect(b.edges[0]).toBe(1800);
    expect(b.edges[128]).toBe(2803);
    expect(b.counts.reduce((a, c) => a + c, 0)).toBe(4994); // 3 stars + 6 tail samples dropped
    expect(weighted(b.counts)).toBe(318388);
    expect(Array.from(b.counts.slice(0, 6))).toEqual([15, 36, 40, 41, 39, 40]);
    expect(Array.from(b.counts.slice(-4))).toEqual([40, 40, 40, 29]);
  });

  it('16-ADU quantized data with stray pixels: grid-snapped bins', () => {
    const h = histogram16(caseB());
    expect(quantizationStep(h)).toBe(16);
    const b = binHistogram(h);
    expect(b.lo).toBe(1600);
    expect(b.hi).toBe(4960);
    expect(b.counts.length).toBe(106);
    expect(b.edges[0]).toBe(1592);
    expect(b.edges[106]).toBe(4984);
    expect(b.counts.reduce((a, c) => a + c, 0)).toBe(5003);
    expect(weighted(b.counts)).toBe(261263);
    expect(Array.from(b.counts.slice(0, 6))).toEqual([49, 47, 48, 48, 47, 47]);
    expect(Array.from(b.counts.slice(-4))).toEqual([48, 47, 47, 24]);
    // Every level sits at a bin centre: no comb of empty bins.
    expect(Array.from(b.counts).every((c) => c > 0)).toBe(true);
  });

  it('constant frame: one bin, range widened by one ADU', () => {
    const h = histogram16(new Uint16Array(64).fill(1000));
    expect(displayRange(h)).toEqual({ lo: 1000, hi: 1001 });
    const b = binHistogram(h);
    expect(b.step).toBe(8);
    expect(Array.from(b.edges)).toEqual([996, 1004]);
    expect(Array.from(b.counts)).toEqual([64]);
  });

  it('continuous random data is not mistaken for a grid', () => {
    const data = new Uint16Array(10000);
    for (let i = 0; i < data.length; i++) data[i] = 2000 + ((i * 2654435761) >>> 0) % 401;
    expect(quantizationStep(histogram16(data))).toBe(1);
  });
});
