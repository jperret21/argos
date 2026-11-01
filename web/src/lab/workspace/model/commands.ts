/**
 * Command palette index and ranking (functional-spaces.md P9). Pure: the
 * index is data, the ranking a small hand-written scorer (prefix, word
 * start, substring, then subsequence), no dependency.
 *
 * The app's shortcut registry (lib/app/keymap.ts) feeds the index, so every
 * shortcut is searchable by its label and the palette teaches the keys.
 */

export type CommandGroup = 'Modes and views' | 'Actions' | 'Hardware' | 'Panels' | 'Stars' | 'Settings' | 'Sections' | 'Help';

export const GROUP_ORDER: readonly CommandGroup[] = [
  'Modes and views',
  'Hardware',
  'Actions',
  'Panels',
  'Stars',
  'Settings',
  'Sections',
  'Help',
];

export interface Command {
  id: string;
  title: string;
  group: CommandGroup;
  icon?: string;
  /** Shortcut spec ("Alt+1", "W", "Mod+K"), shown as key caps. */
  keys?: string;
  /** Extra words that should find it ("park" -> "close arm"). */
  keywords?: string;
  /** Right-side hint ("Mount", "opens the sheet at the field"). */
  hint?: string;
  /** Moves or releases hardware: Enter opens an inline confirmation, never runs at once. */
  hardware?: { question: string; consequence: string; confirm: string };
  /** Why it cannot run now (shown under the title; Enter does nothing). */
  disabled?: string | null;
  run: () => void;
}

export interface Ranked {
  cmd: Command;
  score: number;
  /** Matched character indexes in the title (for highlighting). */
  hits: number[];
}

/** Score of `q` against `text`, with the matched indexes; null when no match. */
export function scoreText(q: string, text: string): { score: number; hits: number[] } | null {
  const t = text.toLowerCase();
  const query = q.toLowerCase().trim();
  if (!query) return { score: 0, hits: [] };
  const range = (start: number, len: number) => Array.from({ length: len }, (_, i) => start + i);
  if (t.startsWith(query)) return { score: 1000 - t.length, hits: range(0, query.length) };
  // Start of a word ("site" in "Observer & site").
  const words = /[\s›·&/(-]+/g;
  let m: RegExpExecArray | null;
  const starts = [0];
  while ((m = words.exec(t))) starts.push(m.index + m[0].length);
  for (const s of starts) {
    if (t.startsWith(query, s)) return { score: 800 - s - t.length * 0.1, hits: range(s, query.length) };
  }
  const sub = t.indexOf(query);
  if (sub >= 0) return { score: 600 - sub - t.length * 0.1, hits: range(sub, query.length) };
  // Subsequence: every character in order; compact matches and word starts score higher.
  const hits: number[] = [];
  let from = 0;
  for (const ch of query) {
    if (ch === ' ') continue;
    const i = t.indexOf(ch, from);
    if (i < 0) return null;
    hits.push(i);
    from = i + 1;
  }
  const spread = hits[hits.length - 1] - hits[0];
  const onStarts = hits.filter((h) => starts.includes(h)).length;
  return { score: 300 - spread * 4 + onStarts * 25 - t.length * 0.1, hits };
}

export function rank(query: string, commands: readonly Command[], recent: readonly string[] = []): Ranked[] {
  const out: Ranked[] = [];
  if (!query.trim()) {
    // Empty field: recent first, then the index in group order.
    const seen = new Set<string>();
    for (const id of recent) {
      const c = commands.find((x) => x.id === id);
      if (c && !seen.has(c.id)) {
        seen.add(c.id);
        out.push({ cmd: c, score: 2000 - out.length, hits: [] });
      }
    }
    for (const c of commands) if (!seen.has(c.id)) out.push({ cmd: c, score: 0, hits: [] });
    return out;
  }
  for (const c of commands) {
    const title = scoreText(query, c.title);
    const kw = c.keywords ? scoreText(query, c.keywords) : null;
    const best = title && (!kw || title.score >= kw.score - 50) ? title : kw ? { score: kw.score - 50, hits: [] } : null;
    if (!best) continue;
    const boost = recent.includes(c.id) ? 40 : 0;
    const penalty = c.disabled ? 30 : 0;
    out.push({ cmd: c, score: best.score + boost - penalty, hits: best.hits });
  }
  return out.sort((a, b) => b.score - a.score);
}
