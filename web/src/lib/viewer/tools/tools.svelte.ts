/**
 * The viewer tools of one viewer (web/spec/04-viewer-and-image-tools.md 2.2-2.4;
 * README 3.11 "Viewer tools", per viewer): what the observer chose, remembered
 * in this browser (prefs.ts, safe without storage), never on the server.
 *
 * - View options: CFA preview (Colour by default, Q-O17), palette (D30: the
 *   choice is kept in Night Red, but Neutral is drawn), crosshair mode
 *   (centre by default, Q-O16), loupe magnification (4x, Q-O23).
 * - Inspect toggles: loupe (Z), saturation highlight (C), region statistics (R);
 *   the Statistics card (I) is a rail card, its state is the mode layout's.
 * - The region box: its last place in frame px (shown there again; else
 *   centred, 80 x 80), and its statistics on the frame on screen.
 *
 * Keys: argos.view.preview, .palette, .crosshair, .loupe, .saturation, .region.
 */

import { isBoolean, loadPref, savePref } from '../../app/prefs';
import { cfaSites } from '../palettes/cfa';
import { isPreview, type Preview } from '../palettes/cfa';
import { isPalette, type Palette } from '../palettes/lut';
import { centredRect, clampRect, isFrameRect, type FrameRect, type Point } from './geometry';
import { regionStats, type RegionStats } from './region';
import type { DecodedFrame } from '../../api/frames';

export type CrosshairMode = 'centre' | 'cursor';
export const LOUPE_MAGS = [2, 4, 8] as const;
export type LoupeMag = (typeof LOUPE_MAGS)[number];

const isCrosshairMode = (v: unknown): v is CrosshairMode => v === 'centre' || v === 'cursor';
const isLoupe = (v: unknown): v is { on: boolean; mag: LoupeMag } =>
  typeof v === 'object' && v !== null && isBoolean((v as { on?: unknown }).on) && (LOUPE_MAGS as readonly unknown[]).includes((v as { mag?: unknown }).mag);
const isRegionPref = (v: unknown): v is { on: boolean; rect: FrameRect | null } =>
  typeof v === 'object' && v !== null && isBoolean((v as { on?: unknown }).on) && ((v as { rect?: unknown }).rect === null || isFrameRect((v as { rect?: unknown }).rect));

type Store = Pick<Storage, 'getItem' | 'setItem'> | null | undefined;

export class ViewerTools {
  preview: Preview;
  palette: Palette;
  crosshairMode: CrosshairMode;
  loupe: boolean;
  loupeMag: LoupeMag;
  saturation: boolean;
  region: boolean;
  /** The region box, frame px (null until it was first placed). */
  regionRect: FrameRect | null;
  /** Statistics of the box on the frame on screen (raw samples). */
  regionResult: RegionStats | null = $state.raw(null);

  private readonly store: Store;

  constructor(store?: Store) {
    this.store = store;
    this.preview = $state(loadPref('argos.view.preview', isPreview, 'colour', store));
    this.palette = $state(loadPref('argos.view.palette', isPalette, 'neutral', store));
    this.crosshairMode = $state(loadPref('argos.view.crosshair', isCrosshairMode, 'centre', store));
    const loupe = loadPref('argos.view.loupe', isLoupe, { on: false, mag: 4 as LoupeMag }, store);
    this.loupe = $state(loupe.on);
    this.loupeMag = $state(loupe.mag);
    this.saturation = $state(loadPref('argos.view.saturation', isBoolean, false, store));
    const region = loadPref('argos.view.region', isRegionPref, { on: false, rect: null }, store);
    this.region = $state(region.on);
    this.regionRect = $state.raw(region.rect);
  }

  setPreview(p: Preview): void {
    this.preview = p;
    savePref('argos.view.preview', p, this.store);
  }

  setPalette(p: Palette): void {
    this.palette = p;
    savePref('argos.view.palette', p, this.store);
  }

  setCrosshairMode(m: CrosshairMode): void {
    this.crosshairMode = m;
    savePref('argos.view.crosshair', m, this.store);
  }

  private saveLoupe(): void {
    savePref('argos.view.loupe', { on: this.loupe, mag: this.loupeMag }, this.store);
  }

  toggleLoupe(on = !this.loupe): void {
    this.loupe = on;
    this.saveLoupe();
  }

  setLoupeMag(m: LoupeMag): void {
    this.loupeMag = m;
    this.saveLoupe();
  }

  toggleSaturation(on = !this.saturation): void {
    this.saturation = on;
    savePref('argos.view.saturation', on, this.store);
  }

  private saveRegion(): void {
    savePref('argos.view.region', { on: this.region, rect: this.regionRect }, this.store);
  }

  /** R: the box at its last place (kept inside this frame), else centred 80 x 80. */
  toggleRegion(frame: { width: number; height: number } | null, on = !this.region): void {
    this.region = on;
    if (on && frame) this.regionRect = this.placeRegion(frame);
    if (!on) this.regionResult = null;
    this.saveRegion();
  }

  /** "Region statistics here" (context menu): the box centred on a frame point, tool on. */
  regionAt(frame: { width: number; height: number }, at: Point): void {
    const side = this.regionRect ? Math.max(this.regionRect.x1 - this.regionRect.x0, this.regionRect.y1 - this.regionRect.y0) : 80;
    this.region = true;
    this.regionRect = centredRect(frame, side, at);
    this.saveRegion();
  }

  setRegionRect(r: FrameRect): void {
    this.regionRect = r;
    this.saveRegion();
  }

  private placeRegion(frame: { width: number; height: number }): FrameRect {
    const r = this.regionRect ? clampRect(this.regionRect, frame) : null;
    return r && r.x1 - r.x0 >= 2 && r.y1 - r.y0 >= 2 ? r : centredRect(frame);
  }

  /** Measure the box on a frame (raw samples); clears the result when the tool is off. */
  measure(frame: DecodedFrame | null, options: { bayer?: string | null; threshold?: number | null } = {}): void {
    if (!this.region || !frame) {
      if (this.regionResult) this.regionResult = null;
      return;
    }
    const h = frame.header;
    // First use, or a frame of another size: the box is (re)placed on this frame.
    const rect = this.placeRegion(h);
    const r = this.regionRect;
    if (!r || rect.x0 !== r.x0 || rect.y0 !== r.y0 || rect.x1 !== r.x1 || rect.y1 !== r.y1) this.regionRect = rect;
    this.regionResult = regionStats(frame.pixels, h.width, h.height, h.channels, rect, {
      sites: h.channels === 1 ? cfaSites(options.bayer) : null,
      threshold: options.threshold ?? null,
    });
  }
}
