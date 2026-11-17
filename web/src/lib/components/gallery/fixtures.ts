/**
 * Sample data for the component gallery (dev only, /?gallery=1). Realistic
 * texts taken from the specs (01 2.3, 02 W1), never shown in the app.
 */

import type { JobEntry } from '../../app/jobs';

export const T0 = Date.parse('2026-11-01T21:03:58Z');

export const SAMPLE_LOG: Record<string, unknown>[] = [
  { level: 'info', source: 'server', topic: 'app', message: 'ARGOS server 0.4.2 started (API 2), log folder ~/Library/Logs/Argos' },
  { level: 'cmd', source: 'discovery', topic: 'discovery', message: 'Starting Alpaca discovery…' },
  { level: 'ok', source: 'discovery', topic: 'discovery', message: 'Found 192.168.1.42:32323' },
  { level: 'cmd', source: 'mount', topic: 'connection', message: 'Connecting mount 192.168.1.42:32323…' },
  { level: 'ok', source: 'mount', topic: 'connection', message: 'Mount connected: Seestar S30 Pro' },
  { level: 'warning', source: 'mount', topic: 'connection', message: 'Mount clock differs from this computer by 4.2 s: GoTo is blocked until it is synchronised.' },
  { level: 'debug', source: 'mount', topic: 'mount', message: 'poll 0.21 s, alt 41.27°, az 182.05°' },
  { level: 'cmd', source: 'camera', topic: 'connection', message: 'Connecting camera 192.168.1.42:32323…' },
  { level: 'error', source: 'camera', topic: 'connection', message: 'Camera: Cannot reach 192.168.1.42:32323 — timed out after 10 s (PUT Connected)' },
  { level: 'info', source: 'network', topic: 'network', message: 'Seestar reachable again (192.168.1.42).' },
  { level: 'cmd', source: 'server', topic: 'camera', message: 'Plate-solving current frame... (hint RA 5.588h Dec −5.39°)' },
  { level: 'ok', source: 'server', topic: 'camera', message: 'Field identified: 3.67″/px' },
  { level: 'warning', source: 'server', topic: 'mount', message: 'Center target: plate-solve the current frame first.' },
  { level: 'error', source: 'core', topic: 'camera', message: 'Solve: ASTAP executable not found' },
];

/** WS-shaped log lines, one every 4 s from T0, seq from 1. */
export function sampleLogLines(count = SAMPLE_LOG.length, from = 1): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = [];
  for (let i = 0; i < count; i++) {
    const seq = from + i;
    const base = SAMPLE_LOG[(seq - 1) % SAMPLE_LOG.length];
    out.push({ type: 'log', id: seq, seq, t: new Date(T0 + (seq - 1) * 4000).toISOString(), ...base });
  }
  return out;
}

const iso = (offsetS: number) => new Date(T0 + offsetS * 1000).toISOString();

function job(patch: Partial<JobEntry>): JobEntry {
  return {
    id: 'job',
    kind: 'discovery',
    state: 'running',
    done: 0,
    total: 3,
    stage: 'broadcast',
    message: null,
    started_utc: iso(0),
    ended_utc: null,
    result: null,
    error: null,
    cancellable: true,
    cancel_requested: false,
    seq: 1,
    cancelling: false,
    cancelError: null,
    ...patch,
  };
}

export const NOW = T0 + 9000;

export const SAMPLE_JOBS: { caption: string; job: JobEntry; title: string; result?: string }[] = [
  { caption: 'queued', title: 'Discovery', job: job({ id: 'q', state: 'queued', done: 0, stage: null }) },
  {
    caption: 'running, determinate',
    title: 'Discovery',
    job: job({ id: 'r', done: 1, stage: 'probe', message: 'Probing 192.168.1.42 and seestar.local' }),
  },
  {
    caption: 'running, indeterminate',
    title: 'Place search',
    job: job({ id: 'i', kind: 'site_search', total: null, stage: 'nominatim', message: 'Asking OpenStreetMap Nominatim for "Mauna Kea"' }),
  },
  {
    caption: 'cancelling',
    title: 'Discovery',
    job: job({ id: 'c', done: 2, stage: 'subnet', message: 'Scanning 192.168.1.0/24', cancelling: true, cancel_requested: true }),
  },
  {
    caption: 'cancel refused',
    title: 'Support bundle',
    job: job({ id: 'n', kind: 'support_bundle', total: null, message: 'Writing argos-support-0.4.2.zip', cancellable: false, cancelError: 'This job cannot be cancelled' }),
  },
  {
    caption: 'done, with actions',
    title: 'Discovery',
    result: 'Found 2 devices: 192.168.1.42:32323, 10.0.0.1:32323',
    job: job({ id: 'd', state: 'done', done: 3, ended_utc: iso(11) }),
  },
  {
    caption: 'failed',
    title: 'Discovery',
    job: job({
      id: 'f',
      state: 'failed',
      done: 1,
      ended_utc: iso(4),
      error: { code: 'network_error', message: 'Discovery: [Errno 65] No route to host (the computer has no network interface up)' },
    }),
  },
  { caption: 'cancelled', title: 'Discovery', job: job({ id: 'x', state: 'cancelled', done: 2, ended_utc: iso(7) }) },
];

export interface DeviceRow {
  id: string;
  icon: string;
  name: string;
  state: 'connected' | 'error' | 'disconnected' | 'connecting' | 'busy';
  detail: string;
}

export const DEVICES: DeviceRow[] = [
  { id: 'mount', icon: 'mount', name: 'Mount', state: 'connected', detail: 'Seestar S30 Pro' },
  {
    id: 'camera',
    icon: 'camera',
    name: 'Camera',
    state: 'error',
    detail: 'Cannot reach 192.168.1.42:32323 — timed out after 10 s (PUT Connected)',
  },
  { id: 'filterwheel', icon: 'filter-wheel', name: 'Filter wheel', state: 'connecting', detail: 'Connecting…' },
  { id: 'focuser', icon: 'focuser', name: 'Focuser', state: 'disconnected', detail: '—' },
];

export interface VariableRow {
  name: string;
  type: string;
  mag: number | null;
  period: number | null;
  sep: number;
}

export const VARIABLES: VariableRow[] = [
  { name: 'SS Cyg', type: 'UGSS', mag: 12.157, period: null, sep: 0.4 },
  { name: 'V1504 Cyg', type: 'UGSU', mag: 13.502, period: 0.0695, sep: 12.8 },
  { name: 'BI Cyg', type: 'LC', mag: 8.405, period: null, sep: 21.3 },
  { name: 'V0402 Cyg', type: 'EA', mag: 11.04, period: 2.7814, sep: 7.1 },
  { name: 'NSV 13789', type: 'VAR', mag: null, period: null, sep: 4.9 },
  { name: 'V0558 Cyg', type: 'RRAB', mag: 14.22, period: 0.5326, sep: 15.6 },
];
