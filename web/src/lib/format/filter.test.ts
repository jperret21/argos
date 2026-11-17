import { describe, expect, it } from 'vitest';
import { filterLabel, filterToken } from './filter';

describe('filter names (S49 in the UI)', () => {
  it('spells the token as the core does', () => {
    expect(filterToken('IR')).toBe('ir');
    expect(filterToken('LP')).toBe('lp');
    expect(filterToken('IR-cut')).toBe('irc');
    expect(filterToken('')).toBe('clear');
    expect(filterToken(null)).toBe('clear');
  });
  it('shows the filter by its name, never the lowercase token', () => {
    expect(filterLabel('ir')).toBe('IR');
    expect(filterLabel('lp')).toBe('LP');
    expect(filterLabel('v')).toBe('V');
    expect(filterLabel('ha')).toBe('Ha');
    expect(filterLabel('irc')).toBe('IR-cut');
    expect(filterLabel('clear')).toBe('no filter');
    expect(filterLabel('lp', ['IR', 'LP', 'Dark'])).toBe('LP');
    expect(filterLabel(null)).toBe('');
  });
});
