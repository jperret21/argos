/**
 * Lab environment: theme, motion preference and the engine that runs the page.
 *
 * - Theme comes from ?theme= (applied before paint by research.html) and is
 *   kept in the URL, never in the app's `argos.theme` storage key.
 * - Motion: "system" follows prefers-reduced-motion; "reduced" and "full"
 *   override it for the demos (html[data-motion], lab.css zeroes the
 *   duration tokens for "reduced" exactly as tokens.css does for the media
 *   query).
 */

import { MediaQuery } from 'svelte/reactivity';

export type LabTheme = 'observatory' | 'charcoal' | 'night-red';
export type MotionPref = 'system' | 'reduced' | 'full';

export const LAB_THEMES: readonly LabTheme[] = ['observatory', 'charcoal', 'night-red'];

const systemReduced = new MediaQuery('(prefers-reduced-motion: reduce)');

function readTheme(): LabTheme {
  const t = document.documentElement.getAttribute('data-theme');
  return t === 'charcoal' || t === 'night-red' ? t : 'observatory';
}

function readMotion(): MotionPref {
  const m = document.documentElement.getAttribute('data-motion');
  return m === 'reduced' || m === 'full' ? m : 'system';
}

export const env = $state({ theme: readTheme(), motion: readMotion() });

/** True when animations must be replaced by an instant state swap. */
export function reducedMotion(): boolean {
  return env.motion === 'reduced' || (env.motion === 'system' && systemReduced.current);
}

function writeUrl(key: string, value: string | null): void {
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

export interface Engine {
  family: 'Chromium' | 'WebKit' | 'Gecko' | 'unknown';
  version: string;
  /** WKWebView / WebKitGTK embed: WebKit without Safari's Version/ token. */
  embedded: boolean;
}

export function detectEngine(ua = navigator.userAgent): Engine {
  const chrome = /Chrom(?:e|ium)\/([\d.]+)/.exec(ua);
  if (chrome) return { family: 'Chromium', version: chrome[1], embedded: !/Safari\//.test(ua) };
  const gecko = /Firefox\/([\d.]+)/.exec(ua);
  if (gecko) return { family: 'Gecko', version: gecko[1], embedded: false };
  const webkit = /AppleWebKit\/([\d.]+)/.exec(ua);
  if (webkit) {
    const safari = /Version\/([\d.]+)/.exec(ua);
    return { family: 'WebKit', version: safari ? `Safari ${safari[1]}` : webkit[1], embedded: !safari };
  }
  return { family: 'unknown', version: '', embedded: false };
}
