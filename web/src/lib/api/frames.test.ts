import { describe, expect, it } from 'vitest';
import { decodeFrame, encodeFrame, FrameDecodeError } from './frames';
import type { FrameHeader } from './types';

/**
 * Build a /ws/frames message byte by byte, independently of encodeFrame():
 * uint32 LE header length, JSON, padding to `pixelOffset`, uint16 LE samples.
 * The padding is filled with 0xEE to prove the decoder never reads it.
 */
function buildMessage(
  header: Record<string, unknown>,
  samples: number[],
  pixelOffset?: number,
  extraTail = 0,
): ArrayBuffer {
  // Find a stable pixel_offset (its digits are part of the header length).
  let offset = pixelOffset ?? 0;
  let json = '';
  for (let i = 0; i < 4; i++) {
    json = JSON.stringify({ ...header, pixel_offset: offset });
    if (pixelOffset !== undefined) break;
    const next = Math.ceil((4 + json.length) / 8) * 8;
    if (next === offset) break;
    offset = next;
  }
  const bytes = new Uint8Array(offset + samples.length * 2 + extraTail);
  const n = json.length; // ASCII-only JSON in these tests
  bytes[0] = n & 0xff;
  bytes[1] = (n >>> 8) & 0xff;
  bytes[2] = (n >>> 16) & 0xff;
  bytes[3] = (n >>> 24) & 0xff;
  for (let i = 0; i < n; i++) bytes[4 + i] = json.charCodeAt(i);
  bytes.fill(0xee, 4 + n, offset);
  samples.forEach((v, i) => {
    bytes[offset + 2 * i] = v & 0xff; // little-endian: low byte first
    bytes[offset + 2 * i + 1] = v >>> 8;
  });
  return bytes.buffer;
}

const baseHeader = {
  seq: 42,
  width: 3, // odd width on purpose (UNPACK_ALIGNMENT matters on upload)
  height: 2,
  channels: 1,
  dtype: 'uint16',
  exposure_s: 2.5,
  timestamp: '2026-11-01T21:04:05.123Z',
  source: 'simulator',
  stats: { min: 0, max: 65535, median: 1104, mad: 16, mean: 12000.5 },
};

describe('decodeFrame', () => {
  it('reads the header, honours padding and decodes little-endian samples', () => {
    const samples = [0x1234, 0, 65535, 1104, 0xabcd, 1];
    const buf = buildMessage(baseHeader, samples);
    const frame = decodeFrame(buf);

    expect(frame.header.seq).toBe(42);
    expect(frame.header.width).toBe(3);
    expect(frame.header.height).toBe(2);
    expect(frame.header.channels).toBe(1);
    expect(frame.header.exposure_s).toBe(2.5);
    expect(frame.header.stats.mad).toBe(16);
    expect(frame.header.pixel_offset % 8).toBe(0);
    expect(frame.byteLength).toBe(buf.byteLength);
    expect(Array.from(frame.pixels)).toEqual(samples);
    // 0x1234 was sent as bytes 34 12: a big-endian read would give 0x3412.
    expect(frame.pixels[0]).toBe(0x1234);
  });

  it('is zero-copy: pixels view the message buffer at pixel_offset', () => {
    const buf = buildMessage(baseHeader, [1, 2, 3, 4, 5, 6]);
    const frame = decodeFrame(buf);
    expect(frame.pixels.buffer).toBe(buf);
    expect(frame.pixels.byteOffset).toBe(frame.header.pixel_offset);
    expect(frame.pixels.length).toBe(6);
  });

  it('accepts a larger-than-minimal padding and ignores trailing bytes', () => {
    const buf = buildMessage(baseHeader, [7, 8, 9, 10, 11, 12], 512, 6);
    const frame = decodeFrame(buf);
    expect(frame.header.pixel_offset).toBe(512);
    expect(Array.from(frame.pixels)).toEqual([7, 8, 9, 10, 11, 12]);
  });

  it('keeps RGB samples interleaved, row 0 first', () => {
    // 2x1 RGB: (r,g,b) of pixel (0,0) then pixel (1,0).
    const buf = buildMessage({ ...baseHeader, width: 2, height: 1, channels: 3 }, [10, 20, 30, 40, 50, 60]);
    const frame = decodeFrame(buf);
    expect(frame.header.channels).toBe(3);
    expect(Array.from(frame.pixels)).toEqual([10, 20, 30, 40, 50, 60]);
  });

  it('decodes a UTF-8 header (non-ASCII in a string field)', () => {
    const header: Omit<FrameHeader, 'pixel_offset'> = {
      ...(baseHeader as unknown as FrameHeader),
      timestamp: '2026-11-01T21:04:05Z',
      source: 'file',
    };
    const extra = { ...header, note: 'Céphée δ' } as unknown as Omit<FrameHeader, 'pixel_offset'>;
    const frame = decodeFrame(encodeFrame(extra, Uint16Array.from([1, 2, 3, 4, 5, 6])));
    expect((frame.header as unknown as { note: string }).note).toBe('Céphée δ');
    expect(Array.from(frame.pixels)).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it('round-trips encodeFrame', () => {
    const px = Uint16Array.from({ length: 5 * 3 }, (_, i) => i * 4099);
    const frame = decodeFrame(
      encodeFrame({ ...(baseHeader as unknown as FrameHeader), width: 5, height: 3 }, px),
    );
    expect(Array.from(frame.pixels)).toEqual(Array.from(px));
    expect(frame.header.pixel_offset % 8).toBe(0);
  });

  describe('rejects malformed messages', () => {
    const bad: Array<[string, () => ArrayBuffer]> = [
      ['shorter than the length prefix', () => new ArrayBuffer(3)],
      [
        'header length beyond the message',
        () => {
          const b = new Uint8Array(16);
          new DataView(b.buffer).setUint32(0, 1000, true);
          return b.buffer;
        },
      ],
      [
        'invalid JSON',
        () => {
          const b = new Uint8Array(16);
          new DataView(b.buffer).setUint32(0, 4, true);
          b.set([0x7b, 0x7b, 0x7b, 0x7b], 4); // "{{{{"
          return b.buffer;
        },
      ],
      ['pixel_offset not a multiple of 8', () => buildMessage(baseHeader, [1, 2, 3, 4, 5, 6], 250)],
      ['pixel_offset inside the header', () => buildMessage(baseHeader, [1, 2, 3, 4, 5, 6], 8)],
      ['truncated pixel data', () => buildMessage(baseHeader, [1, 2, 3, 4, 5])],
      ['unsupported dtype', () => buildMessage({ ...baseHeader, dtype: 'float32' }, [1, 2, 3, 4, 5, 6])],
      ['bad channel count', () => buildMessage({ ...baseHeader, channels: 2 }, new Array(12).fill(0))],
      ['zero width', () => buildMessage({ ...baseHeader, width: 0 }, [])],
    ];
    for (const [name, make] of bad) {
      it(name, () => {
        expect(() => decodeFrame(make())).toThrow(FrameDecodeError);
      });
    }
  });
});
