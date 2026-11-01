/**
 * Wire types of the ARGOS server API (contract version 2, additive over 1:
 * argos/server/protocol.md).
 *
 * These mirror the server JSON exactly (snake_case kept on purpose: no
 * renaming layer between the wire and the UI, so a field grep finds both
 * sides).
 */

/** API level this front-end is written against (GET /api/health "api"). */
export const API_VERSION = 2;

// ---------------------------------------------------------------------------
// REST
// ---------------------------------------------------------------------------

export interface Health {
  ok: boolean;
  version: string;
  api: number;
  /** API 2: identifies the server process (a restarted server has a new one). */
  boot_id?: string;
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
  /** API 2: the server process (also in /api/health and LogPage). */
  boot_id?: string;
  connection: ConnectionState;
  camera: CameraState;
  mount: MountState;
  /** API 2: per-device states (absent from an API 1 server). */
  devices?: DevicesState;
  /** API 2: the active telescope profile. */
  profile?: ProfileSummary;
}

export type ConnectRequest = { mode: 'simulator' } | { mode: 'alpaca'; host: string; port: number };

// ---------------------------------------------------------------------------
// API 2: devices (A13-A15)
// ---------------------------------------------------------------------------

export const DEVICE_IDS = ['mount', 'camera', 'filterwheel', 'focuser'] as const;
export type DeviceId = (typeof DEVICE_IDS)[number];

export type DevicePhase = 'disconnected' | 'connecting' | 'connected' | 'busy' | 'error';

export interface DeviceLink {
  mode: ConnectionMode;
  host: string | null;
  port: number | null;
}

export interface DeviceState {
  state: DevicePhase;
  /** Driver's name once connected. */
  name: string | null;
  /** One line: name, "slewing", filter slot, or the error. */
  info: string | null;
  /** Full error text while state is "error" (never cut). */
  error: string | null;
  /** Mount auto-reconnect in progress (every 10 s). */
  retrying: boolean;
  /** Profile mismatch notes (camera), clock / coordinate-system warnings (mount). */
  warnings: string[];
  link: DeviceLink | null;
  /** ISO 8601 UTC of the last change of state. */
  since: string;
}

export type DevicesState = Record<DeviceId, DeviceState>;

/** Body of the per-device and connect-all routes (defaults: alpaca, config address). */
export type DeviceConnectBody = { mode: 'simulator' } | { mode: 'alpaca'; host?: string; port?: number };

// ---------------------------------------------------------------------------
// API 2: profiles (A17)
// ---------------------------------------------------------------------------

export interface ProfileSummary {
  key: string;
  name: string;
  validated: boolean;
}

export interface Profile extends ProfileSummary {
  caveats: string[];
  aperture_mm: number;
  focal_length_mm: number;
  focal_ratio: number;
  sensor: string;
  pixel_size_um: number;
  sensor_px: [number, number];
  bayer: string | null;
  arcsec_per_px: number;
  fov_deg: [number, number];
  adc_bits: number;
  full_well_adu: number;
  linearity_max_adu: number;
  filter_names: string[];
  ap_host: string | null;
  overrides: Record<string, unknown>;
}

export interface ProfilesState {
  active: string;
  locked: boolean;
  locked_reason: string | null;
  profiles: Profile[];
}

// ---------------------------------------------------------------------------
// API 2: network (A18), discovery (A16), app info (A1), logs (A2), config (A8-A10)
// ---------------------------------------------------------------------------

export interface NetworkState {
  /** null = no Seestar address configured. */
  seestar: boolean | null;
  /** null = not checked since start-up (never probed in the background, Q-G13). */
  internet: boolean | null;
  host: string | null;
  port: number | null;
  /** Last Seestar probe. */
  t: string | null;
  /** Last internet check. */
  internet_t: string | null;
}

export interface DiscoveryBody {
  port?: number;
  candidates?: string[];
  broadcast_timeout_s?: number;
}

export interface DiscoveredDevice {
  host: string;
  port: number;
  name: string | null;
}

export interface DiscoveryResult {
  devices: DiscoveredDevice[];
  method: 'broadcast' | 'probe' | 'subnet' | null;
  searched: string[];
}

export interface AppPaths {
  config: string | null;
  config_dir: string | null;
  sessions: string;
  presets: string;
  calibrations: string;
  diagnostics: string | null;
  log_file: string | null;
}

export interface AppCredit {
  name: string;
  use: string;
  licence: string;
  url: string;
}

export interface AppInfo {
  name: string;
  version: string;
  api: number;
  python: string;
  platform: string;
  paths: AppPaths;
  profile: ProfileSummary;
  log_level: string;
  diagnostics_enabled: boolean;
  astap_configured: boolean;
  licence: string;
  licence_name: string;
  copyright: string;
  author: string;
  description: string;
  credits: AppCredit[];
  project_url: string;
  docs_url: string;
}

export type LogLevel = 'debug' | 'cmd' | 'info' | 'ok' | 'warning' | 'error';

export interface LogEntryWire {
  type?: 'log';
  id?: number;
  seq?: number;
  level: LogLevel;
  source?: string;
  topic?: string;
  message: string;
  t: string;
}

export interface LogPage {
  entries: LogEntryWire[];
  first_seq: number | null;
  last_seq: number | null;
  truncated: boolean;
  /** The server process whose seq space these lines belong to. */
  boot_id?: string;
}

// ---------------------------------------------------------------------------
// API 2: Stellarium bridge (A19)
// ---------------------------------------------------------------------------

export interface StellariumGoto {
  ra_hours: number;
  dec_deg: number;
  t: string;
  /** "slewing", "mount not connected", "mount parked", or the error text. */
  outcome: string;
}

export interface StellariumState {
  running: boolean;
  host: string | null;
  port: number | null;
  clients: number;
  /** The bind error of the last start, kept until the next one. */
  error: string | null;
  last_goto: StellariumGoto | null;
}

export type ConfigValue = string | number | boolean | null | unknown[] | Record<string, unknown>;

export interface KeyMeta {
  type: 'bool' | 'int' | 'float' | 'str' | 'path' | 'host' | 'list' | 'object';
  default: ConfigValue;
  nullable: boolean;
  min: number | null;
  max: number | null;
  step: number | null;
  options: { value: ConfigValue; label: string }[] | null;
  unit: string | null;
  label: string;
  help: string;
  used_by: string[];
  category: string;
  advanced: boolean;
  read_only: boolean;
}

export interface ConfigSnapshot {
  values: Record<string, ConfigValue>;
  meta: Record<string, KeyMeta>;
  revision: number;
  path: string | null;
}

export interface ConfigPatchResult {
  values: Record<string, ConfigValue>;
  changed: Record<string, ConfigValue>;
  warnings: { key: string; message: string }[];
  revision: number;
}

// ---------------------------------------------------------------------------
// API 2: jobs (A80)
// ---------------------------------------------------------------------------

export type JobPhaseWire = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

export interface JobWire {
  id: string;
  kind: string;
  state: JobPhaseWire;
  done: number;
  total: number | null;
  stage: string | null;
  message: string | null;
  started_utc: string;
  ended_utc: string | null;
  result: unknown;
  error: { code: string; message: string } | null;
  cancellable: boolean;
  cancel_requested: boolean;
  seq: number;
}

export interface ExposureRequest {
  exposure_s: number;
  gain: number;
}

/** Body of every 4xx/5xx response (API 2 may add `fields` and `owner`). */
export interface ErrorBody {
  error: { code: string; message: string; fields?: Record<string, string>; owner?: string };
}

// ---------------------------------------------------------------------------
// WS /ws/events
// ---------------------------------------------------------------------------

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

/** A log line: v1 `{level, message, t}`, v2 adds id / seq, source, topic and three levels. */
export interface LogEvent extends LogEntryWire {
  type: 'log';
}

export interface DevicesEvent {
  type: 'devices';
  devices: DevicesState;
}

export interface NetworkEvent extends NetworkState {
  type: 'network';
}

export interface ActivityEvent {
  type: 'activity';
  text: string;
  source: string;
  t: string;
}

export interface ConfigEvent {
  type: 'config';
  changed: Record<string, ConfigValue>;
  values: Record<string, ConfigValue>;
  revision: number;
  source: 'api' | 'file';
}

export interface JobEvent {
  type: 'job';
  job: JobWire;
}

export interface StellariumEvent extends StellariumState {
  type: 'stellarium';
}

export type ServerEvent =
  | StatusEvent
  | MountEvent
  | CameraEvent
  | LogEvent
  | DevicesEvent
  | NetworkEvent
  | ActivityEvent
  | ConfigEvent
  | JobEvent
  | StellariumEvent;

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
