/**
 * Connection screen and status-bar device cluster: what each device state
 * looks like and which action it offers (web/spec/02-connection-and-settings.md
 * sections 2.2 and 2.4; 01 sections 2.3.2 and 2.4.2). Pure, tested without a
 * browser.
 *
 * Every state is double-coded: a word and a mark shape (filled = connected,
 * ring = disconnected, half = connecting / busy, cross = error), so it reads
 * the same in Night Red, where the status colours sit below 3:1 (BRAND 4.2).
 */

import type {
  DeviceId,
  DevicePhase,
  DeviceState,
  DevicesState,
  DiscoveredDevice,
  DiscoveryResult,
  NetworkState,
  Profile,
} from '../api/types';
import { DEVICE_IDS } from '../api/types';
import type { Tone } from '../app/status';
import { fixed, int, signed, TIMES } from '../format/number';

export { DEVICE_IDS };

export const DEVICE_LABELS: Record<DeviceId, string> = {
  mount: 'Mount',
  camera: 'Camera',
  filterwheel: 'Filter wheel',
  focuser: 'Focuser',
};

export const DEVICE_ICONS: Record<DeviceId, string> = {
  mount: 'mount',
  camera: 'camera',
  filterwheel: 'filter-wheel',
  focuser: 'focuser',
};

/** Mark drawn for a state (CSS shapes, never Unicode dots: BRAND 5). */
export type Mark = 'filled' | 'ring' | 'half' | 'cross';

/**
 * What a device row offers: Connect, Disconnect, Retry (error), Stop
 * retrying (mount auto-retry) or Cancel (a connection attempt in progress:
 * the server drops it, protocol.md "Devices").
 */
export type DeviceAction = 'connect' | 'disconnect' | 'retry' | 'stop-retrying' | 'cancel';

export const ACTION_LABELS: Record<DeviceAction, string> = {
  connect: 'Connect',
  disconnect: 'Disconnect',
  retry: 'Retry',
  'stop-retrying': 'Stop retrying',
  cancel: 'Cancel',
};

export const ACTION_ICONS: Record<DeviceAction, string> = {
  connect: 'connect',
  disconnect: 'disconnect',
  retry: 'refresh',
  'stop-retrying': 'disconnect',
  cancel: 'close',
};

/** The action releases a device (or an attempt): it goes through DELETE /api/devices/{id}. */
export function isReleaseAction(a: DeviceAction): boolean {
  return a === 'disconnect' || a === 'stop-retrying' || a === 'cancel';
}

export interface DeviceView {
  id: DeviceId;
  label: string;
  icon: string;
  phase: DevicePhase;
  tone: Tone;
  mark: Mark;
  /** One or two words: "Ready", "Connecting", "Slewing", "Error", "Lost". */
  word: string;
  /** Second column: the driver name, what it does, or the full error. */
  detail: string;
  /** The detail is an error or a warning (danger / warning tone, two lines). */
  problem: 'error' | 'warning' | null;
  action: DeviceAction;
  /** Counts as ready in "n of 4 devices ready". */
  ready: boolean;
  /** A spinner replaces the mark. */
  spinning: boolean;
  /** Warnings the server attached (profile mismatch, mount clock). */
  warnings: string[];
}

const capital = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

export const EMPTY_DEVICE: DeviceState = {
  state: 'disconnected',
  name: null,
  info: null,
  error: null,
  retrying: false,
  warnings: [],
  link: null,
  since: '',
};

/** `info` of a device a Connect all has claimed but not opened yet (protocol.md). */
export const QUEUED_INFO = 'queued';

export function isQueued(d: DeviceState | null | undefined): boolean {
  return d?.state === 'connecting' && d.info === QUEUED_INFO;
}

export function deviceView(id: DeviceId, dev: DeviceState | null | undefined): DeviceView {
  const d = dev ?? EMPTY_DEVICE;
  const base = {
    id,
    label: DEVICE_LABELS[id],
    icon: DEVICE_ICONS[id],
    phase: d.state,
    warnings: d.warnings ?? [],
  };
  switch (d.state) {
    case 'connecting':
      if (isQueued(d)) {
        // Claimed by Connect all, waiting for its turn: nothing is open yet.
        return {
          ...base,
          tone: 'idle',
          mark: 'ring',
          word: 'Queued',
          detail: '',
          problem: null,
          action: 'cancel',
          ready: false,
          spinning: false,
        };
      }
      return {
        ...base,
        tone: 'busy',
        mark: 'half',
        word: 'Connecting',
        detail: d.link?.mode === 'alpaca' && d.link.host ? `${d.link.host}:${d.link.port}` : 'Simulator',
        problem: null,
        action: 'cancel',
        ready: false,
        spinning: true,
      };
    case 'connected':
      return {
        ...base,
        tone: 'ok',
        mark: 'filled',
        word: 'Ready',
        // Name, plus what the device reports when it says more (filter slot, focuser position).
        detail: [d.name, d.info && d.info !== d.name ? d.info : null].filter(Boolean).join(' · '),
        problem: d.warnings?.length ? 'warning' : null,
        action: 'disconnect',
        ready: true,
        spinning: false,
      };
    case 'busy':
      return {
        ...base,
        tone: 'busy',
        mark: 'half',
        word: capital(d.info ?? 'busy'),
        detail: d.name ?? '',
        problem: null,
        action: 'disconnect',
        ready: true,
        spinning: false,
      };
    case 'error':
      if (d.retrying) {
        return {
          ...base,
          tone: 'busy',
          mark: 'cross',
          word: 'Lost',
          detail: `Retrying every 10 s${d.error ? `: ${d.error}` : ''}`,
          problem: 'warning',
          action: 'stop-retrying',
          ready: false,
          spinning: false,
        };
      }
      return {
        ...base,
        tone: 'error',
        mark: 'cross',
        word: 'Error',
        detail: d.error ?? d.info ?? 'Unknown error',
        problem: 'error',
        action: 'retry',
        ready: false,
        spinning: false,
      };
    default:
      return {
        ...base,
        tone: 'idle',
        mark: 'ring',
        word: 'Disconnected',
        detail: '',
        problem: null,
        action: 'connect',
        ready: false,
        spinning: false,
      };
  }
}

export function deviceViews(devices: DevicesState | null | undefined): DeviceView[] {
  return DEVICE_IDS.map((id) => deviceView(id, devices?.[id]));
}

export interface DevicesSummary {
  ready: number;
  total: number;
  /** "2 of 4 devices ready". */
  text: string;
  /** While a connect runs: "connecting camera…", or "checking the address…" before the first. */
  progress: string | null;
  tone: Tone;
  allReady: boolean;
  anyConnected: boolean;
  anyConnecting: boolean;
  anyError: boolean;
  /** Something holds a link (connected, busy, connecting or retrying): the profile and the link are locked. */
  anyLinked: boolean;
}

export function devicesSummary(devices: DevicesState | null | undefined): DevicesSummary {
  const views = deviceViews(devices);
  const ready = views.filter((v) => v.ready).length;
  const total = views.length;
  const anyConnecting = views.some((v) => v.phase === 'connecting');
  const anyError = views.some((v) => v.phase === 'error');
  const anyConnected = views.some((v) => v.phase === 'connected' || v.phase === 'busy');
  const anyLinked = anyConnected || anyConnecting || views.some((v) => v.action === 'stop-retrying');
  const allReady = ready === total;
  const text = `${ready} of ${total} devices ready`;
  const opening = views.find((v) => v.phase === 'connecting' && v.word !== 'Queued');
  const progress = opening
    ? `connecting ${opening.label.toLowerCase()}…`
    : anyConnecting
      ? 'checking the address…'
      : null;
  const tone: Tone = anyError ? 'error' : anyConnecting ? 'busy' : allReady ? 'ok' : ready > 0 ? 'ok' : 'idle';
  return { ready, total, text, progress, tone, allReady, anyConnected, anyConnecting, anyError, anyLinked };
}

/** The link the connected devices share, if any (one link at a time, protocol.md). */
export function currentLink(devices: DevicesState | null | undefined): DeviceState['link'] {
  if (!devices) return null;
  for (const id of DEVICE_IDS) {
    const d = devices[id];
    if (d?.link && d.state !== 'disconnected') return d.link;
  }
  return null;
}

/** Status-bar tooltip of one device mark: "Mount: ready · Seestar S30 Pro". */
export function deviceTooltip(v: DeviceView): string {
  const detail = v.detail ? ` · ${v.detail}` : '';
  const word = v.phase === 'disconnected' ? 'not connected' : v.word.toLowerCase();
  return `${v.label}: ${word}${detail}`;
}

// ---------------------------------------------------------------------------
// Profile and site
// ---------------------------------------------------------------------------

/** "30 mm · f/5.3 · IMX585 · 2.9 µm · 3.74″/px · 3.99° × 2.24° · GRBG" (BRAND 5 formats). */
export function profileSpecs(p: Profile): string {
  const parts = [
    `${int(p.aperture_mm)} mm`,
    `f/${fixed(p.focal_ratio, 1)}`,
    p.sensor,
    `${fixed(p.pixel_size_um, 1)} µm`,
    `${fixed(p.arcsec_per_px, 2)}″/px`,
    `${fixed(p.fov_deg[0], 2)}° ${TIMES} ${fixed(p.fov_deg[1], 2)}°`,
  ];
  if (p.bayer) parts.push(p.bayer);
  return parts.join(' · ');
}

/** Owner decision Q-C2: one wording everywhere. */
export const UNVALIDATED_TEXT = 'Not validated on this hardware: do not use it for scientific photometry.';

export interface SiteSummary {
  /** The site is still the default (0, 0): science metadata would be wrong. */
  missing: boolean;
  name: string;
  coords: string;
  elevation: string;
}

export function siteSummary(values: Record<string, unknown> | null | undefined): SiteSummary {
  const num = (k: string) => (typeof values?.[k] === 'number' ? (values[k] as number) : 0);
  const lat = num('site.latitude');
  const lon = num('site.longitude');
  const elev = num('site.elevation');
  const name = typeof values?.['site.name'] === 'string' ? (values['site.name'] as string).trim() : '';
  const missing = !values || (lat === 0 && lon === 0);
  return {
    missing,
    name: name || (missing ? 'No site set' : 'Unnamed site'),
    coords: `${signed(lat, 5)}° ${signed(lon, 5)}°`,
    elevation: `${int(elev)} m`,
  };
}

export interface ChecklistItem {
  id: 'obscode' | 'site' | 'astap';
  label: string;
  done: boolean;
}

/** First-run checklist (Q-G11): observer code, site, ASTAP. */
export function firstRunChecklist(
  values: Record<string, unknown> | null | undefined,
  astapConfigured: boolean | null | undefined,
): ChecklistItem[] {
  const code = typeof values?.['observer.obscode'] === 'string' ? (values['observer.obscode'] as string) : '';
  return [
    { id: 'obscode', label: 'Observer code', done: code.trim().length > 0 },
    { id: 'site', label: 'Site', done: !siteSummary(values).missing },
    { id: 'astap', label: 'ASTAP', done: !!astapConfigured },
  ];
}

// ---------------------------------------------------------------------------
// Network
// ---------------------------------------------------------------------------

export type ReachWord =
  | 'reachable'
  | 'unreachable'
  | 'not in use'
  | 'not configured'
  | 'not checked'
  | 'offline'
  | 'online';

export interface NetworkView {
  seestar: { mark: Mark | 'none'; word: ReachWord; tone: Tone };
  internet: { mark: Mark | 'none'; word: ReachWord; tone: Tone };
  /** "checked 4 s ago", "" when never. */
  checked: string;
  internetChecked: string;
}

export function ago(iso: string | null | undefined, now: number): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return '';
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return `${s} s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min ago`;
}

/**
 * `seestarInUse`: the Seestar is the link chosen (or held by the devices).
 * An unreachable address that nothing uses (the simulator is the link) is
 * "not in use", idle: never a red alarm on every screen.
 */
export function networkView(n: NetworkState | null | undefined, now: number, seestarInUse = true): NetworkView {
  const seestar =
    n?.seestar === true
      ? { mark: 'filled' as const, word: 'reachable' as const, tone: 'ok' as const }
      : n?.seestar === false
        ? seestarInUse
          ? { mark: 'ring' as const, word: 'unreachable' as const, tone: 'error' as const }
          : { mark: 'none' as const, word: 'not in use' as const, tone: 'idle' as const }
        : { mark: 'none' as const, word: 'not configured' as const, tone: 'idle' as const };
  const internet =
    n?.internet === true
      ? { mark: 'filled' as const, word: 'online' as const, tone: 'ok' as const }
      : n?.internet === false
        ? { mark: 'ring' as const, word: 'offline' as const, tone: 'error' as const }
        : { mark: 'none' as const, word: 'not checked' as const, tone: 'idle' as const };
  return {
    seestar,
    internet,
    checked: n?.seestar === null ? '' : ago(n?.t, now),
    internetChecked: ago(n?.internet_t, now),
  };
}

// ---------------------------------------------------------------------------
// Discovery
// ---------------------------------------------------------------------------

export const NO_DEVICE_FOUND = 'No Alpaca devices found (broadcast, direct probes and subnet scan).';

const METHOD_WORDS: Record<string, string> = {
  broadcast: 'broadcast',
  probe: 'direct probes',
  subnet: 'subnet scan',
  names: 'device names',
};

export function parseDiscoveryResult(raw: unknown): DiscoveryResult | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (!Array.isArray(r.devices)) return null;
  const devices: DiscoveredDevice[] = [];
  for (const d of r.devices) {
    if (typeof d !== 'object' || d === null) continue;
    const x = d as Record<string, unknown>;
    if (typeof x.host !== 'string' || typeof x.port !== 'number') continue;
    devices.push({ host: x.host, port: x.port, name: typeof x.name === 'string' ? x.name : null });
  }
  const method = r.method === 'broadcast' || r.method === 'probe' || r.method === 'subnet' ? r.method : null;
  const searched = Array.isArray(r.searched) ? r.searched.filter((s): s is string => typeof s === 'string') : [];
  return { devices, method, searched };
}

/** "Searched: broadcast, then direct probes". */
export function searchedText(result: DiscoveryResult): string {
  const words = result.searched.map((s) => METHOD_WORDS[s] ?? s);
  return words.length ? `Searched: ${words.join(', then ')}` : '';
}

export function deviceAddress(d: DiscoveredDevice): string {
  return `${d.host}:${d.port}`;
}

// ---------------------------------------------------------------------------
// Confirmations
// ---------------------------------------------------------------------------

export interface RunningState {
  live: boolean;
  exposing: boolean;
  slewing: boolean;
}

/**
 * What a disconnection would stop (02 W10b), or null when nothing runs: the
 * confirmation is only asked then (Q-C5). `devices` limits it to what the
 * devices being disconnected run (all of them by default).
 */
export function disconnectRisk(run: RunningState, devices: readonly DeviceId[] = DEVICE_IDS): string | null {
  const parts: string[] = [];
  if (devices.includes('camera')) {
    if (run.live) parts.push('Live view is running: it stops.');
    else if (run.exposing) parts.push('An exposure is running: the frame is lost.');
  }
  // The server closes the link without AbortSlew (hub.py _disconnect_device):
  // the mount finishes its slew on its own and ARGOS can no longer stop it.
  if (devices.includes('mount') && run.slewing) {
    parts.push('The mount is slewing: it keeps moving to its target, and ARGOS can no longer abort the slew.');
  }
  return parts.length ? parts.join(' ') : null;
}
