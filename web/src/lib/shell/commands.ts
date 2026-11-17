/**
 * Command palette model (Mod+K; web/lab/PROPOSAL.md 3.1 and 6 "W2 (end)";
 * BRAND 7): the command record and the ranking, promoted from the design
 * lab (src/lab/workspace/model/commands.ts, copied and adapted: the groups
 * are the app's). Pure: the index is data, the ranking a small hand-written
 * scorer (prefix, word start, substring, then subsequence), no dependency.
 *
 * The app's shortcut registry (lib/app/keymap.ts) feeds the index
 * (commandIndex.ts), so every shortcut is searchable by its label and the
 * palette teaches the keys.
 */

export type CommandGroup = 'Sections' | 'Hardware' | 'Actions' | 'Settings' | 'Appearance' | 'Help';

export const GROUP_ORDER: readonly CommandGroup[] = ['Sections', 'Hardware', 'Actions', 'Settings', 'Appearance', 'Help'];

export interface Command {
  id: string;
  title: string;
  group: CommandGroup;
  icon?: string;
  /** Shortcut spec ("Alt+1", "W", "Mod+K"), shown as key caps. */
  keys?: string;
  /** Extra words that should find it ("park" -> "close arm"). */
  keywords?: string;
  /** Right-side hint ("Mount", "opens Settings at the field"). */
  hint?: string;
  /** Moves or releases hardware: Enter opens an inline confirmation, never runs at once. */
  hardware?: { question: string; consequence: string; confirm: string };
  /** Why it cannot run now (shown under the title; Enter does nothing). */
  disabled?: string | null;
  run: () => void | Promise<unknown>;
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
  // Only compact subsequences ("wtch" in "Watch"): letters scattered over a long
  // title ("s…i…t…e" across "Plate solving › ASTAP executable") are noise.
  if (spread > 3 * hits.length) return null;
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
    // A keyword match may rank the command, but the title's own hits are still drawn.
    const best = title && (!kw || title.score >= kw.score - 50) ? title : kw ? { score: kw.score - 50, hits: title?.hits ?? [] } : null;
    if (!best) continue;
    const boost = recent.includes(c.id) ? 40 : 0;
    const penalty = c.disabled ? 30 : 0;
    out.push({ cmd: c, score: best.score + boost - penalty, hits: best.hits });
  }
  return out.sort((a, b) => b.score - a.score);
}

export interface PaletteRow {
  r: Ranked;
  /** Position in display order: the one index the highlight, the option id and Enter share. */
  pos: number;
}

export interface PaletteGroup {
  name: string;
  rows: PaletteRow[];
}

/**
 * Groups the ranked commands for display and numbers the rows in the order
 * they are drawn. The highlight, aria-activedescendant, hover and Enter all
 * use `pos`, so the row shown active is the row that runs (with an empty
 * field the ranking is in index order while the display is in group order:
 * indexing the ranking would run another command than the one highlighted).
 */
export function layoutGroups(ranked: readonly Ranked[], query: string, recent: readonly string[] = []): { groups: PaletteGroup[]; flat: PaletteRow[] } {
  const empty = !query.trim();
  const byName = new Map<string, Ranked[]>();
  for (const r of ranked) {
    const name = empty && recent.includes(r.cmd.id) && r.score > 0 ? 'Recent' : r.cmd.group;
    if (!byName.has(name)) byName.set(name, []);
    byName.get(name)!.push(r);
  }
  const order = empty ? ['Recent', ...GROUP_ORDER] : [...new Set(ranked.map((r) => r.cmd.group))];
  const groups: PaletteGroup[] = [];
  const flat: PaletteRow[] = [];
  for (const name of order) {
    const rs = byName.get(name);
    if (!rs) continue;
    const rows = rs.map((r) => {
      const row = { r, pos: flat.length };
      flat.push(row);
      return row;
    });
    groups.push({ name, rows });
  }
  return { groups, flat };
}
