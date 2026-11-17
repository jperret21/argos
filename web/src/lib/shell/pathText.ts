/**
 * A path's display pieces (PathText.svelte): the home folder as '~', then one piece per
 * folder with its trailing '/', so a line breaks only after a slash. Pure; tested in
 * pathText.test.ts.
 */

/** "/Users/o/Library/Logs/Argos" with home "/Users/o" -> "~/Library/Logs/Argos". */
export function tildePath(path: string, home: string | null = null): string {
  const h = home?.replace(/\/+$/, '');
  if (!h || h === '' || !path.startsWith(h)) return path;
  const rest = path.slice(h.length);
  if (rest === '') return '~';
  return rest.startsWith('/') ? `~${rest}` : path;
}

/** ["~/", "Library/", "Logs/", "Argos"]: each piece ends with its slash. */
export function pathSegments(path: string, home: string | null = null): string[] {
  const shown = tildePath(path, home);
  const out: string[] = [];
  let piece = '';
  for (const ch of shown) {
    piece += ch;
    if (ch === '/') {
      out.push(piece);
      piece = '';
    }
  }
  if (piece) out.push(piece);
  return out;
}
