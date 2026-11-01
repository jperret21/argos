<!--
  The image as the hero: the app's real FitsViewer (WebGL2, GPU stretch,
  auto rotation of the portrait frame, pan / zoom, pixel readout) with the
  workspace HUD over it, all in SCREEN space so labels and the check-star
  triangle stay upright whatever the display rotation:

  - top left: what the frame is (LIVE / REC, number, exposure, filter,
    object, time); top right: the field state and a compass (N, E from the
    plate solution, turned with the display);
  - bottom left: scale bar in arcminutes (from the plate scale and zoom);
  - bottom right: cursor readout (pixel, ADU, RA / Dec when solved) and a
    mini histogram with the display levels (brass: they are the levels);
  - role markers (circle / square / triangle, BRAND 6), candidates, the
    hovered row's star and the selection ring (brass: selection);
  - region statistics (R, drag a box), the compact star card (click a star),
    the mode suggestion chip and the live cost of a layout drag.

  Chips are opaque token surfaces (no blur, no translucency: BRAND 9).
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import FitsViewer from '../../../lib/viewer/FitsViewer.svelte';
  import { binHistogram } from '../../../lib/viewer/histogram';
  import { frameToDisplay } from '../../../lib/viewer/rotation';
  import type { DisplayInfo, PointerInfo } from '../../../lib/viewer/types';
  import { rgb01 } from '../../research/tokens';
  import Spark from '../charts/Spark.svelte';
  import { env } from '../model/env.svelte';
  import {
    APERTURE_PX,
    FRAME_H,
    FRAME_W,
    NAMED_STARS,
    PLATE_SCALE,
    ROTATION_DEG,
    STARS,
    TARGET_PX,
    pickStar,
    pixelToSky,
    skyAxes,
    skyToPixel,
    type Star,
  } from '../model/field';
  import { arcmin, fixed, formatDec, formatRA, int, utc } from '../model/format';
  import { MODES } from '../model/layout';
  import { RUN } from '../model/night';
  import { sim, ws } from '../model/app.svelte';
  import StarCard from './StarCard.svelte';

  let fv: ReturnType<typeof FitsViewer> | undefined = $state();
  let stage: HTMLDivElement;
  let rect = $state({ left: 0, top: 0, width: 0, height: 0 });
  let stageSize = $state({ w: 0, h: 0 });
  let pointer: PointerInfo | null = $state(null);
  let display: DisplayInfo | null = $state.raw(null);
  let tint: [number, number, number] = $state([1, 1, 1]);
  let region: { x0: number; y0: number; x1: number; y1: number; done: boolean } | null = $state(null);

  $effect(() => {
    void env.theme;
    const css = getComputedStyle(document.documentElement).getPropertyValue('--viewer-tint').trim();
    tint = rgb01(css || '#ffffff');
  });

  $effect(() => {
    if (!fv) return;
    const api = fv;
    ws.viewer = { fit: () => api.fit(), oneToOne: () => api.oneToOne(), zoomBy: (f) => api.zoomBy(f) };
    return () => (ws.viewer = null);
  });

  // -- Frame <-> screen (display rotation: the portrait frame turns 90° cw) ------------

  const K = 1 as const;
  const DISP_W = FRAME_H;
  const s = $derived(rect.width > 0 ? rect.width / DISP_W : 0);

  function toScreen(x: number, y: number): { x: number; y: number } {
    const d = frameToDisplay(x, y, FRAME_W, FRAME_H, K);
    return { x: rect.left + (d.u + 0.5) * s, y: rect.top + (d.v + 0.5) * s };
  }
  function fromScreen(sx: number, sy: number): { x: number; y: number } {
    const u = (sx - rect.left) / s - 0.5;
    const v = (sy - rect.top) / s - 0.5;
    return { x: v, y: FRAME_H - 1 - u }; // inverse of k = 1, continuous
  }
  /** A frame-pixel vector turned like the display (k = 1: (dx, dy) -> (-dy, dx)). */
  const turn = (dx: number, dy: number) => ({ x: -dy, y: dx });

  // -- What to draw ------------------------------------------------------------------

  const solved = $derived(sim.solved || sim.inRun);
  const showRoles = $derived(solved && ws.mode !== 'focus');
  const r = $derived(Math.max(7, APERTURE_PX * s));

  interface Mark {
    star: Star;
    x: number;
    y: number;
    kind: 'target' | 'comparison' | 'check' | 'candidate';
  }
  const marks: Mark[] = $derived.by(() => {
    if (!showRoles || s <= 0) return [];
    void rect;
    return NAMED_STARS.filter((st) => st.role || ws.mode === 'field').map((st) => {
      const p = toScreen(st.x, st.y);
      return { star: st, x: p.x, y: p.y, kind: st.role ?? 'candidate' };
    });
  });

  function shortName(st: Star): string {
    if (st.role === 'target') return st.name ?? '';
    const id = st.name?.slice(-3) ?? '';
    return ws.mode === 'field' ? (st.name ?? '') : st.role === 'check' ? `${id} chk` : id;
  }

  /** Focus mode: HFD rings on the brightest measured stars. */
  const hfdRings = $derived.by(() => {
    if (ws.mode !== 'focus' || s <= 0) return [];
    void rect;
    const hfd = sim.afRunning ? (sim.af.steps[Math.max(0, sim.afStep - 1)]?.hfd ?? 6) : sim.inRun ? (sim.latest?.hfd ?? 6.3) : 6.3;
    return STARS.filter((st) => st.v < 9.6)
      .slice(0, 14)
      .map((st, i) => {
        const p = toScreen(st.x, st.y);
        return { x: p.x, y: p.y, r: Math.max(5, (hfd * s) / 2 + 4), hfd: hfd * (0.96 + ((i * 37) % 9) / 100) };
      });
  });

  /** RA / Dec graticule from the plate solution. */
  const grid = $derived.by(() => {
    if (!ws.grid || !solved || s <= 0) return { lines: [] as string[], labels: [] as { x: number; y: number; t: string }[] };
    void rect;
    const corners = [pixelToSky(0, 0), pixelToSky(FRAME_W, 0), pixelToSky(0, FRAME_H), pixelToSky(FRAME_W, FRAME_H)];
    const ras = corners.map((c) => c.ra);
    const decs = corners.map((c) => c.dec);
    const [ra0, ra1] = [Math.min(...ras), Math.max(...ras)];
    const [de0, de1] = [Math.min(...decs), Math.max(...decs)];
    const lines: string[] = [];
    const labels: { x: number; y: number; t: string }[] = [];
    const decStep = 10 / 60;
    for (let d = Math.ceil(de0 / decStep) * decStep; d <= de1; d += decStep) {
      const pts: string[] = [];
      for (let k = 0; k <= 24; k++) {
        const p = skyToPixel(ra0 + ((ra1 - ra0) * k) / 24, d);
        const q = toScreen(p.x, p.y);
        pts.push(`${q.x.toFixed(1)},${q.y.toFixed(1)}`);
      }
      lines.push(pts.join(' '));
      const e = skyToPixel(ra1, d);
      const q = toScreen(e.x, e.y);
      labels.push({ x: q.x, y: q.y, t: formatDec(d).slice(0, 8) });
    }
    const raStep = 1 / 60;
    for (let a = Math.ceil(ra0 / raStep) * raStep; a <= ra1; a += raStep) {
      const pts: string[] = [];
      for (let k = 0; k <= 24; k++) {
        const p = skyToPixel(a, de0 + ((de1 - de0) * k) / 24);
        const q = toScreen(p.x, p.y);
        pts.push(`${q.x.toFixed(1)},${q.y.toFixed(1)}`);
      }
      lines.push(pts.join(' '));
    }
    return { lines, labels };
  });

  // -- HUD ----------------------------------------------------------------------------

  // With ?frames=server the chips describe the server's frame (its header).
  const server = $derived(sim.source === 'server' && sim.frame ? sim.frame.header : null);
  const frameNo = $derived(server ? server.seq : sim.inRun ? (sim.latest?.n ?? 0) : sim.liveSeq);
  const frameTime = $derived(server ? Date.parse(server.timestamp) / 1000 : sim.inRun ? (sim.latest?.t ?? sim.now) : sim.now);
  const exposure = $derived(server ? server.exposure_s : sim.inRun ? RUN.exposure : 2);

  const compass = $derived.by(() => {
    const a = skyAxes();
    const n = turn(a.north[0], a.north[1]);
    const e = turn(a.east[0], a.east[1]);
    const L = 22;
    return { nx: n.x * L, ny: n.y * L, ex: e.x * L, ey: e.y * L };
  });

  const scaleBar = $derived.by(() => {
    if (s <= 0) return null;
    const pxPerArcmin = (60 / PLATE_SCALE) * s;
    const choices = [0.5, 1, 2, 5, 10, 15, 20, 30];
    const m = choices.find((c) => c * pxPerArcmin >= 56) ?? 30;
    return { px: m * pxPerArcmin, label: m < 1 ? `${m * 60}″` : `${m}′` };
  });

  const cursor = $derived.by(() => {
    if (!pointer) return null;
    const sky = solved ? pixelToSky(pointer.x, pointer.y) : null;
    return { ...pointer, sky };
  });

  const mini = $derived.by(() => {
    if (!display) return null;
    const b = binHistogram(display.histogram, 64);
    const lv = ws.autoStretch || !ws.stretch ? display.auto : ws.stretch;
    const f = (v: number) => (v - b.lo) / (b.hi - b.lo);
    return { counts: b.counts, marks: [f(lv.black), f(lv.white)] };
  });

  const selectedStar = $derived(ws.selected !== null ? (STARS.find((st) => st.id === ws.selected) ?? null) : null);
  const selectedPos = $derived(selectedStar && s > 0 ? (void rect, toScreen(selectedStar.x, selectedStar.y)) : null);

  const targetOffset = $derived(Math.hypot(TARGET_PX.x - (FRAME_W - 1) / 2, TARGET_PX.y - (FRAME_H - 1) / 2) * PLATE_SCALE / 60);

  // -- Pointer: click to select, R to measure a region ------------------------------------

  let downAt: { x: number; y: number } | null = null;

  function local(e: PointerEvent): { x: number; y: number } {
    const b = stage.getBoundingClientRect();
    return { x: e.clientX - b.left, y: e.clientY - b.top };
  }

  function onDownCapture(e: PointerEvent): void {
    if (e.button !== 0) return;
    const p = local(e);
    downAt = p;
    if (ws.tool === 'region') {
      e.stopPropagation(); // the viewer must not pan while a region is drawn
      e.preventDefault();
      stage.setPointerCapture(e.pointerId);
      region = { x0: p.x, y0: p.y, x1: p.x, y1: p.y, done: false };
    }
  }
  function onMove(e: PointerEvent): void {
    if (region && !region.done) {
      const p = local(e);
      region = { ...region, x1: p.x, y1: p.y };
    }
  }
  function onUp(e: PointerEvent): void {
    const p = local(e);
    if (region && !region.done) {
      region = Math.abs(region.x1 - region.x0) > 4 ? { ...region, done: true } : null;
      if (stage.hasPointerCapture(e.pointerId)) stage.releasePointerCapture(e.pointerId);
      return;
    }
    if (!downAt || Math.hypot(p.x - downAt.x, p.y - downAt.y) > 4 || s <= 0) return;
    const f = fromScreen(p.x, p.y);
    const st = pickStar(f.x, f.y, 18 / s);
    ws.select(st && (st.name || st.v < 11) ? st.id : null);
  }

  const regionStats = $derived.by(() => {
    if (!region?.done || !sim.frame || s <= 0) return null;
    const a = fromScreen(Math.min(region.x0, region.x1), Math.min(region.y0, region.y1));
    const b = fromScreen(Math.max(region.x0, region.x1), Math.max(region.y0, region.y1));
    const x0 = Math.max(0, Math.round(Math.min(a.x, b.x)));
    const x1 = Math.min(FRAME_W - 1, Math.round(Math.max(a.x, b.x)));
    const y0 = Math.max(0, Math.round(Math.min(a.y, b.y)));
    const y1 = Math.min(FRAME_H - 1, Math.round(Math.max(a.y, b.y)));
    const px = sim.frame.pixels;
    const vals: number[] = [];
    let sum = 0;
    let max = 0;
    let clipped = 0;
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        const v = px[y * FRAME_W + x];
        vals.push(v);
        sum += v;
        if (v > max) max = v;
        if (v >= 65535) clipped++;
      }
    }
    if (!vals.length) return null;
    vals.sort((p, q) => p - q);
    const n = vals.length;
    const mean = sum / n;
    let sq = 0;
    for (const v of vals) sq += (v - mean) ** 2;
    return { w: x1 - x0 + 1, h: y1 - y0 + 1, median: vals[n >> 1], mean, sd: Math.sqrt(sq / Math.max(1, n - 1)), max, clipped };
  });

  $effect(() => {
    if (ws.tool !== 'region') region = null;
  });
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="stage"
  class:region-tool={ws.tool === 'region'}
  bind:this={stage}
  bind:clientWidth={stageSize.w}
  bind:clientHeight={stageSize.h}
  onpointerdowncapture={onDownCapture}
  onpointermove={onMove}
  onpointerup={onUp}
>
  <FitsViewer
    bind:this={fv}
    frame={sim.frame}
    autoStretch={ws.autoStretch}
    stretch={ws.stretch}
    nightTint={env.theme === 'night-red'}
    {tint}
    rotation="auto"
    fitMode={ws.fitMode}
    crosshair={ws.crosshair}
    label="Live image"
    onpointer={(p) => (pointer = p)}
    ondisplay={(d) => {
      display = d;
      ws.display = d;
    }}
    onzoom={(z) => (ws.zoom = z)}
    onrect={(rc) => (rect = rc)}
  />

  <svg class="marks" width={stageSize.w} height={stageSize.h} aria-hidden="true">
    {#if grid.lines.length}
      <g class="grid">
        {#each grid.lines as pts, i (i)}<polyline points={pts} />{/each}
      </g>
      {#each grid.labels as l, i (i)}
        <text class="grid-label" x={Math.min(l.x, stageSize.w - 4)} y={l.y - 3} text-anchor="end">{l.t}</text>
      {/each}
    {/if}
    {#each hfdRings as h, i (i)}
      <circle class="hfd" cx={h.x} cy={h.y} r={h.r} />
      <text class="label small" x={h.x + h.r + 3} y={h.y + 3}>{fixed(h.hfd, 1)}</text>
    {/each}
    {#each marks as m (m.star.id)}
      {@const hov = ws.hovered === m.star.id}
      <g class="mark {m.kind}" class:hov>
        {#if m.kind === 'target'}
          <circle cx={m.x} cy={m.y} {r} />
        {:else if m.kind === 'comparison' || m.kind === 'candidate'}
          <rect x={m.x - r * 0.886} y={m.y - r * 0.886} width={r * 1.772} height={r * 1.772} />
        {:else}
          {@const t = r * 1.347}
          <polygon points="{m.x},{m.y - t} {m.x + t * 0.866},{m.y + t * 0.5} {m.x - t * 0.866},{m.y + t * 0.5}" />
        {/if}
        {#if hov}<circle class="hover-ring" cx={m.x} cy={m.y} r={r + 7} />{/if}
        {#if ws.labels && (m.kind !== 'candidate' || hov)}
          <text class="label" x={m.x + r + 5} y={m.y - r * 0.4}>{shortName(m.star)}</text>
        {/if}
      </g>
    {/each}
    {#if selectedPos}
      <circle class="selected" cx={selectedPos.x} cy={selectedPos.y} r={r + 7} />
    {/if}
    {#if region}
      <rect
        class="region"
        x={Math.min(region.x0, region.x1)}
        y={Math.min(region.y0, region.y1)}
        width={Math.abs(region.x1 - region.x0)}
        height={Math.abs(region.y1 - region.y0)}
      />
    {/if}
  </svg>

  <!-- HUD: top left, what this frame is -->
  <div class="hud tl">
    {#if sim.inRun}
      <span class="chip strong"><span class="dot rec" class:held={!sim.running}></span>{sim.running ? 'REC' : sim.runState === 'complete' ? 'DONE' : 'PAUSED'}</span>
    {:else if sim.live}
      <span class="chip strong"><span class="dot live"></span>LIVE</span>
    {:else}
      <span class="chip strong">SHOT</span>
    {/if}
    <span class="chip num">#{frameNo}</span>
    <span class="chip num">{fixed(exposure, 1)} s</span>
    {#if server}
      <span class="chip">{server.source}</span>
    {:else}
      <span class="chip">IR</span>
      <span class="chip">RR Lyr</span>
    {/if}
    <span class="chip num muted">{utc(frameTime)} UTC</span>
    {#if ws.fitMode === 'fill'}<span class="chip">Fill · cropped</span>{/if}
  </div>

  <!-- HUD: top right, field state and orientation -->
  <div class="hud tr">
    {#if solved}
      <span class="chip"><Icon name="plate-solve" size={14} />Field identified</span>
      <span class="chip num">{PLATE_SCALE}″/px</span>
      <span class="chip num">rot {fixed(ROTATION_DEG, 1)}°</span>
      <span class="chip num">target {arcmin(targetOffset)}</span>
    {:else}
      <span class="chip muted"><Icon name="plate-solve" size={14} />Field not identified · S</span>
    {/if}
  </div>
  {#if solved}
    <svg class="compass" width="64" height="64" viewBox="-32 -32 64 64" role="img" aria-label="North and east on the image">
      <circle r="3" class="hub" />
      <line x1="0" y1="0" x2={compass.nx} y2={compass.ny} class="arm n" />
      <line x1="0" y1="0" x2={compass.ex} y2={compass.ey} class="arm" />
      <text x={compass.nx * 1.36} y={compass.ny * 1.36 + 4} text-anchor="middle">N</text>
      <text x={compass.ex * 1.36} y={compass.ey * 1.36 + 4} text-anchor="middle">E</text>
    </svg>
  {/if}

  <!-- HUD: bottom left, scale -->
  {#if scaleBar && solved}
    <div class="hud bl">
      <svg width={scaleBar.px + 2} height="10" aria-hidden="true">
        <path class="bar" d="M1 1V9M1 5H{scaleBar.px + 1}M{scaleBar.px + 1} 1V9" />
      </svg>
      <span class="chip num">{scaleBar.label}</span>
    </div>
  {/if}

  <!-- HUD: bottom right, cursor and histogram -->
  <div class="hud br">
    <div class="readout num" aria-live="off">
      {#if cursor}
        <span><b>X</b>{cursor.x}</span><span><b>Y</b>{cursor.y}</span>
        <span><b>ADU</b>{typeof cursor.value === 'number' ? int(cursor.value) : '—'}</span>
        {#if cursor.sky}
          <span class="sky"><b>RA</b>{formatRA(cursor.sky.ra)}</span>
          <span class="sky"><b>Dec</b>{formatDec(cursor.sky.dec)}</span>
        {/if}
      {:else}
        <span class="muted">Point at the image for pixel, ADU{solved ? ', RA and Dec' : ''}</span>
      {/if}
    </div>
    {#if mini}
      <div class="hist">
        <Spark values={mini.counts} kind="hist" marks={mini.marks} height={26} label="Histogram of this frame with the display levels" />
      </div>
    {/if}
  </div>

  {#if regionStats && region}
    {@const rx = Math.min(Math.max(region.x0, region.x1) + 8, stageSize.w - 260)}
    {@const ry = Math.max(8, Math.min(region.y0, region.y1))}
    <div class="region-chip num" style:left="{rx}px" style:top="{ry}px">
      <div class="rh"><Icon name="region-stats" size={14} /> Region {regionStats.w} × {regionStats.h} px</div>
      <div><b>median</b>{int(regionStats.median)} <b>mean</b>{int(regionStats.mean)}</div>
      <div><b>σ</b>{fixed(regionStats.sd, 1)} <b>max</b>{int(regionStats.max)} <b>clipped</b>{regionStats.clipped}</div>
    </div>
  {:else if ws.tool === 'region' && !region}
    <div class="hud bc"><span class="chip"><Icon name="region-stats" size={14} />Drag a box to measure · Esc ends</span></div>
  {/if}

  {#if selectedStar && selectedPos}
    <StarCard star={selectedStar} x={selectedPos.x} y={selectedPos.y} r={r} bounds={stageSize} />
  {/if}

  {#if ws.dragReadout}
    <div class="hud tc"><span class="chip num strong-chip">{ws.dragReadout}</span></div>
  {/if}
  {#if ws.suggestion}
    {@const m = MODES.find((x) => x.id === ws.suggestion?.mode)}
    <div class="hud bc">
      <span class="chip suggestion">
        {ws.suggestion.text}
        <button type="button" onclick={() => m && ws.setMode(m.id)}><Icon name={m?.icon ?? 'goto'} size={14} />{m?.label} view <kbd class="key">{m?.key.replace('Alt+', '⌥')}</kbd></button>
        <button type="button" class="x" aria-label="Dismiss" onclick={() => (ws.suggestion = null)}><Icon name="close" size={14} /></button>
      </span>
    </div>
  {/if}
</div>

<style>
  .stage {
    position: absolute;
    inset: 0;
    overflow: hidden;
    background: var(--viewer-bg);
  }
  .region-tool {
    cursor: crosshair;
  }
  .marks {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }
  .mark circle,
  .mark rect,
  .mark polygon {
    fill: none;
    stroke-width: 1.5;
  }
  .mark.target circle {
    stroke: var(--role-target);
  }
  .mark.comparison rect {
    stroke: var(--role-comparison);
  }
  .mark.check polygon {
    stroke: var(--role-check);
  }
  .mark.candidate rect {
    stroke: var(--overlay-other);
    stroke-dasharray: 3 3;
  }
  .hover-ring {
    stroke: var(--chart-highlight) !important;
    stroke-width: 1.5;
    stroke-dasharray: 2 3;
  }
  .selected {
    fill: none;
    stroke: var(--accent);
    stroke-width: 2;
  }
  .hfd {
    fill: none;
    stroke: var(--overlay-other);
    stroke-width: 1;
  }
  /* Labels: Plex Mono 11 px, --overlay-label with a 1 px black halo (BRAND 11). */
  .label,
  .grid-label,
  .compass text {
    font-family: var(--font-mono);
    font-size: 11px;
    fill: var(--overlay-label);
    paint-order: stroke;
    stroke: var(--viewer-bg);
    stroke-width: 3px;
    stroke-linejoin: round;
  }
  .label.small,
  .grid-label {
    font-size: 10px;
  }
  .grid polyline {
    fill: none;
    stroke: var(--overlay-grid);
    stroke-width: 1;
    opacity: 0.55;
  }
  .grid-label {
    fill: var(--overlay-grid);
  }
  .region {
    fill: none;
    stroke: var(--fg);
    stroke-width: 1;
    stroke-dasharray: 4 3;
  }

  .hud {
    position: absolute;
    display: flex;
    align-items: center;
    gap: var(--space-1);
    pointer-events: none;
  }
  .hud > * {
    pointer-events: auto;
  }
  .tl {
    top: var(--space-2);
    left: var(--space-2);
  }
  .tr {
    top: var(--space-2);
    right: var(--space-2);
  }
  .bl {
    bottom: var(--space-2);
    left: var(--space-3);
    gap: var(--space-2);
  }
  .br {
    bottom: var(--space-2);
    right: var(--space-2);
    align-items: stretch;
    gap: 0;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    box-shadow: var(--lab-elev-hud);
  }
  .bc {
    bottom: var(--space-3);
    left: 50%;
    transform: translateX(-50%);
  }
  .tc {
    top: 40px;
    left: 50%;
    transform: translateX(-50%);
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 20px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    white-space: nowrap;
    box-shadow: var(--lab-elev-hud);
  }
  .chip :global(.icon) {
    color: var(--fg-muted);
  }
  .chip.num,
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .chip.strong {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
  }
  .muted {
    color: var(--text-muted);
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: var(--radius-round);
  }
  .dot.live {
    background: var(--accent);
  }
  .dot.rec {
    background: var(--danger);
  }
  .dot.rec.held {
    border-radius: 1px;
    background: var(--fg-muted);
  }

  .compass {
    position: absolute;
    top: 34px;
    right: var(--space-2);
    overflow: visible;
    pointer-events: none;
  }
  .compass .arm {
    stroke: var(--overlay-label);
    stroke-width: 1.5;
    stroke-linecap: round;
  }
  .compass .arm.n {
    stroke-width: 2;
  }
  .compass .hub {
    fill: var(--overlay-label);
  }
  .compass text {
    font-size: 10px;
    font-weight: 500;
  }

  .bar {
    fill: none;
    stroke: var(--overlay-label);
    stroke-width: 1.5;
    filter: drop-shadow(0 0 1px var(--viewer-bg));
  }

  .readout {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 34px;
    padding: 0 var(--space-3);
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .readout b {
    margin-right: var(--space-1);
    color: var(--text-muted);
    font-weight: var(--weight-medium);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
  }
  .readout .muted {
    font-family: var(--font-ui);
  }
  .hist {
    width: 132px;
    padding: 4px 6px;
    border-left: var(--border-w) solid var(--border-soft);
  }

  .region-chip {
    position: absolute;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--space-2) var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-xs);
    box-shadow: var(--lab-elev-float);
  }
  .region-chip b {
    margin: 0 var(--space-1) 0 var(--space-2);
    color: var(--text-muted);
    font-weight: var(--weight-medium);
  }
  .region-chip b:first-child {
    margin-left: 0;
  }
  .rh {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    font-family: var(--font-ui);
    font-weight: var(--weight-medium);
  }

  .strong-chip {
    height: 26px;
    padding: 0 var(--space-3);
    border-color: var(--border);
    font-size: var(--text-s);
  }
  .suggestion {
    height: 30px;
    padding: 0 var(--space-1) 0 var(--space-3);
    border-color: var(--border);
    font-size: var(--text-s);
    gap: var(--space-2);
  }
  .suggestion button {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 24px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--surface);
    color: var(--fg);
    font-size: var(--text-s);
    cursor: pointer;
  }
  .suggestion button.x {
    border-color: transparent;
    background: transparent;
  }
</style>
