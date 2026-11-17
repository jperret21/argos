/**
 * What R1 asks of the rest of the app (one channel, `onintent` of SessionReview): the
 * dialogs of front-end B (Re-run, Export AAVSO, Export CSV), R0 and R2, Settings. R1 never
 * opens a dialog itself; the integrator routes each intent (App.svelte):
 *
 *   <SessionReview … onintent={(i) => review.route(i)} />
 *
 * - export-aavso: everything ExportAavsoDialog takes from R1: `source` (protocol Source),
 *   `label` (its `sourceLabel`), `curves` (its `curves`, A69's list), the filter shown and
 *   that filter's target curves (S53: one filter per file; A77-A78: target-role curves only).
 *   The rail card and the toolbar send the same intent.
 * - export-csv: the same for ExportCsvDialog, plus `object` and `folder` (the session's; null
 *   for the live run or an import: a download by default); `keys` empty = every curve.
 * - rerun: the Re-run photometry dialog (M50, A76), for this session (`path`, `label`) or the
 *   live run (`path` null: the integrator gives the live run's folder).
 * - open-frame: R2 at that frame of the session (07 §2.4: Enter, Open frame, Frames row).
 * - sessions: R0 (Mod+Shift+O); open-fits: the FITS picker into R2 (Mod+O in Review).
 * - settings: a Settings category ("observer" for OBSCODE, "photometry").
 */

import type { CurveRefLike, SourceRef } from './session.svelte';

export type ReviewIntent =
  | { kind: 'export-aavso'; source: SourceRef; label: string; curves: CurveRefLike[]; filter: string | null; keys: string[] }
  | { kind: 'export-csv'; source: SourceRef; label: string; curves: CurveRefLike[]; object: string | null; folder: string | null; filter: string | null; keys: string[] }
  | { kind: 'rerun'; path: string | null; label: string }
  | { kind: 'open-frame'; path: string; filename: string; t: number }
  | { kind: 'sessions' }
  | { kind: 'open-fits' }
  | { kind: 'settings'; category: 'observer' | 'photometry' | 'catalogues' };
