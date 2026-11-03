/**
 * Wave-2 gallery fixtures (dev only, /?gallery=1): a slice of the server's
 * config meta copied from argos/server/config_meta.py (KEYS), a fake
 * `PATCH /api/config` that answers like the server (strict ranges, `fields`
 * on a refusal, a warning for a folder that does not exist), an in-memory
 * `GET /api/fs/list`, and a sessions list. Never shown in the app.
 */

import type { ConfigValue, KeyMeta } from '../../api/types';
import type { FsEntry, FsListing, FsListRequest } from '../filepicker';
import type { BundleRequest, BundleResult, BundleSession } from '../supportbundle';

function k(over: Partial<KeyMeta> & Pick<KeyMeta, 'type' | 'default' | 'label' | 'category'>): KeyMeta {
  return {
    nullable: false,
    min: null,
    max: null,
    step: null,
    options: null,
    unit: null,
    help: '',
    used_by: [],
    advanced: false,
    read_only: false,
    ...over,
  };
}

const HOME = '/Users/observer';

export const META: Record<string, KeyMeta> = {
  'observer.name': k({ type: 'str', default: '', label: 'Observer name', help: 'Written to the FITS OBSERVER keyword.', category: 'observer_site' }),
  'observer.obscode': k({
    type: 'str',
    default: '',
    label: 'AAVSO observer code',
    help: 'Stamped on every AAVSO export. Letters and digits, upper-cased.',
    category: 'observer_site',
  }),
  'site.latitude': k({
    type: 'float',
    default: 0,
    label: 'Latitude',
    help: 'Geodetic latitude, north positive. Written to FITS SITELAT; used for altitude, airmass and target visibility.',
    category: 'observer_site',
    min: -90,
    max: 90,
    step: 0.00001,
    unit: '°',
  }),
  'site.longitude': k({
    type: 'float',
    default: 0,
    label: 'Longitude',
    help: 'Geodetic longitude, east positive. Written to FITS SITELONG; used for altitude, airmass and target visibility.',
    category: 'observer_site',
    min: -180,
    max: 180,
    step: 0.00001,
    unit: '°',
  }),
  'site.elevation': k({
    type: 'float',
    default: 0,
    label: 'Elevation',
    help: 'Height above sea level. Written to FITS SITEELEV.',
    category: 'observer_site',
    min: -500,
    max: 9000,
    step: 0.1,
    unit: 'm',
  }),
  'hardware.profile': k({
    type: 'str',
    default: 's30pro',
    label: 'Telescope',
    help: 'The instrument model: plate scale, sensor geometry and FITS identity.',
    category: 'instrument',
    options: [
      { value: 's30pro', label: 'ZWO Seestar S30 Pro' },
      { value: 's30', label: 'ZWO Seestar S30 (unvalidated)' },
      { value: 's50', label: 'ZWO Seestar S50 (unvalidated)' },
    ],
    read_only: true,
  }),
  'hardware.overrides.full_well_adu': k({
    type: 'int',
    default: null,
    nullable: true,
    label: 'Saturation (full well)',
    help: "Saturation threshold of your unit; empty uses the profile's value.",
    category: 'instrument',
    min: 0,
    max: 65535,
    step: 1,
    unit: 'ADU',
  }),
  'astrometry.astap_path': k({ type: 'path', default: '', label: 'ASTAP executable', help: 'Empty: auto-detect (astap_cli on PATH).', category: 'plate_solving' }),
  'astrometry.database': k({
    type: 'str',
    default: '',
    label: 'Database set',
    help: 'ASTAP star database to use; ignored while a star database folder is set.',
    category: 'plate_solving',
    options: [{ value: '', label: 'Auto' }, ...['D05', 'D20', 'D50', 'D80', 'G17', 'H17', 'H18', 'V17', 'W08'].map((n) => ({ value: n, label: n }))],
  }),
  'astrometry.database_path': k({
    type: 'path',
    default: '',
    label: 'Star database folder',
    help: 'When set, ASTAP uses this folder (-d) and ignores the database set.',
    category: 'plate_solving',
  }),
  'astrometry.downsample': k({
    type: 'int',
    default: 2,
    label: 'Downsample',
    help: 'Image reduction before solving; Auto lets ASTAP choose.',
    category: 'plate_solving',
    options: [
      { value: 0, label: 'Auto' },
      { value: 1, label: '1×' },
      { value: 2, label: '2×' },
      { value: 3, label: '3×' },
      { value: 4, label: '4×' },
    ],
  }),
  'astrometry.search_radius_deg': k({
    type: 'int',
    default: 30,
    label: 'Search radius',
    help: 'Radius searched around the pointing hint; 0 = blind, whole sky.',
    category: 'plate_solving',
    min: 0,
    max: 180,
    step: 1,
    unit: '°',
  }),
  'astrometry.use_scale_hint': k({
    type: 'bool',
    default: true,
    label: 'Use the known plate scale as a hint',
    help: "Pass the profile's plate scale to ASTAP (faster solve).",
    category: 'plate_solving',
  }),
  'astrometry.live_timeout_s': k({
    type: 'float',
    default: 25,
    label: 'Automatic solve timeout',
    help: 'Bound on one automatic solve, so the cadence never stalls.',
    category: 'plate_solving',
    min: 1,
    max: 600,
    step: 1,
    unit: 's',
    advanced: true,
  }),
  'catalog.field_stars_enabled': k({
    type: 'bool',
    default: true,
    label: 'Identify field stars with Gaia DR3',
    help: 'Fetch Gaia DR3 sources for a solved field (cached).',
    category: 'catalogues',
  }),
  'catalog.field_stars_mag_limit': k({
    type: 'float',
    default: 18,
    label: 'Gaia depth',
    help: 'Faintest Gaia G magnitude fetched and cached for a field.',
    category: 'catalogues',
    min: 3,
    max: 20,
    step: 0.5,
    unit: 'mag',
  }),
  'catalog.identification_max_objects': k({
    type: 'int',
    default: 400,
    label: 'Identification budget',
    help: 'Total online identities for one field, shared by Gaia and SIMBAD.',
    category: 'catalogues',
    options: [
      { value: 100, label: 'Fast · 100 objects' },
      { value: 200, label: 'Fast · 200 objects' },
      { value: 400, label: 'Balanced · 400 objects' },
      { value: 800, label: 'Detailed · 800 objects' },
      { value: 1600, label: 'Dense field · 1,600 objects' },
    ],
  }),
  sessions_path: k({
    type: 'path',
    default: `${HOME}/Argos/sessions`,
    label: 'Sessions folder',
    help: 'Each observation gets its own subfolder: FITS frames, metadata, products and logs.',
    category: 'data_storage',
  }),
  'ui.log_level': k({
    type: 'str',
    default: 'INFO',
    label: 'Log level',
    help: 'Detail of the server log (stderr and argos.log); applied at once.',
    category: 'privacy_diagnostics',
    options: ['DEBUG', 'INFO', 'WARNING', 'ERROR'].map((v) => ({ value: v, label: v })),
  }),
};

export function initialValues(): Record<string, ConfigValue> {
  return {
    'observer.name': 'A. Observer',
    'observer.obscode': 'XOBS',
    'site.latitude': 43.93167,
    'site.longitude': 5.71333,
    'site.elevation': 650,
    'hardware.profile': 's30pro',
    'hardware.overrides.full_well_adu': null,
    'astrometry.astap_path': '',
    'astrometry.database': 'D50',
    'astrometry.database_path': '',
    'astrometry.downsample': 2,
    'astrometry.search_radius_deg': 45,
    'astrometry.use_scale_hint': true,
    'astrometry.live_timeout_s': 25,
    'catalog.field_stars_enabled': false,
    'catalog.field_stars_mag_limit': 18,
    'catalog.identification_max_objects': 400,
    sessions_path: `${HOME}/Argos/sessions`,
    'ui.log_level': 'INFO',
  };
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** A refusal shaped like ApiError (400 invalid_argument with `fields`). */
function refuse(key: string, message: string): Error & { fields: Record<string, string> } {
  return Object.assign(new Error('Invalid configuration'), { fields: { [key]: message } });
}

/**
 * The server's PATCH, played locally: strict ranges and options from the
 * meta, paths absolute, a warning for a folder that does not exist, 500 ms
 * of latency so the "Saving…" state is seen.
 */
export function fakePatch(values: Record<string, ConfigValue>) {
  return async (changes: Record<string, ConfigValue>) => {
    await wait(500);
    const warnings: { key: string; message: string }[] = [];
    for (const [key, v] of Object.entries(changes)) {
      const m = META[key];
      if (!m || m.read_only) throw refuse(key, 'This key cannot be changed');
      if (typeof v === 'number' && ((m.min !== null && v < m.min) || (m.max !== null && v > m.max))) {
        throw refuse(key, `must be between ${m.min} and ${m.max}`);
      }
      if (m.type === 'path' && typeof v === 'string' && v) {
        if (!v.startsWith('/') && !v.startsWith('~')) throw refuse(key, 'must be an absolute path');
        if (v.startsWith('/Volumes/locked')) throw refuse(key, 'not writable');
        if (!FOLDERS.has(v.replace(/\/$/, ''))) warnings.push({ key, message: 'does not exist, it will be created' });
      }
    }
    Object.assign(values, changes);
    return { values, changed: changes, warnings, revision: 1 };
  };
}

// -- An in-memory home folder for GET /api/fs/list -----------------------------------------

const T = 1793620800; // 2026-11-02 12:00 UTC

const TREE: Record<string, FsEntry[]> = {
  [HOME]: [
    { name: 'Argos', kind: 'dir', mtime: T - 86400 },
    { name: 'Desktop', kind: 'dir', mtime: T - 3600 },
    { name: 'Documents', kind: 'dir', mtime: T - 7 * 86400 },
    { name: '.argos', kind: 'dir', mtime: T - 600 },
  ],
  [`${HOME}/Argos`]: [
    { name: 'sessions', kind: 'dir', mtime: T - 7200 },
    { name: 'sequences', kind: 'dir', mtime: T - 30 * 86400 },
    { name: 'cache', kind: 'dir', mtime: T - 86400 },
  ],
  [`${HOME}/Argos/sessions`]: [
    { name: '20261031T200453Z_SS_Cyg', kind: 'dir', mtime: T - 2 * 86400, fits_count: 412 },
    { name: '20261028T193012Z_RR_Lyr', kind: 'dir', mtime: T - 5 * 86400, fits_count: 1204 },
    { name: '20260925T200453Z_RR_Lyr', kind: 'dir', mtime: T - 38 * 86400, fits_count: 96 },
  ],
  [`${HOME}/Argos/sessions/20261031T200453Z_SS_Cyg`]: [
    { name: 'lights', kind: 'dir', mtime: T - 2 * 86400, fits_count: 412 },
    { name: 'session.json', kind: 'file', size: 3_412, mtime: T - 2 * 86400 },
    { name: 'photometry.csv', kind: 'file', size: 88_120, mtime: T - 2 * 86400 },
    { name: 'SS_Cyg_0001.fits', kind: 'file', size: 4_147_200, mtime: T - 2 * 86400 },
    { name: 'SS_Cyg_0002.fits', kind: 'file', size: 4_147_200, mtime: T - 2 * 86400 },
  ],
  [`${HOME}/Argos/sequences`]: [{ name: 'ss_cyg_night.json', kind: 'file', size: 1_208, mtime: T - 30 * 86400 }],
  [`${HOME}/Argos/cache`]: [],
  [`${HOME}/Desktop`]: [
    { name: 'argos-support-0.4.2-20261101T213405Z.zip', kind: 'file', size: 612_000, mtime: T - 50_000 },
    { name: 'notes.txt', kind: 'file', size: 812, mtime: T - 9000 },
  ],
  [`${HOME}/Documents`]: [],
  [`${HOME}/.argos`]: [{ name: 'cache', kind: 'dir', mtime: T - 600 }],
  [`${HOME}/.argos/cache`]: [
    { name: 'gaia', kind: 'dir', mtime: T - 600 },
    { name: 'catalog', kind: 'dir', mtime: T - 600 },
  ],
  [`${HOME}/.argos/cache/gaia`]: [],
  [`${HOME}/.argos/cache/catalog`]: [],
};
const FOLDERS = new Set(Object.keys(TREE));

export const PLACES = [
  { id: 'home', label: 'Home', path: HOME, exists: true },
  { id: 'desktop', label: 'Desktop', path: `${HOME}/Desktop`, exists: true },
  { id: 'sessions', label: 'Sessions', path: `${HOME}/Argos/sessions`, exists: true },
  { id: 'presets', label: 'Presets', path: `${HOME}/Argos/sequences`, exists: true },
  { id: 'calibrations', label: 'Calibrations', path: `${HOME}/.argos/calibrations`, exists: false },
];

function parent(p: string): string | null {
  if (p === HOME) return null; // the listing stops at the allowed roots
  const i = p.lastIndexOf('/');
  return i > 0 ? p.slice(0, i) : null;
}

export function listing(path: string, hidden = false): FsListing {
  const all = TREE[path] ?? [];
  const entries = hidden ? all : all.filter((e) => !e.name.startsWith('.'));
  return { path, parent: parent(path), root: HOME, places: PLACES, entries, truncated: false };
}

/** The listing route, played locally (forbidden outside home, as the server). */
export async function fakeList(req: FsListRequest): Promise<FsListing> {
  await wait(150);
  const raw = (req.path ?? HOME).replace(/^~/, HOME).replace(/\/$/, '') || '/';
  if (!raw.startsWith(HOME)) {
    throw Object.assign(new Error(`${raw} is outside the folders ARGOS may browse (home and the ARGOS data folders)`), {
      code: 'forbidden_path',
    });
  }
  if (!(raw in TREE)) throw Object.assign(new Error(`No folder ${raw}`), { code: 'not_found' });
  return listing(raw, req.hidden);
}

export const SESSIONS: BundleSession[] = [
  { path: `${HOME}/Argos/sessions/20261031T200453Z_SS_Cyg`, object: 'SS Cyg', started_utc: '2026-10-31T20:04:53Z', frames: 412 },
  { path: `${HOME}/Argos/sessions/20261028T193012Z_RR_Lyr`, object: 'RR Lyr', started_utc: '2026-10-28T19:30:12Z', frames: 1204 },
  { path: `${HOME}/Argos/sessions/20260925T200453Z_RR_Lyr`, object: 'RR Lyr', started_utc: '2026-09-25T20:04:53Z', frames: 96 },
];

/** The support-bundle job, played locally (409 file_exists without overwrite, as the server). */
export async function fakeBundle(req: BundleRequest): Promise<BundleResult> {
  await wait(900);
  if (req.destination?.startsWith('/Volumes/locked')) throw new Error("Permission denied: '/Volumes/locked'");
  const name = req.destination?.split('/').pop() ?? 'argos-support.zip';
  if (!req.overwrite && TREE[`${HOME}/Desktop`].some((e) => `${HOME}/Desktop/${e.name}` === req.destination)) {
    throw Object.assign(new Error(`${name} already exists`), { code: 'file_exists' });
  }
  const files = ['README.txt', 'manifest.json', 'logs/argos.log', 'logs/argos.log.1'];
  if (req.include_crash_reports) files.push('crash/crash-20261101T221502Z-4120.txt');
  if (req.include_session) files.push('session/session.json', 'session/photometry.csv');
  return { path: req.destination, name, bytes: 48_211, files, download: req.destination === null, session_included: req.include_session, site_included: req.include_site };
}

export const HOME_DIR = HOME;
