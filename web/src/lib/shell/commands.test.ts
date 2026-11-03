import { describe, expect, it } from 'vitest';
import { layoutGroups, rank, scoreText, type Command } from './commands';

const noop = () => {};
const C = (id: string, title: string, extra: Partial<Command> = {}): Command => ({ id, title, group: 'Actions', run: noop, ...extra });

const INDEX: Command[] = [
  C('park', 'Park the mount', { group: 'Hardware', keywords: 'close arm stop tracking' }),
  C('unpark', 'Unpark the mount', { group: 'Hardware' }),
  C('run', 'Observe', { group: 'Sections', keys: 'F2' }),
  C('site', 'Observer & site › Site latitude', { group: 'Settings' }),
  C('solve', 'Identify field', { keys: 'S', keywords: 'plate solve astap' }),
  C('watch', 'Watch the run from a distance', { keys: 'W' }),
];

describe('palette ranking', () => {
  it('prefers a prefix, then a word start, then a substring', () => {
    expect(scoreText('park', 'Park the mount')!.score).toBeGreaterThan(scoreText('park', 'Unpark the mount')!.score);
    const r = rank('park', INDEX);
    expect(r[0].cmd.id).toBe('park');
    expect(r[1].cmd.id).toBe('unpark');
  });

  it('finds a word start inside a settings path', () => {
    const r = rank('site', INDEX);
    expect(r[0].cmd.id).toBe('site');
    expect(r[0].hits.length).toBe(4);
  });

  it('matches keywords ("astap" finds Identify field) and subsequences ("wtch")', () => {
    expect(rank('astap', INDEX)[0].cmd.id).toBe('solve');
    expect(rank('wtch', INDEX)[0].cmd.id).toBe('watch');
  });

  it('drops scattered subsequences (letters spread over a long title)', () => {
    expect(rank('site', [C('x', 'Plate solving › ASTAP executable')])).toEqual([]);
  });

  it('draws the title hits even when a keyword ranked the command', () => {
    const r = rank('site', [C('s', 'Observer & site › Site name', { keywords: 'site.name' })]);
    expect(r[0].hits.length).toBe(4);
  });

  it('drops what does not match', () => {
    expect(rank('zzz', INDEX)).toEqual([]);
  });

  it('lists recent commands first when the field is empty', () => {
    const r = rank('', INDEX, ['watch', 'site']);
    expect(r.slice(0, 2).map((x) => x.cmd.id)).toEqual(['watch', 'site']);
    expect(r).toHaveLength(INDEX.length);
  });

  it('ranks a disabled command below an enabled one of the same score', () => {
    const idx = [C('a', 'Pause the run', { disabled: 'no run' }), C('b', 'Pause the run and slew')];
    expect(rank('pause', idx)[0].cmd.id).toBe('b');
  });
});

describe('palette layout (the highlighted row is the row Enter runs)', () => {
  // The index lists Hardware before Sections, as buildIndex does; the display is in group order.
  const IDX: Command[] = [
    C('connect', 'Connect all equipment', { group: 'Hardware' }),
    C('park', 'Park the mount', { group: 'Hardware' }),
    C('unpark', 'Unpark the mount', { group: 'Hardware' }),
    C('conn', 'Connection', { group: 'Sections' }),
    C('obs', 'Observe', { group: 'Sections' }),
    C('review', 'Review', { group: 'Sections' }),
    C('help', 'Keyboard shortcuts', { group: 'Help' }),
  ];

  /** What the palette draws at display row `active`, and what Enter runs there. */
  function both(query: string, active: number, recent: string[] = []) {
    const { groups, flat } = layoutGroups(rank(query, IDX, recent), query, recent);
    const drawn = groups.flatMap((g) => g.rows).find((row) => row.pos === active)!;
    return { drawn: drawn.r.cmd.id, runs: flat[active].r.cmd.id, first: flat[0].r.cmd.id };
  }

  it('numbers rows in display order with an empty field', () => {
    for (let a = 0; a < IDX.length; a++) {
      const { drawn, runs } = both('', a);
      expect(runs).toBe(drawn);
    }
    // Opens on the first visual row (a section), never on a hardware row.
    expect(both('', 0).first).toBe('conn');
    // Three ArrowDown from the top: Review is highlighted and Review runs.
    expect(both('', 2)).toMatchObject({ drawn: 'review', runs: 'review' });
  });

  it('keeps the two in step with a query and with recent commands', () => {
    for (let a = 0; a < 2; a++) expect(both('park', a).runs).toBe(both('park', a).drawn);
    const recent = ['unpark', 'help'];
    for (let a = 0; a < IDX.length; a++) expect(both('', a, recent).runs).toBe(both('', a, recent).drawn);
    expect(both('', 0, recent).first).toBe('unpark');
  });

  it('gives each row a unique position covering 0..n-1', () => {
    const { flat } = layoutGroups(rank('', IDX), '');
    expect(flat.map((r) => r.pos)).toEqual(IDX.map((_, i) => i));
  });
});
