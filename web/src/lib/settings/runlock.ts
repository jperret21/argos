/**
 * Settings locked while a sequence runs: the server answers a `PATCH /api/config` touching
 * them with `409 run_active` (protocol.md "Photometry geometry and noise model locked (S15,
 * S84)"). One curve keeps one aperture (S15) and one error model (S84: the noise model, the
 * read noise and the camera's e-/ADU, from the gain table or the photon-transfer folder, set
 * the SNR the gates read and every formal error). The Settings pages (Photometry,
 * Instrument) show these keys unavailable during a run, with the server's own sentence,
 * rather than refusing an edit after the fact. tests/server/test_settings_wave2.py checks
 * the keys and sentences against the server's (argos/server/sequence.py).
 */

export const GEOMETRY_KEYS = [
  'photometry.aperture_fwhm_mult',
  'photometry.aperture_min_px',
  'photometry.annulus_in_px',
  'photometry.annulus_out_px',
] as const;

export const NOISE_MODEL_KEYS = [
  'photometry.noise_model',
  'photometry.read_noise_e',
  'camera.egain_table',
  'data_paths.camera_calibration_directory',
] as const;

export const GEOMETRY_LOCK_REASON = 'The aperture geometry is locked while a sequence runs (one curve, one aperture).';

export const NOISE_MODEL_LOCK_REASON =
  "The noise model and the camera's e-/ADU are locked while a sequence runs (one curve, one error model).";

/** A SettingsBlock's `reasons`: every locked key with its sentence while a run is active, none otherwise. */
export function runLockReasons(runActive: boolean): Record<string, string> {
  if (!runActive) return {};
  return Object.fromEntries([
    ...GEOMETRY_KEYS.map((k) => [k, GEOMETRY_LOCK_REASON]),
    ...NOISE_MODEL_KEYS.map((k) => [k, NOISE_MODEL_LOCK_REASON]),
  ]);
}
