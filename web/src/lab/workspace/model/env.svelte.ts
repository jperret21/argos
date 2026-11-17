/**
 * Lab environment: theme, motion and density. Applied on <html> (tokens
 * switch there) and mirrored in the URL (?theme=, ?motion=, ?density=),
 * never in the app's argos.theme key. Canvas code reads `env.theme` to
 * redraw with the new tokens.
 */

import { MediaQuery } from 'svelte/reactivity';
import type { Theme } from '../../../lib/app/theme';

export type Motion = 'system' | 'reduced' | 'full';
export type Density = 'compact' | 'comfortable';

const systemReduced = new MediaQuery('(prefers-reduced-motion: reduce)');
const html = document.documentElement;

function readTheme(): Theme {
  const t = html.getAttribute('data-theme');
  return t === 'charcoal' || t === 'night-red' ? t : 'observatory';
}

export const env = $state({
  theme: readTheme(),
  motion: (html.getAttribute('data-motion') as Motion | null) ?? 'system',
  density: (html.getAttribute('data-density') as Density | null) ?? 'compact',
});

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

export function setTheme(theme: Theme): void {
  env.theme = theme;
  html.setAttribute('data-theme', theme);
  writeUrl('theme', theme === 'observatory' ? null : theme);
}

export function setMotion(motion: Motion): void {
  env.motion = motion;
  if (motion === 'system') html.removeAttribute('data-motion');
  else html.setAttribute('data-motion', motion);
  writeUrl('motion', motion === 'system' ? null : motion);
}

export function setDensity(density: Density): void {
  env.density = density;
  if (density === 'compact') html.removeAttribute('data-density');
  else html.setAttribute('data-density', density);
  writeUrl('density', density === 'compact' ? null : density);
}
