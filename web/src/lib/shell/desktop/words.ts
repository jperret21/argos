/**
 * The words of the quit flow (01 2.3.7, M18): what runs, what quitting stops, and the
 * server's shutdown stages. Pure; tested in words.test.ts.
 *
 * The 409 of A7 says what runs, each item with its sentence ("A sequence is running: SS Cyg,
 * 34 of 120 frames.", protocol.md "Shutdown (A7)"), shown as is. An item without words is
 * worded here, with what the UI knows (the sequence's object and frames). When the server
 * has no A7 (older than W8), the list is built from the UI's own records (`localBusy`).
 */

import type { BusyItem } from '../../api/desktop';

/** What the UI itself sees running (ArgosApp records). */
export interface LocalActivity {
  /** An active run (`isActive`): its state name, object and frames. */
  sequence?: { state: string; object: string | null; done: number; total: number } | null;
  /** CameraState.state: live, exposing, downloading, … */
  camera?: string | null;
  /** The exposure in progress, s. */
  exposureS?: number | null;
  autofocus?: boolean;
  slewing?: boolean;
  /** A field identification runs (Identify field, file solve). */
  solving?: boolean;
  /** Running jobs (JobStore.active). */
  jobs?: readonly { kind: string }[];
}

/** Jobs that write files or hold data: quitting would cut them short. */
const WRITING_JOBS = new Set(['rerun', 'export', 'support_bundle', 'session_open']);

/** The UI's own list of what runs (also the fallback when the server has no A7). */
export function localBusy(a: LocalActivity): BusyItem[] {
  const out: BusyItem[] = [];
  const add = (kind: string) => {
    if (!out.some((o) => o.kind === kind)) out.push({ kind, label: null, detail: null });
  };
  if (a.sequence) add('sequence');
  if (a.camera === 'live') add('live');
  else if (a.camera === 'exposing' || a.camera === 'downloading') add('exposure');
  if (a.autofocus) add('autofocus');
  if (a.slewing) add('slew');
  if (a.solving) add('solve');
  for (const j of a.jobs ?? []) {
    const kind = j.kind === 'field_solve' || j.kind === 'file_solve' ? 'solve' : j.kind;
    if (WRITING_JOBS.has(kind) || kind === 'solve') add(kind);
  }
  return out;
}

const SENTENCES: Record<string, string> = {
  sequence: 'A sequence is running.',
  exposure: 'An exposure is in progress.',
  live: 'Live view is running.',
  autofocus: 'Autofocus is running.',
  slew: 'The mount is slewing.',
  jog: 'The mount is moving (jog).',
  focuser: 'The focuser is moving.',
  filterwheel: 'The filter wheel is turning.',
  solve: 'A field identification is running.',
  rerun: 'A photometry re-run is running.',
  export: 'An export is being written.',
  support_bundle: 'A support bundle is being written.',
  session_open: 'A session is being opened.',
  write: 'A FITS file is being written.',
  discovery: 'Searching the network for devices.',
  site_search: 'Searching for a place.',
  sessions_scan: 'Scanning the sessions folder.',
  file_catalogue: 'Querying the catalogue for a file.',
};

/** Icon of each kind (design/icons); `attention` for a kind this build does not know. */
export const BUSY_ICONS: Record<string, string> = {
  sequence: 'nav-sequencer',
  exposure: 'camera',
  live: 'live',
  autofocus: 'autofocus',
  slew: 'mount',
  jog: 'mount',
  focuser: 'focuser',
  filterwheel: 'filter-wheel',
  solve: 'plate-solve',
  rerun: 'rerun-photometry',
  export: 'export',
  support_bundle: 'support-bundle',
  session_open: 'open-session',
  sessions_scan: 'open-session',
  write: 'save',
  discovery: 'discover',
  site_search: 'site',
  file_catalogue: 'catalogue',
};

export function busyIcon(kind: string): string {
  return BUSY_ICONS[kind] ?? 'attention';
}

function frames(n: number): string {
  return `${n} ${n === 1 ? 'frame' : 'frames'}`;
}

/** One line of the dialog for `item`: the server's sentence, else worded with what the UI knows. */
export function busySentence(item: BusyItem, a: LocalActivity = {}): string {
  if (item.label) return /[.!?]$/.test(item.label) ? item.label : `${item.label}.`;
  if (item.kind === 'sequence' && a.sequence) {
    const s = a.sequence;
    const verb = s.state === 'paused' ? 'is paused' : s.state === 'waiting' || s.state === 'scheduled' ? 'waits for its start time' : 'is running';
    const parts = [s.object, s.total > 0 ? `${s.done} of ${frames(s.total)}` : null].filter(Boolean);
    return `A sequence ${verb}${parts.length ? `: ${parts.join(', ')}` : ''}.`;
  }
  if (item.kind === 'exposure' && a.exposureS && a.exposureS > 0) {
    return `An exposure of ${a.exposureS.toFixed(1)} s is in progress.`;
  }
  return SENTENCES[item.kind] ?? `A ${item.kind.replace(/_/g, ' ')} is running.`;
}

const STOPS: Record<string, string> = {
  sequence: 'the sequence',
  exposure: 'the camera',
  live: 'the camera',
  autofocus: 'autofocus',
  slew: "the mount's motion",
  jog: "the mount's motion",
  focuser: 'the focuser',
  filterwheel: 'the filter wheel',
};

function joinAnd(parts: string[]): string {
  if (parts.length <= 1) return parts.join('');
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

/** "Quitting stops the sequence and the camera, closes the equipment connections and shuts down the ARGOS server." */
export function quitConsequence(items: readonly BusyItem[]): string {
  const stops: string[] = [];
  let jobs = false;
  for (const it of items) {
    const s = STOPS[it.kind];
    if (s) {
      if (!stops.includes(s)) stops.push(s);
    } else if (it.kind !== 'write') jobs = true; // a FITS being written is finished, never cut
  }
  if (jobs) stops.push('the running tasks');
  const tail = 'closes the equipment connections and shuts down the ARGOS server.';
  return stops.length ? `Quitting stops ${joinAnd(stops)}, ${tail}` : `Quitting ${tail}`;
}

/** Stage ids of the server's shutdown (A7) and their words; a stage the server words itself keeps its words. */
const STAGES: Record<string, string> = {
  requested: 'Shutting down',
  starting: 'Shutting down',
  begin: 'Shutting down',
  sequence: 'Stopping the sequence',
  run: 'Stopping the sequence',
  camera: 'Stopping the camera',
  exposure: 'Stopping the camera',
  live: 'Stopping the camera',
  autofocus: 'Stopping autofocus',
  mount: 'Stopping the mount',
  jobs: 'Cancelling running tasks',
  services: 'Stopping background tasks',
  files: 'Finishing file writes',
  photometry: 'Finishing the photometry',
  workers: 'Stopping the workers',
  stellarium: 'Stopping the Stellarium bridge',
  network: 'Stopping the network monitor',
  devices: 'Closing the equipment connections',
  disconnect: 'Closing the equipment connections',
  equipment: 'Closing the equipment connections',
  config: 'Saving the settings',
  save: 'Saving the settings',
  server: 'Stopping the ARGOS server',
  done: 'ARGOS server stopped',
  stopped: 'ARGOS server stopped',
  exit: 'Stopping the ARGOS server',
};

/** Words of a stage: the server's, else the table's, else the id made readable. */
export function stageLabel(stage: string, label: string | null = null): string {
  if (label) return label.replace(/[.…]+$/, '');
  const id = stage.toLowerCase().replace(/^(stopping|stop|closing|close)_/, '');
  const known = STAGES[stage.toLowerCase()] ?? STAGES[id];
  if (known) return known;
  const words = stage.replace(/[_-]+/g, ' ').trim();
  return words ? words[0].toUpperCase() + words.slice(1) : 'Shutting down';
}

/**
 * "< 0.1 s", "0.3 s", "12 s", "1 min 05 s": elapsed time of a stage, counted up (never
 * rounded up: honest). Tenths under 10 s, and "< 0.1 s" below that, so a quick stage does
 * not read "0 s" (as if skipped).
 */
export function elapsedText(ms: number): string {
  const t = Math.max(0, ms);
  if (t < 100) return '< 0.1 s';
  if (t < 10_000) return `${(Math.floor(t / 100) / 10).toFixed(1)} s`;
  const s = Math.floor(t / 1000);
  if (s < 60) return `${s} s`;
  return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s`;
}
