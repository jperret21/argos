/**
 * Wire types of the ARGOS server API (contract version 1).
 *
 * These mirror the server JSON exactly (snake_case kept on purpose: no
 * renaming layer between the wire and the UI, so a field grep finds both
 * sides).
 */

export const API_VERSION = 1;

// ---------------------------------------------------------------------------
// REST
// ---------------------------------------------------------------------------

export interface Health {
  ok: boolean;
  version: string;
  api: number;
}

export type ConnectionPhase = 'disconnected' | 'connecting' | 'connected' | 'error';
export type ConnectionMode = 'simulator' | 'alpaca';

export interface ConnectionState {
  state: ConnectionPhase;
  mode: ConnectionMode | null;
  device_name: string | null;
  message: string | null;
}

export type CameraPhase = 'idle' | 'exposing' | 'downloading' | 'live' | 'error';

export interface SensorInfo {
  width: number;
  height: number;
  bitpix: 16;
  bayer: string | null;
}

export interface CameraState {
  state: CameraPhase;
  exposure_s: number;
  gain: number;
  last_frame_seq: number | null;
  sensor: SensorInfo | null;
}

export type MountPhase = 'parked' | 'idle' | 'slewing' | 'tracking' | 'error';
export type PierSide = 'east' | 'west';

export interface EquatorialTarget {
  ra_hours: number;
  dec_deg: number;
}

export interface MountState {
  state: MountPhase;
  ra_hours: number;
  dec_deg: number;
  alt_deg: number | null;
  az_deg: number | null;
  tracking: boolean;
  pier_side: PierSide | null;
  target: EquatorialTarget | null;
}

export interface Status {
  connection: ConnectionState;
  camera: CameraState;
  mount: MountState;
}

export type ConnectRequest = { mode: 'simulator' } | { mode: 'alpaca'; host: string; port: number };

export interface ExposureRequest {
  exposure_s: number;
  gain: number;
}

/** Body of every 4xx/5xx response. */
export interface ErrorBody {
  error: { code: string; message: string };
}

// ---------------------------------------------------------------------------
// WS /ws/events
// ---------------------------------------------------------------------------

export type LogLevel = 'info' | 'warning' | 'error';

export interface StatusEvent extends Status {
  type: 'status';
}

export interface MountEvent {
  type: 'mount';
  mount: MountState;
}

export interface CameraEvent {
  type: 'camera';
  camera: CameraState;
}

export interface LogEvent {
  type: 'log';
  level: LogLevel;
  message: string;
  /** ISO 8601 UTC. */
  t: string;
}

export type ServerEvent = StatusEvent | MountEvent | CameraEvent | LogEvent;

// ---------------------------------------------------------------------------
// WS /ws/frames (binary): see frames.ts for the byte layout
// ---------------------------------------------------------------------------

export type FrameSource = 'simulator' | 'alpaca' | 'file';

export interface FrameStats {
  min: number;
  max: number;
  median: number;
  /** Raw median absolute deviation (NOT scaled by 1.4826). */
  mad: number;
  mean: number;
}

export interface FrameHeader {
  seq: number;
  width: number;
  height: number;
  channels: 1 | 3;
  dtype: 'uint16';
  pixel_offset: number;
  exposure_s: number;
  /** ISO 8601 UTC. */
  timestamp: string;
  source: FrameSource;
  stats: FrameStats;
}
