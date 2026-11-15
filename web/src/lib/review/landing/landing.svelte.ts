/**
 * R0 state: the session list (A67, `GET /api/sessions`), its loading and error, and the
 * recent items (per viewer). The integrator holds one per app:
 *
 *   const landing = new LandingStore((q, o) => app.client.sessions(q, o));
 *   landing.load();                       // on entering R0, and on Refresh
 *   landing.opened({ kind: 'import', path }) // after a source opened: it joins the recent items
 */

import type { SessionPage } from '../../api/types';
import type { RequestOptions } from '../../api/client';
import { loadPref, savePref } from '../../app/prefs';
import { forget, isRecentList, isScope, pathRecent, PREF_RECENT, PREF_SCOPE, remember, sessionRecent, type RecentItem, type ReviewSource, type Scope } from './landing';

export type SessionsFetch = (query: { offset?: number; limit?: number }, options?: RequestOptions) => Promise<SessionPage>;

/** The newest sessions the list holds (A67 caps `limit` at 500). */
export const PAGE_LIMIT = 500;

export class LandingStore {
  page: SessionPage | null = $state.raw(null);
  loading = $state(false);
  error: string | null = $state(null);
  query = $state('');
  scope: Scope = $state('all');
  recent: RecentItem[] = $state.raw([]);
  private controller: AbortController | null = null;

  constructor(
    private readonly fetchSessions: SessionsFetch,
    load = true,
  ) {
    if (!load) return;
    this.recent = loadPref(PREF_RECENT, isRecentList, []);
    this.scope = loadPref(PREF_SCOPE, isScope, 'all');
  }

  /** (Re)read the list; a newer call supersedes an older one. Keeps the last list on error. */
  async load(): Promise<void> {
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    this.loading = true;
    this.error = null;
    try {
      const page = await this.fetchSessions({ offset: 0, limit: PAGE_LIMIT }, { signal: controller.signal });
      if (this.controller !== controller) return;
      this.page = page;
    } catch (err) {
      if (this.controller !== controller) return;
      this.error = err instanceof Error ? err.message : String(err);
    } finally {
      if (this.controller === controller) {
        this.loading = false;
        this.controller = null;
      }
    }
  }

  setScope(scope: Scope): void {
    this.scope = scope;
    savePref(PREF_SCOPE, scope);
  }

  /** A source opened: it goes to the top of the recent items (the live run is not kept). */
  opened(source: ReviewSource, now: number = Date.now()): void {
    if (source.kind === 'live') return;
    const known = source.kind === 'session' ? this.page?.sessions.find((s) => s.path === source.path) : undefined;
    const item = known ? sessionRecent(known, now) : pathRecent(source.kind, source.path, now);
    this.recent = remember(this.recent, item);
    savePref(PREF_RECENT, this.recent);
  }

  forget(item: Pick<RecentItem, 'kind' | 'path'>): void {
    this.recent = forget(this.recent, item);
    savePref(PREF_RECENT, this.recent);
  }

  dispose(): void {
    this.controller?.abort();
    this.controller = null;
  }
}
