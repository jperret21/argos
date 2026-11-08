import { describe, expect, it } from 'vitest';
import { candidateRow, candidateRows, commonFlags, ensembleRows, ensembleSummary, roleByPosition, sortCandidates } from './candidates';
import { checkField, checkLayers, checkSelection, checkTargets, FieldStore, pendingFrom, type FieldClient } from './field.svelte';
import type { Candidate, TargetStar } from './types';

const C = (o: Partial<Candidate> & { key: string }): Candidate => ({
  auid: null,
  label: null,
  x: 10,
  y: 20,
  v_mag: 11,
  b_minus_v: 0.6,
  delta_b_minus_v: 0.1,
  sep_arcmin: 5,
  peak_adu: 20000,
  snr: 150,
  saturated: false,
  neighbours_in_aperture: 0,
  role: null,
  ...o,
});

const star = (o: Partial<TargetStar> & { key: string; role: TargetStar['role'] }): TargetStar => ({
  name: o.key,
  ra_hours: 19.4,
  dec_deg: 42.8,
  auid: null,
  source: 'vsp',
  mags: { V: 10.5 },
  chart_id: null,
  note: null,
  ...o,
});

class MemStore {
  data = new Map<string, string>();
  getItem(k: string) {
    return this.data.get(k) ?? null;
  }
  setItem(k: string, v: string) {
    this.data.set(k, v);
  }
}

describe('candidates table', () => {
  it('flags with words, never colour alone: clipped, non-linear, blend, colour, distance', () => {
    expect(candidateRow(C({ key: 'a' })).flags).toEqual([]);
    expect(candidateRow(C({ key: 'a' })).status).toBe('—');
    const r = candidateRow(C({ key: 'b', peak_adu: 65535, neighbours_in_aperture: 2, delta_b_minus_v: -0.45, sep_arcmin: 31 }));
    expect(r.flags).toEqual(['clipped', 'blend risk', 'colour', 'far']);
    expect(r.snr).toBeNull(); // a clipped star has no meaningful SNR
    expect(candidateRow(C({ key: 'c', saturated: true })).flags).toEqual(['non-linear']);
    expect(candidateRow(C({ key: 'd', delta_b_minus_v: 0.3 })).flags).toEqual([]);
    expect(candidateRow(C({ key: 'e', peak_adu: 65520 }), 65520).clipped).toBe(true);
  });

  it('names a star by AUID, else its VSP label, else its key', () => {
    expect(candidateRow(C({ key: 'k', auid: '000-BBC-123', label: '114' })).name).toBe('000-BBC-123');
    expect(candidateRow(C({ key: 'k', label: '114' })).name).toBe('114');
    expect(candidateRow(C({ key: 'k' })).name).toBe('k');
  });

  it('lists every candidate but the target; the ensemble keeps comparisons and check', () => {
    const list = [C({ key: 't', role: 'target' }), C({ key: 'c1', role: 'comparison' }), C({ key: 'k', role: 'check' }), C({ key: 'x' })];
    expect(candidateRows(list, 'candidates').map((r) => r.key)).toEqual(['c1', 'k', 'x']);
    expect(candidateRows(list, 'ensemble').map((r) => r.key)).toEqual(['c1', 'k']);
    const s = ensembleSummary(list);
    expect(s).toEqual({ candidates: 3, comparisons: 1, check: 'k', flagged: 0 });
  });

  it('adds set stars that are not VSP candidates to the ensemble', () => {
    const rows = ensembleRows([C({ key: 'c1', role: 'comparison' })], [star({ key: 'gaia1', role: 'comparison', display_name: 'Gaia 123' }), star({ key: 'c1', role: 'comparison' })]);
    expect(rows.map((r) => r.key)).toEqual(['c1', 'gaia1']);
    expect(rows[1].name).toBe('Gaia 123');
    expect(rows[1].v).toBe(10.5);
  });

  it("flags 'far' with the observer's limit and 'variable?' for a VSX entry", () => {
    const limits = { comparison_max_separation_arcmin: 60, comparison_max_delta_mag: 1.5, comparison_min_snr: 10, gaia_depth_g: 9.8 };
    const list = [C({ key: 'a', sep_arcmin: 39.6 }), C({ key: 'b', sep_arcmin: 61 }), C({ key: 'v', vsx: { name: 'NSV 24798', suspected: true } })];
    expect(candidateRows(list, 'candidates').map((r) => r.flags)).toEqual([['far'], ['far'], ['variable?']]);
    expect(candidateRows(list, 'candidates', null, { limits }).map((r) => r.flags)).toEqual([[], ['far'], ['variable?']]);
  });

  it('states a flag most rows share once instead of underlining every row', () => {
    const rows = [5, 30, 40, 50].map((sep, i) => candidateRow(C({ key: `k${i}`, sep_arcmin: sep, neighbours_in_aperture: i === 0 ? 1 : 0 })));
    const common = commonFlags(rows);
    expect(common.get('far')).toBe(3);
    expect(common.has('blend risk')).toBe(false); // 1 of 4: underlined on its row
  });

  it('gives a candidate the role its star has under another identity (same position)', () => {
    const c = C({ key: 'auid:000-BJW-666', ra_hours: 19.4, dec_deg: 42.8 });
    const vsxCheck = star({ key: 'auid:000-BJW-999', role: 'check', ra_hours: 19.4 + 0.5 / 3600 / 15, dec_deg: 42.8 });
    expect(roleByPosition(c, [vsxCheck])).toBe('check');
    expect(roleByPosition(c, [{ ...vsxCheck, dec_deg: 42.81 }])).toBeNull();
    expect(candidateRows([c], 'ensemble', null, { stars: [vsxCheck] }).map((r) => r.role)).toEqual(['check']);
    // One row in the ensemble, not two identities.
    expect(ensembleRows([c], [vsxCheck]).map((r) => r.key)).toEqual(['auid:000-BJW-666']);
  });

  it('sorts |Δ(B−V)|, clipped peaks as the brightest, missing values last both ways', () => {
    const rows = [C({ key: 'a', delta_b_minus_v: -0.4 }), C({ key: 'b', delta_b_minus_v: 0.05 }), C({ key: 'c', delta_b_minus_v: null }), C({ key: 'd', delta_b_minus_v: 0.2 })].map((c) =>
      candidateRow(c),
    );
    expect(sortCandidates(rows, 'dbv', true).map((r) => r.key)).toEqual(['b', 'd', 'a', 'c']);
    expect(sortCandidates(rows, 'dbv', false).map((r) => r.key)).toEqual(['a', 'd', 'b', 'c']);
    const peaks = [C({ key: 'p', peak_adu: 65535 }), C({ key: 'q', peak_adu: 30000 })].map((c) => candidateRow(c));
    expect(sortCandidates(peaks, 'peak', false)[0].key).toBe('p');
    const roles = [C({ key: 'n' }), C({ key: 'k', role: 'check' }), C({ key: 'c', role: 'comparison' })].map((c) => candidateRow(c));
    expect(sortCandidates(roles, 'role', true).map((r) => r.key)).toEqual(['c', 'k', 'n']);
  });
});

describe('message checks', () => {
  it('accepts the protocol records and drops malformed ones', () => {
    expect(checkField({ state: 'solved', auto: false, solution: { ra_hours: 19.4, dec_deg: 42.8 }, grid: { lines: [] } })?.grid?.labels).toEqual([]);
    expect(checkField({ state: 'bogus' })).toBeNull();
    const l = checkLayers({ generation: 3, available: true, layers: { stars: [{ x: 1, y: 2 }, { x: 'a' }], nope: [] }, counts: { stars: 1 }, candidates: [{ key: 'a' }, {}] });
    expect(l?.layers.stars?.length).toBe(1);
    expect(l?.candidates.length).toBe(1);
    expect(checkLayers({ generation: 'x', layers: {} })).toBeNull();
    expect(checkSelection({ id: null, selection: null })).toEqual({ id: null, selection: null, message: null });
    expect(checkSelection({ id: 4, state: 'weird', selection: null })).toBeNull();
    expect(checkTargets({ object_name: 'RR Lyr', stars: [{ key: 'a', role: 'target' }, { key: 'b', role: 'nope' }] })?.stars.length).toBe(1);
  });

  it('builds the A52 body that puts a removed star back', () => {
    const p = pendingFrom(star({ key: 'a', role: 'comparison', ra_hours: 2 }));
    expect(p.ra_deg).toBe(30);
    expect(p.dec_deg).toBe(42.8);
  });
});

function fakeClient(answers: Record<string, unknown>): FieldClient & { calls: [string, string, unknown][] } {
  const calls: [string, string, unknown][] = [];
  return {
    calls,
    async request<T>(method: string, path: string, body?: unknown): Promise<T> {
      calls.push([method, path, body]);
      const a = answers[`${method} ${path}`];
      if (a instanceof Error) throw a;
      return a as T;
    },
  };
}

const sel = (id: number, extra: Record<string, unknown> = {}) => ({
  id,
  state: 'identifying',
  selection: { id, kind: 'measured', title: 'Measured star', rows: [], ring: { x: 1, y: 2, r_px: 10, aperture: 'star' }, pending_star: null, key: null, role: null, roles_enabled: true, roles_reason: null, removable: false, identifying: true, ...extra },
});

describe('FieldStore', () => {
  it('remembers the layer toggles per viewer, merged over the defaults', () => {
    const storage = new MemStore();
    const a = new FieldStore({ storage });
    expect(a.visibility.vsp).toBe(false);
    a.setVisible('vsp', true);
    a.toggle('stars');
    const b = new FieldStore({ storage });
    expect(b.visibility.vsp).toBe(true);
    expect(b.visibility.stars).toBe(false);
    expect(b.visibility.labels).toBe(false);
  });

  it('keeps Framing and Focus to the grid and the set by default, remembered per mode', () => {
    const storage = new MemStore();
    const a = new FieldStore({ storage });
    a.mode = 'framing';
    expect(a.visibility.variables).toBe(false);
    expect(a.visibility.grid && a.visibility.selected).toBe(true);
    a.setVisible('variables', true);
    a.mode = 'field';
    expect(a.visibility.variables).toBe(true); // Field's own default
    a.setVisible('variables', false);
    const b = new FieldStore({ storage });
    b.mode = 'framing';
    expect(b.visibility.variables).toBe(true);
    b.mode = 'focus';
    expect(b.visibility.variables).toBe(false);
    b.mode = 'field';
    expect(b.visibility.variables).toBe(false);
  });

  it('applies a tracking transform only to the layers of its generation', () => {
    const f = new FieldStore({ storage: new MemStore() });
    f.ingest('field', { state: 'solved', auto: false, solution: { ra_hours: 1, dec_deg: 2 } });
    f.ingest('field_layers', { generation: 2, available: true, layers: {}, counts: {} });
    f.ingest('field_transform', { generation: 1, dx: 1, dy: 1, rot_deg: 0, cx: 0, cy: 0 });
    expect(f.activeTransform).toBeNull();
    f.ingest('field_transform', { generation: 2, dx: 1, dy: 1, rot_deg: 0, cx: 0, cy: 0 });
    expect(f.activeTransform?.dx).toBe(1);
    expect(f.layersAvailable).toBe(true);
  });

  it('drops the layers, the transform and the selection when the field is invalidated (P24)', () => {
    const f = new FieldStore({ storage: new MemStore() });
    f.ingest('field_layers', { generation: 2, available: true, layers: {}, counts: {} });
    f.ingest('selection', sel(1));
    f.ingest('field', { state: 'invalidated', auto: false, reason: 'slew', solution: null });
    expect(f.layers).toBeNull();
    expect(f.selection).toBeNull();
    expect(f.solved).toBe(false);
  });

  it('keeps the newest click: a late answer to a replaced click is dropped (P21)', async () => {
    const f = new FieldStore({ storage: new MemStore() });
    const client = fakeClient({ 'POST /api/field/select': sel(2) });
    f.ingest('selection', sel(1));
    await f.select(client, { x: 1, y: 2, seq: 5, tol_px: 20 });
    expect(f.selection?.id).toBe(2);
    expect(f.ingest('selection', { ...sel(1), state: 'resolved' })).toBe(false);
    expect(f.selection?.id).toBe(2);
    expect(f.ingest('selection', { ...sel(2), state: 'resolved' })).toBe(true);
    expect(f.selection?.state).toBe('resolved');
    expect(client.calls[0]).toEqual(['POST', '/api/field/select', { x: 1, y: 2, seq: 5, tol_px: 20 }]);
  });

  it('forgets the superseded ids of a server that restarted (its ids start at 1 again)', async () => {
    const f = new FieldStore({ storage: new MemStore() });
    const client = fakeClient({ 'POST /api/field/select': sel(2) });
    f.ingest('selection', sel(1));
    await f.select(client, { x: 1, y: 2, seq: 5, tol_px: 20 });
    await f.clearSelection(null);
    expect(f.ingest('selection', sel(1))).toBe(false);
    f.restart();
    expect(f.ingest('selection', sel(1))).toBe(true);
    expect(f.selection?.id).toBe(1);
  });

  it('keeps a resolved event that beat the HTTP reply', async () => {
    const f = new FieldStore({ storage: new MemStore() });
    const client = {
      async request<T>(): Promise<T> {
        f.ingest('selection', { ...sel(7), state: 'resolved' });
        return sel(7) as T;
      },
    };
    await f.select(client, { x: 0, y: 0 });
    expect(f.selection?.state).toBe('resolved');
  });

  it('sets a role from the selection and undoes it by removing the added star', async () => {
    const f = new FieldStore({ storage: new MemStore() });
    f.ingest('targets', { object_name: 'RR Lyr', stars: [] });
    const after = { object_name: 'RR Lyr', stars: [star({ key: 'rr', role: 'target' })] };
    const client = fakeClient({ 'POST /api/targets': after, 'DELETE /api/targets/rr': { object_name: 'RR Lyr', stars: [], removed: star({ key: 'rr', role: 'target' }) } });
    const r = await f.setRole(client, 'target', { selection: 9 });
    expect(client.calls[0]).toEqual(['POST', '/api/targets', { role: 'target', selection: 9 }]);
    expect(f.targets?.stars.length).toBe(1);
    await r.undo?.run();
    expect(client.calls[1]).toEqual(['DELETE', '/api/targets/rr', undefined]);
    expect(f.targets?.stars.length).toBe(0);
  });

  it('undoes a role change by restoring the old role, and a removal with the removed star', async () => {
    const f = new FieldStore({ storage: new MemStore() });
    const k = star({ key: 'k', role: 'comparison', ra_hours: 2 });
    f.ingest('targets', { object_name: 'X', stars: [k] });
    const client = fakeClient({
      'POST /api/targets': { object_name: 'X', stars: [{ ...k, role: 'check' }] },
      'DELETE /api/targets/k': { object_name: 'X', stars: [], removed: k },
    });
    const r = await f.setRole(client, 'check', { star: pendingFrom(k), key: 'k' });
    await r.undo?.run();
    expect(client.calls[1][2]).toMatchObject({ role: 'comparison', star: { ra_deg: 30 } });
    const d = await f.remove(client, 'k');
    expect(d.undo).not.toBeNull();
  });

  it('a null hover from one source never clears another source\'s mark', () => {
    const f = new FieldStore({ storage: new MemStore() });
    f.setHover({ source: 'candidates', key: 'a', points: [{ x: 1, y: 1 }] });
    f.setHover(null, 'image');
    expect(f.hover?.key).toBe('a');
    f.setHover(null, 'candidates');
    expect(f.hover).toBeNull();
  });

  it('keeps the last five inspected stars, newest first', () => {
    const f = new FieldStore({ storage: new MemStore() });
    for (const k of ['a', 'b', 'c', 'd', 'e', 'f', 'b']) f.inspect(k);
    expect(f.history).toEqual(['b', 'f', 'e', 'd', 'c']);
  });
});

describe('aperture thumbnail', () => {
  it('samples the window turned like the display, stretched and tinted', async () => {
    const { thumbPixels, thumbSize } = await import('./thumb');
    // 5 x 3 frame, a bright pixel right of the centre (x = 3, y = 1).
    const px = new Uint16Array(15);
    px[1 * 5 + 3] = 1000;
    const src = { pixels: px, width: 5, height: 3, channels: 1 as const };
    const lv = { black: 0, white: 1000, midtones: 0.5, mode: 'linear' as const };
    const flat = thumbPixels(src, 2, 1, 3, lv, [255, 0, 0], 0);
    // Unturned: right of centre = thumbnail (u 2, v 1), red only.
    expect([flat[(1 * 3 + 2) * 4], flat[(1 * 3 + 2) * 4 + 1]]).toEqual([255, 0]);
    // Turned 90° clockwise: frame +x points down on screen -> (u 1, v 2).
    const turned = thumbPixels(src, 2, 1, 3, lv, [255, 0, 0], 1);
    expect(turned[(2 * 3 + 1) * 4]).toBe(255);
    expect(turned[(1 * 3 + 2) * 4]).toBe(0);
    expect(thumbSize(10, 30)).toBe(69);
    expect(thumbSize(null, null) % 2).toBe(1);
  });
});

describe('field words and the star card places', () => {
  it('says the field state in words (03 2.4)', async () => {
    const { fieldChip, identifyReason } = await import('./present');
    const sol = { ra_hours: 19.4, dec_deg: 42.8, scale_arcsec_px: 1.19, rotation_deg: -12.34, delta_target_arcmin: 2.4, frame_seq: 1 };
    const base = { auto: false, reason: null, wcs: null, grid: null, target_reticle: null };
    expect(fieldChip(null).text).toBe('Field not identified');
    expect(fieldChip({ ...base, state: 'solved', solution: sol, auto: true }).text).toBe('Identified · 1.19″/px · PA −12.3° · Δtarget 2.4′ · Auto');
    const lost = { generation: 1, rot_deg: 0, dx: 0, dy: 0, cx: 0, cy: 0, tracking: 'lost' as const };
    expect(fieldChip({ ...base, state: 'solved', solution: sol }, null, lost)).toMatchObject({ text: 'Identified · tracking lost', tone: 'warn' });
    expect(fieldChip({ ...base, state: 'solved', solution: sol }, { state: 'fetching', counts: {}, warnings: [] }).tone).toBe('busy');
    expect(fieldChip({ ...base, state: 'failed', solution: sol }).text).toBe('Identification failed, last solution kept');
    expect(fieldChip({ ...base, state: 'invalidated', solution: null }).tone).toBe('warn');
    expect(identifyReason(false, null)).toMatch(/No frame yet/);
    expect(identifyReason(true, null)).toBeNull();
  });

  it('titles the star card with the identity alone and builds its facts from the fields', async () => {
    const { cardText, vsxTypeWord } = await import('./present');
    const base = { id: 1, ring: null, key: null, role: null, roles_enabled: true, roles_reason: null, removable: false, identifying: false };
    const vsp = {
      ...base,
      kind: 'vsp' as const,
      title: 'VSP reference · 000-BJW-666',
      rows: [{ key: 'AAVSO VSP reference', value: '000-BJW-666' }],
      pending_star: { ra_deg: 291.0, dec_deg: 42.5, ra_hours: 291.0 / 15, name: '000-BJW-666', mags: { V: 7.902, B: 8.596 } },
    };
    const t = cardText(vsp, { target: { ra_hours: 19.4244, dec_deg: 42.7844 } });
    expect(t.title).toBe('000-BJW-666');
    expect(t.facts).toMatch(/^V 7\.90 · B−V 0\.69 · \d+\.\d′ from target · VSP comparison$/);
    const variable = {
      ...base,
      kind: 'variable' as const,
      title: 'Variable · KIC 7201168',
      rows: [{ key: 'Type', value: 'ROT' }, { key: 'Max', value: '10.99 Kp' }, { key: 'Min', value: '11.01 Kp' }],
      pending_star: { ra_deg: 291.0, dec_deg: 42.5, name: 'KIC 7201168', mags: {} },
    };
    const v = cardText(variable, { alias: 'VSP 000-BJW-666' });
    expect(v.title).toBe('KIC 7201168 · VSP 000-BJW-666');
    expect(v.facts).toBe('10.99 Kp – 11.01 Kp · rotational (VSX)');
    expect(vsxTypeWord('RRAB/BL')).toBe('RR Lyrae');
    expect(vsxTypeWord('')).toBeNull();
    const target = { ...variable, role: 'target' as const, title: 'Target · RR Lyr', rows: [{ key: 'Role', value: 'target' }, { key: 'Source', value: 'vsx' }], pending_star: { ra_deg: 291.37, dec_deg: 42.78, name: 'RR Lyr', mags: {} } };
    expect(cardText(target).facts).toBe('target of the set');
  });

  it('gives the photometry pre-check reasons in the Qt order (M50, 03 1.14 #1-#3)', async () => {
    const { photometryProblem } = await import('./present');
    const sol = { ra_hours: 19.4, dec_deg: 42.8, scale_arcsec_px: 1.19, rotation_deg: 0, delta_target_arcmin: null, frame_seq: 1 };
    const base = { auto: false, reason: null, wcs: null, grid: null, target_reticle: null };
    const star = (key: string, role: 'target' | 'comparison' | 'check') => ({ key, role, name: key, ra_hours: 19.4, dec_deg: 42.8 }) as unknown as TargetStar;
    const set = (stars: TargetStar[]) => ({ object_name: 'RR Lyr', path: '/x/targets/RR_Lyr.json', stars, summary: null, geometry: null }) as never;
    expect(photometryProblem(null, null)).toBe('identify the field first');
    expect(photometryProblem({ ...base, state: 'invalidated', solution: null }, set([star('t', 'target')]))).toBe('identify the field first');
    const solved = { ...base, state: 'solved' as const, solution: sol };
    expect(photometryProblem(solved, set([star('c', 'comparison')]))).toBe('assign a target star first');
    expect(photometryProblem(solved, set([star('t', 'target'), star('k', 'check')]))).toMatch(/^the target set has no comparison stars/);
    expect(photometryProblem(solved, set([star('t', 'target'), star('c', 'comparison')]))).toBeNull();
  });

  it('places the card beside the star inside the stage, and docks it by corner', async () => {
    const { besideStar, cornerPos, dockKey, nearestCorner } = await import('./present');
    const card = { width: 250, height: 96 };
    const stage = { width: 900, height: 600 };
    expect(besideStar({ x: 100, y: 300, r: 13 }, card, stage)).toEqual({ x: 127, y: 252 });
    // Near the right edge it flips to the left of the star.
    expect(besideStar({ x: 850, y: 300, r: 13 }, card, stage).x).toBe(850 - 27 - 250);
    // Never under the HUD chip row.
    expect(besideStar({ x: 100, y: 10, r: 13 }, card, stage).y).toBe(44);
    expect(cornerPos(3, card, stage)).toEqual({ x: 638, y: 492 });
    expect(nearestCorner({ x: 600, y: 20 }, card, stage)).toBe(1);
    expect(dockKey(-1, 'ArrowUp')).toBe(0);
    expect(dockKey(0, 'ArrowRight')).toBe(1);
    expect(dockKey(3, 'Home')).toBe(-1);
    expect(dockKey(2, 'x')).toBeNull();
  });
});
