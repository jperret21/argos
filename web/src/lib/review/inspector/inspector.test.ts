import { describe, expect, it } from 'vitest';
import type { DecodedFrame } from '../../api/frames';
import { ApiError } from '../../api/client';
import type { Job, JobEntry } from '../../app/jobs';
import { frameRows, type FrameRow } from '../frames/frames';
import { binaryFetch, fileFrameInfo, InspectorApi, parseFileLayers, parseFileSolution, parseFitsHeader, parseStarMeasure, type FileSolution, type FitsHeader, type InspectorRequest, type StarMeasure } from './api';
import { APERTURE_MAX, cardsText, catalogueWarning, countsFor, filterCards, frameLines, isAperture, measureView, neighbours, nextReason, prevReason, solutionLines } from './inspect';
import { InspectorStore, type JobsLike } from './inspector.svelte';

const NNBSP = ' ';

const FRAMES = [0, 1, 2, 3].map((i) => ({
  index: i,
  filename: `Light_SW_And_10.0s_IRCUT_2026092${5}-20${String(i).padStart(2, '0')}00.fit`,
  image_type: i === 3 ? 'Dark' : 'Light',
  filter_name: 'IR',
  filter: 'ir',
  exposure_s: 10,
  gain: 80,
  timestamp: `2026-09-25T20:${String(i).padStart(2, '0')}:00`,
  hfd: 2.4,
  fwhm: 2.1,
  star_count: 312,
  sky_adu: 1450,
  peak_adu: 30000,
  eccentricity: 0.31,
  ccd_temp: -2.5,
  path: i === 1 ? null : `/data/s/lights/f${i}.fit`,
  header: { date_obs: null, mid_utc: null, jd_mid: null, airmass: 1.2346, altitude: null, azimuth: null, width: 1080, height: 1920, bayer: 'GRBG' },
}));
const ROWS: FrameRow[] = frameRows(FRAMES);
const LIGHTS = ROWS.filter((r) => r.light && !r.missing); // f0, f2

const CARDS = [
  { key: 'SIMPLE', value: 'True', comment: 'conforms to FITS standard' },
  { key: 'EXPTIME', value: '10.0', comment: 'Exposure time (s)' },
  { key: 'FILTER', value: 'IRCUT', comment: '' },
  { key: 'COMMENT', value: 'written by ARGOS', comment: '' },
];

describe('R2: previous / next', () => {
  it('walks the openable light frames in time order and says why an end is reached', () => {
    const at0 = neighbours(LIGHTS, '/data/s/lights/f0.fit');
    expect(at0.position).toBe('1 / 2');
    expect(at0.prev).toBeNull();
    expect(at0.next?.path).toBe('/data/s/lights/f2.fit');
    expect(prevReason(at0)).toBe('this is the first light frame');
    expect(nextReason(at0)).toBeNull();
    const at2 = neighbours(LIGHTS, '/data/s/lights/f2.fit');
    expect(nextReason(at2)).toBe('this is the last light frame');
    const alone = neighbours(LIGHTS, '/elsewhere/x.fits');
    expect(alone.position).toBeNull();
    expect(prevReason(alone)).toMatch(/not one of the session/);
    expect(neighbours(LIGHTS, null).index).toBe(-1);
  });
});

describe('R2: FITS header card', () => {
  it('filters on every word (key, value, comment) and copies the cards shown', () => {
    expect(filterCards(CARDS, '').length).toBe(4);
    expect(filterCards(CARDS, 'exp time').map((c) => c.key)).toEqual(['EXPTIME']);
    expect(filterCards(CARDS, 'ircut').map((c) => c.key)).toEqual(['FILTER']);
    expect(filterCards(CARDS, 'nothing')).toEqual([]);
    expect(cardsText(CARDS.slice(1))).toBe('EXPTIME = 10.0 / Exposure time (s)\nFILTER  = IRCUT\nCOMMENT written by ARGOS\n');
  });

  it('parses A72 and refuses a malformed answer', () => {
    const h = parseFitsHeader({ path: '/a.fit', file_name: 'a.fit', text: 'SIMPLE = T\nEND', cards: [{ key: 'NAXIS', value: 2, comment: null }, { key: 'X', value: null }], keywords: { EXPTIME: '10', GAIN: null } });
    expect(h.cards).toEqual([
      { key: 'NAXIS', value: '2', comment: '' },
      { key: 'X', value: '', comment: '' },
    ]);
    expect(h.keywords).toEqual({ EXPTIME: '10' });
    expect(() => parseFitsHeader({ cards: [] })).toThrow(/fits-header/);
  });
});

describe('R2: Frame card', () => {
  it('reads the session row first, the header keywords for a file opened alone', () => {
    const row = ROWS[0];
    const lines = frameLines({ width: 1080, height: 1920 }, null, null, row);
    expect(lines[0]).toBe(`1${NNBSP}080 × 1${NNBSP}920 px · Light · IR`);
    expect(lines[1]).toBe('10.0 s · gain 80 · −2.5 °C');
    expect(lines[2]).toBe('2026-09-25 20:00:00 UTC · X 1.235');
    const alone = frameLines({ width: 100, height: 50 }, fileFrameInfo({ image_type: 'Light Frame', filter: 'V', date_obs: '2026-09-07T04:07:25' }), { EXPTIME: '0.5', GAIN: '120', 'CCD-TEMP': '4', AIRMASS: '1.5' }, null);
    expect(alone).toEqual(['100 × 50 px · Light Frame · V', '0.500 s · gain 120 · 4.0 °C', '2026-09-07 04:07:25 UTC · X 1.500']);
    expect(frameLines(null, null, null, null)).toEqual(['—']);
  });

  it('reads A71’s file header (raw unless the server says converted)', () => {
    expect(fileFrameInfo({ raw: false }).raw).toBe(false);
    expect(fileFrameInfo(null).raw).toBe(true);
  });
});

describe('R2: Selected star and Identification cards', () => {
  const found: StarMeasure = parseStarMeasure({
    found: true,
    message: null,
    x: 1024.26,
    y: 2210.84,
    fwhm_px: 4.42,
    hfd_px: 4.9,
    fwhm_arcsec: 6.6,
    hfd_arcsec: 7.3,
    scale_arcsec_px: 1.49,
    scale_source: 'profile',
    eccentricity: 0.21,
    snr: 152.4,
    peak_adu: 23456,
    sky_adu: 1450.2,
    flux: 1e5,
    radius_green_px: 5,
    ra_hours: null,
    dec_deg: null,
  });

  it('shows the measure in frame px, the scale’s source, and asks to identify for RA / Dec', () => {
    const v = measureView(found);
    expect(v.title).toBe(`x 1${NNBSP}024.3 · y 2${NNBSP}210.8`); // grouped as the HUD (BRAND 5)
    // Peak over the sky's σ, not the photometric SNR of the curves (science review).
    expect(v.rows.find((r) => r.label === 'SNR')).toBeUndefined();
    expect(v.rows.find((r) => r.label === 'Peak/σ')?.title).toMatch(/not the aperture photometry SNR/);
    expect(v.rows.find((r) => r.label === 'FWHM')?.value).toBe('4.42 px (6.60″)');
    expect(v.rows.find((r) => r.label === 'Peak')?.value).toBe(`23${NNBSP}456 ADU`);
    expect(v.rows.find((r) => r.label === 'Scale')?.value).toBe('1.49″/px (profile)');
    expect(v.sky).toMatch(/Identify the field/);
    const solved = measureView({ ...found, ra_hours: 19.4428, dec_deg: 42.784, scale_source: 'solution' });
    expect(solved.sky).not.toMatch(/Identify/);
    expect(solved.rows.find((r) => r.label === 'Scale')?.value).toBe('1.49″/px');
  });

  it('says a catalogue failure in one line, the exception in the tooltip', () => {
    const raw = "Gaia DR3 unavailable: Gaia catalogue request failed: HTTPSConnectionPool(host='gea.esac.esa.int', port=443): Max retries exceeded with url: /tap-server/tap/sync (Caused by ConnectTimeoutError(<HTTPSConnection at 0x1203c0650>,";
    expect(catalogueWarning(raw)).toEqual({ short: 'Gaia DR3 unreachable (timeout)', full: raw });
    expect(catalogueWarning('SIMBAD unavailable: Max retries exceeded (NameResolutionError)').short).toBe('SIMBAD unreachable (offline)');
    expect(catalogueWarning('VSX failed: HTTP 503 Service Unavailable').short).toBe('VSX unreachable (HTTP 503)');
  });

  it('says the core’s message when no star is there', () => {
    const v = measureView(parseStarMeasure({ found: false, message: 'No star near (10, 20).' }));
    expect(v.title).toBe('No star near (10, 20).');
    expect(v.rows).toEqual([]);
    expect(() => parseStarMeasure({})).toThrow(/measure-star/);
  });

  it('says the solution: centre, scale, rotation (true minus), mirror, size', () => {
    const s = parseFileSolution({ path: '/a.fit', solution: { ra_hours: 19.4428, dec_deg: 42.784, scale_arcsec_px: 1.49, rotation_deg: -12.34, mirrored: true, frame_shape: [1920, 1080] }, wcs: {}, grid: { lines: [[[0, 0], [1, 1]]], labels: [] } }) as FileSolution;
    const lines = solutionLines(s.solution);
    expect(lines[0].startsWith('RA 19h 26m 34.1s  Dec +42°')).toBe(true);
    expect(lines[1]).toBe(`1.49″/px · rot −12.3° · mirrored · 1${NNBSP}080 × 1${NNBSP}920 px`);
    expect(s.grid?.lines.length).toBe(1);
    expect(parseFileSolution({ solution: { ra_hours: 'x' } })).toBeNull();
    expect(parseFileSolution({ solution: { ra_hours: 1, dec_deg: 2 }, grid: { polylines: [[[0, 0]]] } })?.grid?.lines.length).toBe(1);
  });

  it('keeps the aperture within Qt’s range', () => {
    expect(isAperture(5)).toBe(true);
    expect(isAperture(APERTURE_MAX + 1)).toBe(false);
    expect(isAperture(1)).toBe(false);
    expect(isAperture(4.5)).toBe(false);
  });
});

describe('R2: catalogue layers (A75)', () => {
  it('parses FileLayers, counts what the server sent, keeps the catalogue warnings', () => {
    const l = parseFileLayers({
      path: '/a.fit',
      frame_shape: [1920, 1080],
      display_mag_limit: 15,
      layers: { stars: [{ x: 1, y: 2, g_mag: 12 }, { x: 'bad' }], variables: [{ x: 3, y: 4, name: 'SW And' }] },
      counts: { stars: 1 },
      catalog: { warnings: ['SIMBAD unreachable'] },
    })!;
    expect(l.layers.stars?.length).toBe(1);
    expect(l.counts).toMatchObject({ stars: 1, variables: 1 });
    expect(l.warnings).toEqual(['SIMBAD unreachable']);
    expect(l.frame_shape).toEqual([1920, 1080]);
    const flat = parseFileLayers({ markers: [{ layer: 'vsp', x: 1, y: 1 }, { layer: 'nope', x: 1, y: 1 }] })!;
    expect(flat.counts).toEqual({ vsp: 1 });
    expect(parseFileLayers(null)).toBeNull();
  });

  it('counts are null until the field is identified (the popover says "identify first")', () => {
    expect(countsFor(['stars', 'vsp'] as const, null)).toEqual({ stars: null, vsp: null });
    expect(countsFor(['stars', 'vsp'] as const, { stars: 4 })).toEqual({ stars: 4, vsp: 0 });
  });
});

// -- The routes and the store ------------------------------------------------------------------

function fakeFrame(path: string): DecodedFrame {
  return {
    header: { seq: 1, width: 4, height: 2, channels: 1, dtype: 'uint16', pixel_offset: 0, exposure_s: 10, timestamp: '2026-09-25T20:00:05Z', source: 'file', path, file_name: path.slice(path.lastIndexOf('/') + 1), bayer: 'GRBG', raw: true } as unknown as DecodedFrame['header'],
    pixels: new Uint16Array(8),
    byteLength: 64,
  };
}

const HEADER: FitsHeader = { path: '', file_name: '', text: 'END', cards: CARDS, keywords: {} };

class FakeApi {
  calls: string[] = [];
  failFrame: string | null = null;
  solutionFor: Record<string, FileSolution | null> = {};
  async frame(path: string): Promise<DecodedFrame> {
    this.calls.push(`frame ${path}`);
    if (path === this.failFrame) throw new ApiError(400, 'invalid_fits', 'not a FITS image');
    return fakeFrame(path);
  }
  async header(path: string): Promise<FitsHeader> {
    this.calls.push(`header ${path}`);
    return { ...HEADER, path };
  }
  async solution(path: string): Promise<FileSolution | null> {
    return this.solutionFor[path] ?? null;
  }
  async measure(body: { x: number; y: number; radius?: number; snap?: boolean }): Promise<StarMeasure> {
    this.calls.push(`measure ${body.x},${body.y} r${body.radius} ${body.snap ? 'snap' : 'nosnap'}`);
    return parseStarMeasure({ found: true, x: body.x + 0.5, y: body.y, radius_green_px: body.radius });
  }
  async solve(path: string) {
    this.calls.push(`solve ${path}`);
    return { job_id: 'solve-1', job: { id: 'solve-1', kind: 'file_solve', state: 'running' } };
  }
  async catalogue(path: string) {
    this.calls.push(`catalogue ${path}`);
    return { job_id: 'cat-1', job: { id: 'cat-1', kind: 'file_catalogue', state: 'running' } };
  }
}

class FakeJobs implements JobsLike {
  held: Record<string, JobEntry> = {};
  cancelled: string[] = [];
  get(id: string): JobEntry | null {
    return this.held[id] ?? null;
  }
  ingest(raw: unknown): Job | null {
    const j = raw as Partial<Job> & { id: string };
    this.held[j.id] = { done: 0, total: null, stage: null, message: null, started_utc: null, ended_utc: null, result: null, error: null, cancellable: true, cancel_requested: false, seq: 1, cancelling: false, cancelError: null, ...j } as JobEntry;
    return this.held[j.id];
  }
  async cancel(id: string): Promise<void> {
    this.cancelled.push(id);
  }
}

const SOLUTION = { path: '/data/s/lights/f0.fit', file_name: 'f0.fit', solution: { ra_hours: 19.44, dec_deg: 42.78, scale_arcsec_px: 1.49, rotation_deg: 0, mirrored: false, frame_shape: [2, 4] }, wcs: {}, grid: null };

describe('R2 store', () => {
  function make() {
    const api = new FakeApi();
    const jobs = new FakeJobs();
    const store = new InspectorStore(api as unknown as InspectorApi, jobs, false);
    store.setSession(LIGHTS, 'SW And · 2026-09-25');
    return { api, jobs, store };
  }

  it('opens a file with its header and steps to the next light frame', async () => {
    const { api, store } = make();
    expect(await store.open('/data/s/lights/f0.fit')).toBeNull();
    expect(store.path).toBe('/data/s/lights/f0.fit');
    expect(store.header?.cards.length).toBe(4);
    expect(store.near.position).toBe('1 / 2');
    expect(store.row?.filename).toMatch(/^Light_SW_And/);
    await store.step(1);
    expect(store.path).toBe('/data/s/lights/f2.fit');
    expect(api.calls.filter((c) => c.startsWith('frame'))).toEqual(['frame /data/s/lights/f0.fit', 'frame /data/s/lights/f2.fit']);
    await store.step(1); // the last one: nothing happens
    expect(store.path).toBe('/data/s/lights/f2.fit');
  });

  it('a failed open keeps the previous frame and says why (P28)', async () => {
    const { api, store } = make();
    await store.open('/data/s/lights/f0.fit');
    api.failFrame = '/data/s/lights/f2.fit';
    const why = await store.open('/data/s/lights/f2.fit');
    expect(why).toBe('not a FITS image');
    expect(store.path).toBe('/data/s/lights/f0.fit');
    expect(store.frame?.header).toMatchObject({ path: '/data/s/lights/f0.fit' });
    expect(store.error).toBe('Could not open f2.fit: not a FITS image');
    expect(store.loading).toBeNull();
  });

  it('measures where clicked (snap), re-measures the same star without snap on a new aperture', async () => {
    const { api, store } = make();
    await store.open('/data/s/lights/f0.fit');
    await store.measureAt(10, 20);
    expect(store.measure?.x).toBe(10.5);
    store.setAperture(8);
    await Promise.resolve();
    await Promise.resolve();
    expect(api.calls.filter((c) => c.startsWith('measure'))).toEqual(['measure 10,20 r5 snap', 'measure 10.5,20 r8 nosnap']);
    store.setAperture(99); // out of range: ignored
    expect(store.aperture).toBe(8);
    store.clearMeasure();
    expect(store.measure).toBeNull();
  });

  it('identifies (a job), then fetches the catalogue; a cancel goes to the job', async () => {
    const { api, jobs, store } = make();
    await store.open('/data/s/lights/f0.fit');
    await store.identify();
    expect(store.solveJobId).toBe('solve-1');
    expect(store.solving).toBe(true);
    store.cancelSolve();
    expect(jobs.cancelled).toEqual(['solve-1']);
    store.finishSolve({ ...jobs.get('solve-1')!, state: 'done', result: SOLUTION });
    expect(store.solution?.solution.ra_hours).toBe(19.44);
    await Promise.resolve();
    expect(api.calls).toContain('catalogue /data/s/lights/f0.fit');
    store.finishCatalogue({ ...jobs.get('cat-1')!, state: 'done', result: { path: '/data/s/lights/f0.fit', display_mag_limit: 14.5, layers: { stars: [{ x: 1, y: 1 }] } } });
    expect(store.layers?.counts.stars).toBe(1);
    expect(store.gLimit).toBe(14.5);
  });

  it('a failed or cancelled solve says so; stepping keeps the field wanted and refetches around a kept solution', async () => {
    const { api, jobs, store } = make();
    await store.open('/data/s/lights/f0.fit');
    await store.identify();
    store.finishSolve({ ...jobs.get('solve-1')!, state: 'failed', error: { code: 'not_solved', message: 'ASTAP: no solution' } });
    expect(store.solveError).toBe('ASTAP: no solution');
    store.finishSolve({ ...jobs.get('solve-1')!, state: 'cancelled' });
    expect(store.solveError).toBe('Identification cancelled.');
    api.solutionFor['/data/s/lights/f2.fit'] = parseFileSolution({ ...SOLUTION, path: '/data/s/lights/f2.fit' });
    await store.step(1);
    expect(store.solveError).toBeNull();
    expect(store.solution?.path).toBe('/data/s/lights/f2.fit');
    await Promise.resolve();
    expect(api.calls).toContain('catalogue /data/s/lights/f2.fit');
  });

  it('stretch: manual levels stay, Auto toggles, Reset is linear', () => {
    const { store } = make();
    store.autoLevels = { mode: 'linear', black: 0.1, white: 0.9, mid: 0.5 } as never;
    expect(store.levels).toEqual(store.autoLevels);
    store.setLevel({ black: 0.2 } as never);
    expect(store.autoStretch).toBe(false);
    expect((store.levels as unknown as { black: number }).black).toBe(0.2);
    store.toggleAuto();
    expect(store.autoStretch).toBe(true);
    store.resetStretch();
    expect(store.autoStretch).toBe(false);
  });
});

describe('R2 routes', () => {
  it('requests A71-A75 at the contract’s paths; a 404 solution is null', async () => {
    const seen: string[] = [];
    const client: InspectorRequest = {
      async request<T>(method: string, path: string, body?: unknown): Promise<T> {
        seen.push(`${method} ${path}${body ? ` ${JSON.stringify(body)}` : ''}`);
        if (path.startsWith('/api/files/solution')) throw new ApiError(404, 'not_found', 'never solved');
        if (path.startsWith('/api/files/fits-header')) return { text: 'END', cards: [] } as T;
        if (path === '/api/files/measure-star') return { found: false, message: 'No star near (1, 2).' } as T;
        return { job_id: 'j', job: {} } as T;
      },
    };
    const bin: string[] = [];
    const api = new InspectorApi(client, async (p) => {
      bin.push(p);
      throw new ApiError(400, 'invalid_fits', 'x');
    });
    const p = '/data/s/lights/a b.fit';
    await expect(api.frame(p)).rejects.toThrow('x');
    expect(bin).toEqual(['/api/files/frame?path=%2Fdata%2Fs%2Flights%2Fa%20b.fit&view=raw']);
    await api.header(p);
    expect(await api.solution(p)).toBeNull();
    expect((await api.measure({ path: p, x: 1, y: 2 })).found).toBe(false);
    expect((await api.solve(p)).job_id).toBe('j');
    await api.catalogue(p);
    expect(seen).toEqual([
      'GET /api/files/fits-header?path=%2Fdata%2Fs%2Flights%2Fa%20b.fit',
      'GET /api/files/solution?path=%2Fdata%2Fs%2Flights%2Fa%20b.fit',
      `POST /api/files/measure-star {"path":"${p}","x":1,"y":2}`,
      `POST /api/files/solve {"path":"${p}"}`,
      `POST /api/files/catalogue {"path":"${p}"}`,
    ]);
  });

  it('the binary fetch sends the token and turns an HTTP error into an ApiError', async () => {
    let auth = '';
    const ok = binaryFetch({ apiBase: 'http://h:1', token: 't0k' }, async (_url, init) => {
      auth = String((init?.headers as Record<string, string>).Authorization);
      return new Response(new Uint8Array([1, 2, 3]));
    });
    expect((await ok('/api/files/frame?path=x')).byteLength).toBe(3);
    expect(auth).toBe('Bearer t0k');
    const bad = binaryFetch({ apiBase: 'http://h:1', token: 't' }, async () => new Response(JSON.stringify({ error: { code: 'invalid_fits', message: 'too large' } }), { status: 400 }));
    await expect(bad('/x')).rejects.toMatchObject({ status: 400 });
    const down = binaryFetch({ apiBase: 'http://h:1', token: 't' }, async () => {
      throw new TypeError('fetch failed');
    });
    await expect(down('/x')).rejects.toThrow(/Cannot reach the ARGOS server/);
  });
});
