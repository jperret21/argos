/**
 * Synthetic Review sessions in the A68 / A69 wire shapes as argos/server/review.py writes them
 * (protocol.md "Review (wave 7)": ReviewSession, CurveSet), for the gallery,
 * the vitest checks and the large-session check. No real data and no personal metadata:
 * the star names and AUIDs are invented ("SW And", "000-AAA-…"), the observer code is the
 * fake "XYZ", no site is given.
 *
 * - An RR Lyrae light curve (period 0.4423 d, 0.9 mag sawtooth) for the target, a check star
 *   constant at its catalogue V + a small offset, comparisons with their own noise and one
 *   "noisy" comparison; errors 0.008-0.02 mag with a σ_sys floor; BJD = JD + 0.00236 d.
 * - Frames every `cadence` s with HFD / FWHM / stars / sky, an HFD episode, a gap, missing
 *   FITS, suspect and saturated points at fixed rows (S56: suspect drawn hollow).
 * - Two filters (S49 keys "<AUID>@<token>") when asked.
 */

export interface SessionOpts {
  n?: number;
  /** Seconds between frames. */
  cadence?: number;
  exposure?: number;
  comps?: number;
  check?: boolean;
  filters?: string[];
  /** Start, unix s. */
  start?: number;
  seed?: number;
  gapAt?: number | null;
  gapS?: number;
  hfdEpisodeAt?: number | null;
  missing?: number[];
  suspect?: number[];
  saturated?: number[];
  /** No `filter` on the curves (a CSV written before 0.5.0). */
  legacy?: boolean;
  /** No BJD (the site was not set). */
  noBjd?: boolean;
  /** Frames carry the header AIRMASS (and the CSV's is off: a wrong Settings site, A68 `airmass_source: "header"`). */
  headerAirmass?: boolean;
  /** Rows whose frame the flight recorder flags (zp_outlier on every star; the target 1.2 mag off). */
  zpOutlier?: number[];
  /** Write the vetting report. */
  quality?: boolean;
  object?: string;
}

export const FIX_START = Date.UTC(2026, 10, 1, 20, 0, 0) / 1000;
const JD_UNIX = 2440587.5;

function rng(seed: number): () => number {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13;
    s ^= s >>> 17;
    s ^= s << 5;
    return (s >>> 0) / 4294967296;
  };
}
function gauss(r: () => number): number {
  const u = Math.max(1e-12, r());
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * r());
}

/** RR Lyrae-like phase curve (fast rise, slow decline), magnitude offset from the mean. */
function rrl(phase: number): number {
  const p = ((phase % 1) + 1) % 1;
  return p < 0.15 ? 0.45 - (p / 0.15) * 0.9 : -0.45 + ((p - 0.15) / 0.85) * 0.9;
}

const round = (v: number, d: number) => Math.round(v * 10 ** d) / 10 ** d;

export interface SessionFixture {
  path: string;
  session: Record<string, unknown>;
  /** A69 CurveSet: the curves, their problems and the rest as the server writes it. */
  curves: { curves: Record<string, unknown>[]; problems: string[] } & Record<string, unknown>;
}

export function makeSession(o: SessionOpts = {}): SessionFixture {
  const n = o.n ?? 240;
  const cadence = o.cadence ?? 30;
  const exposure = o.exposure ?? 10;
  const ncomp = o.comps ?? 5;
  const filters = o.filters ?? ['ir'];
  const start = o.start ?? FIX_START;
  const r = rng(o.seed ?? 7);
  const object = o.object ?? 'SW And';
  const gapAt = o.gapAt === undefined ? Math.floor(n * 0.55) : o.gapAt;
  const gapS = o.gapS ?? 1200;
  const hfdAt = o.hfdEpisodeAt === undefined ? Math.floor(n * 0.3) : o.hfdEpisodeAt;
  const suspect = new Set(o.suspect ?? [Math.floor(n * 0.2), Math.floor(n * 0.71)]);
  const saturated = new Set(o.saturated ?? [Math.floor(n * 0.42)]);
  const missing = new Set(o.missing ?? [3, 4]);
  const zpOut = new Set(o.zpOutlier ?? []);

  // Frame start times, all filters interleaved (one frame per filter in turn).
  const frames: Record<string, unknown>[] = [];
  const startT: number[] = [];
  let t = start;
  for (let i = 0; i < n; i++) {
    if (gapAt !== null && i === gapAt) t += gapS;
    startT.push(t);
    t += cadence;
  }
  const filterOf = (i: number) => filters[i % filters.length];
  const wheelName = (tok: string) => (tok === 'clear' ? '' : tok.toUpperCase());
  for (let i = 0; i < n; i++) {
    const episode = hfdAt !== null && i >= hfdAt && i < hfdAt + 8;
    const hfd = (episode ? 4.1 : 2.3) + 0.12 * gauss(r);
    const alt = 70 - (40 * i) / n;
    const midIso = new Date((startT[i] + exposure / 2) * 1000).toISOString();
    frames.push({
      index: i,
      filename: `${object.replace(/ /g, '_')}_${filterOf(i)}_light_e${String(exposure * 1000).padStart(6, '0')}ms_g080_${String(i + 1).padStart(5, '0')}.fit`,
      image_type: 'Light Frame',
      filter_name: wheelName(filterOf(i)),
      filter: filterOf(i),
      light: true,
      exposure_s: exposure,
      gain: 80,
      timestamp: new Date(startT[i] * 1000).toISOString().replace('Z', '+00:00'),
      hfd: round(hfd, 2),
      fwhm: round(hfd * 0.42 + 0.05 * gauss(r), 2),
      star_count: Math.round((episode ? 1900 : 3100) + 80 * gauss(r)),
      sky_adu: Math.round(1170 + i * 0.4 + 6 * gauss(r)),
      peak_adu: 65520,
      eccentricity: round(0.45 + 0.04 * gauss(r), 3),
      ccd_temp: round(24.5 - (3 * i) / n, 1),
      path: missing.has(i) ? null : `/sessions/demo/lights/frame_${i + 1}.fit`,
      header: missing.has(i)
        ? null
        : {
            date_obs: new Date(startT[i] * 1000).toISOString().slice(0, 19),
            mid_utc: midIso,
            jd_mid: (startT[i] + exposure / 2) / 86400 + JD_UNIX,
            airmass: o.headerAirmass ? round(1 / Math.sin((alt * Math.PI) / 180), 4) : null,
            altitude: o.headerAirmass ? round(alt, 3) : null,
            azimuth: null,
            software: 'ARGOS 0.5.0',
            width: 1920,
            height: 1080,
            bayer: 'GRBG',
          },
    });
  }

  const mid = (i: number) => startT[i] + exposure / 2;
  const jd = (i: number) => mid(i) / 86400 + JD_UNIX;
  const sigma = 0.006;
  type Star = { role: string; name: string; auid: string; mag: number; noise: number };
  const stars: Star[] = [{ role: 'target', name: object, auid: '000-AAA-001', mag: 9.6, noise: 0.012 }];
  if (o.check !== false) stars.push({ role: 'check', name: '000-AAA-090', auid: '000-AAA-090', mag: 10.74, noise: 0.011 });
  for (let k = 0; k < ncomp; k++) stars.push({ role: 'comparison', name: `000-AAA-1${String(k).padStart(2, '0')}`, auid: `000-AAA-1${String(k).padStart(2, '0')}`, mag: 9.9 + 0.35 * k, noise: k === ncomp - 1 ? 0.034 : 0.009 + 0.002 * k });

  const curves: Record<string, unknown>[] = [];
  for (const f of filters) {
    const rows = [...Array(n).keys()].filter((i) => filterOf(i) === f);
    for (const s of stars) {
      const cols: Record<string, (number | boolean | null | string[])[]> = {
        jd_utc: [],
        bjd_tdb: [],
        mag: [],
        mag_err: [],
        formal_mag_err: [],
        sigma_syst: [],
        airmass: [],
        fwhm: [],
        sky_adu: [],
        comps_used: [],
        relative_flux: [],
        relative_flux_err: [],
        relative_comps_used: [],
        saturated: [],
        suspect: [],
        frame: [],
        frame_dt_s: [],
        header_airmass: [],
        zero_point: [],
        zp_rms: [],
        snr: [],
        flags: [],
      };
      const off = f === 'ir' ? 0 : 0.21;
      for (const i of rows) {
        const formal = round(s.noise * (0.8 + 0.4 * r()), 4);
        const base = s.role === 'target' ? s.mag + rrl((jd(i) - 2461346.0) / 0.4423) : s.role === 'check' ? s.mag + 0.012 : s.mag;
        // A blank-sky frame (the recorder's zp_outlier): the target's point is far off; the flag is on every star.
        const v = base + off + s.noise * gauss(r) + (zpOut.has(i) && s.role === 'target' ? 1.2 : 0);
        const sat = s.role === 'target' && saturated.has(i);
        const sus = s.role === 'target' && suspect.has(i);
        const alt = 70 - (40 * i) / n;
        cols.jd_utc.push(jd(i));
        cols.bjd_tdb.push(o.noBjd ? null : jd(i) + 0.0023612 + i * 1e-8);
        cols.mag.push(round(v + (sus ? 0.35 : 0), 4));
        cols.mag_err.push(Math.hypot(formal, sigma));
        cols.formal_mag_err.push(formal);
        cols.sigma_syst.push(sigma);
        // The CSV airmass is computed from the Settings site: here deliberately off by 2x when
        // the header gives the right one (the RR Lyr 2026-09-25 case).
        cols.airmass.push(round((1 / Math.sin((alt * Math.PI) / 180)) * (o.headerAirmass ? 2 : 1), 4));
        cols.fwhm.push(round(2.1 + 0.1 * gauss(r), 2));
        cols.sky_adu.push(1176);
        cols.comps_used.push(s.role === 'comparison' ? ncomp - 1 : i % 37 === 5 ? ncomp - 2 : ncomp);
        const flux = 10 ** (-0.4 * (v - 10));
        cols.relative_flux.push(flux);
        cols.relative_flux_err.push(flux * formal * 0.921);
        cols.relative_comps_used.push(ncomp);
        cols.saturated.push(sat);
        cols.suspect.push(sus);
        cols.frame.push(i);
        cols.frame_dt_s.push(0);
        cols.header_airmass.push(missing.has(i) || !o.headerAirmass ? null : round(1 / Math.sin((alt * Math.PI) / 180), 4));
        cols.zero_point.push(round(zpOut.has(i) ? 21.9 + 1.3 : 21.9 + 0.01 * gauss(r), 4));
        cols.zp_rms.push(round(0.012 + 0.002 * r(), 4));
        cols.snr.push(round(1 / (s.noise * 0.921), 1));
        cols.flags.push(zpOut.has(i) ? ['zp_outlier'] : []);
      }
      const token = o.legacy ? '' : f;
      const key = `${s.auid}@${token}`;
      const file = `${s.role}_${object.replace(/ /g, '_')}_${o.legacy ? '' : `${f.toUpperCase()}_`}${s.auid}.csv`;
      curves.push({
        key,
        identity: s.auid,
        role: s.role,
        name: s.name,
        auid: s.auid,
        role_source: 'prefix',
        filter: token,
        filter_source: o.legacy ? null : 'name',
        csv: `/sessions/demo/photometry/${file}`,
        file_name: file,
        mags: s.role === 'target' ? {} : { V: s.mag, TG: s.mag + 0.03 },
        catalogue_v: s.role === 'target' ? null : s.mag,
        sigma_syst: sigma,
        exportable: true,
        problem: null,
        n: rows.length,
        columns: cols,
      });
    }
  }

  const quality = (f: string, withFilter: boolean) => ({
    schema: 1,
    generated_utc: new Date((start + n * cadence) * 1000).toISOString(),
    selection_status: 'live_preview_consistent',
    scientific_note: 'Leave-one-out live-preview assessment only. Confirm the ensemble on registered, calibrated frames in Siril / star_var_script.',
    criteria: { min_points: 10, max_scatter_mag: 0.03, max_formal_error_mag: 0.1 },
    comparison_stars: stars
      .filter((s) => s.role === 'comparison')
      .map((s) => ({ name: s.name, auid: s.auid, n_valid: Math.floor(n / filters.length), scatter_mag: round(s.noise * 1.02, 5), median_formal_error_mag: round(s.noise, 5), status: s.noise > 0.03 ? 'unstable' : 'stable' })),
    ...(withFilter ? { filter: f } : {}),
  });

  const folder = `20261101T200000Z_${object.replace(/ /g, '_')}`;
  const path = `/sessions/${folder}`;
  const filterCounts: Record<string, number> = {};
  for (let i = 0; i < n; i++) filterCounts[wheelName(filterOf(i)) || '—'] = (filterCounts[wheelName(filterOf(i)) || '—'] ?? 0) + 1;
  // A68 `readiness`: one session_warning per missing FITS (load_session's text), the site check.
  const issues: Record<string, unknown>[] = [...missing].sort((a, b) => a - b).map((i) => ({ code: 'session_warning', level: 'warn', message: `Missing FITS frame: ${frames[i].filename as string}` }));
  if (o.headerAirmass)
    issues.push({
      code: 'site_mismatch',
      level: 'warn',
      message:
        "The site in Settings was not where the telescope was during this run (the mount's direction is 41.2° from the one computed for that site): the curves' airmass is wrong; the FITS header AIRMASS (from the mount) is right.",
    });
  if (zpOut.size) issues.push({ code: 'flagged_points', level: 'warn', message: `${zpOut.size} target points are flagged by the run's flight recorder (zero point or SNR)`, count: zpOut.size });
  const stars0 = stars.map((s) => ({ key: s.auid, role: s.role, name: s.name, display_name: s.name, auid: s.auid, ra_hours: null, dec_deg: null, source: 'vsp', mags: s.role === 'target' ? {} : { V: s.mag, TG: s.mag + 0.03 }, chart_id: 'X99999AA' }));
  const targets = { object_name: object, chart_id: 'X99999AA', stars: stars0 };
  const multi = filters.length > 1;
  const reports = o.quality === false ? null : multi ? Object.fromEntries(filters.slice(1).map((f) => [f, quality(f, true)])) : {};
  return {
    path,
    session: {
      source: { kind: 'session', path },
      path,
      folder,
      object,
      started_utc: new Date(start * 1000).toISOString(),
      software: 'ARGOS 0.5.0',
      observer: '',
      summary: { frames: n, lights: n },
      counts: { frames: n, lights: n, missing_frames: missing.size, filters: filterCounts, image_types: { 'Light Frame': n } },
      metadata: { telescope: 'Seestar S50', camera: 'IMX462', focal_mm: 250, aperture_mm: 50 },
      quality: { default: o.quality === false ? null : quality(filters[0], !o.legacy), default_filter: o.quality === false || o.legacy ? null : filters[0], by_filter: reports ?? {} },
      warnings: [...missing].sort((a, b) => a - b).map((i) => `Missing FITS frame: ${frames[i].filename as string}`),
      readiness: { state: issues.length ? 'warnings' : 'ready', issues },
      frames,
      targets,
      curves: curves.map((c) => ({ key: c.key, role: c.role, name: c.name, filter: c.filter, n: c.n, file_name: c.file_name })),
      filters: o.legacy ? [] : filters,
      multi_filter: multi,
      site_check: o.headerAirmass
        ? { state: 'mismatch', frames: n, median_deg: 41.2, max_deg: 44.0, message: 'The site in Settings was not where the telescope was during this run.' }
        : { state: 'ok', frames: n, median_deg: 0.4, max_deg: 0.9, message: '' },
      airmass_source: o.headerAirmass ? 'header' : 'csv',
      diagnostics: { file: null, frames: 0 },
      revision: 'fixture',
      opened_utc: new Date((start + n * cadence + 3600) * 1000).toISOString(),
    },
    curves: { source: { kind: 'session', path }, object, root: path, targets, curves, filters: o.legacy ? [] : filters, multi_filter: multi, problems: [], airmass_source: o.headerAirmass ? 'header' : 'csv', revision: 'fixture' },
  };
}

/** A fake loader answering from a fixture (optionally after a delay). */
export function fixtureLoader(f: SessionFixture, delayMs = 0) {
  const wait = <T>(v: T) => new Promise<T>((res) => setTimeout(() => res(v), delayMs));
  return {
    session: () => wait(f.session),
    curves: () => wait(f.curves),
  };
}
