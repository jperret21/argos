/**
 * The run on the client (wave 6a): the server's `sequence` snapshot (A63: the WS event,
 * `GET /api/sequence` after a reconnect), the subs this run saved (`frame_saved` with
 * source "sequence", read back from `GET /api/camera/saved`), the preflight (A64) and the
 * transport (A62). One instance in the app state; the Plan screen, the Run card and, in 6b,
 * Watch and the status bar read it.
 *
 * Usage:
 *   const seq = new SequenceStore();
 *   const off = seq.attach(events, client);   // on start
 *   await seq.refresh();                       // after each (re)connection
 *   seq.state?.frames_done; seq.frameTimes; seq.lastSaved
 *   await seq.start(startAt);                  // rejects with the ApiError (server's words)
 */

import { checkSequence, sequenceApi, unixOf, type Preflight, type SeqClient, type SequenceState } from '../api/sequence';
import { observedCadence } from '../charts/conditions';

export interface SeqEventSource {
  on(type: string, fn: (msg: Record<string, unknown>) => void): () => void;
}

/** A saved sub of the run (the run strip's second line). */
export interface SavedSub {
  seq: number;
  /** DATE-OBS (the exposure start): the clock of the server's cadence and of the age. */
  t: number;
  name: string;
  hfd: number | null;
  fwhm: number | null;
  stars: number | null;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** A `frame_saved` of the sequence in the run folder `root` (its `run_root`, else its path), or null. */
export function checkSaved(m: unknown, root: string | null): SavedSub | null {
  if (!isObj(m) || m.source !== 'sequence') return null;
  const path = typeof m.path === 'string' ? m.path : '';
  if (root && (typeof m.run_root === 'string' ? m.run_root !== root : path && !path.startsWith(root))) return null;
  const t = unixOf(m.date_obs) ?? unixOf(m.t);
  const seq = num(m.seq);
  if (t === null || seq === null) return null;
  const r = isObj(m.record) ? m.record : {};
  return { seq, t, name: typeof m.name === 'string' ? m.name : (path.split(/[\\/]/).pop() ?? ''), hfd: num(r.hfd), fwhm: num(r.fwhm), stars: num(r.star_count) };
}

export class SequenceStore {
  state: SequenceState | null = $state.raw(null);
  /** DATE-OBS (unix s) of this run's subs, ascending. */
  frameTimes: number[] = $state.raw([]);
  lastSaved: SavedSub | null = $state.raw(null);
  preflight: Preflight | null = $state.raw(null);
  preflightError: string | null = $state(null);
  /** The outcome line of the last run was dismissed (it comes back with the next run's end). */
  dismissed = $state(false);

  private client: SeqClient | null = null;
  private runKey: string | null = null;
  private seenSaves = new Set<number>();
  private resultKey: string | null = null;

  /**
   * The cadence the last-frame age is held against: the server's observed one (median of the
   * step's last subs, pauses excluded), else the client's median, else the step's planned one.
   */
  get cadence(): number | null {
    return this.state?.observed_cadence_s ?? observedCadence(this.frameTimes, this.frameTimes.length) ?? this.state?.cadence_s ?? null;
  }

  /** DATE-OBS of the newest sub: the server's `last_frame_utc`, else the store's. */
  get lastFrameAt(): number | null {
    const n = this.frameTimes.length;
    const mine = n ? this.frameTimes[n - 1] : null;
    const srv = this.state?.last_frame_t ?? null;
    return mine === null ? srv : srv === null ? mine : Math.max(mine, srv);
  }

  attach(events: SeqEventSource, client: SeqClient | null = null): () => void {
    this.client = client;
    const offs = [
      events.on('sequence', (m) => void this.ingest(m)),
      events.on('status', (m) => {
        if (isObj(m.sequence)) void this.ingest(m.sequence);
      }),
      events.on('frame_saved', (m) => this.ingestSaved(m)),
    ];
    return () => offs.forEach((off) => off());
  }

  /** One `sequence` record; returns whether it was kept. */
  ingest(m: unknown): boolean {
    const s = checkSequence(m);
    if (!s) return false;
    const key = s.run_id ?? s.run_root;
    if (key !== this.runKey && (s.state !== 'idle' || key !== null)) {
      // A new run (or the first record): its subs start again.
      if (this.runKey !== null || this.frameTimes.length) {
        this.frameTimes = [];
        this.lastSaved = null;
        this.seenSaves.clear();
      }
      this.runKey = key;
    }
    const r = s.last_result;
    const rk = r ? `${s.run_id ?? r.run_root ?? ''}|${r.ended_utc ?? ''}|${r.frames_saved}` : null;
    if (rk !== this.resultKey) {
      this.resultKey = rk;
      this.dismissed = false;
    }
    this.state = s;
    return true;
  }

  /**
   * One `frame_saved`: kept when it is a sub of the run in progress (or of the run that just
   * ended). With no run folder known yet, only a sub taken after the run started counts: a
   * waiting or idle store never adopts the saves of an older run (the server keeps 200).
   */
  ingestSaved(m: unknown): boolean {
    const st = this.state;
    if (!st || st.state === 'waiting') return false;
    const root = st.run_root ?? st.last_result?.run_root ?? null;
    const sub = checkSaved(m, root);
    if (!sub || this.seenSaves.has(sub.seq)) return false;
    if (!root && (st.state === 'idle' || st.started_t === null || sub.t < st.started_t - 1)) return false;
    this.seenSaves.add(sub.seq);
    const t = this.frameTimes;
    // Saves arrive in order; a read-back may interleave: keep the times sorted.
    this.frameTimes = t.length && sub.t < t[t.length - 1] ? [...t, sub.t].sort((a, b) => a - b) : [...t, sub.t];
    if (!this.lastSaved || sub.t >= this.lastSaved.t) this.lastSaved = sub;
    return true;
  }

  /** After a (re)connection: the run's state and the saves this client missed (the server keeps the last 200). */
  async refresh(client: SeqClient | null = this.client): Promise<void> {
    if (!client) return;
    try {
      this.ingest(await client.request<unknown>('GET', '/api/sequence'));
    } catch {
      // An older server, or the link dropped: the socket's snapshot will come.
    }
    try {
      const r = await client.request<{ saves?: unknown[] }>('GET', '/api/camera/saved');
      for (const m of r.saves ?? []) this.ingestSaved(m);
    } catch {
      // The live stream still feeds the store; the strip shows frames by count meanwhile.
    }
  }

  /** A64 for a start now, or at `startAt` (the scheduled time). */
  async loadPreflight(client: SeqClient | null = this.client, startAt: number | null = null): Promise<void> {
    if (!client) return;
    try {
      this.preflight = await sequenceApi.preflight(client, startAt);
      this.preflightError = null;
    } catch (err) {
      this.preflightError = err instanceof Error ? err.message : String(err);
    }
  }

  // The transport: each call rejects with the server's ApiError (409 / 400 in words).
  start(startAt: number | null = null, client: SeqClient | null = this.client): Promise<unknown> {
    if (!client) return Promise.reject(new Error('Not connected to the ARGOS server'));
    return sequenceApi.start(client, startAt);
  }

  pause(client: SeqClient | null = this.client): Promise<unknown> {
    return client ? sequenceApi.pause(client) : Promise.reject(new Error('Not connected to the ARGOS server'));
  }

  resume(client: SeqClient | null = this.client): Promise<unknown> {
    return client ? sequenceApi.resume(client) : Promise.reject(new Error('Not connected to the ARGOS server'));
  }

  stop(client: SeqClient | null = this.client): Promise<unknown> {
    return client ? sequenceApi.stop(client) : Promise.reject(new Error('Not connected to the ARGOS server'));
  }

  /** Hide the outcome line of the run that ended (it comes back with the next run's end). */
  dismissOutcome(): void {
    this.dismissed = true;
  }

  get outcomeVisible(): boolean {
    return !!this.state?.last_result && this.state.state === 'idle' && !this.dismissed;
  }
}
