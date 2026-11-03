/**
 * Settings screen model (web/spec/02-connection-and-settings.md sections 2.1-2.4
 * and appendix A; README 1.2, D13, D14, D28, Q-C4, Q-C8, Q-G11).
 *
 * - The nine canonical categories (D13) and the server keys each one shows.
 *   Every key comes from the server's config meta (`GET /api/config`); the
 *   few keys of another server category that Settings mirrors (online
 *   permissions in Privacy, the Observe display values in Appearance) are
 *   listed here, once.
 * - The Settings attention mark (Q-G11, wave 2): observer code or site
 *   missing, or the Settings site disagrees with the mount (site check).
 * - The facts of the "About this setting" column (Q-C8).
 *
 * Pure; unit-tested in categories.test.ts.
 */

import type { ConfigValue, KeyMeta, SiteCheck } from '../api/types';
import { formatValue, signedFor } from '../components/settings';
import { fixed, formatRange, int, signed } from '../format/number';

export const SETTINGS_CATEGORIES = [
  'observer_site',
  'instrument',
  'plate_solving',
  'catalogues',
  'photometry',
  'data_storage',
  'privacy_diagnostics',
  'appearance',
  'about',
] as const;
export type SettingsCategoryId = (typeof SETTINGS_CATEGORIES)[number];

export function isSettingsCategory(v: unknown): v is SettingsCategoryId {
  return typeof v === 'string' && (SETTINGS_CATEGORIES as readonly string[]).includes(v);
}

export interface CategoryDef {
  id: SettingsCategoryId;
  label: string;
  icon: string;
  /** One line under the title (what the category is for). */
  intro: string;
}

/** D13: 02's nine categories are canonical; icons of 02 2.2 (1.6 #1-#5). */
export const CATEGORIES: readonly CategoryDef[] = [
  {
    id: 'observer_site',
    label: 'Observer & site',
    icon: 'site',
    intro: 'Who observed and from where: FITS OBSERVER, SITELAT, SITELONG, SITEELEV, the airmass and the AAVSO code.',
  },
  {
    id: 'instrument',
    label: 'Instrument',
    icon: 'mount',
    intro: 'The telescope profile and the corrections for your unit: saturation, linearity, electron gain.',
  },
  {
    id: 'plate_solving',
    label: 'Plate solving',
    icon: 'plate-solve',
    intro: 'ASTAP, its star database and how a field is identified. Solving runs on the green channel.',
  },
  {
    id: 'catalogues',
    label: 'Catalogues',
    icon: 'catalogue',
    intro: 'What is fetched and drawn for a solved field. Online catalogues are cached; context layers are local.',
  },
  {
    id: 'photometry',
    label: 'Photometry',
    icon: 'photometry',
    intro: 'Apertures, comparison selection and the error model of the live and re-run photometry.',
  },
  {
    id: 'data_storage',
    label: 'Data & storage',
    icon: 'browse',
    intro: 'Where sessions, presets and catalogue caches live on this computer.',
  },
  {
    id: 'privacy_diagnostics',
    label: 'Privacy & diagnostics',
    icon: 'log',
    intro: 'What leaves this computer, what is recorded locally, and the support bundle.',
  },
  {
    id: 'appearance',
    label: 'Appearance',
    icon: 'theme',
    intro: 'Theme, density and layouts of this browser, and the display values every viewer shares.',
  },
  {
    id: 'about',
    label: 'About',
    icon: 'about',
    intro: 'Version, licence, credits and documentation.',
  },
];

export const CATEGORY_BY_ID: Record<SettingsCategoryId, CategoryDef> = Object.fromEntries(
  CATEGORIES.map((c) => [c.id, c]),
) as Record<SettingsCategoryId, CategoryDef>;

/** Online permissions mirrored in Privacy & diagnostics (02 2.1 "Online services"). */
export const PRIVACY_MIRRORS = [
  'catalog.named_objects_allow_network',
  'catalog.exoplanet_hosts_allow_network',
  'stellarium.online_target_lookup',
] as const;

/** Q-C3: binding the Stellarium bridge beyond this computer is an explicit, warned setting. */
export const NETWORK_EXPOSURE = ['stellarium.host'] as const;

/** Keys edited on the Connection screen (Link and Planetarium cards). */
export const CONNECTION_KEYS = ['alpaca.host', 'alpaca.port', 'stellarium.port'] as const;

/**
 * The Settings category a server key belongs to (its home form), or null
 * for a key whose home is the Connection screen.
 */
export function homeCategory(key: string, meta: KeyMeta): SettingsCategoryId | null {
  if ((NETWORK_EXPOSURE as readonly string[]).includes(key)) return 'privacy_diagnostics';
  if (key === 'stellarium.online_target_lookup') return 'privacy_diagnostics';
  if (meta.category === 'connection') return null;
  if (meta.category === 'observe') return 'appearance';
  return isSettingsCategory(meta.category) ? meta.category : null;
}

/** Keys whose home is a category, in the server's order. */
export function keysOf(meta: Record<string, KeyMeta>, id: SettingsCategoryId): string[] {
  return Object.keys(meta).filter((k) => homeCategory(k, meta[k]) === id);
}

// ---------------------------------------------------------------------------
// Site check (protocol.md "Site check"; PROPOSAL section 7)
// ---------------------------------------------------------------------------

export type SiteCheckTone = 'ok' | 'mismatch' | 'unknown';

export interface SiteCheckView {
  tone: SiteCheckTone;
  /** "Agrees with the mount", "Disagrees with the mount", "Not checked". */
  word: string;
  /** The server's one line. */
  message: string;
  /** Both altitudes and the difference, when compared. */
  rows: { label: string; value: string }[];
  /** "21:04:05 UTC · on connection", "" before any check. */
  when: string;
  /** One line about the driver's own site, when it says. */
  driver: string | null;
}

const TRIGGERS: Record<string, string> = {
  connect: 'on connection',
  periodic: 'every 5 min',
  site_change: 'after a site change',
  manual: 'checked on request',
};

/** Alt / Az: 2 decimals, no space before ° (BRAND 5, as the Mount card). */
const altAz = (alt: number, az: number) => `alt ${fixed(alt, 2)}°, az ${fixed(az, 2)}°`;

export function utcTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return '';
  return `${new Date(t).toISOString().slice(11, 19)} UTC`;
}

export function siteCheckView(sc: SiteCheck | null | undefined): SiteCheckView {
  if (!sc) {
    return { tone: 'unknown', word: 'Not checked', message: 'The server has not reported a site check yet.', rows: [], when: '', driver: null };
  }
  const rows: { label: string; value: string }[] = [];
  if (sc.mount) rows.push({ label: 'Mount reports', value: altAz(sc.mount.alt_deg, sc.mount.az_deg) });
  if (sc.expected) rows.push({ label: 'From the Settings site', value: altAz(sc.expected.alt_deg, sc.expected.az_deg) });
  if (sc.separation_deg !== null) {
    const alt = sc.altitude_diff_deg !== null ? ` (altitude ${signed(sc.altitude_diff_deg, 1)}°)` : '';
    rows.push({ label: 'Difference', value: `${fixed(sc.separation_deg, 1)}° apart${alt} · limit ${fixed(sc.tolerance_deg, 0)}°` });
  }
  const when = sc.checked_utc ? [utcTime(sc.checked_utc), sc.trigger ? TRIGGERS[sc.trigger] : ''].filter(Boolean).join(' · ') : '';
  let driver: string | null = null;
  const d = sc.driver_site;
  if (d) {
    // Site coordinates: 5 decimals everywhere, as the Settings fields (BRAND 2.3).
    const where = `${signed(d.latitude, 5)}° ${signed(d.longitude, 5)}°`;
    driver =
      d.distance_km === null
        ? `The mount's own site: ${where}.`
        : `The mount's own site: ${where}, ${int(Math.round(d.distance_km))} km from the Settings site${d.state === 'mismatch' ? ' (more than 100 km)' : ''}.`;
  }
  const word = sc.state === 'ok' ? 'Agrees with the mount' : sc.state === 'mismatch' ? 'Disagrees with the mount' : 'Not compared';
  return { tone: sc.state, word, message: sc.message, rows, when, driver };
}

// ---------------------------------------------------------------------------
// Attention (Q-G11, wave 2)
// ---------------------------------------------------------------------------

export interface Attention {
  category: SettingsCategoryId;
  text: string;
  /**
   * BRAND 8 levels, one shape each: `attention` (the upright mark, a bar over
   * a dot: the site disagrees with the mount, no site at all) and `info` (the
   * hollow ring: no AAVSO code, nothing is wrong until an export).
   */
  level: 'attention' | 'info';
}

function siteMissing(values: Record<string, ConfigValue> | null | undefined): boolean {
  const lat = values?.['site.latitude'];
  const lon = values?.['site.longitude'];
  return !values || ((lat === 0 || typeof lat !== 'number') && (lon === 0 || typeof lon !== 'number'));
}

/**
 * What the Settings rail mark (Q-G11) and the category list point at:
 * missing observer code, missing site, and the site check's mismatch.
 */
export function settingsAttention(
  values: Record<string, ConfigValue> | null | undefined,
  siteCheck: SiteCheck | null | undefined,
): Attention[] {
  if (!values) return [];
  const out: Attention[] = [];
  const code = values['observer.obscode'];
  if (typeof code !== 'string' || !code.trim()) {
    out.push({ category: 'observer_site', text: 'No AAVSO observer code: AAVSO exports cannot be stamped', level: 'info' });
  }
  if (siteMissing(values)) {
    out.push({ category: 'observer_site', text: 'No observing site: FITS site keywords and airmass would be wrong', level: 'attention' });
  } else if (siteCheck?.state === 'mismatch') {
    out.push({ category: 'observer_site', text: 'The Settings site disagrees with the mount', level: 'attention' });
  }
  return out;
}

// ---------------------------------------------------------------------------
// "About this setting" (Q-C8)
// ---------------------------------------------------------------------------

export interface KeyFacts {
  label: string;
  help: string;
  key: string;
  facts: { label: string; value: string; mono?: boolean }[];
  usedBy: string[];
}

export function keyFacts(key: string, meta: KeyMeta, value: ConfigValue | undefined): KeyFacts {
  const facts: KeyFacts['facts'] = [];
  const num = meta.type === 'int' || meta.type === 'float';
  if ((meta as KeyMeta & { personal?: boolean }).personal) {
    // The shipped "" / 0 is a placeholder, not a value to go back to (0°, 0° is not a site).
    facts.push({ label: 'Default', value: 'None: your own value' });
  } else {
    facts.push({ label: 'Default', value: formatValue(meta.default, meta, key), mono: num });
  }
  if (value !== undefined) facts.push({ label: 'Now', value: formatValue(value, meta, key), mono: num });
  if (meta.min !== null && meta.max !== null) {
    // One range notation everywhere (format/number.ts): "−90° … +90°", "1 … 3 600 s".
    facts.push({ label: 'Range', value: formatRange(meta.min, meta.max, { signed: signedFor(key), unit: meta.unit }), mono: true });
  } else if (meta.min !== null || meta.max !== null) {
    const lo = meta.min !== null ? formatRange(meta.min, meta.min, { unit: meta.unit }).split(' … ')[0] : '−∞';
    const hi = meta.max !== null ? formatRange(meta.max, meta.max, { unit: meta.unit }).split(' … ')[1] : '∞';
    facts.push({ label: 'Range', value: `${lo} … ${hi}`, mono: true });
  }
  if (meta.nullable) facts.push({ label: 'Empty', value: 'allowed' });
  if (meta.read_only) facts.push({ label: 'Read-only', value: meta.read_only_reason ?? 'yes' });
  return { label: meta.label, help: meta.help, key, facts, usedBy: [...meta.used_by] };
}
