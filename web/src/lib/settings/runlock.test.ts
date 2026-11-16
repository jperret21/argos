import { describe, expect, it } from 'vitest';
import { GEOMETRY_LOCK_REASON, NOISE_MODEL_LOCK_REASON, runLockReasons } from './runlock';

describe('settings locked during a run (S15, S84)', () => {
  it('names the aperture geometry, the noise model and the e-/ADU, with the server sentence, only while a run is active', () => {
    const locked = runLockReasons(true);
    expect(Object.keys(locked).sort()).toEqual([
      'camera.egain_table',
      'data_paths.camera_calibration_directory',
      'photometry.annulus_in_px',
      'photometry.annulus_out_px',
      'photometry.aperture_fwhm_mult',
      'photometry.aperture_min_px',
      'photometry.noise_model',
      'photometry.read_noise_e',
    ]);
    expect(locked['photometry.aperture_min_px']).toBe(GEOMETRY_LOCK_REASON);
    expect(locked['photometry.noise_model']).toBe(NOISE_MODEL_LOCK_REASON);
    expect(locked['photometry.read_noise_e']).toBe(NOISE_MODEL_LOCK_REASON);
    // the camera's e-/ADU (S73's chain) sets the same SNR and errors (validation F1)
    expect(locked['camera.egain_table']).toBe(NOISE_MODEL_LOCK_REASON);
    expect(locked['data_paths.camera_calibration_directory']).toBe(NOISE_MODEL_LOCK_REASON);
    expect(locked['photometry.min_comparisons']).toBeUndefined(); // the comparison selection stays free
    expect(runLockReasons(false)).toEqual({});
  });
});
