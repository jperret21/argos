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
  // -- Wave 3 (A21-A24; protocol.md "Camera: capture settings, owner, Take shot").
  // Optional so an API 1 / wave 1-2 record (and the test fixtures) stay valid.
  /** Who drives the camera ("sequence": wave 6). */
  owner?: CameraOwner;
  /** What the NEXT frame uses: server state shared by every client (Q-O13). */
  settings?: CaptureSettings;
  /** The frame being exposed now (null when nothing exposes). */
  current?: FrameSettings | null;
  /** Take shots still waiting for their frame (0 or 1). */
  save_pending?: number;
  /** A Dark / Bias Take shot waiting for the wheel to settle on Dark (S1). */
  waiting_for?: 'filterwheel' | null;
  /** The driver's limits; null when disconnected. */
  limits?: CameraLimits | null;
  /** null: the driver has no Offset (field hidden). */
  offset?: { min: number; max: number } | null;
  /** null: MaxBin 1 (field hidden). */
  binning?: { max: number } | null;
  /** Sensor °C, read every 10 s while connected. */
  temperature_c?: number | null;
}

export type CameraOwner = 'idle' | 'live' | 'single' | 'autofocus' | 'sequence';
export type FrameType = 'light' | 'dark' | 'flat' | 'bias';

export interface CameraLimits {
  gain_min: number;
  gain_max: number;
  exposure_min_s: number;
  exposure_max_s: number;
}

export interface CaptureSettings {
  exposure_s: number;
  gain: number;
  frame_type: FrameType;
  /** Slot for Light / Flat (FITS metadata only without a wheel, Q-O5). */
  filter: string;
  /** Read back from the driver; null when unsupported. */
  offset: number | null;
  binning: number;
}

export interface FrameSettings {
  exposure_s: number;
  gain: number;
  frame_type: FrameType;
  filter: string;
  object_name: string;
  light: boolean;
  origin: 'single' | 'live' | 'autofocus';
  /** This frame is the one a Take shot saves. */
  save: boolean;
  /** DATE-OBS of the frame. */
  started_utc: string;
}

/** PUT /api/camera/settings: one commit, every field checked first, never clamped. */
export type CaptureSettingsBody = Partial<Pick<CaptureSettings, 'exposure_s' | 'gain' | 'frame_type' | 'filter' | 'binning'>> & {
  offset?: number;
};

/** POST /api/camera/capture (v1 body still valid; `save` makes it a Take shot). */
export interface CaptureBody {
  exposure_s?: number;
  gain?: number;
  frame_type?: FrameType;
  save?: boolean;
}

/** WS `frame_saved` (A24) and the rows of GET /api/camera/saved. */
export interface FrameSaved {
  seq: number;
  frame_seq: number;
  path: string;
  name: string;
  source: 'single' | 'sequence';
  object: string;
  filter: string;
  frame_type: FrameType;
  image_type: string;
  exposure_s: number;
  gain: number;
  date_obs: string;
  t: string;
  record?: {
    hfd: number | null;
    fwhm: number | null;
    star_count: number | null;
    sky_adu: number | null;
    peak_adu: number | null;
    eccentricity: number | null;
  };
}

/** FilterWheelState (A28). */
export interface FilterWheelState {
  state: 'disconnected' | 'idle' | 'moving' | 'error';
  name: string | null;
  slots: string[];
  dark_slot: boolean;
  position: number | null;
  slot: string | null;
  target: string | null;
  message: string | null;
  settled_utc: string | null;
}

/** FocuserState (A34). */
export interface FocuserState {
  state: 'disconnected' | 'idle' | 'moving' | 'error';
  name: string | null;
  position: number | null;
  target: number | null;
  queued: number | null;
  temperature_c: number | null;
  max_step: number | null;
  max_increment: number | null;
  absolute: boolean | null;
  step_size_um: number | null;
  locked_by: 'autofocus' | null;
  message: string | null;
  t: string;
}

/** FocuserCommand: the answer of move / step / halt (A35). */
export interface FocuserCommand {
  focuser: FocuserState;
  requested: number | null;
  sent: number | null;
  clamped: boolean;
  queued: boolean;
}

/** AutofocusState (A36). */
export interface AutofocusState {
  state: 'idle' | 'running' | 'stopping' | 'done' | 'rejected' | 'cancelled' | 'failed';
  stage: 'coarse' | 'fine' | 'verify' | 'returning' | null;
  step: number;
  total: number;
  params: { exposure_s: number; gain: number; half_range: number; num_steps: number } | null;
  start_position: number | null;
  position: number | null;
  samples: { position: number; hfd_px: number | null; stage: 'coarse' | 'fine' | 'verify'; t: string }[];
  best: { position: number; hfd_px: number | null; fitted_hfd_px: number | null; method: 'parabola' | 'raw' | 'none' } | null;
  fit: { coeffs: number[] | null; window: number[]; samples: number[][] } | null;
  message: string | null;
  run: number;
  started_utc: string | null;
  ended_utc: string | null;
}

export interface AutofocusBody {
  exposure_s?: number;
  gain?: number;
  half_range?: number;
  num_steps?: number;
}

/** Observation identity (A38, D11): the FITS OBJECT and its folder. */
export interface Observation {
  object_name: string;
  target: {
    name: string;
    ra_hours: number;
    dec_deg: number;
    object_type: string;
    type_label: string;
    is_variable: boolean;
    source: string;
    programme: 'variable' | 'exoplanet' | 'other';
  } | null;
  photometry_target: { key: string; name: string; path: string } | null;
  locked: boolean;
  locked_reason: string | null;
  revision: number;
}

export interface ObservationTargetBody {
  name: string;
  ra_hours: number;
  dec_deg: number;
  object_type?: string;
  source?: string;
  programme?: 'variable' | 'exoplanet' | 'other';
}

/** GET /api/catalog/resolve (A40). */
export interface Resolved {
  name: string;
  ra_hours: number;
  dec_deg: number;
  object_type: string;
  type_label: string;
  is_variable: boolean;
  source: string;
}

/** A name near some coordinates (A20). */
export interface Candidate extends Resolved {
  separation_arcsec: number;
}

/** WS `target_suggestions` (A20): names near the last Stellarium GoTo. */
export interface TargetSuggestions {
  ra_hours: number;
  dec_deg: number;
  state: 'checking' | 'ready' | 'failed';
  candidates: Candidate[];
  message: string | null;
  t: string;
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
  // -- Wave 3 (A29-A31), optional for API 1 / wave 1-2 records.
  alignment?: 'altaz' | 'eq' | 'eq_gem' | null;
  tracking_rate?: TrackingRate | null;
  tracking_rates?: TrackingRate[];
  /** GoTo / Sync / Center are refused (H4: mount clock more than 60 s off). */
  goto_blocked?: { reason: 'clock'; clock_error_s: number; message: string } | null;
  center_available?: boolean;
  /** What the server commands now, per axis (deg/s, 0 = stopped); null without a mount. */
  jog?: MountJog | null;
}

export type TrackingRate = 'sidereal' | 'lunar' | 'solar' | 'king';

export interface MountJog {
  primary: number;
  secondary: number;
  stop_pending: ('primary' | 'secondary')[];
  /** Stops still failing after the retries (ERROR said "use Abort"): retried slower. */
  stop_failed?: ('primary' | 'secondary')[];
  max_rate_deg_s: number;
  deadman_s: number;
  last_stop: { axis: string; reason: string; t: string } | null;
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
  /** API 2, wave 2: the Settings site against the mount's pointing (protocol.md "Site check"). */
  site_check?: SiteCheck;
  /** Wave 3: the snapshots a client opened later needs at once. */
  filterwheel?: FilterWheelState;
  focuser?: FocuserState;
  autofocus?: AutofocusState;
  observation?: Observation;
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
  /** Wave 3 (A20): the newest target-name suggestion after a Stellarium GoTo. */
  suggestions?: TargetSuggestions | null;
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
  /** Wave 2: why a read_only key cannot be PATCHed (shown under the field). */
  read_only_reason?: string | null;
  /** Wave 2: what a "path" key names (FilePicker mode); null for other types. */
  path_kind?: 'dir' | 'file' | 'exe' | null;
}

/** Wave 2: a key of 02 appendix A deliberately not in `meta`, with the reason. */
export interface OmittedKey {
  key: string;
  reason: string;
}

export interface ConfigSnapshot {
  values: Record<string, ConfigValue>;
  meta: Record<string, KeyMeta>;
  revision: number;
  path: string | null;
  /** Wave 2: the appendix A keys left out on purpose (exit criterion of wave 2). */
  omitted?: OmittedKey[];
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

// ---------------------------------------------------------------------------
// API 2, wave 2: site check, files, sessions, support bundle, settings helpers
// ---------------------------------------------------------------------------

export type SiteCheckState = 'ok' | 'mismatch' | 'unknown';
export type SiteCheckReason = 'no_mount' | 'no_site' | 'waiting' | 'no_position';

export interface SiteCheck {
  state: SiteCheckState;
  /** Set when the state is unknown. */
  reason: SiteCheckReason | null;
  /** One line for the observer (the server's words). */
  message: string;
  tolerance_deg: number;
  /** The clock the comparison used. */
  checked_utc: string | null;
  trigger: 'connect' | 'periodic' | 'site_change' | 'manual' | null;
  site: { name: string; latitude: number; longitude: number } | null;
  /** The mount reading compared. */
  mount: { ra_hours: number; dec_deg: number; alt_deg: number; az_deg: number } | null;
  /** The same RA / Dec seen from the Settings site. */
  expected: { alt_deg: number; az_deg: number } | null;
  /** Angle between the two directions (the rule). */
  separation_deg: number | null;
  /** Mount minus expected altitude (for the text only). */
  altitude_diff_deg: number | null;
  driver_site: {
    latitude: number;
    longitude: number;
    elevation_m: number | null;
    distance_km: number | null;
    state: SiteCheckState;
  } | null;
}

/** GET /api/sessions (A67, list only). */
export interface SessionSummary {
  path: string;
  folder: string;
  object: string;
  started_utc: string;
  frames: number;
  lights: number;
  filters: Record<string, number>;
  image_types: Record<string, number>;
  missing_frames: number;
  curves: { target: number; comparison: number; check: number };
  has_quality: boolean;
  has_targets: boolean;
  issues: string[];
}

export interface SessionPage {
  root: string;
  exists: boolean;
  total: number;
  offset: number;
  limit: number;
  sessions: SessionSummary[];
  scanned_utc: string;
}

/** GET /api/diagnostics/crash-reports (A6). */
export interface CrashReports {
  directory: string | null;
  reports: { path: string; name: string; t: string; size: number; summary: string }[];
}

/** GET /api/astrometry/astap (A81). */
export interface AstapState {
  astap: string | null;
  configured: string;
  configured_found: boolean;
  database_dir: string | null;
  database_source: 'configured' | 'detected' | null;
  database_found: boolean;
  database: string;
  database_ignored: boolean;
  database_args: string[];
  message: string;
}

/** Result of a `site_search` job (A82). */
export interface PlaceResult {
  label: string;
  latitude: number;
  longitude: number;
  elevation_m: number | null;
}

/** GET /api/caches (A83). */
export interface CacheInfo {
  kind: 'object' | 'exoplanet' | 'aavso' | 'gaia' | 'field_catalogue';
  label: string;
  key: string;
  path: string;
  path_kind: 'file' | 'dir';
  exists: boolean;
  files: number;
  bytes: number;
}

/** GET /api/catalogues/essential (A84). */
export interface EssentialCatalogue {
  name: string;
  version: string;
  source: string;
  source_url: string;
  object_count: number;
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

export interface SiteCheckEvent extends SiteCheck {
  type: 'site_check';
}

export interface FilterWheelEvent extends FilterWheelState {
  type: 'filterwheel';
}

export interface FocuserEvent extends FocuserState {
  type: 'focuser';
}

export interface AutofocusEvent extends AutofocusState {
  type: 'autofocus';
}

export interface ObservationEvent extends Observation {
  type: 'observation';
}

export interface TargetSuggestionsEvent extends TargetSuggestions {
  type: 'target_suggestions';
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
  | StellariumEvent
  | SiteCheckEvent
  | FilterWheelEvent
  | FocuserEvent
  | AutofocusEvent
  | ObservationEvent
  | TargetSuggestionsEvent;

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
