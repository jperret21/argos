import { describe, expect, it } from 'vitest';
import { stripLayout } from '../layout';
import {
  AVAILABLE_MODES,
  BAND,
  bandLayout,
  bandMax,
  CARD_IDS,
  arrangementChanged,
  changedKeys,
  clonePreset,
  drawerHeight,
  isMode,
  layoutCost,
  MODES,
  PRESETS,
  RAIL,
  sanitize,
} from './layout';

/** A Seestar frame (1080 x 1920) after the "auto" display rotation. */
const FRAME = { width: 1920, height: 1080 };
/** Centre region at 1440 x 900 (D8): 1440 − 92 rail − 400 panel − 1 separator; 900 − 44 − 28. */
const C1440 = { width: 947, height: 828 };
/** Same at 1280 x 800. */
const C1280 = { width: 787, height: 728 };

describe('band layout (BRAND 11.1, stripLayout unchanged)', () => {
  it('takes exactly the band the fitted image leaves at 1440 x 900', () => {
    const b = bandLayout(C1440, FRAME, 0, true, null);
    expect(b.compact).toBe(false);
    expect(b.height).toBe(stripLayout(C1440, FRAME, 0, true).height);
    expect(b.height).toBe(295);
    expect(b.sideBands.x).toBe(0);
    expect(b.sideBands.y).toBeLessThan(1); // no dead band
  });

  it('takes exactly the band at 1280 x 800 too', () => {
    const b = bandLayout(C1280, FRAME, 0, true, null);
    expect(b.compact).toBe(false);
    expect(b.height).toBe(285);
    expect(b.sideBands.y).toBeLessThan(1);
  });

  it('turns into the one-row summary below 150 px, still as tall as the band', () => {
    const b = bandLayout(C1440, FRAME, 216, true, null);
    expect(b.compact).toBe(true);
    expect(b.height).toBe(79);
    expect(b.sideBands.y).toBeLessThan(1);
    const narrow = bandLayout({ width: 947, height: 828 }, FRAME, 160, true, null);
    expect(narrow.height).toBe(135);
    expect(narrow.compact).toBe(true); // 135 < 150: summary (the lab used 120)
  });

  it('a dragged band overrides the rule, keeps 200 px of viewer, and shows the cost', () => {
    const b = bandLayout(C1440, FRAME, 0, true, 790);
    expect(b.viewer).toBe(BAND.minViewer);
    expect(b.height).toBe(628);
    expect(b.sideBands.x).toBeGreaterThan(0);
    expect(layoutCost('band', b, {})).toBe('Band 628 px · image 356 × 200 · side margins 296 px');
    expect(bandMax(C1440, 0)).toBe(628);
    const low = bandLayout(C1440, FRAME, 0, true, 90);
    expect(low.compact).toBe(true);
    expect(low.height).toBe(BAND.compactH);
    expect(layoutCost('band', bandLayout(C1440, FRAME, 0, true, null), { fits: true })).toBe(
      'Band 295 px (fits the image) · image 947 × 533 · no black margin',
    );
  });

  it('closed band: the whole height goes to the viewer', () => {
    const b = bandLayout(C1440, FRAME, 0, false, null);
    expect(b.height).toBe(0);
    expect(b.viewer).toBe(828);
    expect(layoutCost('rail', b, { rail: 400 })).toBe('Right panel 400 px · image 947 × 533 · top and bottom margins 148 px');
  });

  it('a drawer is kept between 160 px and half the section', () => {
    expect(drawerHeight({ drawerOpen: false, drawerH: 300 }, 828)).toBe(0);
    expect(drawerHeight({ drawerOpen: true, drawerH: 216 }, 828)).toBe(216);
    expect(drawerHeight({ drawerOpen: true, drawerH: 600 }, 828)).toBe(414);
    expect(drawerHeight({ drawerOpen: true, drawerH: 100 }, 828)).toBe(160);
  });
});

describe('modes and presets', () => {
  it('Framing, Focus and Field are available; Run says why not', () => {
    expect(AVAILABLE_MODES).toEqual(['framing', 'focus', 'field']);
    for (const m of MODES.filter((d) => d.unavailable)) expect(m.unavailable).toMatch(/wave/);
    expect(isMode('focus')).toBe(true);
    expect(isMode('watch')).toBe(false);
  });

  it('keeps one card order and the D8 panel width; Focus opens the focuser', () => {
    expect(CARD_IDS).toEqual(['camera', 'statistics', 'inspector', 'photometry', 'mount', 'focuser']);
    // D9: the Statistics card is hidden by default in every mode (I shows it).
    for (const m of MODES) expect(PRESETS[m.id].cards.statistics).toBe('hidden');
    expect(PRESETS.framing.railW).toBe(RAIL.default);
    expect(PRESETS.focus.cards.focuser).toBe('open');
    expect(PRESETS.framing.cards.focuser).toBe('folded');
  });

  it('a fresh preset is unmodified; a fold is reported; the preset itself is never touched', () => {
    const l = clonePreset('focus');
    expect(changedKeys('focus', l)).toEqual([]);
    l.cards.mount = 'hidden';
    l.bandH = 320;
    expect(changedKeys('focus', l)).toEqual(['bandH', 'card.mount']);
    expect(PRESETS.focus.cards.mount).toBe('folded');
  });

  it('sanitize keeps valid fields and drops the rest', () => {
    const l = sanitize('framing', {
      railW: 9999,
      bandH: 310.4,
      drawerTab: 'conditions',
      drawerH: 12,
      cards: { mount: 'hidden', camera: 'sideways', run: 'open' },
    });
    expect(l.railW).toBe(PRESETS.framing.railW);
    expect(l.bandH).toBe(310);
    expect(l.drawerTab).toBe('conditions');
    expect(l.drawerH).toBe(PRESETS.framing.drawerH);
    expect(l.cards.mount).toBe('hidden');
    expect(l.cards.camera).toBe('open');
    expect(sanitize('focus', 'garbage')).toEqual(clonePreset('focus'));
    expect(sanitize('focus', { bandH: null }).bandH).toBeNull();
  });
});

describe('the layout-changed mark (review of wave 3)', () => {
  it('ignores the drawer and the band toggle, counts the arrangement', () => {
    const l = { ...PRESETS.focus, cards: { ...PRESETS.focus.cards }, drawerOpen: !PRESETS.focus.drawerOpen, bandOpen: !PRESETS.focus.bandOpen };
    expect(arrangementChanged('focus', l)).toEqual([]);
    expect(changedKeys('focus', l)).toContain('drawerOpen');
    expect(arrangementChanged('focus', { ...l, railW: PRESETS.focus.railW + 40 })).toEqual(['railW']);
  });
});
