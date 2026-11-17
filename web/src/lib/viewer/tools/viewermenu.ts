/**
 * The viewer's context menu (web/spec/04-viewer-and-image-tools.md 2.2 rows
 * 1.2, 2.3 "Viewer context menu"): task actions in the observer's words
 * instead of the pyqtgraph defaults (View All, axis inversion that mirrored
 * the sky, mouse modes: dropped, P25). Pure: which items, enabled or why not.
 */

import { formatDec, formatRA } from '../../format/astro';
import type { MenuEntry } from '../../components/menu';

export interface ViewerMenuContext {
  /** The frame pixel under the pointer (null: off the image). */
  pixel: { x: number; y: number } | null;
  /** Its sky position when the field is identified. */
  sky: { raHours: number; decDeg: number } | null;
  /** Shortcuts from the registry. */
  keys: { fit?: string; one?: string; region?: string };
  /** Measure / identify is wired (the field's star selection, A49). */
  canIdentify: boolean;
  /** Why identification is not available (null: it is). */
  identifyReason?: string | null;
  /** A star is selected (Clear selection acts). */
  hasSelection: boolean;
}

export type ViewerMenuAction = 'fit' | 'one' | 'identify' | 'copy-pixel' | 'copy-sky' | 'region' | 'clear' | 'save-png';

export function pixelText(p: { x: number; y: number }): string {
  return `x ${Math.round(p.x)} · y ${Math.round(p.y)}`;
}

export function skyText(s: { raHours: number; decDeg: number }): string {
  return `${formatRA(s.raHours)}  ${formatDec(s.decDeg, 1)}`;
}

export function viewerMenuItems(c: ViewerMenuContext): MenuEntry[] {
  const off = c.pixel ? null : 'the pointer is not on the image';
  return [
    { id: 'fit', label: 'Fit to window', icon: 'zoom-fit', shortcut: c.keys.fit },
    { id: 'one', label: 'Actual pixels (1:1)', icon: 'zoom-1to1', shortcut: c.keys.one },
    { kind: 'separator' },
    {
      id: 'identify',
      label: 'Measure / identify here',
      icon: 'crosshair',
      detail: 'the same as a click on the star',
      disabledReason: off ?? (c.canIdentify ? null : (c.identifyReason ?? 'star selection is not available here')),
    },
    { id: 'copy-pixel', label: 'Copy pixel position', icon: 'copy', detail: c.pixel ? pixelText(c.pixel) : undefined, disabledReason: off },
    {
      id: 'copy-sky',
      label: 'Copy RA / Dec',
      icon: 'copy',
      detail: c.sky ? skyText(c.sky) : undefined,
      disabledReason: off ?? (c.sky ? null : 'identify the field first (S)'),
    },
    { kind: 'separator' },
    { id: 'region', label: 'Region statistics here', icon: 'region-stats', shortcut: c.keys.region, disabledReason: off },
    { id: 'clear', label: 'Clear selection', icon: 'clear', shortcut: 'Escape', disabledReason: c.hasSelection ? null : 'no star is selected' },
    { kind: 'separator' },
    { id: 'save-png', label: 'Save view as PNG…', icon: 'export', detail: 'the image and its overlays, at screen resolution' },
  ];
}
