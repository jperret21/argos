/**
 * The records the wave-3 instruments draw (web/spec/README.md section 4.3,
 * rows A28 filter wheel, A29-A30 mount geometry and jog, A34-A35 focuser,
 * A36 autofocus), as `argos/server/protocol.md` "API 2 routes, wave 3"
 * defines them. The instruments take these as props, so a card passes the
 * server's records through unchanged and wires the commands to the REST
 * client; nothing in this folder talks to the network.
 *
 * Field names keep the server's snake_case (a grep finds both sides). Every
 * field the instruments do not strictly need is optional: an older or
 * partial record degrades to "—" or to a disabled control with its reason,
 * never to a wrong value.
 */

/** FocuserState (A34). Position and IsMoving are polled by the server: 0.5 s moving, 5 s idle. */
export interface FocuserView {
  state: 'disconnected' | 'idle' | 'moving' | 'error' | (string & {});
  name?: string | null;
  /** Last POLLED position: the needle (never interpolated between polls). */
  position: number | null;
  /** The last move sent to the driver (the move in progress while moving). */
  target?: number | null;
  /** Target waiting for the move in progress (D9: taps queued, sent as one move). */
  queued?: number | null;
  /** Polled every 10 s. */
  temperature_c?: number | null;
  /** Travel 0 … max_step: Go to is bounded by it, never clamped (H10). */
  max_step?: number | null;
  max_increment?: number | null;
  absolute?: boolean | null;
  step_size_um?: number | null;
  /** "autofocus" while autofocus owns the focuser: manual moves are refused (H10). */
  locked_by?: 'autofocus' | (string & {}) | null;
  /** The driver's words (an error, a refusal). */
  message?: string | null;
  t?: string;
}

/** FocuserCommand: the answer of move / step / halt (A35). */
export interface FocuserCommandResult {
  focuser: FocuserView;
  /** The position asked for (a step: target + delta). */
  requested: number | null;
  /** What was sent to the driver now (null: queued, or a halt). */
  sent: number | null;
  /** A step was clamped to 0 … max_step (reported, H10). */
  clamped: boolean;
  queued: boolean;
}

export type AutofocusStage = 'coarse' | 'fine' | 'verify' | 'returning';

export interface AutofocusSample {
  position: number;
  hfd_px: number | null;
  stage?: 'coarse' | 'fine' | 'verify' | (string & {}) | null;
  t?: string;
}

export interface AutofocusBest {
  position: number;
  /** Measured at the end (the verification exposure). */
  hfd_px?: number | null;
  fitted_hfd_px?: number | null;
  method?: 'parabola' | 'raw' | 'none' | (string & {}) | null;
}

export interface AutofocusParams {
  exposure_s: number;
  gain: number;
  half_range: number;
  num_steps: number;
}

/** AutofocusState (A36). `stopping`: Stop AF was pressed; the focuser returns to its start (S23). */
export interface AutofocusView {
  state: 'idle' | 'running' | 'stopping' | 'done' | 'rejected' | 'cancelled' | 'failed' | (string & {});
  stage?: AutofocusStage | (string & {}) | null;
  /** Samples taken / announced. */
  step?: number | null;
  total?: number | null;
  /** Exposure and gain the sweep uses: the server applies the gain (S22). */
  params?: AutofocusParams | null;
  /** Where the sweep started (where Stop AF returns). */
  start_position?: number | null;
  /** The focuser at the end. */
  position?: number | null;
  samples?: readonly AutofocusSample[];
  best?: AutofocusBest | null;
  fit?: { coeffs: readonly number[] | null; window: readonly number[]; samples: readonly (readonly number[])[] } | null;
  message?: string | null;
  run?: number;
  started_utc?: string | null;
  ended_utc?: string | null;
}

/** FilterWheelState (A28). */
export interface FilterWheelView {
  state: 'disconnected' | 'idle' | 'moving' | 'error' | (string & {});
  /** The wheel's driver name. */
  name?: string | null;
  /** The active profile's slot names, in wheel order. */
  slots: readonly string[];
  /** A "Dark" slot exists (it blocks the light: Dark and Bias shots need it, S1). */
  dark_slot?: boolean;
  /** Settled slot index; null while moving or unknown. */
  position: number | null;
  /** Settled slot name. */
  slot?: string | null;
  /** The slot a move goes to. */
  target?: string | null;
  /** Why the position is unknown, or the driver's refusal (H9). */
  message?: string | null;
  settled_utc?: string | null;
}

/** MountState.alignment (A29): axis words on alt-az, compass letters on EQ (Q-O4). */
export type MountAlignment = 'altaz' | 'eq' | 'eq_gem' | null;

export type JogAxis = 'primary' | 'secondary';

/** MountState.jog (A30): what the SERVER commands now, per axis, signed °/s (0 = stopped). */
export interface MountJogView {
  primary: number;
  secondary: number;
  /** An axis whose stop failed: the server retries it (H3). */
  stop_pending?: readonly JogAxis[];
  max_rate_deg_s?: number;
  deadman_s?: number;
  last_stop?: { axis: string; reason: string; t: string } | null;
}
