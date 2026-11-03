/**
 * Paths shown in a field narrower than they are (02 section 2.2): the middle
 * is cut, never the end, because the last segment is what tells two paths
 * apart (a file name with its UTC time, a cache folder). Pure; tested.
 */

/** U+2026 HORIZONTAL ELLIPSIS. */
export const ELLIPSIS = '…';

/**
 * `path` in at most `max` characters: the head as far as it fits, "…", then
 * the last segment whole ("/Users/…/Desktop/argos-support-0.5.0-20261102T202437Z.zip").
 * When even the last segment does not fit, its start is cut ("…20261102T202437Z.zip").
 */
export function middleEllipsis(path: string, max: number): string {
  if (max <= 0) return '';
  if (path.length <= max) return path;
  if (max <= 1) return ELLIPSIS;
  const sep = path.includes('\\') && !path.includes('/') ? '\\' : '/';
  const cut = path.lastIndexOf(sep, path.length - 2); // a trailing separator stays with its name
  const tail = cut >= 0 ? path.slice(cut) : path; // "/argos-support-….zip"
  const parts = cut >= 0 ? path.slice(0, cut).split(sep) : [];
  // "<left>/…<right><tail>": at least one segment elided; the tail always whole.
  const build = (a: number, b: number) =>
    `${parts.slice(0, a).join(sep)}${sep}${ELLIPSIS}${parts.slice(b).map((p) => sep + p).join('')}${tail}`;
  if (parts.length < 2 || build(1, parts.length).length > max) {
    return ELLIPSIS + path.slice(path.length - (max - 1));
  }
  let a = 1;
  let b = parts.length;
  // Grow toward the tail first (the folder that holds the file), then from the start.
  for (let grew = true; grew; ) {
    grew = false;
    if (b - 1 > a && build(a, b - 1).length <= max) {
      b--;
      grew = true;
    }
    if (a + 1 < b && build(a + 1, b).length <= max) {
      a++;
      grew = true;
    }
  }
  return build(a, b);
}
