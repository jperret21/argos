import { describe, expect, it } from 'vitest';
import { bandLayout, changedKeys, clonePreset, PRESETS, sanitize } from './layout';

const FRAME = { width: 1920, height: 1080 }; // displayed (portrait frame rotated)

describe('band layout', () => {
  it('takes exactly the band the fitted image leaves at 1440 x 900 (rail 400)', () => {
    // centre: 1440 - 92 rail - 400 right rail - 1 separator; 900 - 44 toolbar - 28 status bar.
    const b = bandLayout({ width: 947, height: 828 }, FRAME, 0, true, null);
    expect(b.compact).toBe(false);
    expect(b.height).toBe(295);
    expect(b.sideBands.x).toBe(0);
    expect(b.sideBands.y).toBeLessThan(1);
  });

  it('falls back to one compact row, as tall as the band, when the drawer eats it', () => {
    const b = bandLayout({ width: 947, height: 828 }, FRAME, 216, true, null);
    expect(b.compact).toBe(true);
    expect(b.height).toBe(79);
    expect(b.sideBands.y).toBeLessThan(1);
  });

  it('a dragged band keeps at least 200 px of viewer', () => {
    const b = bandLayout({ width: 947, height: 828 }, FRAME, 0, true, 790);
    expect(b.viewer).toBe(200);
    expect(b.sideBands.x).toBeGreaterThan(0);
  });

  it('closed band: the whole height goes to the viewer', () => {
    const b = bandLayout({ width: 947, height: 828 }, FRAME, 0, false, null);
    expect(b.height).toBe(0);
    expect(b.viewer).toBe(828);
  });
});

describe('presets', () => {
  it('a fresh preset is unmodified; a fold is reported', () => {
    const l = clonePreset('run');
    expect(changedKeys('run', l)).toEqual([]);
    l.cards.conditions = 'folded';
    expect(changedKeys('run', l)).toEqual(['card.conditions']);
    expect(PRESETS.run.cards.conditions).toBe('open');
  });

  it('sanitize keeps valid fields and drops the rest', () => {
    const l = sanitize('field', { railW: 9999, drawerTab: 'curve', cards: { run: 'open', mount: 'sideways' } });
    expect(l.railW).toBe(PRESETS.field.railW);
    expect(l.drawerTab).toBe('curve');
    expect(l.cards.run).toBe('open');
    expect(l.cards.mount).toBe(PRESETS.field.cards.mount);
  });
});
