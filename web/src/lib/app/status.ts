/**
 * Device states -> badge tone + observer wording.
 *
 * Tones map to the status tokens (BRAND 4.1): idle = --status-idle,
 * ok = --status-ok, busy = --status-busy, error = --status-error, and active
 * = --accent (kept for the one thing that must stand out; live view is "ok",
 * its brass is on the image chip and the toolbar toggle). A tone is only the
 * dot; the label always says the state in words (Night Red: dots fall below
 * 3:1, the label carries the state).
 *
 * `stale` = the server link is down: the device records on screen are the
 * last ones received, so no device state is claimed ("No link").
 */

import type { LinkState } from '../api/socket';
import type { CameraState, ConnectionState, MountState } from '../api/types';

export type Tone = 'idle' | 'ok' | 'busy' | 'error' | 'active';

export interface StatusView {
  tone: Tone;
  label: string;
}

export function connectionStatus(c: ConnectionState | null, link: LinkState): StatusView {
  if (link === 'unauthorized') return { tone: 'error', label: 'Token rejected' };
  if (link === 'forbidden') return { tone: 'error', label: 'Origin refused' };
  if (link !== 'open') {
    return link === 'idle' || link === 'connecting'
      ? { tone: 'busy', label: 'Reaching server' }
      : { tone: 'error', label: 'Server offline' };
  }
  switch (c?.state) {
    case 'connected':
      return { tone: 'ok', label: 'Connected' };
    case 'connecting':
      return { tone: 'busy', label: 'Connecting' };
    case 'error':
      return { tone: 'error', label: 'Connection error' };
    default:
      return { tone: 'idle', label: 'Disconnected' };
  }
}

export const NO_LINK: StatusView = { tone: 'idle', label: 'No link' };

export function cameraStatus(cam: CameraState | null, connected: boolean, stale = false): StatusView {
  if (stale) return NO_LINK;
  if (!connected || !cam) return { tone: 'idle', label: 'Offline' };
  switch (cam.state) {
    case 'exposing':
      return { tone: 'busy', label: 'Exposing' };
    case 'downloading':
      return { tone: 'busy', label: 'Downloading' };
    case 'live':
      // Running as asked: --status-ok. The LIVE chip and the toolbar toggle
      // already carry the brass; a third brass dot would dilute it (BRAND 3).
      return { tone: 'ok', label: 'Live' };
    case 'error':
      return { tone: 'error', label: 'Error' };
    default:
      return { tone: 'ok', label: 'Idle' };
  }
}

export function mountStatus(m: MountState | null, connected: boolean, stale = false): StatusView {
  if (stale) return NO_LINK;
  if (!connected || !m) return { tone: 'idle', label: 'Offline' };
  switch (m.state) {
    case 'parked':
      return { tone: 'idle', label: 'Parked' };
    case 'slewing':
      return { tone: 'busy', label: 'Slewing' };
    case 'tracking':
      return { tone: 'ok', label: 'Tracking' };
    case 'error':
      return { tone: 'error', label: 'Error' };
    default:
      // Unparked and not tracking: the field drifts (Qt shows "Tracking OFF" in warning).
      return m.tracking ? { tone: 'ok', label: 'Tracking' } : { tone: 'busy', label: 'Not tracking' };
  }
}
