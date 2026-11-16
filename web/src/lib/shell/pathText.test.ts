import { describe, expect, it } from 'vitest';
import { pathSegments, tildePath } from './pathText';

describe('path display (start-up failure, crash notice)', () => {
  it('shows the home folder as ~', () => {
    expect(tildePath('/Users/o/Library/Logs/Argos', '/Users/o')).toBe('~/Library/Logs/Argos');
    expect(tildePath('/Users/o', '/Users/o/')).toBe('~');
    expect(tildePath('/Users/ob/x', '/Users/o')).toBe('/Users/ob/x');
    expect(tildePath('~/Library/Logs/Argos')).toBe('~/Library/Logs/Argos');
  });

  it('breaks only after a slash: a hyphenated folder stays whole', () => {
    expect(pathSegments('/private/tmp/perso-dev-argos/log')).toEqual(['/', 'private/', 'tmp/', 'perso-dev-argos/', 'log']);
    expect(pathSegments('/Users/o/Library/Logs/Argos', '/Users/o')).toEqual(['~/', 'Library/', 'Logs/', 'Argos']);
    expect(pathSegments('')).toEqual([]);
  });
});
