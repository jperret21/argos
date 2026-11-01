/**
 * The two stores of the prototype, as module singletons (one workspace per
 * page). In the app, `sim` is replaced by the server's status record and
 * events, and `ws` by lib/app state plus prefs.
 */

import { Sim } from './sim.svelte';
import { Workspace } from './workspace.svelte';

export const sim = new Sim();
export const ws = new Workspace();
