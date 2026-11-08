import { describe, expect, it } from 'vitest';
import { seconds } from '../format/number';
import { cursorReadout, frameChips, miniHistogram, showMiniHistogram, utcTime, type FrameHeaderV3 } from './hud';
import { histogram16 } from './stretch';

const header = (extra: Partial<FrameHeaderV3> = {}): FrameHeaderV3 => ({
  seq: 1234,
  width: 1080,
  height: 1920,
  channels: 1,
  dtype: 'uint16',
  pixel_offset: 256,
  exposure_s: 2,
  timestamp: '2026-11-08T21:34:05.123Z',
  source: 'simulator',
  stats: { min: 1, max: 2, median: 1, mad: 1, mean: 1 },
  ...extra,
});

const ids = (c: { id: string }[]) => c.map((x) => x.id);

describe('image HUD', () => {
  it('describes the frame on screen: state, number, exposure, filter, type, object, time', () => {
    const chips = frameChips(
      { header: header({ origin: 'live', filter: 'IR', frame_type: 'light' }), live: true, exposing: false, stale: false, object: 'RR Lyr' },
      seconds,
    );
    expect(ids(chips)).toEqual(['state', 'seq', 'exposure', 'filter', 'object', 'time']);
    expect(chips[0]).toMatchObject({ text: 'Live', dot: 'live' });
    expect(chips[1].text).toBe('#1\u202f234');
    expect(chips[2].text).toBe(seconds(2));
    expect(chips.at(-1)?.text).toBe('21:34:05 UTC');
    // A Dark frame names its type; Light is the default and is not repeated.
    const dark = frameChips({ header: header({ origin: 'single', frame_type: 'dark', filter: 'Dark' }), live: false, exposing: false, stale: false }, seconds);
    expect(dark.find((c) => c.id === 'type')?.text).toBe('Dark frame'); // never 'Dark · Dark' with the filter chip
    expect(dark[0].text).toBe('Shot');
  });

  it('says when the frame is not current, and marks a saved frame and a crop', () => {
    const chips = frameChips({ header: header(), live: true, exposing: false, stale: true, savedName: 'RR_Lyr_IR_Light_e2000ms_g80_1.fit', cropped: true }, seconds);
    expect(chips[0]).toMatchObject({ text: 'Last frame', muted: true });
    expect(chips.find((c) => c.id === 'saved')?.title).toBe('RR_Lyr_IR_Light_e2000ms_g80_1.fit');
    expect(chips.at(-1)?.id).toBe('crop');
  });

  it('dates an opened file from its exposure midpoint and names the file', () => {
    const chips = frameChips(
      { header: header({ source: 'file', origin: 'file', file_name: 'a.fit', path: '/tmp/a.fit', epoch_utc: '2026-09-25T20:05:01Z' }), live: false, exposing: false, stale: false, object: 'ignored' },
      seconds,
    );
    expect(chips[0].text).toBe('File');
    expect(chips.find((c) => c.id === 'file')?.title).toBe('/tmp/a.fit');
    expect(chips.find((c) => c.id === 'object')).toBeUndefined();
    expect(chips.find((c) => c.id === 'time')?.text).toBe('20:05:01 UTC');
    expect(utcTime(null)).toBe('—');
  });

  it('reads the cursor in frame px and raw ADU; RA / Dec only with a WCS', () => {
    expect(cursorReadout(null)).toBeNull();
    expect(cursorReadout({ x: 512, y: 1001, value: 1834 })).toEqual({ x: '512', y: '1\u202f001', value: '1\u202f834', ra: null, dec: null });
    expect(cursorReadout({ x: 1, y: 2, value: [1820, 1834, 1790] }, { ra: '18h 35m 12s', dec: '+42° 47′' })?.value).toBe('R 1\u202f820 · G 1\u202f834 · B 1\u202f790');
  });

  it('bins a 64-bin mini histogram with the levels, shown only when the band does not show the levels', () => {
    const px = new Uint16Array(10000);
    for (let i = 0; i < px.length; i++) px[i] = 1000 + (i % 200);
    const m = miniHistogram(histogram16(px), { black: 1000, white: 1199, midtones: 0.5, mode: 'linear' })!;
    expect(m.counts.length).toBeLessThanOrEqual(64);
    expect(m.black).toBeCloseTo(0, 1);
    expect(m.white).toBeGreaterThan(0.9);
    expect(showMiniHistogram('framing', true)).toBe(false);
    expect(showMiniHistogram('framing', false)).toBe(true);
    expect(showMiniHistogram('focus', true)).toBe(true);
  });
});

describe('HUD after autofocus (review of wave 3)', () => {
  it('keeps the busy dot on an AF sample only while the sweep runs', () => {
    const h = { seq: 9, exposure_s: 1, timestamp: '2026-11-08T13:38:00Z', origin: 'autofocus' } as unknown as Parameters<typeof frameChips>[0]['header'];
    const running = frameChips({ header: h, live: false, exposing: false, stale: false, afRunning: true }, (s) => `${s} s`);
    expect(running[0]).toMatchObject({ text: 'AF', dot: 'busy' });
    const ended = frameChips({ header: h, live: false, exposing: false, stale: false, afRunning: false }, (s) => `${s} s`);
    expect(ended[0].dot).toBeUndefined();
    expect(ended[0].muted).toBe(true);
  });
});
