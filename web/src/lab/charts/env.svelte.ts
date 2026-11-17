/**
 * Lab environment: theme, motion preference and the engine running the page.
 * Theme comes from ?theme= (applied before paint by lab/charts.html) and is
 * kept in the URL, never in the app's `argos.theme` key. Motion "system"
 * follows prefers-reduced-motion; "reduced" / "full" override it
 * (html[data-motion], lab.css zeroes the duration tokens like tokens.css).
 */

import { MediaQuery } from 'svelte/reactivity';

export type LabTheme = 'observatory' | 'charcoal' | 'night-red';
export type MotionPref = 'system' | 'reduced' | 'full';

export const LAB_THEMES: readonly LabTheme[] = ['observatory', 'charcoal', 'night-red'];
export const THEME_LABEL: Record<LabTheme, string> = { observatory: 'Observatory', charcoal: 'Charcoal', 'night-red': 'Night Red' };

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
    /* the URL is a convenience only */
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

export function engineName(ua = navigator.userAgent): string {
  const chrome = /Chrom(?:e|ium)\/([\d.]+)/.exec(ua);
  if (chrome) return `Chromium ${chrome[1].split('.')[0]}`;
  const webkit = /AppleWebKit\/([\d.]+)/.exec(ua);
  if (webkit) {
    const safari = /Version\/([\d.]+)/.exec(ua);
    return safari ? `Safari ${safari[1]}` : `WebKit ${webkit[1]} (embedded)`;
  }
  return 'unknown engine';
}

/** Lab toasts (export results, hints). */
export const toasts = $state<{ id: number; text: string }[]>([]);
let toastId = 0;
export function toast(text: string, ms = 3200): void {
  const id = ++toastId;
  toasts.push({ id, text });
  setTimeout(() => {
    const i = toasts.findIndex((t) => t.id === id);
    if (i >= 0) toasts.splice(i, 1);
  }, ms);
}
