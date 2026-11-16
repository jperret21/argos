import { describe, expect, it } from 'vitest';
import { nativeMenuGuard, suppressNativeMenu, type Theme } from './theme';

describe('M20: the native context menu in Night Red', () => {
  it('is suppressed in Night Red only', () => {
    expect(suppressNativeMenu('night-red')).toBe(true);
    expect(suppressNativeMenu('observatory')).toBe(false);
    expect(suppressNativeMenu('charcoal')).toBe(false);
  });

  it('follows the theme of the moment, until the guard is removed', () => {
    const target = new EventTarget();
    let theme: Theme = 'observatory';
    const stop = nativeMenuGuard(target, () => theme);
    const menu = () => {
      const e = new Event('contextmenu', { cancelable: true });
      target.dispatchEvent(e);
      return e.defaultPrevented;
    };
    expect(menu()).toBe(false);
    theme = 'night-red';
    expect(menu()).toBe(true);
    stop();
    expect(menu()).toBe(false);
  });
});
