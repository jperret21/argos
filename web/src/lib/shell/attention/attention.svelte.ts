/**
 * The attention list on the client (wave 6b; PROPOSAL §7, BRAND §13): the server's items
 * (WS `attention`, `GET /api/attention` after each (re)connection: the active list and the
 * run's history, so a client joining mid-run sees what happened), the shared
 * acknowledgement (`POST /api/attention/{id}/ack`) and the tones. One instance in the app
 * state; the status-bar chip, its list, the Run card and Watch read it.
 *
 * Usage:
 *   const att = new AttentionStore();
 *   const off = att.attach(events, client, window);   // returns the detach (timers, audio)
 *   await att.refresh();                               // after each (re)connection
 *   att.setPrefs(prefsFrom(app.configValues));         // the config keys (Settings › Alerts)
 *   att.open; att.top; att.chip; await att.ack(id);
 *
 * Replays never sound (`quiet`); a new item sounds once (highest level of a batch); a
 * Critical item still active and open repeats every 30 s until acknowledged.
 */

import { attentionApi, checkAttentionBatch, type AttentionBatch, type AttentionClient, type AttentionItem, type AttentionLevel, type RunBaseline } from '../../api/attention';
import { chipView, newToneState, nextTone, openItems, sortItems, type ChipView, type SoundPrefs } from './model';
import { alertSound, AlertSound, armOnGesture } from './sound';

export interface AttentionEvents {
  on(type: string, fn: (msg: Record<string, unknown>) => void): () => void;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);

export class AttentionStore {
  /** Every item of this run (active, cleared, acknowledged), sorted for the list. */
  items: AttentionItem[] = $state.raw([]);
  /** Ids whose acknowledgement is on its way. */
  pending: ReadonlySet<string> = $state.raw(new Set());
  /** The server's refusal of the last acknowledgement, verbatim. */
  error: string | null = $state(null);
  prefs: SoundPrefs = $state.raw({ level: 'normal', info: false });
  /** The audio context runs (a gesture armed it). */
  armed = $state(false);
  /** The server answers GET /api/attention (false: an older server, the list stays empty). */
  supported = $state(true);
  /** The alerts.* thresholds in force on the server (the snapshot's): the Run band draws the rules with them. */
  thresholds: Record<string, unknown> | null = $state.raw(null);
  /** The run's HFD and star baselines in force on the server (the snapshot's): the rule lines. */
  baselines: readonly RunBaseline[] = $state.raw([]);
  /** The last tone played (level and unix s): the gallery and the checks read it. */
  lastTone: { level: AttentionLevel; t: number } | null = $state.raw(null);

  readonly sound: AlertSound;
  private client: AttentionClient | null = null;
  private tones = newToneState();
  private byId = new Map<string, AttentionItem>();
  private first = true;
  private revision: number | null = null;
  private prefsSet = false;
  private readonly clock: () => number;
  /** Who acknowledges (AckBody.by, at most 64 characters): this client's label. */
  private readonly by: string | undefined;

  constructor(opts: { sound?: AlertSound; clock?: () => number; by?: string } = {}) {
    this.sound = opts.sound ?? alertSound;
    this.clock = opts.clock ?? (() => Date.now() / 1000);
    this.by = opts.by?.slice(0, 64);
  }

  /** Items needing the observer (Critical, Attention, not acknowledged), most urgent first. */
  get open(): AttentionItem[] {
    return openItems(this.items);
  }

  /** The most urgent open item: Watch's first row, the chip's headline. */
  get top(): AttentionItem | null {
    return this.open[0] ?? null;
  }

  get chip(): ChipView {
    return chipView(this.items);
  }

  /**
   * Listen to the server; `win` arms the sound on the first press or key and drives the
   * repeat of open Critical items (every 5 s it checks whether one is due). Returns the detach.
   */
  attach(events: AttentionEvents, client: AttentionClient | null = null, win: (Pick<EventTarget, 'addEventListener' | 'removeEventListener'> & { setInterval?: typeof setInterval; clearInterval?: typeof clearInterval }) | null = null): () => void {
    this.client = client;
    const offs = [
      events.on('attention', (m) => this.ingest(m)),
      events.on('status', (m) => {
        if (isObj(m.attention)) this.ingest(m.attention, true);
      }),
    ];
    if (win) {
      offs.push(armOnGesture(this.sound, win));
      const markArmed = () => setTimeout(() => (this.armed = this.sound.armed), 50);
      const types = ['pointerdown', 'keydown'] as const;
      types.forEach((t) => win.addEventListener(t, markArmed, true));
      offs.push(() => types.forEach((t) => win.removeEventListener(t, markArmed, true)));
      const timer = setInterval(() => this.tick(), 5000);
      offs.push(() => clearInterval(timer));
    }
    return () => {
      offs.forEach((off) => off());
      this.sound.dispose();
      this.armed = false;
    };
  }

  /**
   * One message: the WS `attention` snapshot (sent on every change, and once to a client
   * that connects), a single item, or the REST answer. A snapshot replaces the list; one
   * older than the list held (`revision`) is dropped. The first message after a
   * (re)connection is a replay: it never sounds (except an open Critical item, which
   * repeats until acknowledged). Returns whether it was kept.
   */
  ingest(m: unknown, replay = false): boolean {
    const b = checkAttentionBatch(m);
    if (!b) return false;
    return this.apply(b, replay || this.first);
  }

  private apply(b: AttentionBatch, quiet: boolean): boolean {
    if (b.revision !== null && this.revision !== null && b.revision < this.revision) return false;
    if (b.revision !== null) this.revision = b.revision;
    if (b.replace) this.byId = new Map(b.items.map((a) => [a.id, a]));
    else for (const a of b.items) this.byId.set(a.id, a);
    if (b.thresholds) this.thresholds = b.thresholds;
    if (b.baselines) this.baselines = b.baselines;
    if (b.sound && !this.prefsSet) this.prefs = { level: b.sound.level, info: b.sound.info, ...(b.sound.repeatS !== null ? { repeatS: b.sound.repeatS } : {}) };
    this.items = sortItems(this.byId.values());
    this.first = false;
    this.sound_(quiet);
    return true;
  }

  /**
   * The sound settings from the config values (Settings › Alerts, the `config` event): they
   * win over the snapshot's copy from then on (a choice made here is never undone by a
   * snapshot sent before it reached the server).
   */
  setPrefs(p: SoundPrefs): void {
    this.prefsSet = true;
    this.prefs = p;
  }

  /** Load items as a replay (gallery, tests): no tone. */
  seed(items: readonly AttentionItem[]): void {
    this.apply({ items: [...items], replace: true, revision: null, sound: null, unacked: null, thresholds: null }, true);
  }

  /**
   * After a (re)connection (call it from onFirstStatus, before the server's snapshot): the
   * next snapshot is read as a replay, then the active list and the history are read (an
   * older server answers 404: the list stays empty and says so).
   */
  async refresh(client: AttentionClient | null = this.client): Promise<void> {
    if (!client) return;
    this.first = true;
    this.revision = null;
    try {
      const b = await attentionApi.list(client);
      this.supported = true;
      if (b) this.apply(b, true);
    } catch (err) {
      const status = (err as { status?: number })?.status;
      if (status === 404) this.supported = false;
    }
  }

  /** Acknowledge for every client; rejects with the server's words (also kept in `error`). */
  async ack(id: string): Promise<void> {
    const c = this.client;
    if (!c || this.pending.has(id)) return;
    await this.call([id], () => attentionApi.ack(c, id, this.by));
  }

  /** Acknowledge every open item at once. */
  async ackAll(): Promise<void> {
    const c = this.client;
    const ids = this.open.map((a) => a.id);
    if (!c || !ids.length) return;
    await this.call(ids, () => attentionApi.ackAll(c, this.by));
  }

  private async call(ids: string[], fn: () => Promise<AttentionBatch | null>): Promise<void> {
    this.pending = new Set([...this.pending, ...ids]);
    this.error = null;
    try {
      const b = await fn();
      if (b) this.apply(b, false);
    } catch (err) {
      this.error = err instanceof Error ? err.message : String(err);
      throw err;
    } finally {
      const next = new Set(this.pending);
      for (const id of ids) next.delete(id);
      this.pending = next;
    }
  }

  /** Arm from a gesture the caller handles (Watch opened, Soft / Normal chosen). */
  arm(): void {
    this.sound.arm();
    setTimeout(() => (this.armed = this.sound.armed), 50);
  }

  /** "Test sound": arm, then play the level's tones at the chosen volume (or Normal when Off). */
  test(level: AttentionLevel = 'attention'): boolean {
    this.arm();
    const v = this.prefs.level === 'off' ? 'normal' : this.prefs.level;
    return this.sound.play(level, v);
  }

  /** The repeat check (the attach's timer; tests call it with their clock). Also keeps
   * `armed` true to the context: one the OS suspended says "not armed" within 5 s. */
  tick(): void {
    this.armed = this.sound.armed;
    this.sound_(false, true);
  }

  private sound_(quiet: boolean, repeatOnly = false): void {
    const now = this.clock();
    const level = nextTone(this.items, this.tones, this.prefs, now, quiet || repeatOnly);
    if (!level) return;
    if (this.sound.play(level, this.prefs.level)) this.lastTone = { level, t: now };
  }

  /** Forget the list (a new server or a reset): the next message is read as a replay. */
  clear(): void {
    this.byId.clear();
    this.items = [];
    this.tones = newToneState();
    this.first = true;
    this.revision = null;
  }
}
