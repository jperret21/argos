<!--
  Region statistics tool (web/spec/04-viewer-and-image-tools.md 2.1 E5, 2.2 rows 1.1 #9-10
  and 1.5 #10, 2.4; Qt RectROI fits_viewer.py:386-414): a box over the image whose pixels
  are measured on the frame's own RAW samples (tools/region.ts), with the result in a chip
  beside the box (Mean · σ · N) and in the Statistics card's Region block.

  A screen-space layer over the viewer (sibling of the HUD and the field overlay), placed
  from FitsViewer's geometry, so the box stays a frame-aligned rectangle under any display
  rotation and its edges stay crisp at any zoom.
  - Drag inside the box: move it. Four corner handles resize it.
  - Shift + drag on the image: draw a new box (the viewer does not pan).
  - Arrow keys while the box has focus: move it 1 frame px (Shift: 10), in the direction
    of the arrow on screen; never the mount (the jog ignores a handled key).
  - The box is the region tool's own state: R toggles it, its place is remembered.
  Brass: the box is the selected measurement (04 2.1 "region box --accent"); handles and
  chip are neutral.
-->
<script lang="ts">
  import { fixed, int } from '../../format/number';
  import { frameRectToScreen, moveRect, screenRectToFrame, screenToFrame, type FrameRect, type ScreenRect, type ViewerGeometry } from './geometry';
  import type { ViewerTools } from './tools.svelte';

  interface Props {
    tools: ViewerTools;
    geometry: ViewerGeometry | null;
    /** The stage width and height (where the chip may go). */
    stage: { width: number; height: number };
    /** No drawing gestures (a gallery still). */
    interactive?: boolean;
  }

  let { tools, geometry, stage, interactive = true }: Props = $props();

  let root: SVGSVGElement | undefined = $state();
  /** A box being drawn with Shift + drag (screen px). */
  let drawing: ScreenRect | null = $state.raw(null);

  const rect = $derived(tools.region ? tools.regionRect : null);
  const box = $derived(geometry && rect ? frameRectToScreen(geometry, rect) : null);
  const shownBox = $derived(drawing ?? box);
  const stats = $derived(tools.regionResult);

  /** Frame delta for a screen move of (sx, sy) CSS px, rounded to whole pixels. */
  function frameDelta(g: ViewerGeometry, sx: number, sy: number): { dx: number; dy: number } {
    const a = screenToFrame(g, 0, 0);
    const b = screenToFrame(g, sx, sy);
    return { dx: Math.round(b.x - a.x), dy: Math.round(b.y - a.y) };
  }

  function local(e: PointerEvent): { x: number; y: number } {
    const b = root!.getBoundingClientRect();
    return { x: e.clientX - b.left, y: e.clientY - b.top };
  }

  // -- Move and resize ------------------------------------------------------------------
  type Grab = { id: number; kind: 'move' | 'corner'; start: { x: number; y: number }; rect: FrameRect; fixed?: { x: number; y: number } };
  let grab: Grab | null = null;

  function startMove(e: PointerEvent): void {
    if (!geometry || !rect || e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    grab = { id: e.pointerId, kind: 'move', start: local(e), rect };
  }

  function startCorner(e: PointerEvent, cx: number, cy: number): void {
    if (!geometry || !rect || !box || e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    // The opposite corner stays where it is on screen.
    const fixed = { x: cx ? box.left : box.left + box.width, y: cy ? box.top : box.top + box.height };
    grab = { id: e.pointerId, kind: 'corner', start: local(e), rect, fixed };
  }

  function onMove(e: PointerEvent): void {
    const g = grab;
    if (!g || e.pointerId !== g.id || !geometry) return;
    const p = local(e);
    if (g.kind === 'move') {
      const d = frameDelta(geometry, p.x - g.start.x, p.y - g.start.y);
      tools.setRegionRect(moveRect(g.rect, d.dx, d.dy, geometry.frame));
    } else if (g.fixed) {
      const r = screenRectToFrame(geometry, {
        left: Math.min(g.fixed.x, p.x),
        top: Math.min(g.fixed.y, p.y),
        width: Math.abs(p.x - g.fixed.x),
        height: Math.abs(p.y - g.fixed.y),
      });
      if (r.x1 - r.x0 >= 2 && r.y1 - r.y0 >= 2) tools.setRegionRect(r);
    }
  }

  /** The box sits over the image: the wheel still zooms the viewer under it. */
  function forwardWheel(e: WheelEvent): void {
    const viewer = root?.parentElement?.querySelector<HTMLElement>('[role="application"]');
    if (!viewer) return;
    e.preventDefault();
    viewer.dispatchEvent(new WheelEvent('wheel', e));
  }

  function onUp(e: PointerEvent): void {
    if (grab && e.pointerId === grab.id) grab = null;
  }

  function onKey(e: KeyboardEvent): void {
    if (!geometry || !rect) return;
    const step = e.shiftKey ? 10 : 1;
    const dir: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    const d = dir[e.key];
    if (!d || e.altKey || e.ctrlKey || e.metaKey) return;
    // Handled here: neither the viewer's pan nor the keyboard jog takes this key.
    e.preventDefault();
    e.stopPropagation();
    const s = geometry.view.scale;
    const f = frameDelta(geometry, d[0] * s, d[1] * s);
    tools.setRegionRect(moveRect(rect, f.dx * step, f.dy * step, geometry.frame));
  }

  // -- Shift + drag on the image draws a new box (capture phase: the viewer never pans) --
  $effect(() => {
    const host = root?.parentElement;
    if (!host || !interactive || !tools.region) return;
    let start: { id: number; x: number; y: number } | null = null;
    const onImage = (e: Event) => !!(e.target as Element | null)?.closest?.('[role="application"]');
    const down = (e: PointerEvent) => {
      if (e.button !== 0 || !e.shiftKey || !onImage(e) || !geometry) return;
      e.stopPropagation();
      e.preventDefault();
      host.setPointerCapture(e.pointerId);
      const p = local(e);
      start = { id: e.pointerId, ...p };
      drawing = { left: p.x, top: p.y, width: 0, height: 0 };
    };
    const move = (e: PointerEvent) => {
      if (!start || e.pointerId !== start.id) return;
      e.stopPropagation();
      const p = local(e);
      drawing = { left: Math.min(start.x, p.x), top: Math.min(start.y, p.y), width: Math.abs(p.x - start.x), height: Math.abs(p.y - start.y) };
    };
    const up = (e: PointerEvent) => {
      if (!start || e.pointerId !== start.id) return;
      e.stopPropagation();
      if (host.hasPointerCapture(e.pointerId)) host.releasePointerCapture(e.pointerId);
      const d = drawing;
      start = null;
      drawing = null;
      if (!d || !geometry) return;
      const r = screenRectToFrame(geometry, d);
      if (r.x1 - r.x0 >= 2 && r.y1 - r.y0 >= 2) tools.setRegionRect(r);
    };
    host.addEventListener('pointerdown', down, true);
    host.addEventListener('pointermove', move, true);
    host.addEventListener('pointerup', up, true);
    host.addEventListener('pointercancel', up, true);
    return () => {
      host.removeEventListener('pointerdown', down, true);
      host.removeEventListener('pointermove', move, true);
      host.removeEventListener('pointerup', up, true);
      host.removeEventListener('pointercancel', up, true);
    };
  });

  // The chip: to the right of the box, else to its left, else inside; never off the stage.
  const CHIP_W = 216;
  const chip = $derived.by(() => {
    const b = shownBox;
    if (!b || !stats || drawing) return null;
    let left = b.left + b.width + 8;
    if (left + CHIP_W > stage.width - 8) left = b.left - CHIP_W - 8;
    if (left < 8) left = Math.min(Math.max(8, b.left + 8), stage.width - CHIP_W - 8);
    const top = Math.min(Math.max(8, b.top), Math.max(8, stage.height - 56));
    return { left, top };
  });
  const H = 7; // handle side, CSS px
</script>

{#if tools.region}
  <svg class="region-layer" bind:this={root} width={stage.width} height={stage.height} data-region-tool>
    {#if shownBox}
      {@const b = shownBox}
      <!-- A focusable box that the arrow keys move (no ARIA role fits a movable rectangle);
           the pointer affordances below have this keyboard equivalent. -->
      <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
      <g
        class="box"
        class:drawing={!!drawing}
        role="group"
        tabindex={drawing ? -1 : 0}
        aria-label={rect ? `Region box x ${rect.x0}–${rect.x1 - 1}, y ${rect.y0}–${rect.y1 - 1}: drag to move, corners resize, arrow keys move it (Shift: 10 px)` : 'Region box'}
        onkeydown={onKey}
      >
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <rect class="hit" onwheel={forwardWheel} x={b.left} y={b.top} width={b.width} height={b.height} onpointerdown={startMove} onpointermove={onMove} onpointerup={onUp} onpointercancel={onUp} />
        <rect class="edge" x={Math.round(b.left) + 0.5} y={Math.round(b.top) + 0.5} width={Math.max(0, Math.round(b.width) - 1)} height={Math.max(0, Math.round(b.height) - 1)} />
        {#if !drawing}
          {#each [[0, 0], [1, 0], [0, 1], [1, 1]] as [cx, cy] (`${cx}${cy}`)}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <rect
              class="handle"
              class:nwse={cx === cy}
              x={Math.round(b.left + cx * b.width) - (H - 1) / 2 - 0.5}
              y={Math.round(b.top + cy * b.height) - (H - 1) / 2 - 0.5}
              width={H}
              height={H}
              onpointerdown={(e) => startCorner(e, cx, cy)}
              onpointermove={onMove}
              onpointerup={onUp}
              onpointercancel={onUp}
            />
          {/each}
        {/if}
      </g>
    {/if}
  </svg>
  {#if chip && stats}
    <div class="chip num" style:left="{chip.left}px" style:top="{chip.top}px" style:width="{CHIP_W}px" data-region-chip>
      <span><b>Mean</b>{fixed(stats.mean, 1, { group: true })}</span>
      <span><b>σ</b>{fixed(stats.std, 1, { group: true })}</span>
      <span><b>N</b>{int(stats.n)}</span>
    </div>
  {/if}
{/if}

<style>
  .region-layer {
    position: absolute;
    inset: 0;
    z-index: 2;
    overflow: visible;
    pointer-events: none;
  }
  .box {
    outline: none;
  }
  .hit {
    fill: transparent;
    pointer-events: all;
    cursor: move;
  }
  .edge {
    fill: none;
    stroke: var(--accent);
    stroke-width: 1.5;
    pointer-events: none;
  }
  .box.drawing .edge {
    stroke-dasharray: 4 3;
  }
  .box:focus-visible .edge {
    stroke: var(--focus-ring);
    stroke-width: 2;
  }
  .handle {
    fill: var(--bg-2);
    stroke: var(--fg-muted);
    stroke-width: 1;
    pointer-events: all;
    cursor: nesw-resize;
  }
  .handle.nwse {
    cursor: nwse-resize;
  }
  .chip {
    position: absolute;
    z-index: 2;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    height: 22px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    box-shadow: var(--elev-hud);
    color: var(--fg);
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
    font-size: var(--text-xs);
    white-space: nowrap;
    pointer-events: none;
  }
  .chip b {
    margin-right: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
  }
</style>
