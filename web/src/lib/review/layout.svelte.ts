/**
 * The wall's per-viewer layout (spec 07 §2.4 "Persistence": cell order, hidden cells, the
 * quality metric), reactive, saved through lib/app/prefs.ts (try / catch: the wall works the
 * same without storage). "Reset layout" restores every session plot in the default order
 * (07 1.1 #16: fixes P4) and is effective at once (P18). Expanding a cell is a view state,
 * not remembered.
 */

import { arrange, DEFAULT_LAYOUT, isMetric, loadWallLayout, moveCell, saveWallLayout, type MetricId, type WallCell } from './wall';

type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem'>;

export class WallLayoutState {
  order: string[] = $state([]);
  hidden: string[] = $state([]);
  metric: MetricId = $state('hfd');
  /** The cell that fills the wall (Expand), null: the grid. */
  expanded: string | null = $state(null);
  private readonly storage: Storage | null | undefined;

  constructor(storage?: Storage | null) {
    this.storage = storage;
    const l = loadWallLayout(storage);
    this.order = l.order;
    this.hidden = l.hidden;
    this.metric = l.metric;
  }

  private save(): void {
    saveWallLayout({ order: [...this.order], hidden: [...this.hidden], metric: this.metric }, this.storage);
  }

  arrange(cells: readonly WallCell[]): { shown: WallCell[]; hidden: WallCell[] } {
    return arrange(cells, { order: this.order, hidden: this.hidden });
  }

  isHidden(id: string): boolean {
    return this.hidden.includes(id);
  }

  setHidden(id: string, hide: boolean): void {
    if (hide === this.isHidden(id)) return;
    this.hidden = hide ? [...this.hidden, id] : this.hidden.filter((h) => h !== id);
    if (hide && this.expanded === id) this.expanded = null;
    this.save();
  }

  move(shown: readonly WallCell[], id: string, dir: -1 | 1): void {
    this.order = moveCell(shown, id, dir);
    this.save();
  }

  setMetric(m: MetricId): void {
    if (!isMetric(m) || m === this.metric) return;
    this.metric = m;
    this.save();
  }

  toggleExpand(id: string): void {
    this.expanded = this.expanded === id ? null : id;
  }

  /** Every plot back, default order and metric, the grid (no confirmation: layout only). */
  reset(): void {
    this.order = [...DEFAULT_LAYOUT.order];
    this.hidden = [...DEFAULT_LAYOUT.hidden];
    this.metric = DEFAULT_LAYOUT.metric;
    this.expanded = null;
    this.save();
  }
}
