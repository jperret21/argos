/**
 * Start-up screen model (01 section 2.3.8): honest stages, each marked when
 * it really completes, and a failure that stays on screen until the observer
 * acts. Pure: the caller feeds what it knows, the screen draws the result.
 *
 * Stages:
 * - desktop app only: "Starting the ARGOS server…" until the sidecar prints
 *   ARGOS_PORT / ARGOS_TOKEN;
 * - "Connecting to the ARGOS server…" until `GET /api/health` answers and
 *   `/ws/events` has sent its first `status`.
 */

export type StageState = 'pending' | 'active' | 'done' | 'failed';

export interface StartupStage {
  id: string;
  label: string;
  state: StageState;
}

export interface StartupFailure {
  title: string;
  message: string;
  /** Exact text (traceback, server answer), shown in mono and copied as is. */
  detail?: string | null;
  /** Folder or file of the server log, when known (GET /api/app/info paths.log_file). */
  logPath?: string | null;
}

export interface StartupInputs {
  /** Inside the Tauri shell (the sidecar stage exists). */
  desktop: boolean;
  sidecar?: 'starting' | 'ready' | 'failed';
  health: 'pending' | 'ok' | 'failed';
  firstStatus: boolean;
  /** Set when a stage failed: what the observer needs to act. */
  failure?: StartupFailure | null;
}

export interface StartupView {
  stages: StartupStage[];
  ready: boolean;
  failure: StartupFailure | null;
}

export function startupView(input: StartupInputs): StartupView {
  const stages: StartupStage[] = [];
  let blocked = false;
  if (input.desktop) {
    const s = input.sidecar ?? 'starting';
    stages.push({
      id: 'server',
      label: s === 'ready' ? 'ARGOS server started' : 'Starting the ARGOS server…',
      state: s === 'ready' ? 'done' : s === 'failed' ? 'failed' : 'active',
    });
    blocked = s !== 'ready';
  }
  const linkDone = input.health === 'ok' && input.firstStatus;
  stages.push({
    id: 'link',
    label: linkDone ? 'Connected to the ARGOS server' : 'Connecting to the ARGOS server…',
    state: blocked ? 'pending' : linkDone ? 'done' : input.health === 'failed' ? 'failed' : 'active',
  });
  const failed = stages.some((s) => s.state === 'failed') || !!input.failure;
  return {
    stages,
    ready: !failed && stages.every((s) => s.state === 'done'),
    failure: failed
      ? (input.failure ?? {
          title: 'ARGOS could not start',
          message: 'The ARGOS server did not answer.',
        })
      : null,
  };
}

/** The text "Copy details" puts on the clipboard. */
export function failureReport(failure: StartupFailure, version?: string | null): string {
  return [
    failure.title,
    failure.message,
    failure.detail ? `\n${failure.detail}\n` : '',
    failure.logPath ? `Log folder: ${failure.logPath}` : '',
    version ? `ARGOS ${version}` : '',
    `Time: ${new Date().toISOString()}`,
  ]
    .filter(Boolean)
    .join('\n');
}
