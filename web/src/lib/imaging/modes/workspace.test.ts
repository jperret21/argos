import { describe, expect, it } from 'vitest';
import { MODE_KEY, modeLayoutKey, PRESETS } from './layout';
import { ObserveWorkspace } from './workspace.svelte';

function memory(init: Record<string, string> = {}) {
  const m = new Map(Object.entries(init));
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    map: m,
  };
}

describe('Observe workspace (D1)', () => {
  it('starts in Framing and remembers each mode with its own layout', () => {
    const store = memory();
    const ws = new ObserveWorkspace({ store });
    expect(ws.mode).toBe('framing');
    ws.edit((l) => (l.bandH = 320));
    expect(ws.modified).toBe(true);
    expect(ws.setMode('focus')).toBeNull();
    expect(ws.mode).toBe('focus');
    expect(ws.layout.bandH).toBeNull(); // Focus keeps its own band
    expect(ws.modified).toBe(false);
    expect(ws.modifiedMode('framing')).toBe(true);
    expect(store.map.get(MODE_KEY)).toBe('"focus"');
    // A new page reads both back.
    const again = new ObserveWorkspace({ store });
    expect(again.mode).toBe('focus');
    expect(again.layouts.framing.bandH).toBe(320);
  });

  it('refuses the modes this version does not have, with the reason', () => {
    const ws = new ObserveWorkspace({ store: memory() });
    expect(ws.setMode('run')).toMatch(/waves 5 and 6/);
    expect(ws.mode).toBe('framing');
    // Field arrived with wave 4.
    expect(ws.setMode('field')).toBeNull();
    expect(ws.mode).toBe('field');
    // A stored unavailable mode is not restored.
    expect(new ObserveWorkspace({ store: memory({ [MODE_KEY]: '"run"' }) }).mode).toBe('framing');
  });

  it('folds cards, toggles the band, rail and drawer, and keeps the rail in its D8 range', () => {
    const ws = new ObserveWorkspace({ store: memory() });
    ws.setCardOpen('camera', false);
    expect(ws.layout.cards.camera).toBe('folded');
    ws.setCard('mount', 'hidden');
    ws.setCardOpen('mount', true); // a hidden card has no header to fold
    expect(ws.layout.cards.mount).toBe('hidden');
    ws.toggleBand();
    expect(ws.layout.bandOpen).toBe(false);
    ws.toggleDrawer('log');
    expect(ws.layout).toMatchObject({ drawerOpen: true, drawerTab: 'log' });
    ws.toggleDrawer('conditions');
    expect(ws.layout).toMatchObject({ drawerOpen: true, drawerTab: 'conditions' });
    ws.toggleDrawer('conditions');
    expect(ws.layout.drawerOpen).toBe(false);
    ws.setRailWidth(900);
    expect(ws.layout.railW).toBe(580);
    ws.setRailWidth(10);
    expect(ws.layout.railW).toBe(360);
  });

  it('resets one mode or all, forgets the keys, and offers Undo', () => {
    const store = memory();
    const undos: [string, () => void][] = [];
    const ws = new ObserveWorkspace({ store, onreset: (what, undo) => undos.push([what, undo]) });
    ws.setCard('camera', 'hidden');
    expect(store.map.has(modeLayoutKey('framing'))).toBe(true);
    ws.resetMode();
    expect(ws.layout.cards.camera).toBe(PRESETS.framing.cards.camera);
    expect(store.map.has(modeLayoutKey('framing'))).toBe(false);
    expect(undos[0][0]).toBe('Framing layout reset');
    undos[0][1]();
    expect(ws.layout.cards.camera).toBe('hidden');
    ws.setMode('focus');
    ws.edit((l) => (l.railOpen = false));
    ws.resetAll();
    expect(ws.layouts.framing.cards.camera).toBe('open');
    expect(ws.layouts.focus.railOpen).toBe(true);
    undos[1][1]();
    expect(ws.layouts.framing.cards.camera).toBe('hidden');
    expect(ws.layouts.focus.railOpen).toBe(false);
  });

  it('reload() follows a "Reset all layouts" made elsewhere, and works without storage', () => {
    const store = memory();
    const ws = new ObserveWorkspace({ store });
    ws.toggleBand();
    store.map.delete(modeLayoutKey('framing'));
    ws.reload();
    expect(ws.layout.bandOpen).toBe(true);
    const none = new ObserveWorkspace({ store: null });
    none.toggleBand();
    expect(none.layout.bandOpen).toBe(false);
  });
});
