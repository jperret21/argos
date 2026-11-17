/**
 * Filter wheel selection: the pure part of FilterWheelControl.svelte,
 * unit-tested. The wheel is driven by argos/server/protocol.md "Filter wheel
 * (A28)" (a port of DeviceSession.move_filter with the 0.5.0 fix H9:
 * notes/release_0_5_0.md "A refused wheel move ends busy and shows the slot
 * the wheel is on"):
 *
 * - The segmented control shows the slot the wheel REPORTS it settled on,
 *   never the one asked for: choosing a slot only requests it (deferred);
 *   the block slides when the wheel says it arrived (spec 05 P2, P3).
 * - Manual activation: the arrows walk the slots without moving the wheel;
 *   Space / Enter choose (PROPOSAL 3.3 "never moves it three times").
 * - While it turns, the requested slot spins and the others wait.
 * - Without a wheel the slot is FITS metadata only (Q-O5): the choice is the
 *   capture setting `filter`, applied at once.
 */

import type { SegmentOption } from '../../components/segmented';
import type { FilterWheelView } from './types';

export type WheelMode = 'wheel' | 'metadata';

/** A connected wheel drives the choice; without one the slot is FITS metadata only. */
export function wheelMode(w: FilterWheelView | null | undefined): WheelMode {
  return w && w.state !== 'disconnected' ? 'wheel' : 'metadata';
}

/** The settled slot name the wheel reports, or null (moving, unknown). */
export function settledSlot(w: FilterWheelView | null | undefined): string | null {
  if (!w || w.state === 'moving') return null;
  if (w.slot) return w.slot;
  if (w.position !== null && w.position !== undefined && w.position >= 0 && w.position < w.slots.length) return w.slots[w.position];
  return null;
}

export function wheelOptions(slots: readonly string[]): SegmentOption[] {
  return slots.map((s) => ({ value: s, label: s }));
}

/** Why no slot can be chosen now, or null. */
export function wheelReason(
  w: FilterWheelView | null | undefined,
  ctx: { cameraOwner?: string | null } = {},
): string | null {
  if (ctx.cameraOwner === 'autofocus') return 'Autofocus owns the camera';
  if (ctx.cameraOwner === 'sequence') return 'The sequence owns the camera';
  if (!w) return null;
  if (w.state === 'disconnected') return w.slots.length ? null : 'No filter slots in the active profile';
  return null;
}

/** The slot being turned to (spinner), or null. */
export function wheelBusy(w: FilterWheelView | null | undefined): string | null {
  return w && w.state === 'moving' ? (w.target ?? null) : null;
}

export interface WheelLine {
  kind: 'plain' | 'muted' | 'reason' | 'bad';
  text: string;
}

/** The line under the control (aria-live): turning, refused (H9), unknown, metadata only. */
export function wheelLine(w: FilterWheelView | null | undefined, metadataFilter?: string | null): WheelLine | null {
  if (!w || w.state === 'disconnected') {
    const name = metadataFilter ? `‘${metadataFilter}’` : 'The chosen slot';
    return { kind: 'muted', text: `No filter wheel: ${name} is written to FITS FILTER only` };
  }
  if (w.state === 'moving') return { kind: 'plain', text: `Turning to ${w.target ?? 'the slot'}…` };
  if (w.state === 'error') return { kind: 'bad', text: w.message ?? 'Filter wheel error: position unknown' };
  const slot = settledSlot(w);
  if (w.message) return { kind: 'reason', text: slot ? `${w.message} The wheel is on ${slot}.` : w.message };
  if (!slot) return { kind: 'reason', text: 'Position unknown: choose a slot to move the wheel' };
  return null;
}
