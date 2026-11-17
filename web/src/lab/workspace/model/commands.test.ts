import { describe, expect, it } from 'vitest';
import { rank, scoreText, type Command } from './commands';

const noop = () => {};
const C = (id: string, title: string, extra: Partial<Command> = {}): Command => ({ id, title, group: 'Actions', run: noop, ...extra });

const INDEX: Command[] = [
  C('park', 'Park the mount', { group: 'Hardware', keywords: 'close arm stop tracking' }),
  C('unpark', 'Unpark the mount', { group: 'Hardware' }),
  C('run', 'Observe · Run', { group: 'Modes and views', keys: 'Alt+4' }),
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
