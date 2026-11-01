import { describe, expect, it, vi } from 'vitest';
import { FocusReturn, handleTrapKey, trapStep } from './focus';
import { layersToClose, topModalIndex } from './layers';
import { edgeIndex, isTypeaheadKey, moveIndex, navTarget, Typeahead } from './listnav';
import { entryLabel, isChoice, type MenuEntry } from './menu';
import { placeFloating } from './position';
import { applySort, ariaSort, type Column, nextSort, sortRows, toTsv } from './table';

// -- Focus trap and restore ------------------------------------------------------

class FakeEl {
  isConnected = true;
  focused = 0;
  constructor(readonly name: string) {}
  focus(): void {
    this.focused++;
    doc.activeElement = this;
  }
}
const doc: { activeElement: unknown } = { activeElement: null };

const tab = (shiftKey = false) => ({ key: 'Tab', shiftKey, preventDefault: vi.fn() });

describe('focus trap', () => {
  it('wraps Tab and Shift+Tab at both ends', () => {
    expect(trapStep(3, 0, false)).toBe(1);
    expect(trapStep(3, 2, false)).toBe(0);
    expect(trapStep(3, 0, true)).toBe(2);
    expect(trapStep(3, 1, true)).toBe(0);
    expect(trapStep(3, -1, false)).toBe(0); // focus outside: back to the first
    expect(trapStep(3, -1, true)).toBe(2);
    expect(trapStep(0, -1, false)).toBe(-1);
  });

  it('keeps focus inside the dialog over a full cycle', () => {
    const items = [new FakeEl('cancel'), new FakeEl('field'), new FakeEl('confirm')];
    const dialog = new FakeEl('dialog');
    items[2].focus();
    const e = tab();
    expect(handleTrapKey(e, items, doc.activeElement, dialog)).toBe(true);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(doc.activeElement).toBe(items[0]);
    handleTrapKey(tab(true), items, doc.activeElement, dialog);
    expect(doc.activeElement).toBe(items[2]);
    for (let i = 0; i < 6; i++) handleTrapKey(tab(), items, doc.activeElement, dialog);
    expect(items).toContain(doc.activeElement);
  });

  it('keeps focus on the dialog itself when it holds no control', () => {
    const dialog = new FakeEl('dialog');
    handleTrapKey(tab(), [], null, dialog);
    expect(doc.activeElement).toBe(dialog);
  });

  it('ignores other keys', () => {
    const e = { key: 'a', shiftKey: false, preventDefault: vi.fn() };
    expect(handleTrapKey(e, [new FakeEl('x')], null, new FakeEl('d'))).toBe(false);
    expect(e.preventDefault).not.toHaveBeenCalled();
  });
});

describe('focus return', () => {
  it('gives focus back to the control that opened the layer', () => {
    const trigger = new FakeEl('trigger');
    trigger.focus();
    const back = new FocusReturn(doc);
    new FakeEl('first field').focus();
    expect(back.restore()).toBe(trigger);
    expect(doc.activeElement).toBe(trigger);
  });

  it('uses the explicit target, and falls back when the opener is gone', () => {
    const menuItem = new FakeEl('menu item');
    menuItem.focus();
    const back = new FocusReturn(doc);
    menuItem.isConnected = false; // the menu closed and took its item with it
    const helpButton = new FakeEl('help');
    expect(back.restore(helpButton)).toBe(helpButton);
    const explicit = new FakeEl('anchor');
    expect(new FocusReturn(doc, explicit).restore()).toBe(explicit);
    expect(new FocusReturn(null).restore()).toBeNull();
  });
});

describe('layer stack', () => {
  const stack = [
    { id: 'dialog', modal: true },
    { id: 'select', modal: false },
    { id: 'menu', modal: false },
  ];

  it('a press outside closes the non-modal layers above the one hit, not the modal', () => {
    expect(layersToClose(stack, -1).map((l) => l.id)).toEqual(['menu', 'select']);
    expect(layersToClose(stack, 1).map((l) => l.id)).toEqual(['menu']);
    expect(layersToClose(stack, 2)).toEqual([]);
    expect(topModalIndex(stack)).toBe(0);
    expect(topModalIndex([{ modal: false }])).toBe(-1);
  });
});

// -- Menu keyboard navigation ------------------------------------------------------

const items: MenuEntry[] = [
  { kind: 'header', label: 'Image' },
  { id: 'fit', label: 'Fit' },
  { id: 'fill', label: 'Fill' },
  { kind: 'separator' },
  { id: 'save', label: 'Save view as PNG', disabledReason: 'no frame yet' },
  { id: 'stats', label: 'Statistics', kind: 'checkbox', checked: true },
  { id: 'sat', label: 'Saturation', kind: 'checkbox', checked: false },
];
const skip = (i: number) => !isChoice(items[i]);
const labels = items.map(entryLabel);

describe('menu navigation', () => {
  it('skips headers and separators, wraps at both ends', () => {
    expect(edgeIndex(items.length, 'first', skip)).toBe(1);
    expect(edgeIndex(items.length, 'last', skip)).toBe(6);
    expect(moveIndex(items.length, 2, 1, true, skip)).toBe(4); // over the separator
    expect(moveIndex(items.length, 6, 1, true, skip)).toBe(1); // wraps past the header
    expect(moveIndex(items.length, 1, -1, true, skip)).toBe(6);
    expect(moveIndex(items.length, 1, -1, false, skip)).toBe(1); // no wrap: stays
    expect(moveIndex(items.length, -1, 1, true, skip)).toBe(1);
    expect(moveIndex(items.length, -1, -1, true, skip)).toBe(6);
  });

  it('keeps disabled items reachable (they say why), but not dividers', () => {
    expect(navTarget('ArrowDown', items.length, 2, skip)).toBe(4);
    expect(navTarget('Home', items.length, 5, skip)).toBe(1);
    expect(navTarget('End', items.length, 1, skip)).toBe(6);
    expect(navTarget('PageDown', items.length, 1, skip, { page: 10 })).toBe(6);
    expect(navTarget('x', items.length, 1, skip)).toBeNull();
  });

  it('jumps by type-ahead, cycling on a repeated letter', () => {
    let t = 0;
    const ta = new Typeahead(500, () => t);
    expect(ta.push('s', labels, 1, skip)).toBe(4); // "Save view as PNG"
    t += 100;
    expect(ta.push('s', labels, 4, skip)).toBe(5); // "ss": next item starting with S
    t += 100;
    expect(ta.push('s', labels, 5, skip)).toBe(6);
    t += 100;
    expect(ta.push('s', labels, 6, skip)).toBe(4); // cycles back
    t += 1000; // pause: a new search
    expect(ta.push('f', labels, 4, skip)).toBe(1);
    t += 100;
    expect(ta.push('i', labels, 1, skip)).toBe(1); // "fi": Fit still matches
    t += 100;
    expect(ta.push('l', labels, 1, skip)).toBe(2); // "fil": Fill
  });

  it('matches a longer prefix from the current item first', () => {
    let t = 0;
    const ta = new Typeahead(500, () => t);
    expect(ta.push('s', labels, -1, skip)).toBe(4);
    t += 50;
    expect(ta.push('t', labels, 4, skip)).toBe(5); // "st" -> Statistics
    expect(new Typeahead(500, () => 0).push('z', labels, 1, skip)).toBe(-1);
  });

  it('only printable keys without modifiers start a type-ahead', () => {
    const k = (key: string, extra = {}) => ({ key, ctrlKey: false, metaKey: false, altKey: false, ...extra });
    expect(isTypeaheadKey(k('s'))).toBe(true);
    expect(isTypeaheadKey(k(' '))).toBe(false);
    expect(isTypeaheadKey(k('ArrowDown'))).toBe(false);
    expect(isTypeaheadKey(k('s', { metaKey: true }))).toBe(false);
  });
});

// -- Table sorting ---------------------------------------------------------------------

interface Star {
  name: string;
  mag: number | null;
  sep: number;
}
const stars: Star[] = [
  { name: 'Comp 10', mag: 11.2, sep: 3.1 },
  { name: 'comp 2', mag: null, sep: 1.0 },
  { name: 'Comp 1', mag: 9.87, sep: 7.5 },
  { name: 'Check', mag: 11.2, sep: 2.2 },
  { name: 'Target', mag: Number.NaN, sep: 0 },
];
const columns: Column<Star>[] = [
  { id: 'name', label: 'Name', value: (s) => s.name },
  { id: 'mag', label: 'V mag', numeric: true, value: (s) => s.mag, format: (s) => (s.mag === null ? '—' : s.mag.toFixed(3)) },
  { id: 'sep', label: 'Sep.', numeric: true, value: (s) => s.sep, sortable: false },
];

describe('table sorting', () => {
  it('sorts numbers numerically and keeps missing values last in both directions', () => {
    const asc = sortRows(stars, (s) => s.mag, 'asc').map((s) => s.name);
    expect(asc).toEqual(['Comp 1', 'Comp 10', 'Check', 'comp 2', 'Target']);
    const desc = sortRows(stars, (s) => s.mag, 'desc').map((s) => s.name);
    expect(desc).toEqual(['Comp 10', 'Check', 'Comp 1', 'comp 2', 'Target']);
  });

  it('is stable for equal values (Comp 10 and Check stay in table order)', () => {
    expect(sortRows(stars, (s) => s.mag, 'asc').slice(1, 3).map((s) => s.name)).toEqual(['Comp 10', 'Check']);
  });

  it('sorts text naturally and case-insensitively', () => {
    expect(sortRows(stars, (s) => s.name, 'asc').map((s) => s.name)).toEqual([
      'Check',
      'Comp 1',
      'comp 2',
      'Comp 10',
      'Target',
    ]);
  });

  it('cycles ascending, descending, then the table order, with aria-sort', () => {
    let s = nextSort(null, 'mag');
    expect(s).toEqual({ column: 'mag', dir: 'asc' });
    expect(ariaSort(s, 'mag')).toBe('ascending');
    expect(ariaSort(s, 'name')).toBe('none');
    s = nextSort(s, 'mag');
    expect(ariaSort(s, 'mag')).toBe('descending');
    s = nextSort(s, 'mag');
    expect(s).toBeNull();
    expect(nextSort({ column: 'mag', dir: 'desc' }, 'name')).toEqual({ column: 'name', dir: 'asc' });
  });

  it('leaves the order alone for an unsortable or unknown column', () => {
    expect(applySort(stars, columns, { column: 'sep', dir: 'asc' })).toEqual(stars);
    expect(applySort(stars, columns, { column: 'nope', dir: 'asc' })).toEqual(stars);
    expect(applySort(stars, columns, null)).not.toBe(stars);
  });

  it('copies the shown text as TSV with a header', () => {
    expect(toTsv(columns, stars.slice(0, 2))).toBe('Name\tV mag\tSep.\nComp 10\t11.200\t3.1\ncomp 2\t—\t1\n');
  });
});

// -- Placement ----------------------------------------------------------------------------

describe('floating placement', () => {
  const viewport = { width: 1440, height: 900 };
  it('opens below the anchor, aligned to its start', () => {
    const p = placeFloating({
      anchor: { left: 100, top: 40, width: 30, height: 30 },
      floating: { width: 260, height: 200 },
      viewport,
      placement: 'bottom-start',
    });
    expect(p).toEqual({ x: 100, y: 74, side: 'bottom' });
  });

  it('flips above when there is no room below, and stays on screen', () => {
    const p = placeFloating({
      anchor: { left: 1400, top: 820, width: 30, height: 30 },
      floating: { width: 260, height: 200 },
      viewport,
      placement: 'bottom-start',
    });
    expect(p.side).toBe('top');
    expect(p.y).toBe(820 - 4 - 200);
    expect(p.x).toBe(1440 - 8 - 260);
  });

  it('opens to the right of the rail and clamps to the bottom edge', () => {
    const p = placeFloating({
      anchor: { left: 30, top: 800, width: 32, height: 32 },
      floating: { width: 280, height: 220 },
      viewport,
      placement: 'right-end',
    });
    expect(p).toEqual({ x: 66, y: 612, side: 'right' });
  });
});
