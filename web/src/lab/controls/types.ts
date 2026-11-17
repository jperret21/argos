/** Shared option and item types of the lab controls. */

import type { MenuEntry } from '../../lib/components/menu';
import type { ExposureSim, FocuserSim, MountSim } from './sim.svelte';


export interface SegOption<V extends string> {
  value: V;
  label: string;
  icon?: string;
  /** Mono detail after the label ("0.5 °/s"). */
  detail?: string;
  /** Show only the icon (the label becomes the accessible name and tip). */
  iconOnly?: boolean;
  disabledReason?: string | null;
}

/** One tool of a toolbar (Toolbar.svelte): a button, a toggle, a split button or a readout. */
export interface ToolDef {
  id: string;
  /** Tools of one group stay together; groups are separated by a rule. */
  group: string;
  kind: 'button' | 'toggle' | 'split' | 'readout';
  icon: string;
  label: string;
  shortcut?: string;
  /** Higher stays longer; Infinity is never moved to the overflow menu. */
  priority: number;
  pressed?: boolean;
  layoutToggle?: boolean;
  showLabel?: boolean;
  variant?: 'ghost' | 'secondary' | 'primary' | 'danger';
  glyphTone?: 'danger';
  disabledReason?: string | null;
  busy?: boolean;
  progress?: number | null;
  progressText?: string;
  /** Readout text ("48 %") or the split button's detail ("2.0 s"). */
  text?: string;
  /** Split button options. */
  items?: readonly MenuEntry[];
  /** Placed after the flexible space, at the toolbar's right end. */
  end?: boolean;
}

/** The simulated hardware shared by every plate. */
export interface Hardware {
  focuser: FocuserSim;
  mount: MountSim;
  exposure: ExposureSim;
}
