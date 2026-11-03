import { describe, expect, it } from 'vitest';
import {
  baseName,
  breadcrumbs,
  FITS_FILTER,
  folderDetail,
  formatMtime,
  formatSize,
  type FsListing,
  isAbsolute,
  joinPath,
  mtimeMs,
  nameProblem,
  normalizePlaces,
  parentOf,
  pickerChoice,
  sortEntries,
  visibleEntries,
  withSuffix,
  ZIP_FILTER,
} from './filepicker';

const N = '\u202f'; // U+202F NARROW NO-BREAK SPACE

describe('paths', () => {
  it('joins, splits and climbs POSIX and Windows paths', () => {
    expect(joinPath('/Users/me', 'Argos')).toBe('/Users/me/Argos');
    expect(joinPath('/', 'tmp')).toBe('/tmp');
    expect(joinPath('C:\\Users\\me', 'Argos')).toBe('C:\\Users\\me\\Argos');
    expect(baseName('/Users/me/Argos/')).toBe('Argos');
    expect(parentOf('/Users/me/Argos')).toBe('/Users/me');
    expect(parentOf('/Users')).toBe('/');
    expect(parentOf('/')).toBeNull();
    expect(parentOf('C:\\Users')).toBe('C:\\');
    expect(isAbsolute('~/Argos')).toBe(true);
    expect(isAbsolute('Argos')).toBe(false);
  });

  it('reads home as ~ in the breadcrumb', () => {
    expect(breadcrumbs('/Users/me/Argos/sessions', '/Users/me')).toEqual([
      { label: '~', path: '/Users/me' },
      { label: 'Argos', path: '/Users/me/Argos' },
      { label: 'sessions', path: '/Users/me/Argos/sessions' },
    ]);
    expect(breadcrumbs('/Volumes/data', '/Users/me').map((c) => c.label)).toEqual(['/', 'Volumes', 'data']);
  });

  it('accepts places as paths or records', () => {
    expect(
      normalizePlaces([
        '/Users/me',
        { id: 'sessions', label: 'Sessions', path: '/Users/me/Argos/sessions', exists: false },
        '',
        null as never,
      ]),
    ).toEqual([
      { label: 'me', path: '/Users/me', exists: true },
      { id: 'sessions', label: 'Sessions', path: '/Users/me/Argos/sessions', exists: false },
    ]);
  });

  it('lists a folder once when two places name it (presets folder set to the Desktop)', () => {
    const places = normalizePlaces([
      { id: 'home', label: 'Home', path: '/Users/me' },
      { id: 'desktop', label: 'Desktop', path: '/Users/me/Desktop' },
      { id: 'presets', label: 'Sequence presets', path: '/Users/me/Desktop' },
    ]);
    expect(places.map((p) => p.id)).toEqual(['home', 'desktop']);
  });
});

describe('entries', () => {
  const entries = [
    { name: 'frame_10.fits', kind: 'file' as const, size: 4_000_000 },
    { name: 'frame_2.fits', kind: 'file' as const, size: 4_000_000 },
    { name: 'notes.txt', kind: 'file' as const, size: 12 },
    { name: 'lights', kind: 'dir' as const, fits_count: 412 },
    { name: '.cache', kind: 'dir' as const },
  ];

  it('lists folders first, in natural order', () => {
    expect(sortEntries(entries).map((e) => e.name)).toEqual(['.cache', 'lights', 'frame_2.fits', 'frame_10.fits', 'notes.txt']);
  });

  it('shows what the mode can choose, hides dot files unless asked', () => {
    expect(visibleEntries(entries, 'open-file', FITS_FILTER, false).map((e) => e.name)).toEqual([
      'lights',
      'frame_2.fits',
      'frame_10.fits',
    ]);
    expect(visibleEntries(entries, 'open-folder', FITS_FILTER, true).map((e) => e.name)).toEqual(['.cache', 'lights']);
  });

  it('formats sizes, FITS counts and UTC times', () => {
    expect(formatSize(4_000_000)).toBe('4.0 MB');
    expect(formatSize(812_000)).toBe('812 kB');
    expect(formatSize(12)).toBe('12 B');
    expect(formatSize(null)).toBe('');
    expect(folderDetail(entries[3])).toBe('412 FITS');
    expect(folderDetail({ name: 'x', kind: 'dir', fits_count: 1204 })).toBe(`1${N}204 FITS`);
    expect(formatMtime(1793620800)).toBe('2026-11-02 12:00');
    expect(mtimeMs('2026-11-02T12:00:00Z')).toBe(1793620800000);
    expect(mtimeMs(1793620800000)).toBe(1793620800000);
  });
});

describe('the primary button', () => {
  const listing: FsListing = {
    path: '/Users/me/Desktop',
    parent: '/Users/me',
    places: [],
    entries: [
      { name: 'argos-support.zip', kind: 'file' },
      { name: 'old', kind: 'dir' },
    ],
  };

  it('chooses the current folder or the selected one', () => {
    expect(pickerChoice('open-folder', listing, null, '', ZIP_FILTER).path).toBe('/Users/me/Desktop');
    expect(pickerChoice('open-folder', listing, listing.entries[1], '', ZIP_FILTER).path).toBe('/Users/me/Desktop/old');
  });

  it('needs a file to open, says why otherwise', () => {
    expect(pickerChoice('open-file', listing, null, '', ZIP_FILTER)).toMatchObject({ path: null, reason: 'choose a file' });
    expect(pickerChoice('open-file', null, null, '', ZIP_FILTER).reason).toMatch(/loading/);
  });

  it('save: adds the suffix, detects a file to replace, refuses bad names', () => {
    expect(withSuffix('bundle', ZIP_FILTER)).toBe('bundle.zip');
    expect(pickerChoice('save-file', listing, null, 'argos-support', ZIP_FILTER)).toMatchObject({
      path: '/Users/me/Desktop/argos-support.zip',
      exists: true,
    });
    expect(pickerChoice('save-file', listing, null, 'new', ZIP_FILTER).exists).toBe(false);
    expect(nameProblem('a/b')).toMatch(/cannot contain/);
    expect(pickerChoice('save-file', listing, null, '  ', ZIP_FILTER).reason).toBe('enter a file name');
  });
});
