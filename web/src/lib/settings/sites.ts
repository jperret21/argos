/**
 * Observer & site helpers (02 1.7 #7-#15; Qt configuration_page.py:883-990):
 * the default site's four keys, a place found by the search (A82), and the
 * saved sites (`site.favorites`). Pure; unit-tested in sites.test.ts.
 */

import type { ConfigValue, PlaceResult } from '../api/types';
import { fixed, int, signed } from '../format/number';

export interface SiteValues {
  name: string;
  latitude: number;
  longitude: number;
  elevation: number;
}

export interface Favorite {
  name: string;
  latitude: number;
  longitude: number;
  elevation: number;
}

const round = (v: number, digits: number) => Math.round(v * 10 ** digits) / 10 ** digits;

/** The default site held by the configuration. */
export function currentSite(values: Record<string, ConfigValue> | null | undefined): SiteValues {
  const num = (k: string) => (typeof values?.[k] === 'number' ? (values[k] as number) : 0);
  const name = typeof values?.['site.name'] === 'string' ? (values['site.name'] as string) : '';
  return { name, latitude: num('site.latitude'), longitude: num('site.longitude'), elevation: num('site.elevation') };
}

/** The PATCH that makes a site the default (one commit for its four keys). */
export function siteChanges(site: SiteValues): Record<string, ConfigValue> {
  return {
    'site.name': site.name.slice(0, 80),
    'site.latitude': round(site.latitude, 5),
    'site.longitude': round(site.longitude, 5),
    'site.elevation': round(site.elevation, 1),
  };
}

/** A search result as the default site: its first label part is the name (Qt :915). */
export function siteFromPlace(place: PlaceResult, current: SiteValues): SiteValues {
  return {
    name: place.label.split(',', 1)[0].trim().slice(0, 80) || 'Found place',
    latitude: round(place.latitude, 5),
    longitude: round(place.longitude, 5),
    // A failed elevation lookup keeps the elevation already set (Qt :918-919).
    elevation: place.elevation_m === null ? current.elevation : round(place.elevation_m, 1),
  };
}

export function coordsText(lat: number, lon: number): string {
  return `${signed(lat, 5)}° ${signed(lon, 5)}°`;
}

export function elevationText(m: number | null): string {
  return m === null ? 'no elevation' : `${int(Math.round(m))} m`;
}

export function siteText(site: SiteValues): string {
  return `${site.name || 'Unnamed site'} · ${coordsText(site.latitude, site.longitude)} · ${fixed(site.elevation, 0)} m`;
}

/** Valid saved sites (Qt :931-933: items without a name are skipped). */
export function favoritesOf(value: ConfigValue | undefined): Favorite[] {
  if (!Array.isArray(value)) return [];
  const out: Favorite[] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') continue;
    const o = item as Record<string, unknown>;
    if (typeof o.name !== 'string' || !o.name.trim()) continue;
    const n = (k: string) => (typeof o[k] === 'number' ? (o[k] as number) : 0);
    out.push({ name: o.name, latitude: n('latitude'), longitude: n('longitude'), elevation: n('elevation') });
  }
  return out;
}

const same = (a: string, b: string) => a.trim().toLocaleLowerCase() === b.trim().toLocaleLowerCase();

/** Save the current site under `name`: a saved site of that name (any case) is replaced (Qt :954-972). */
export function upsertFavorite(list: readonly Favorite[], fav: Favorite): { list: Favorite[]; replaced: boolean } {
  const replaced = list.some((f) => same(f.name, fav.name));
  const site = {
    name: fav.name.trim().slice(0, 80),
    latitude: round(fav.latitude, 5),
    longitude: round(fav.longitude, 5),
    elevation: round(fav.elevation, 1),
  };
  return { list: [...list.filter((f) => !same(f.name, fav.name)), site], replaced };
}

export function removeFavorite(list: readonly Favorite[], name: string): Favorite[] {
  return list.filter((f) => !same(f.name, name));
}

/** The saved site that is the current default (same name and coordinates), if any. */
export function isDefaultFavorite(fav: Favorite, site: SiteValues): boolean {
  return (
    same(fav.name, site.name) &&
    Math.abs(fav.latitude - site.latitude) < 5e-6 &&
    Math.abs(fav.longitude - site.longitude) < 5e-6
  );
}
