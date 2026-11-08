<!--
  Field overlay (wave 4; web/spec/04-viewer-and-image-tools.md 2.3-2.4, 03 2.4; promoted
  from the marks of src/lab/workspace/observe/Viewer.svelte, web/lab/PROPOSAL.md 6). An SVG
  layer in SCREEN space over the viewer, sibling of the HUD: labels and the check-star
  triangle stay upright whatever the display rotation, symbols keep their size at any zoom,
  and labels are de-overlapped in screen px after each zoom (P27).

  Drawn, bottom first: the RA / Dec grid (1 px dotted, broken under its labels, which are in
  the UI's coordinate format); the catalogue layers, ONE <path> per layer (the Gaia layer
  reaches 5 000 markers; culled to the stage), 1 px at fit zoom and 1.5 px from 50 %, a
  source of the target set left to its role mark, variables smaller when more than 60 are on
  screen; VSP references (+); the target set (circle target, square comparison, upright
  triangle check, 2.5 px, at least 17 / 15 px radius so the set stands out, BRAND 6.8 and
  11); the observation's target reticle; corner brackets in the foreground ink for what a
  list hovers (candidates table, exposure check); the hovered marker (stroke +1 px at once,
  its identity after ~500 ms, BRAND 7); the selection as four corner brackets in --accent
  outside the role mark (brass = the selected object, BRAND 3; never the target's circle).
  Labels avoid each other and the HUD (chips, compass, scale bar, readout); the set's in
  --fg, the catalogue's in --text-muted, at most 40 at fit zoom (nearest the target first).
  While the tracking lock is lost (A48 `tracking: "lost"`) everything placed through the
  reference solve is dimmed. Tokens only: Night Red stays red, shape carries identity.

  The catalogue layers (thousands of markers) are drawn on a canvas under the SVG, the rest
  (roles, grid, labels, marks) in the SVG. A pan moves both with a CSS translate and
  rebuilds them once the gesture settles (250 ms): re-rasterising every marker per pointer
  move cost 5 fps (technical review); a moved canvas is a bitmap blit.

  Every catalogue position is a REFERENCE-solve frame px (A47); the tracking transform (A48)
  moves it onto the frame on screen, then the display rotation and the viewer's pan / zoom
  (rect, from FitsViewer `onrect`) place it on the stage (project.ts).

  Pointer grammar (04 2.4), on the viewer under this layer: a click (≤ 4 px travel, no
  modifier, not the second click of a double click) reports the frame px, the hit tolerance
  of 10 screen px in frame px (A49 `tol_px`) and the marker hit, if any; hovering reports the
  marker under the pointer. The layer itself never takes the pointer: pan and zoom stay the
  viewer's.
-->
<script lang="ts" module>
  import type { Placed } from './layers';
  import type { Point } from './project';

  /** A mark from a list (a candidates row, an exposure-check bar): frame px. */
  export interface ListMark {
    points: readonly Point[];
    /** Reference-solve px (catalogue positions): the tracking transform applies. */
    reference?: boolean;
  }

  export interface SelectAt {
    /** Frame px of the click (current frame, sub-pixel). */
    x: number;
    y: number;
    /** 10 screen px in frame px. */
    tol_px: number;
    hit: Placed | null;
  }
</script>

<script lang="ts">
  import { untrack } from 'svelte';
  import { displaySize, type Turns } from '../rotation';
  import {
    asRole,
    bracketPath,
    DENSE_VARIABLE_RADIUS,
    DENSE_VARIABLES,
    gridLabelText,
    hitTest,
    LABEL_CHAR_W,
    LABEL_H,
    LAYER_IDS,
    layerPath,
    markerId,
    markerLabel,
    passesDepth,
    placeLabels,
    RADIUS,
    rolePath,
    roleRadius,
    tipContent,
    type Box,
    type LabelRequest,
    type LayerId,
    type LayerMarkers,
    type Role,
    type TipRow,
    type Visibility,
  } from './layers';
  import { onStage, placeRing, project, screenScale, screenToFrame, tolFramePx, type Rect, type RigidTransform, type ScreenMap, type Size } from './project';

  interface Props {
    /**
     * Where the image is: FitsViewer's `ongeometry` record ({view, frame, turns}), or the
     * image rectangle (FitsViewer `onrect`) with the frame size and the display turns.
     */
    geometry?: { view: { scale: number; tx: number; ty: number }; frame: Size; turns: Turns } | null;
    rect?: Rect | null;
    frame?: Size | null;
    turns?: Turns;
    /** The stage this layer covers (CSS px, the viewer's box). */
    stage: Size;
    markers?: LayerMarkers | null;
    transform?: RigidTransform | null;
    visibility: Visibility;
    /** Gaia display depth (stars only). */
    gLimit?: number | null;
    grid?: { lines: readonly (readonly (readonly [number, number])[])[]; labels: readonly { x: number; y: number; text: string; axis?: string }[] } | null;
    reticle?: { x: number; y: number; name?: string | null } | null;
    /** The selection ring (A49): `space` "reference" (catalogue hit, tracked) or "frame". */
    ring?: { x: number; y: number; r_px: number; space?: string | null } | null;
    /** Rings for what a list hovers. */
    mark?: ListMark | null;
    /** A key the set or a list hovers: that marker is drawn hot. */
    hotKey?: string | null;
    /** Photometry aperture radius, frame px (role markers are drawn at least that size). */
    apertureR?: number | null;
    /** The pointer grammar is on (off in a gallery still, or while a tool owns the pointer). */
    interactive?: boolean;
    onselect?: (at: SelectAt) => void;
    onhover?: (hit: Placed | null) => void;
    /** Hover delay of the identity popover, ms (BRAND 7: about 500). */
    tipDelay?: number;
    /** A48 lock health: "lost" dims everything placed through the reference solve. */
    tracking?: string | null;
  }

  let {
    geometry = null,
    rect = null,
    frame = null,
    turns = 0,
    stage,
    markers = null,
    transform = null,
    visibility,
    gLimit = null,
    grid = null,
    reticle = null,
    ring = null,
    mark = null,
    hotKey = null,
    apertureR = null,
    interactive = true,
    onselect,
    onhover,
    tipDelay = 500,
    tracking = null,
  }: Props = $props();

  let root: HTMLDivElement | undefined = $state();

  /** Where the image is now (clicks use it). */
  const live: ScreenMap | null = $derived.by(() => {
    if (geometry) {
      const g = geometry;
      const d = displaySize(g.frame.width, g.frame.height, g.turns);
      const r = { left: g.view.tx, top: g.view.ty, width: d.width * g.view.scale, height: d.height * g.view.scale };
      return g.frame.width > 0 && r.width > 0 ? { rect: r, frame: g.frame, turns: g.turns } : null;
    }
    return rect && frame && rect.width > 0 && frame.width > 0 ? { rect, frame, turns } : null;
  });

  /**
   * The map the paths were built with. A pan (same zoom, frame and turns) keeps it and moves
   * the drawn layer by `shift`; the paths are rebuilt when the gesture settles.
   */
  let map = $state.raw<ScreenMap | null>(null);
  /** A pan rebuilds the paths once the pointer rests this long. */
  const SETTLE_MS = 250;
  let settleTimer = 0;
  const panOnly = (a: ScreenMap, b: ScreenMap) =>
    a.turns === b.turns && a.frame.width === b.frame.width && a.frame.height === b.frame.height && Math.abs(a.rect.width - b.rect.width) < 1e-6 && Math.abs(a.rect.height - b.rect.height) < 1e-6;
  $effect(() => {
    const m = live;
    untrack(() => {
      clearTimeout(settleTimer);
      if (!m || !map || !panOnly(m, map)) {
        map = m;
        return;
      }
      settleTimer = window.setTimeout(() => (map = live), SETTLE_MS);
    });
  });
  $effect(() => () => clearTimeout(settleTimer));
  const shift = $derived(live && map ? { x: live.rect.left - map.rect.left, y: live.rect.top - map.rect.top } : { x: 0, y: 0 });

  const frameSize = $derived(live?.frame ?? null);
  const scale = $derived(map ? screenScale(map) : 0);
  const radiusOf = (role: Role) => roleRadius(apertureR, scale, role);
  const rRole = $derived(radiusOf('target'));
  /** Catalogue strokes: 1 px at fit zoom, 1.5 px from 50 %. */
  const fine = $derived(scale > 0 && scale < 0.5);

  /** Catalogue markers that are a star of the set (same key, or within 2″): its role mark only. */
  const inSet: Set<string> = $derived.by(() => {
    const out = new Set<string>();
    const set = markers?.selected ?? [];
    if (!markers || !set.length) return out;
    const keys = new Set(set.map((m) => m.key).filter(Boolean));
    const near = (m: { ra_hours?: number; dec_deg?: number }) => {
      if (typeof m.ra_hours !== 'number' || typeof m.dec_deg !== 'number') return false;
      const cos = Math.cos((m.dec_deg * Math.PI) / 180);
      return set.some(
        (s) => typeof s.ra_hours === 'number' && typeof s.dec_deg === 'number' && Math.hypot(((((m.ra_hours! - s.ra_hours) * 15 + 540) % 360) - 180) * cos, m.dec_deg! - s.dec_deg) * 3600 <= 2,
      );
    };
    for (const layer of LAYER_IDS) {
      if (layer === 'selected') continue;
      (markers[layer] ?? []).forEach((m, i) => {
        if ((m.key && keys.has(m.key)) || near(m)) out.add(`${layer}#${i}`);
      });
    }
    return out;
  });

  // -- Placement ------------------------------------------------------------------------------

  /** Every visible marker on the stage, in drawing order. */
  const placed: Placed[] = $derived.by(() => {
    const out: Placed[] = [];
    const m = map;
    if (!m || !markers) return out;
    for (const layer of LAYER_IDS) {
      if (!visibility[layer]) continue;
      const list = markers[layer];
      if (!list) continue;
      for (let i = 0; i < list.length; i++) {
        const mk = list[i];
        if (!passesDepth(layer, mk, gLimit)) continue;
        if (layer !== 'selected' && inSet.has(`${layer}#${i}`)) continue;
        const p = project(m, transform, mk.x, mk.y);
        if (!onStage(p, stage, 40)) continue;
        out.push({ layer, index: i, marker: mk, sx: p.x, sy: p.y });
      }
    }
    return out;
  });

  /** Many variables on screen: drawn smaller so they do not hide the image. */
  const varR = $derived(placed.reduce((n, p) => n + (p.layer === 'variables' ? 1 : 0), 0) > DENSE_VARIABLES ? DENSE_VARIABLE_RADIUS : RADIUS.variables);
  const radiusOfLayer = (layer: Exclude<LayerId, 'selected'>) => (layer === 'variables' ? varR : RADIUS[layer]);

  /** One path per catalogue layer (suspected variables apart: dashed). */
  const paths = $derived.by(() => {
    const d: Partial<Record<Exclude<LayerId, 'selected'> | 'suspected', string[]>> = {};
    for (const p of placed) {
      if (p.layer === 'selected') continue;
      const key = p.layer === 'variables' && p.marker.suspected ? 'suspected' : p.layer;
      (d[key] ??= []).push(layerPath(p.layer, p.sx, p.sy, radiusOfLayer(p.layer)));
    }
    return Object.entries(d).map(([k, v]) => ({ key: k, d: (v ?? []).join('') }));
  });

  const roles = $derived(placed.filter((p) => p.layer === 'selected').map((p) => ({ p, role: (asRole(p.marker.role) ?? 'target') as Role })));

  // -- The catalogue layers on a canvas (a pan moves a bitmap, never re-rasterises) ---------

  let canvas: HTMLCanvasElement | undefined = $state();
  /** Overlay tokens per layer path key (the same as the SVG classes did). */
  const INK: Record<string, string> = {
    stars: '--overlay-field-star',
    variables: '--overlay-variable',
    suspected: '--overlay-variable',
    galaxies: '--overlay-galaxy',
    nebulae_clusters: '--overlay-nebula',
    exoplanets: '--overlay-exoplanet',
    other_objects: '--overlay-other',
    vsp: '--role-comparison',
  };
  /** The theme changed (data-theme on <html>): the tokens are read again. */
  let themeTick = $state(0);
  $effect(() => {
    const watch = new MutationObserver(() => themeTick++);
    watch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class', 'style'] });
    return () => watch.disconnect();
  });
  $effect(() => {
    const c = canvas;
    const list = paths;
    const thin = fine;
    const { width, height } = stage;
    void themeTick;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.round(width * dpr));
    const h = Math.max(1, Math.round(height * dpr));
    if (c.width !== w) c.width = w;
    if (c.height !== h) c.height = h;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const css = getComputedStyle(c);
    ctx.lineJoin = 'round';
    for (const p of list) {
      ctx.strokeStyle = css.getPropertyValue(INK[p.key] ?? '--overlay-other').trim() || '#888';
      ctx.lineWidth = p.key === 'stars' || thin ? 1 : 1.5;
      ctx.setLineDash(p.key === 'suspected' ? [4, 3] : []);
      ctx.stroke(new Path2D(p.d));
    }
  });

  // -- The HUD as an obstacle for labels (chips, compass, scale bar, cursor readout) ---------

  let obstacles: Box[] = $state.raw([]);
  function measureObstacles(): void {
    const host = root?.parentElement;
    if (!host) return;
    const b = host.getBoundingClientRect();
    const out: Box[] = [];
    for (const el of host.querySelectorAll('[data-hud], [data-compass], [data-scale-bar]')) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) out.push({ x0: r.left - b.left - 3, y0: r.top - b.top - 3, x1: r.right - b.left + 3, y1: r.bottom - b.top + 3 });
    }
    const same = out.length === obstacles.length && out.every((o, i) => Math.abs(o.x0 - obstacles[i].x0) + Math.abs(o.y0 - obstacles[i].y0) + Math.abs(o.x1 - obstacles[i].x1) + Math.abs(o.y1 - obstacles[i].y1) < 1);
    if (!same) obstacles = out;
  }
  $effect(() => {
    void stage.width;
    void stage.height;
    untrack(measureObstacles);
    const t = window.setInterval(measureObstacles, 1000);
    return () => clearInterval(t);
  });
  const hits = (b: Box) => obstacles.some((o) => b.x0 < o.x1 && o.x0 < b.x1 && b.y0 < o.y1 && o.y0 < b.y1);

  /** Polylines of the grid on the stage. */
  const gridLines = $derived.by(() => {
    const m = map;
    if (!m || !grid || !visibility.grid) return [] as string[];
    return grid.lines
      .filter((line) => line.length > 1)
      .map((line) =>
        line
          .map(([x, y]) => {
            const q = project(m, transform, x, y);
            return `${q.x.toFixed(1)},${q.y.toFixed(1)}`;
          })
          .join(' '),
      );
  });
  /** Grid labels in the UI's format, inside the stage, off the HUD; the line breaks under each. */
  const gridLabels = $derived.by(() => {
    const m = map;
    if (!m || !grid || !visibility.grid) return [];
    return grid.labels
      .map((l) => ({ ...l, text: gridLabelText(l.text, l.axis), p: project(m, transform, l.x, l.y) }))
      .filter((l) => onStage(l.p, stage, -4))
      .map((l) => {
        // A label at an edge reads inward (start / end anchored), never cut in half.
        const w = l.text.length * LABEL_CHAR_W;
        const half = w / 2 + 4;
        const anchor: 'start' | 'end' | 'middle' = l.p.x < half ? 'start' : l.p.x > stage.width - half ? 'end' : 'middle';
        const x = anchor === 'start' ? 4 : anchor === 'end' ? stage.width - 4 : l.p.x;
        const y = Math.min(Math.max(l.p.y, 14), stage.height - 4);
        const x0 = anchor === 'start' ? x : anchor === 'end' ? x - w : x - w / 2;
        const box = { x0: x0 - 2, y0: y - LABEL_H + 2, x1: x0 + w + 2, y1: y + 3 };
        return { text: l.text, x, y, anchor, box };
      })
      .filter((l) => !hits({ x0: l.box.x0 + shift.x, y0: l.box.y0 + shift.y, x1: l.box.x1 + shift.x, y1: l.box.y1 + shift.y }));
  });
  const maskId = `grid-gaps-${Math.random().toString(36).slice(2, 8)}`;

  /** The observation's target reticle, unless the set's target marker already sits there. */
  const reticleAt = $derived.by(() => {
    if (!map || !reticle) return null;
    const onTarget = (markers?.selected ?? []).some((s) => s.role === 'target' && Math.hypot(s.x - reticle.x, s.y - reticle.y) < 4);
    return onTarget ? null : project(map, transform, reticle.x, reticle.y);
  });
  const ringAt = $derived.by(() => {
    if (!map || !ring) return null;
    // Outside the role marker it may sit on, so the brass brackets read as "this one" (lab: r + 7).
    const p = placeRing(map, transform, ring, rRole);
    return { x: p.x, y: p.y, r: p.r + 7 };
  });
  const markAt = $derived.by(() => {
    const m = map;
    if (!m || !mark) return [];
    return mark.points.map((q) => project(m, mark.reference ? transform : null, q.x, q.y)).filter((q) => onStage(q, stage, 0));
  });

  // -- Hover ----------------------------------------------------------------------------------

  let hovered: Placed | null = $state.raw(null);
  let tip: { title: string; kind: string; rows: TipRow[]; x: number; y: number; flip: boolean } | null = $state(null);
  let tipTimer = 0;

  const hot = $derived.by(() => {
    if (hovered) return hovered;
    if (!hotKey) return null;
    return placed.find((p) => p.marker.key === hotKey) ?? null;
  });

  function setHovered(h: Placed | null): void {
    const same = h && hovered && h.layer === hovered.layer && h.index === hovered.index;
    if (same || (!h && !hovered)) return;
    hovered = h;
    onhover?.(h);
    clearTimeout(tipTimer);
    tip = null;
    if (h && (h.marker.tooltip || markerLabel(h.marker))) {
      tipTimer = window.setTimeout(() => {
        const c = tipContent(h.layer, h.marker);
        const flip = h.sx + shift.x > stage.width - 280;
        tip = { ...c, x: h.sx, y: h.sy, flip };
      }, tipDelay);
    }
  }

  // A new set of markers (or a pan) moves things away from under the pointer.
  $effect(() => {
    void placed;
    untrack(() => {
      if (hovered && !placed.some((p) => p.layer === hovered!.layer && p.index === hovered!.index)) setHovered(null);
    });
  });

  // -- Labels ---------------------------------------------------------------------------------

  const ORDER: Record<LayerId, number> = { selected: 0, variables: 1, other_objects: 2, galaxies: 3, nebulae_clusters: 4, exoplanets: 5, stars: 6, vsp: 9 };

  /** At fit zoom, catalogue labels are capped (nearest the target first). */
  const FIT_LABELS = 40;

  const labels = $derived.by(() => {
    const reqs: LabelRequest[] = [];
    const target = placed.find((p) => p.layer === 'selected' && asRole(p.marker.role) === 'target');
    const cx = target?.sx ?? stage.width / 2;
    const cy = target?.sy ?? stage.height / 2;
    const sorted = [...placed].sort((a, b) => ORDER[a.layer] - ORDER[b.layer] || (a.layer === 'selected' ? 0 : Math.hypot(a.sx - cx, a.sy - cy) - Math.hypot(b.sx - cx, b.sy - cy)));
    let catalogue = 0;
    for (const p of sorted) {
      if (p.layer === 'vsp') continue; // VSP chart labels are magnitudes, not names (Qt fits_viewer.py:751-754)
      const isHot = hot && hot.layer === p.layer && hot.index === p.index;
      if (p.layer !== 'selected' && !visibility.labels && !isHot) continue;
      const text = markerLabel(p.marker);
      if (!text) continue;
      if (p.layer !== 'selected' && !isHot && fine && catalogue >= FIT_LABELS) continue;
      if (p.layer !== 'selected') catalogue++;
      const r = p.layer === 'selected' ? radiusOf(asRole(p.marker.role) ?? 'target') : radiusOfLayer(p.layer);
      reqs.push({ id: markerId(p.layer, p.index, p.marker), text, x: p.sx, y: p.sy, r });
    }
    // The hovered marker's label wins its spot first.
    if (hot) {
      const id = markerId(hot.layer, hot.index, hot.marker);
      const i = reqs.findIndex((q) => q.id === id);
      if (i > 0) reqs.unshift(...reqs.splice(i, 1));
    }
    // The HUD in drawn space (the layer may be shifted by a pan in progress).
    const hud = obstacles.map((o) => ({ x0: o.x0 - shift.x, y0: o.y0 - shift.y, x1: o.x1 - shift.x, y1: o.y1 - shift.y }));
    return placeLabels(reqs, stage, 250, hud);
  });

  // -- Pointer grammar ------------------------------------------------------------------------

  $effect(() => {
    const host = root?.parentElement;
    if (!host || !interactive) return;
    let down: { x: number; y: number; id: number } | null = null;
    const local = (e: MouseEvent): Point => {
      const b = host.getBoundingClientRect();
      return { x: e.clientX - b.left, y: e.clientY - b.top };
    };
    // Only the image itself (the viewer, role="application"); never a card or a chip over it.
    const onImage = (e: Event) => !!(e.target as Element | null)?.closest?.('[role="application"]');
    // The drawn layer may be shifted by a pan in progress.
    const drawn = (p: Point): Point => ({ x: p.x - shift.x, y: p.y - shift.y });
    const move = (e: PointerEvent) => {
      if (!onImage(e) || e.buttons) return setHovered(null);
      setHovered(hitTest(placed, drawn(local(e)), 10));
    };
    const leave = () => setHovered(null);
    const press = (e: PointerEvent) => {
      if (e.button !== 0 || !onImage(e)) return;
      const p = local(e);
      down = { x: p.x, y: p.y, id: e.pointerId };
    };
    const click = (e: MouseEvent) => {
      const d = down;
      down = null;
      const m = live;
      if (!d || !m || e.button !== 0 || e.detail > 1 || e.shiftKey || e.altKey || e.metaKey || e.ctrlKey) return;
      if (!onImage(e)) return;
      const p = local(e);
      if (Math.hypot(p.x - d.x, p.y - d.y) > 4) return; // a pan, not a click
      const f = screenToFrame(m, p.x, p.y);
      const fs = frameSize;
      if (!fs || f.x < -0.5 || f.y < -0.5 || f.x > fs.width - 0.5 || f.y > fs.height - 0.5) return;
      onselect?.({ x: f.x, y: f.y, tol_px: tolFramePx(m, 10), hit: hitTest(placed, drawn(p), 10) });
    };
    host.addEventListener('pointermove', move);
    host.addEventListener('pointerleave', leave);
    host.addEventListener('pointerdown', press);
    host.addEventListener('click', click);
    return () => {
      host.removeEventListener('pointermove', move);
      host.removeEventListener('pointerleave', leave);
      host.removeEventListener('pointerdown', press);
      host.removeEventListener('click', click);
      clearTimeout(tipTimer);
    };
  });

  const reticlePath = (x: number, y: number) => {
    // BRAND 6.8 reticle: a ring broken at N/E/S/W with ticks through the gaps.
    const r = 16;
    const g = 5;
    const a = Math.asin(g / r);
    const arcs: string[] = [];
    for (let k = 0; k < 4; k++) {
      const a0 = (k * Math.PI) / 2 + a;
      const a1 = ((k + 1) * Math.PI) / 2 - a;
      arcs.push(`M${(x + r * Math.cos(a0)).toFixed(1)} ${(y + r * Math.sin(a0)).toFixed(1)}A${r} ${r} 0 0 1 ${(x + r * Math.cos(a1)).toFixed(1)} ${(y + r * Math.sin(a1)).toFixed(1)}`);
    }
    const t = `M${x + r - 4} ${y}h8M${x - r - 4} ${y}h8M${x} ${y + r - 4}v8M${x} ${y - r - 4}v8`;
    return arcs.join('') + t;
  };
</script>

<div class="field-overlay" bind:this={root}>
  <canvas
    class="layers"
    data-overlay="catalogue"
    class:lost={tracking === 'lost'}
    bind:this={canvas}
    style:width="{stage.width}px"
    style:height="{stage.height}px"
    style:transform={shift.x || shift.y ? `translate(${shift.x}px, ${shift.y}px)` : undefined}
  ></canvas>
  <svg width={stage.width} height={stage.height} aria-hidden="true" class:fine class:lost={tracking === 'lost'} style:transform={shift.x || shift.y ? `translate(${shift.x}px, ${shift.y}px)` : undefined}>
    {#if gridLines.length}
      <mask id={maskId} maskUnits="userSpaceOnUse" x={-stage.width} y={-stage.height} width={3 * stage.width} height={3 * stage.height}>
        <rect x={-stage.width} y={-stage.height} width={3 * stage.width} height={3 * stage.height} fill="white" />
        {#each gridLabels as l, i (i)}<rect x={l.box.x0} y={l.box.y0} width={l.box.x1 - l.box.x0} height={l.box.y1 - l.box.y0} fill="black" />{/each}
      </mask>
      <g class="grid ref" mask="url(#{maskId})">
        {#each gridLines as pts, i (i)}<polyline points={pts} />{/each}
      </g>
    {/if}
    <g class="ref">
      {#each roles as { p, role } (p.index)}
        <path class="role {role}" d={rolePath(role, p.sx, p.sy, radiusOf(role))} />
      {/each}
      {#if reticleAt}
        <path class="reticle" d={reticlePath(reticleAt.x, reticleAt.y)} />
      {/if}
    </g>
    {#each markAt as q, i (i)}
      <path class="list-mark halo" d={bracketPath(q.x, q.y, Math.max(rRole, 14) + 6)} />
      <path class="list-mark" d={bracketPath(q.x, q.y, Math.max(rRole, 14) + 6)} />
    {/each}
    {#if hot}
      {#if hot.layer === 'selected'}
        <path class="role hot {asRole(hot.marker.role) ?? 'target'}" d={rolePath(asRole(hot.marker.role) ?? 'target', hot.sx, hot.sy, radiusOf(asRole(hot.marker.role) ?? 'target'))} />
      {:else}
        <path class="layer hot {hot.layer}" class:suspected={hot.layer === 'variables' && hot.marker.suspected} d={layerPath(hot.layer, hot.sx, hot.sy, radiusOfLayer(hot.layer))} />
      {/if}
    {/if}
    {#if ringAt}
      <path class="selection halo" d={bracketPath(ringAt.x, ringAt.y, ringAt.r)} />
      <path class="selection" d={bracketPath(ringAt.x, ringAt.y, ringAt.r)} />
    {/if}
    {#each gridLabels as l, i (i)}
      <text class="grid-label" x={l.x} y={l.y} text-anchor={l.anchor}>{l.text}</text>
    {/each}
    {#each labels as l (l.id)}
      <text class="label" class:set={l.id.startsWith('selected')} x={l.x} y={l.y} text-anchor={l.anchor}>{l.text}</text>
    {/each}
    {#if reticleAt && reticle?.name}
      <text class="label set" x={reticleAt.x + 22} y={reticleAt.y - 18}>{reticle.name}</text>
    {/if}
  </svg>
  {#if tip}
    <div class="tip" class:flip={tip.flip} style:left="{tip.x + shift.x}px" style:top="{tip.y + shift.y}px" role="tooltip">
      <span class="kind">{tip.kind}</span>
      <b class="title">{tip.title}</b>
      {#if tip.rows.length}
        <dl>
          {#each tip.rows as r, i (i)}
            {#if r.k}<dt>{r.k}</dt><dd class="num">{r.v}</dd>{:else}<dd class="wide">{r.v}</dd>{/if}
          {/each}
        </dl>
      {/if}
    </div>
  {/if}
</div>

<style>
  .field-overlay {
    position: absolute;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
  }
  svg,
  canvas {
    position: absolute;
    inset: 0;
    overflow: visible;
  }
  canvas.lost {
    opacity: 0.35;
  }
  path,
  polyline {
    fill: none;
    stroke-width: 1.5;
    stroke-linejoin: round;
  }
  /* Catalogue layers (04 2.4): shapes match the layer icons; 1 px at fit zoom. */
  .fine .layer {
    stroke-width: 1;
  }
  .layer.stars {
    stroke: var(--overlay-field-star);
    stroke-width: 1;
  }
  .layer.variables,
  .layer.suspected {
    stroke: var(--overlay-variable);
  }
  .layer.suspected,
  .layer.hot.suspected {
    stroke-dasharray: 4 3;
  }
  .layer.galaxies {
    stroke: var(--overlay-galaxy);
  }
  .layer.nebulae_clusters {
    stroke: var(--overlay-nebula);
  }
  .layer.exoplanets {
    stroke: var(--overlay-exoplanet);
  }
  .layer.other_objects {
    stroke: var(--overlay-other);
  }
  .layer.vsp {
    stroke: var(--role-comparison);
  }
  /* The target set: 2.5 px, role colour AND shape (Night Red collapses the hues). */
  .role {
    stroke-width: 2.5;
  }
  .role.target {
    stroke: var(--role-target);
  }
  .role.comparison {
    stroke: var(--role-comparison);
  }
  .role.check {
    stroke: var(--role-check);
  }
  /* Hover: the marker's own stroke +1 px at once (BRAND 7). */
  .hot,
  .fine .layer.hot {
    stroke-width: 2.5;
  }
  .layer.hot.stars,
  .fine .layer.hot.stars {
    stroke-width: 2;
  }
  .role.hot {
    stroke-width: 3.5;
  }
  .reticle {
    stroke: var(--role-target);
    stroke-width: 1.5;
    stroke-linecap: round;
  }
  /* Tracking lost: what the reference solve places is where the field WAS. */
  .lost .ref {
    opacity: 0.35;
  }
  /* What a list row hovers: corner brackets in the foreground ink over a black halo. */
  .list-mark {
    stroke: var(--chart-highlight);
    stroke-width: 1.5;
    stroke-linecap: square;
  }
  .halo {
    stroke: var(--viewer-bg);
    stroke-width: 3.5;
  }
  /* Brass = the selected object (BRAND 3): a viewfinder, never the target's circle. */
  .selection {
    stroke: var(--accent);
    stroke-width: 2;
    stroke-linecap: square;
  }
  .selection.halo {
    stroke: var(--viewer-bg);
    stroke-width: 4;
  }
  /* 1 px dotted, butt caps (round caps cost as much to rasterise as the markers). */
  .grid polyline {
    stroke: var(--overlay-grid);
    stroke-width: 1;
    stroke-dasharray: 1 3;
  }
  /* Labels: Plex Mono 11 px, a 1 px black halo (BRAND 11); the set in --fg, the catalogue
     in --text-muted (text tokens, BRAND 10). */
  .label,
  .grid-label {
    font-family: var(--font-mono);
    font-size: 11px;
    fill: var(--text-muted);
    paint-order: stroke;
    stroke: var(--viewer-bg);
    stroke-width: 2px;
    stroke-linejoin: round;
  }
  .label.set,
  .grid-label {
    fill: var(--overlay-label);
  }
  .tip {
    position: absolute;
    min-width: 180px;
    max-width: 300px;
    padding: var(--space-2) var(--space-3);
    transform: translate(16px, -50%);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    box-shadow: var(--shadow-2);
    color: var(--fg);
    font-size: var(--text-xs);
    line-height: 1.4;
  }
  .tip.flip {
    transform: translate(calc(-100% - 16px), -50%);
  }
  .kind {
    display: block;
    color: var(--text-muted);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .title {
    display: block;
    font-family: var(--font-mono);
    font-weight: var(--weight-medium);
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0 var(--space-2);
    margin: var(--space-1) 0 0;
  }
  dt {
    color: var(--text-muted);
    white-space: nowrap;
  }
  dd {
    margin: 0;
    font-family: var(--font-mono);
    white-space: nowrap;
  }
  dd.wide {
    grid-column: 1 / -1;
    color: var(--text-muted);
    font-family: inherit;
    white-space: normal;
  }
</style>
