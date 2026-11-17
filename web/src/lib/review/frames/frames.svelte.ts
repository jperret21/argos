/**
 * State of the Review Frames drawer tab (07 WF-C): the session's rows, the text filter, the
 * hidden columns and the sort (both remembered per viewer, README 3.5), and the selected row
 * shared with the plots (one selected time, 07 2.4 "Selection model").
 *
 *   const frames = new FramesView();
 *   frames.setFrames(session.frames);        // A68 frames[]
 *   frames.selectAt(t)                       // a plot point was selected: highlight its frame
 *   <FramesTools view={frames} /> + <FramesTable view={frames} onselect onactivate />
 */

import { applySort, isSortState, toTsv, type SortState } from '../../components/table';
import { loadPref, savePref } from '../../app/prefs';
import {
  DEFAULT_HIDDEN,
  filterRows,
  frameAt,
  frameCounts,
  frameRows,
  isColumnId,
  openableLights,
  visibleColumns,
  type FrameColumnId,
  type FrameRow,
} from './frames';

export const PREF_HIDDEN = 'argos.review.frames.hidden';
export const PREF_SORT = 'argos.review.frames.sort';

const isHidden = (v: unknown): v is FrameColumnId[] => Array.isArray(v) && v.every(isColumnId);

export class FramesView {
  rows: FrameRow[] = $state.raw([]);
  query = $state('');
  hidden: ReadonlySet<FrameColumnId> = $state.raw(new Set(DEFAULT_HIDDEN));
  sort: SortState | null = $state(null);
  /** Key of the selected row (the time cursor's frame). */
  selected: string | null = $state(null);

  readonly shown = $derived(filterRows(this.rows, this.query));
  readonly columns = $derived(visibleColumns(this.hidden));
  readonly counts = $derived(frameCounts(this.rows));
  readonly lights = $derived(openableLights(this.rows));

  constructor(load = true) {
    if (!load) return;
    this.hidden = new Set(loadPref(PREF_HIDDEN, isHidden, [...DEFAULT_HIDDEN]));
    this.sort = loadPref(PREF_SORT, isSortState, null);
  }

  setFrames(frames: readonly unknown[]): void {
    this.rows = frameRows(frames);
    if (this.selected && !this.rows.some((r) => r.key === this.selected)) this.selected = null;
  }

  row(key: string | null): FrameRow | null {
    return key === null ? null : (this.rows.find((r) => r.key === key) ?? null);
  }

  /** The row of a server frame index (a curve point's `frame` column, A69), or null. */
  byIndex(index: number | null | undefined): FrameRow | null {
    if (index === null || index === undefined) return null;
    return this.rows.find((r) => r.index === index) ?? null;
  }

  /** The row of a frame file name (a point's matched frame), or null. */
  byName(filename: string | null | undefined): FrameRow | null {
    if (!filename) return null;
    const base = filename.slice(filename.lastIndexOf('/') + 1);
    return this.rows.find((r) => r.filename === base || r.path === filename) ?? null;
  }

  /** Select the frame a plot time (unix s) falls on; returns it (null: none, selection cleared). */
  selectAt(t: number | null): FrameRow | null {
    const r = t === null ? null : frameAt(this.rows, t);
    this.selected = r?.key ?? null;
    return r;
  }

  toggleColumn(id: FrameColumnId, on: boolean): void {
    const next = new Set(this.hidden);
    if (on) next.delete(id);
    else next.add(id);
    this.hidden = next;
    savePref(PREF_HIDDEN, [...next]);
  }

  setSort(s: SortState | null): void {
    this.sort = s;
    savePref(PREF_SORT, s);
  }

  /** TSV of the rows shown (filter, sort and columns as on screen), header first. */
  tsv(): string {
    return toTsv(this.columns, applySort(this.shown, this.columns, this.sort));
  }
}
