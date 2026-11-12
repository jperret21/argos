/**
 * The Plan screen's state (06 §2, A59-A66): the server's draft and its answer, the explicit
 * selection, the presets, the run snapshot, and the writes in order.
 *
 * - One writer: every edit builds the next plan from the newest one and PUTs it whole. Writes
 *   are serialised, so two quick edits never cross; the screen shows the edit at once and the
 *   answer (plan as kept, derived values, issues) replaces it. A refused write puts back the
 *   last plan the server accepted and rejects with its words (the field shows them).
 * - Nothing is clamped or substituted here: a value is sent as typed, the server says what is
 *   wrong with it (A59 issues), the field keeps it.
 * - The plan is locked while a run is active (Q-P9): the server says it in the record
 *   (`locked`, re-sent as `sequence_plan` when a run starts or ends); the run snapshot (A63,
 *   lib/run's SequenceStore) gives each row its progress.
 * - Another client's edit arrives as `sequence_plan` and replaces the draft when nothing of
 *   ours is being written.
 *
 *   const plan = new PlanStore(new PlanApi(app.client), () => run.state);
 *   const off = plan.attach(app.events);
 *   await plan.load();
 */

import { checkPlanDoc, type PlanApi, type PlanDoc, type PlanStep, type PresetInfo, type SequencePlan } from '../api/plan';
import type { SequenceState } from '../api/sequence';
import { addStep, duplicateStep, moveStep, patchStep, removeStep, runActive, samePlan, type StepEdit } from './model';

export interface PlanEvents {
  on(type: string, fn: (msg: Record<string, unknown>) => void): () => void;
}

export class PlanStore {
  /** The server's answer (or the edit shown while it is written). */
  doc: PlanDoc | null = $state.raw(null);
  loadError: string | null = $state(null);
  loading = $state(false);
  /** Row selected in the Steps table (explicit; null = no row action). */
  selected: number | null = $state(null);
  /** Writes not answered yet (the totals line says "Saving…"). */
  pending = $state(0);
  presets: PresetInfo[] = $state.raw([]);
  presetsDir: string | null = $state(null);
  presetsError: string | null = $state(null);
  /** The plan as last opened from or saved to a preset or a file (unsaved-changes check). */
  baseline: { name: string; plan: SequencePlan } | null = $state.raw(null);
  /** Stable keys of the rows: an editor follows its step when steps move. */
  ids: number[] = $state.raw([]);

  private nextId = 1;
  private accepted: PlanDoc | null = null;
  private chain: Promise<unknown> = Promise.resolve();
  private writeSeq = 0;

  constructor(
    private readonly api: PlanApi,
    /** The run (A63, the shared SequenceStore's state); null until the server has said. */
    private readonly run: () => SequenceState | null = () => null,
  ) {}

  get seq(): SequenceState | null {
    return this.run();
  }

  get plan(): SequencePlan | null {
    return this.doc?.plan ?? null;
  }

  get steps(): PlanStep[] {
    return this.doc?.plan.steps ?? [];
  }

  /** A run is active: the plan and the object are locked (Q-P9). */
  get locked(): boolean {
    return !!this.doc?.locked || runActive(this.seq);
  }

  get lockedReason(): string | null {
    return this.locked ? (this.doc?.locked_reason ?? 'The plan is locked while the sequence runs.') : null;
  }

  /** The draft holds steps that no preset or file holds (asked before replacing it). */
  get unsaved(): boolean {
    const p = this.plan;
    if (!p || !p.steps.length) return false;
    return !this.baseline || !samePlan(p, this.baseline.plan);
  }

  // -- Server ------------------------------------------------------------------------------------

  attach(events: PlanEvents): () => void {
    // Another client's edit, a transit plan, a run starting or ending: newer revisions only.
    return events.on('sequence_plan', (m) => {
      const d = checkPlanDoc(m);
      if (d && !this.pending && (this.doc?.revision ?? -1) < d.revision) {
        if (this.doc && d.plan.steps.length !== this.doc.plan.steps.length) this.selected = null;
        this.setAccepted(d);
      }
    });
  }

  async load(): Promise<void> {
    this.loading = true;
    try {
      this.setAccepted(await this.api.plan());
      this.loadError = null;
    } catch (err) {
      this.loadError = err instanceof Error ? err.message : String(err);
    } finally {
      this.loading = false;
    }
  }

  private setAccepted(d: PlanDoc): void {
    this.accepted = d;
    this.doc = d;
    if (this.ids.length !== d.plan.steps.length) this.ids = d.plan.steps.map(() => this.nextId++);
    if (this.selected !== null && this.selected >= d.plan.steps.length) this.selected = d.plan.steps.length ? d.plan.steps.length - 1 : null;
  }

  /**
   * Write the next plan (built from the newest one by `next`). Resolves with the server's
   * answer; rejects with its words after putting back the last accepted plan.
   */
  write(next: (p: SequencePlan) => SequencePlan): Promise<PlanDoc> {
    const run = async (): Promise<PlanDoc> => {
      const base = this.doc?.plan;
      if (!base) throw new Error('The plan is not loaded yet');
      const plan = next(base);
      const id = ++this.writeSeq;
      this.doc = { ...(this.doc as PlanDoc), plan };
      this.pending++;
      try {
        const answer = await this.api.putPlan(plan);
        if (id === this.writeSeq) this.setAccepted(answer);
        else this.accepted = answer;
        return answer;
      } catch (err) {
        if (id === this.writeSeq && this.accepted) this.doc = this.accepted;
        throw err;
      } finally {
        this.pending--;
      }
    };
    const p = this.chain.then(run, run);
    this.chain = p.catch(() => undefined);
    return p;
  }

  editStep(i: number, patch: Partial<PlanStep>): Promise<PlanDoc> {
    return this.write((p) => ({ ...p, steps: patchStep(p.steps, i, patch) }));
  }

  setOptions(patch: Partial<Omit<SequencePlan, 'steps'>>): Promise<PlanDoc> {
    return this.write((p) => ({ ...p, ...patch }));
  }

  /**
   * One row operation: `make` runs on the steps on screen (selection, row keys) and again on
   * the newest plan when the write goes out; `keys` moves the row keys the same way.
   */
  private applyEdit(make: (steps: PlanStep[]) => StepEdit | null, keys: (ids: number[], e: StepEdit) => void): Promise<PlanDoc> | null {
    const e = make(this.steps);
    if (!e) return null;
    const ids = [...this.ids];
    keys(ids, e);
    this.ids = ids;
    this.selected = e.selected;
    return this.write((p) => ({ ...p, steps: make(p.steps)?.steps ?? p.steps }));
  }

  add(wheel: readonly string[]): Promise<PlanDoc> | null {
    const sel = this.selected;
    return this.applyEdit(
      (steps) => addStep(steps, sel, wheel),
      (ids, e) => ids.splice(e.selected ?? ids.length, 0, this.nextId++),
    );
  }

  duplicate(): Promise<PlanDoc> | null {
    const sel = this.selected;
    return this.applyEdit(
      (steps) => duplicateStep(steps, sel),
      (ids, e) => ids.splice(e.selected ?? ids.length, 0, this.nextId++),
    );
  }

  move(dir: -1 | 1): Promise<PlanDoc> | null {
    const sel = this.selected;
    if (sel === null) return null;
    return this.reorder(sel, sel + dir);
  }

  reorder(from: number, to: number): Promise<PlanDoc> | null {
    return this.applyEdit(
      (steps) => moveStep(steps, from, to),
      (ids) => ids.splice(to, 0, ...ids.splice(from, 1)),
    );
  }

  /** Remove the selected step; returns what was removed and where, for the Undo toast. */
  remove(): { done: Promise<PlanDoc>; removed: PlanStep; at: number } | null {
    const r = removeStep(this.steps, this.selected);
    if (!r) return null;
    const at = r.at;
    const ids = [...this.ids];
    ids.splice(at, 1);
    this.ids = ids;
    this.selected = r.selected;
    const done = this.write((p) => ({ ...p, steps: removeStep(p.steps, at)?.steps ?? p.steps }));
    return { done, removed: r.removed, at };
  }

  /** Undo of a removal: the step back at its place. */
  restore(step: PlanStep, at: number): Promise<PlanDoc> {
    const pos = Math.min(at, this.steps.length);
    const ids = [...this.ids];
    ids.splice(pos, 0, this.nextId++);
    this.ids = ids;
    this.selected = pos;
    return this.write((p) => {
      const steps = [...p.steps];
      steps.splice(Math.min(at, steps.length), 0, step);
      return { ...p, steps };
    });
  }

  /** Replace the whole plan (preset, Undo of a replacement). */
  replace(plan: SequencePlan): Promise<PlanDoc> {
    this.selected = null;
    this.ids = plan.steps.map(() => this.nextId++);
    return this.write(() => plan);
  }

  // -- Presets (A60, A61) --------------------------------------------------------------------------

  async loadPresets(): Promise<void> {
    try {
      this.setPresets(await this.api.presets());
    } catch (err) {
      this.presetsError = err instanceof Error ? err.message : String(err);
    }
  }

  private setPresets(list: { directory: string | null; presets: PresetInfo[] }): void {
    this.presets = list.presets;
    this.presetsDir = list.directory;
    this.presetsError = null;
  }

  /** A preset or a file becomes the draft, as Qt's Load preset (A61: metadata not restored). */
  async importPlan(from: { preset: string } | { path: string }): Promise<PlanDoc> {
    await this.chain;
    const doc = await this.api.importPlan(from);
    this.selected = null;
    this.ids = [];
    this.setAccepted(doc);
    this.baseline = { name: 'preset' in from ? from.preset : from.path, plan: doc.plan };
    return doc;
  }

  /** Save the draft under a name; `409 file_exists` unless `overwrite`. */
  async savePreset(name: string, overwrite: boolean): Promise<void> {
    await this.chain;
    const plan = this.plan;
    this.setPresets(await this.api.savePreset(name, overwrite));
    if (plan) this.baseline = { name, plan };
  }

  /** Delete a preset; resolves with its plan so Undo can write it back. */
  async deletePreset(name: string): Promise<SequencePlan> {
    const plan = await this.api.preset(name);
    this.setPresets(await this.api.deletePreset(name));
    return plan;
  }

  async restorePreset(name: string, plan: SequencePlan): Promise<void> {
    this.setPresets(await this.api.savePreset(name, false, plan));
  }

  /** The draft as a file in Qt's format; `409 file_exists` unless `overwrite`. */
  async exportFile(path: string, overwrite: boolean): Promise<string> {
    await this.chain;
    const plan = this.plan;
    const r = await this.api.exportPlan(path, overwrite);
    if (plan) this.baseline = { name: r.path ?? path, plan };
    return r.path ?? path;
  }

  /** A transit plan written by the server becomes the draft (A66). */
  adopt(doc: PlanDoc): void {
    this.selected = null;
    this.ids = [];
    this.setAccepted(doc);
  }
}
