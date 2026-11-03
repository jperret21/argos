/**
 * Reduced motion, for the motion JavaScript decides (a time ring stepped in
 * quarters, a still spinner). CSS durations already follow the tokens
 * (tokens.css zeroes them under prefers-reduced-motion).
 */

import { MediaQuery } from 'svelte/reactivity';

const query = new MediaQuery('(prefers-reduced-motion: reduce)', false);

/** True when motion must be replaced by an instant state swap. */
export function reducedMotion(): boolean {
  return query.current;
}
