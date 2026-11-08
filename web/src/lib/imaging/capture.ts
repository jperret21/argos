/**
 * Take shot rules the Observe screen states before the server would refuse
 * (pure, unit-tested). The server stays the authority (argos/server/capture.py,
 * protocol.md "What a Take shot writes"); these only let the toolbar and the
 * Camera card say it in words first.
 *
 * - S1 (0.5.0): the Seestar has no shutter, so a Dark or Bias needs the opaque
 *   Dark slot. The server turns the wheel to Dark before the exposure and
 *   answers 409 busy while the wheel is turning to another slot.
 * - Who owns the camera (A21): autofocus and a sequence refuse capture
 *   settings and shots.
 */

import type { FilterWheelState, FrameType } from '../api/types';

type Wheel = Pick<FilterWheelState, 'state' | 'dark_slot' | 'slot' | 'target'> | null | undefined;

const WORD: Record<FrameType, string> = { light: 'Light', dark: 'Dark', flat: 'Flat', bias: 'Bias' };

export function frameWord(t: FrameType | string): string {
  return WORD[t as FrameType] ?? t;
}

/** A frame type that needs the light blocked. */
export function needsDark(t: FrameType | string | undefined): boolean {
  return t === 'dark' || t === 'bias';
}

const isDarkSlot = (name: string | null | undefined): boolean => name?.toLowerCase() === 'dark';

/**
 * Why a Take shot of this type is refused now (mirrors the server's 409), or
 * null. Dark / Bias: only a wheel turning to ANOTHER slot refuses; a wheel
 * elsewhere and settled is turned to Dark by the server. Light / Flat: the
 * opaque slot refuses (409 dark_slot), since the server leaves the wheel on
 * Dark after a dark frame and a light frame through it would be pure pedestal.
 */
export function darkGuard(frameType: FrameType | string | undefined, wheel: Wheel): string | null {
  if (!wheel || wheel.state === 'disconnected' || !wheel.dark_slot) return null;
  const word = frameWord((frameType ?? 'light') as FrameType);
  if (!needsDark(frameType)) {
    if (wheel.state === 'moving' && isDarkSlot(wheel.target)) return `the filter wheel is turning to ${wheel.target}, which blocks the light: choose a filter for the ${word} frame`;
    if (wheel.state !== 'moving' && isDarkSlot(wheel.slot)) return `the filter wheel is on ${wheel.slot}, which blocks the light: choose a filter for the ${word} frame`;
    return null;
  }
  if (wheel.state === 'moving' && wheel.target && !isDarkSlot(wheel.target)) {
    return `the filter wheel is turning to ${wheel.target}: a ${word} frame needs it settled on Dark first`;
  }
  return null;
}

/** Why autofocus would sweep in the dark (mirrors the server's 409), or null. */
export function autofocusWheelGuard(wheel: Wheel): string | null {
  if (!wheel || wheel.state === 'disconnected' || !wheel.dark_slot) return null;
  if (wheel.state === 'moving') return `the filter wheel is turning to ${wheel.target ?? 'a slot'}`;
  if (isDarkSlot(wheel.slot)) return `the filter wheel is on ${wheel.slot}, which blocks the light: choose a filter first`;
  return null;
}

export interface FrameNote {
  text: string;
  tone: 'info' | 'warn';
}

/** The Camera card's line under the frame type: what a Dark / Bias shot will do, or why it cannot. */
export function frameNote(frameType: FrameType | string | undefined, wheel: Wheel, waitingForWheel: boolean): FrameNote | null {
  if (waitingForWheel) {
    return { text: 'Turning the wheel to Dark: the exposure starts once it has settled (no shutter).', tone: 'info' };
  }
  const guard = darkGuard(frameType, wheel);
  if (guard) return { text: `Take shot refused now: ${guard}.`, tone: 'warn' };
  if (!needsDark(frameType)) return null;
  if (wheel && wheel.state !== 'disconnected' && wheel.dark_slot) {
    return wheel.slot?.toLowerCase() === 'dark'
      ? { text: 'The wheel is on Dark: the light is blocked.', tone: 'info' }
      : { text: `Take shot turns the wheel to Dark first (now ${wheel.slot ?? 'unknown'}): the Seestar has no shutter.`, tone: 'info' };
  }
  return { text: 'No filter wheel to block the light: cover the telescope for a dark frame.', tone: 'warn' };
}

/** Why the capture settings cannot change now (the camera's owner), or null. */
export function ownerReason(owner: string | undefined | null): string | null {
  if (owner === 'autofocus') return 'autofocus owns the camera until it ends';
  if (owner === 'sequence') return 'the sequence owns the camera';
  return null;
}

/** The exposure and gain the next autofocus sweep uses (S22: the capture settings, exposure capped at 10 s). */
export function afFrames(
  af: { state?: string; params?: { exposure_s: number; gain: number } | null } | null | undefined,
  settings: { exposure_s: number; gain: number } | null | undefined,
): { exposure_s: number; gain: number } | null {
  if ((af?.state === 'running' || af?.state === 'stopping') && af.params) return { exposure_s: af.params.exposure_s, gain: af.params.gain };
  if (!settings) return null;
  return { exposure_s: Math.min(10, settings.exposure_s), gain: settings.gain };
}
