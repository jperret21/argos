/**
 * Lab environment: theme, motion preference, engine.
 *
 * - Theme comes from ?theme= (applied before paint by controls.html) and is
 *   kept in the URL only, never in the app's `argos.theme` key.
 * - Motion: "system" follows prefers-reduced-motion; "reduced" forces it
 *   (html[data-motion], controls.css zeroes the duration tokens exactly as
 *   tokens.css does under the media query).
 * - `reduced()` is what every JS motion asks before moving (Tween / Spring
 *   durations, the hold ring's stepped fill).
 */

import { MediaQuery } from 'svelte/reactivity';

export type LabTheme = 'observatory' | 'charcoal' | 'night-red';
export type MotionPref = 'system' | 'reduced';

export const LAB_THEMES: readonly LabTheme[] = ['observatory', 'charcoal', 'night-red'];
export const THEME_LABEL: Record<LabTheme, string> = {
  observatory: 'Observatory',
  charcoal: 'Charcoal',
  'night-red': 'Night Red',
};

const systemReduced = new MediaQuery('(prefers-reduced-motion: reduce)');

function readTheme(): LabTheme {
  const t = document.documentElement.getAttribute('data-theme');
  return t === 'charcoal' || t === 'night-red' ? t : 'observatory';
}

function readMotion(): MotionPref {
  return document.documentElement.getAttribute('data-motion') === 'reduced' ? 'reduced' : 'system';
}

export const env = $state({ theme: readTheme(), motion: readMotion() });

/** True when motion must be replaced by an instant state swap. */
export function reduced(): boolean {
  return env.motion === 'reduced' || systemReduced.current;
}

/** A duration in ms, or 0 under reduced motion. */
export function dur(ms: number): number {
  return reduced() ? 0 : ms;
}

export function writeUrl(key: string, value: string | null): void {
  try {
    const url = new URL(location.href);
    if (value === null) url.searchParams.delete(key);
    else url.searchParams.set(key, value);
    history.replaceState(null, '', url);
  } catch {
    /* sandboxed: the URL is a convenience only */
  }
}

export function setTheme(theme: LabTheme): void {
  env.theme = theme;
  document.documentElement.setAttribute('data-theme', theme);
  writeUrl('theme', theme === 'observatory' ? null : theme);
}

export function setMotion(motion: MotionPref): void {
  env.motion = motion;
  if (motion === 'system') document.documentElement.removeAttribute('data-motion');
  else document.documentElement.setAttribute('data-motion', motion);
  writeUrl('motion', motion === 'system' ? null : motion);
}

export function engineLabel(ua = navigator.userAgent): string {
  const chrome = /Chrom(?:e|ium)\/(\d+)/.exec(ua);
  if (chrome) return `Chromium ${chrome[1]}`;
  const webkit = /AppleWebKit\/([\d.]+)/.exec(ua);
  if (webkit) {
    const safari = /Version\/([\d.]+)/.exec(ua);
    return safari ? `WebKit · Safari ${safari[1]}` : `WebKit ${webkit[1]} · embedded`;
  }
  const gecko = /Firefox\/(\d+)/.exec(ua);
  return gecko ? `Gecko ${gecko[1]}` : 'unknown engine';
}
