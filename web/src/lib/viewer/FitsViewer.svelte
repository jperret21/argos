<!--
  Scientific image viewer: 16-bit frames on WebGL2, GPU stretch, pan/zoom.

  Display only: nothing here changes the data written to FITS. Row 0 of the
  frame is at the top, like the Qt viewer, and `rotation` turns the display
  like the Qt viewer's ROTATION_MODES ("auto": portrait frames 90° clockwise).
  Pointer readouts and overlays stay in un-rotated frame pixels. Frames arriving
  faster than the screen refreshes are coalesced: only the latest one is
  uploaded, measured and drawn.

  Imperative API (bind:this): fit(), oneToOne(), zoomBy(factor, at?), getZoom().
  Mouse: drag = pan, wheel = zoom around the cursor, double-click = fit.
  Keyboard: the viewer is a tab stop; arrow keys pan it (Shift: 10x steps).
  Arrows never move hardware (BRAND 7).

  `fitMode` says how "fit" frames the image: the whole frame ("fit"), or the
  viewer filled with the frame's long sides cropped ("fill"). Until the
  observer zooms or pans, the view re-frames itself on every resize.
-->
<script lang="ts">
  import { onMount, type Snippet } from 'svelte';
  import type { DecodedFrame } from '../api/frames';
  import { ImageRenderer } from './renderer';
  import {
    displaySize,
    displayToFrame,
    effectiveTurns,
    overlayMatrix,
    type RotationMode,
    type Turns,
  } from './rotation';
  import { autoStf, histogram16, NEUTRAL_STRETCH, type StretchParams } from './stretch';
  import type { DisplayInfo, OverlayContext, PointerInfo } from './types';
  import {
    clampPan,
    oneToOneView,
    scaleLimits,
    screenToImage,
    wheelZoomFactor,
    zoomAt,
    framedView,
    type FitMode,
    type Size,
    type ViewState,
  } from './view';

  interface Props {
    /** Frame to show; null clears the viewer. */
    frame?: DecodedFrame | null;
    /** Use auto_stf() levels of each frame (default) instead of `stretch`. */
    autoStretch?: boolean;
    /** Manual levels, used when autoStretch is false. */
    stretch?: StretchParams | null;
    /** Render the image in red only (Night Red theme). */
    nightTint?: boolean;
    /** Full-scale colour of a stretched pixel, 0..1 RGB (the --viewer-tint token). */
    tint?: readonly [number, number, number];
    /** Display rotation (default "auto": portrait frames turn landscape). */
    rotation?: RotationMode;
    /** How fit() frames the image: whole frame, or the viewer filled (cropped). */
    fitMode?: FitMode;
    /** Show a crosshair at the image centre. */
    crosshair?: boolean;
    /** Fence the GPU when timing uploads/draws (measurements only: it stalls). */
    syncTiming?: boolean;
    /** Accessible name of the viewer region. */
    label?: string;
    onpointer?: (info: PointerInfo | null) => void;
    /** Once per frame actually displayed: histogram, auto levels, timings. */
    ondisplay?: (info: DisplayInfo) => void;
    /** Zoom changed (device px per image px; 1 = 1:1). */
    onzoom?: (zoom: number) => void;
    /** The view became the framed one (true) or the observer's zoom/pan (false). */
    onfitted?: (fitted: boolean) => void;
    onerror?: (message: string) => void;
    /** Where the image sits in the viewer (CSS px, may extend past the edges). */
    onrect?: (rect: { left: number; top: number; width: number; height: number }) => void;
    /** Image-space SVG content (see OverlayContext for the coordinate convention). */
    overlay?: Snippet<[OverlayContext]>;
    /** Shown while there is no frame. */
    empty?: Snippet;
  }

  let {
    frame = null,
    autoStretch = true,
    stretch = null,
    nightTint = false,
    tint = [1, 1, 1],
    rotation = 'auto',
    fitMode = 'fit',
    crosshair = false,
    syncTiming = false,
    label = 'Image viewer',
    onpointer,
    ondisplay,
    onzoom,
    onfitted,
    onerror,
    onrect,
    overlay,
    empty,
  }: Props = $props();

  let container: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  let renderer: ImageRenderer | null = null;

  let viewport: Size = $state.raw({ width: 0, height: 0 });
  let dpr = $state(1);
  let view: ViewState = $state.raw({ scale: 1, tx: 0, ty: 0 });
  /** Displayed (rotated) image size; all view maths work in this space. */
  let imageSize: Size | null = $state.raw(null);
  /** Frame size as delivered (un-rotated) and the quarter turns applied. */
  let frameSize: Size | null = $state.raw(null);
  let turns: Turns = $state(0);
  let error: string | null = $state(null);
  let dragging = $state(false);

  /** Re-fit on resize until the user pans or zooms. */
  let fitted = true;
  /** Last frame drawn (CPU copy for pixel readout; same buffer as the texture source). */
  let shown: DecodedFrame | null = null;
  let pending: DecodedFrame | null = null;
  let autoParams: StretchParams = { ...NEUTRAL_STRETCH };
  let raf = 0;
  let lastPointer: { x: number; y: number } | null = null;

  // -- Public API -------------------------------------------------------------

  /** Framed view (fitMode): whole image visible, or the viewer filled. Centred. */
  export function fit(): void {
    if (!imageSize) return;
    setView(framedView(fitMode, imageSize, viewport), true);
  }

  /** One image pixel per device pixel, centre kept. */
  export function oneToOne(): void {
    if (!imageSize) return;
    setView(oneToOneView(imageSize, viewport, view, dpr), false);
  }

  /** Multiply the zoom by `factor` around `at` (CSS px in the viewer; default: centre). */
  export function zoomBy(factor: number, at?: { x: number; y: number }): void {
    if (!imageSize) return;
    const p = at ?? { x: viewport.width / 2, y: viewport.height / 2 };
    const next = zoomAt(view, factor, p.x, p.y, scaleLimits(imageSize, viewport, dpr));
    setView(clampPan(next, imageSize, viewport), false);
  }

  /** Current zoom in device px per image px (1 = 1:1). */
  export function getZoom(): number {
    return view.scale * dpr;
  }

  // -- Internals --------------------------------------------------------------

  function setView(next: ViewState, isFit: boolean): void {
    const zoomChanged = next.scale !== view.scale;
    view = next;
    setFitted(isFit);
    if (zoomChanged) onzoom?.(next.scale * dpr);
    schedule();
  }

  function setFitted(value: boolean): void {
    if (value === fitted) return;
    fitted = value;
    onfitted?.(value);
  }

  function effectiveStretch(): StretchParams {
    if (!autoStretch && stretch) return stretch;
    return autoParams;
  }

  function schedule(): void {
    if (raf === 0 && renderer) raf = requestAnimationFrame(paint);
  }

  function fail(message: string): void {
    error = message;
    onerror?.(message);
  }

  function paint(): void {
    raf = 0;
    if (!renderer) return;
    const next = pending;
    pending = null;
    let uploadMs = 0;
    let statsMs = 0;
    let info: Omit<DisplayInfo, 'timing'> | null = null;

    if (next) {
      const h = next.header;
      try {
        uploadMs = renderer.upload(
          { width: h.width, height: h.height, channels: h.channels, pixels: next.pixels },
          syncTiming,
        );
      } catch (err) {
        fail((err as Error).message);
        return;
      }
      const t0 = performance.now();
      const histogram = histogram16(next.pixels);
      autoParams = autoStf(histogram);
      statsMs = performance.now() - t0;
      shown = next;
      info = { frame: next, histogram, auto: autoParams };
      applyGeometry(h.width, h.height);
      error = null;
      if (lastPointer) emitPointer(lastPointer.x, lastPointer.y);
    }

    const drawMs = renderer.draw(
      { view, stretch: effectiveStretch(), nightTint, tint, rotation: turns, dpr },
      syncTiming,
    );
    if (info) {
      ondisplay?.({
        ...info,
        timing: {
          seq: info.frame.header.seq,
          decodeMs: info.frame.decodeMs ?? null,
          uploadMs,
          statsMs,
          drawMs,
        },
      });
    }
  }

  /** Frame size or rotation changed: new displayed size, and a re-fit. */
  function applyGeometry(width: number, height: number): void {
    const k = effectiveTurns(rotation, width, height);
    const d = displaySize(width, height, k);
    const same =
      imageSize !== null &&
      frameSize !== null &&
      frameSize.width === width &&
      frameSize.height === height &&
      k === turns;
    if (same) return;
    frameSize = { width, height };
    turns = k;
    imageSize = d;
    view = framedView(fitMode, d, viewport);
    setFitted(true);
    onzoom?.(view.scale * dpr);
  }

  function emitPointer(cssX: number, cssY: number): void {
    if (!onpointer) return;
    const f = shown;
    if (!f) return onpointer(null);
    const p = screenToImage(view, cssX, cssY);
    const u = Math.floor(p.x);
    const v = Math.floor(p.y);
    const { width, height, channels } = f.header;
    const d = displaySize(width, height, turns);
    if (u < 0 || v < 0 || u >= d.width || v >= d.height) return onpointer(null);
    const { x, y } = displayToFrame(u, v, width, height, turns);
    const i = (y * width + x) * channels;
    const px = f.pixels;
    onpointer({ x, y, value: channels === 1 ? px[i] : [px[i], px[i + 1], px[i + 2]] });
  }

  function localPoint(e: MouseEvent): { x: number; y: number } {
    const r = container.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  function onResize(cssW: number, cssH: number, devW: number, devH: number): void {
    const old = viewport;
    viewport = { width: cssW, height: cssH };
    dpr = cssW > 0 ? devW / cssW : window.devicePixelRatio || 1;
    renderer?.resize(devW, devH);
    if (imageSize) {
      if (fitted) {
        view = framedView(fitMode, imageSize, viewport);
        onzoom?.(view.scale * dpr);
      } else {
        // Keep the image point at the centre where it was.
        view = clampPan(
          {
            scale: view.scale,
            tx: view.tx + (cssW - old.width) / 2,
            ty: view.ty + (cssH - old.height) / 2,
          },
          imageSize,
          viewport,
        );
      }
    }
    schedule();
  }

  // -- Prop reactions -----------------------------------------------------------

  $effect(() => {
    const f = frame;
    if (f) {
      pending = f;
      schedule();
    } else {
      pending = null;
      shown = null;
      imageSize = null;
      frameSize = null;
      renderer?.clear();
      schedule();
    }
  });

  $effect(() => {
    // Rotation mode changed: re-derive the displayed geometry of the current frame.
    const mode = rotation;
    const f = frameSize;
    if (!f) return;
    if (effectiveTurns(mode, f.width, f.height) !== turns) {
      applyGeometry(f.width, f.height);
      if (lastPointer) emitPointer(lastPointer.x, lastPointer.y);
      schedule();
    }
  });

  $effect(() => {
    // Fit mode changed while framed: re-frame in the new mode.
    const mode = fitMode;
    if (!imageSize || !fitted) return;
    const next = framedView(mode, imageSize, viewport);
    if (next.scale !== view.scale || next.tx !== view.tx || next.ty !== view.ty) {
      setView(next, true);
    }
  });

  $effect(() => {
    if (!imageSize || !onrect) return;
    onrect({
      left: view.tx,
      top: view.ty,
      width: imageSize.width * view.scale,
      height: imageSize.height * view.scale,
    });
  });

  $effect(() => {
    // Track every input of a redraw (uniform changes only, no re-upload).
    void autoStretch;
    void nightTint;
    void [tint[0], tint[1], tint[2]];
    if (stretch) void [stretch.black, stretch.white, stretch.midtones, stretch.mode];
    schedule();
  });

  // -- Lifecycle ----------------------------------------------------------------

  onMount(() => {
    try {
      renderer = new ImageRenderer(canvas, schedule);
    } catch (err) {
      fail((err as Error).message);
    }

    const ro = new ResizeObserver((entries) => {
      const entry = entries[entries.length - 1];
      if (!entry) return;
      const css = entry.contentRect;
      const ratio = window.devicePixelRatio || 1;
      const expectW = css.width * ratio;
      const expectH = css.height * ratio;
      // devicePixelContentBoxSize is the exact backing size (no rounding
      // drift at fractional DPRs), but Chrome's device emulation reports CSS
      // px there: only trust it when it agrees with devicePixelRatio.
      const dev = entry.devicePixelContentBoxSize?.[0];
      const exact =
        dev !== undefined &&
        Math.abs(dev.inlineSize - expectW) <= 1.5 &&
        Math.abs(dev.blockSize - expectH) <= 1.5;
      onResize(
        css.width,
        css.height,
        exact ? dev.inlineSize : Math.round(expectW),
        exact ? dev.blockSize : Math.round(expectH),
      );
    });
    try {
      ro.observe(container, { box: 'device-pixel-content-box' });
    } catch {
      ro.observe(container); // WebKit: no device-pixel-content-box
    }

    // DPR changes without a size change (window moved to another screen) are
    // not reported by WebKit's ResizeObserver: watch the resolution instead.
    let mql: MediaQueryList | null = null;
    const onDprChange = () => {
      armDprWatch();
      const r = container.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      onResize(r.width, r.height, r.width * ratio, r.height * ratio);
    };
    function armDprWatch(): void {
      mql?.removeEventListener('change', onDprChange);
      mql = window.matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`);
      mql.addEventListener('change', onDprChange);
    }
    armDprWatch();

    let drag: { id: number; x: number; y: number; tx: number; ty: number } | null = null;

    const onPointerDown = (e: PointerEvent) => {
      if (e.button !== 0 && e.button !== 1) return;
      if (!imageSize) return;
      e.preventDefault();
      container.setPointerCapture(e.pointerId);
      const p = localPoint(e);
      drag = { id: e.pointerId, x: p.x, y: p.y, tx: view.tx, ty: view.ty };
      dragging = true;
    };
    const onPointerMove = (e: PointerEvent) => {
      const p = localPoint(e);
      lastPointer = p;
      if (drag && e.pointerId === drag.id && imageSize) {
        const next = { scale: view.scale, tx: drag.tx + p.x - drag.x, ty: drag.ty + p.y - drag.y };
        setView(clampPan(next, imageSize, viewport), false);
      }
      emitPointer(p.x, p.y);
    };
    const endDrag = (e: PointerEvent) => {
      if (!drag || e.pointerId !== drag.id) return;
      drag = null;
      dragging = false;
      if (container.hasPointerCapture(e.pointerId)) container.releasePointerCapture(e.pointerId);
    };
    const onPointerLeave = () => {
      if (drag) return;
      lastPointer = null;
      onpointer?.(null);
    };
    const onWheel = (e: WheelEvent) => {
      if (!imageSize) return;
      e.preventDefault();
      const p = localPoint(e);
      zoomBy(wheelZoomFactor(e.deltaY, e.deltaMode, e.ctrlKey), p);
      emitPointer(p.x, p.y);
    };
    const onDblClick = (e: MouseEvent) => {
      e.preventDefault();
      fit();
    };
    const PAN_KEYS: Record<string, [number, number]> = {
      ArrowLeft: [1, 0],
      ArrowRight: [-1, 0],
      ArrowUp: [0, 1],
      ArrowDown: [0, -1],
    };
    const onKeyDown = (e: KeyboardEvent) => {
      const dir = PAN_KEYS[e.key];
      if (!dir || !imageSize || e.altKey || e.ctrlKey || e.metaKey) return;
      e.preventDefault();
      // The arrow shows more of the image on its side: the image moves the other way.
      const step = KEY_PAN_PX * (e.shiftKey ? 10 : 1);
      const next = { scale: view.scale, tx: view.tx + dir[0] * step, ty: view.ty + dir[1] * step };
      setView(clampPan(next, imageSize, viewport), false);
    };

    container.addEventListener('pointerdown', onPointerDown);
    container.addEventListener('pointermove', onPointerMove);
    container.addEventListener('pointerup', endDrag);
    container.addEventListener('pointercancel', endDrag);
    container.addEventListener('pointerleave', onPointerLeave);
    container.addEventListener('wheel', onWheel, { passive: false });
    container.addEventListener('dblclick', onDblClick);
    container.addEventListener('keydown', onKeyDown);

    schedule();

    return () => {
      ro.disconnect();
      mql?.removeEventListener('change', onDprChange);
      container.removeEventListener('pointerdown', onPointerDown);
      container.removeEventListener('pointermove', onPointerMove);
      container.removeEventListener('pointerup', endDrag);
      container.removeEventListener('pointercancel', endDrag);
      container.removeEventListener('pointerleave', onPointerLeave);
      container.removeEventListener('wheel', onWheel);
      container.removeEventListener('dblclick', onDblClick);
      container.removeEventListener('keydown', onKeyDown);
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      renderer?.dispose();
      renderer = null;
    };
  });

  /** Arrow-key pan step, CSS px (Shift: 10x). */
  const KEY_PAN_PX = 32;

  // Crosshair geometry in CSS px: through the image centre, with a gap so the
  // star sitting there stays visible.
  const CROSS_GAP = 10;
  let cross = $derived.by(() => {
    if (!imageSize) return null;
    const x0 = view.tx;
    const y0 = view.ty;
    const x1 = view.tx + imageSize.width * view.scale;
    const y1 = view.ty + imageSize.height * view.scale;
    const cx = view.tx + (imageSize.width / 2) * view.scale;
    const cy = view.ty + (imageSize.height / 2) * view.scale;
    return { x0, y0, x1, y1, cx, cy };
  });
</script>

<!-- A pannable canvas: keyboard users need a tab stop on it to pan with the
     arrows (Svelte counts role="application" as non-interactive). -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
  class="viewer"
  class:dragging
  bind:this={container}
  role="application"
  aria-roledescription="image viewer"
  tabindex="0"
  aria-label={frameSize
    ? `${label}, ${frameSize.width} by ${frameSize.height} pixels; arrow keys pan`
    : label}
>
  <canvas bind:this={canvas}></canvas>

  <svg class="overlay" width={viewport.width} height={viewport.height} aria-hidden="true">
    {#if imageSize}
      {#if overlay}
        <!-- +0.5 px: numpy/photutils convention, pixel centres at integer coordinates. -->
        <g
          transform="translate({view.tx + 0.5 * view.scale} {view.ty + 0.5 * view.scale}) scale({view.scale})"
        >
          {#if frameSize}
            <g transform={overlayMatrix(frameSize.width, frameSize.height, turns)}>
              {@render overlay({ scale: view.scale, width: frameSize.width, height: frameSize.height })}
            </g>
          {/if}
        </g>
      {/if}
      {#if crosshair && cross}
        <g class="crosshair" shape-rendering="crispEdges">
          <line x1={cross.x0} y1={cross.cy} x2={cross.cx - CROSS_GAP} y2={cross.cy} />
          <line x1={cross.cx + CROSS_GAP} y1={cross.cy} x2={cross.x1} y2={cross.cy} />
          <line x1={cross.cx} y1={cross.y0} x2={cross.cx} y2={cross.cy - CROSS_GAP} />
          <line x1={cross.cx} y1={cross.cy + CROSS_GAP} x2={cross.cx} y2={cross.y1} />
        </g>
      {/if}
    {/if}
  </svg>

  {#if error}
    <div class="message error" role="alert">{error}</div>
  {:else if !imageSize && empty}
    <div class="message">{@render empty()}</div>
  {/if}
</div>

<style>
  .viewer {
    position: relative;
    width: 100%;
    height: 100%;
    min-height: 0;
    overflow: hidden;
    background: var(--viewer-bg);
    cursor: crosshair;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
  }

  .viewer.dragging {
    cursor: grabbing;
  }

  /* Inset ring, drawn above the canvas: the viewer fills its cell, so an
     outset ring would be clipped, and an outline would sit under the image. */
  .viewer:focus-visible {
    outline: none;
  }
  .viewer:focus-visible::after {
    content: '';
    position: absolute;
    inset: 0;
    box-shadow: inset 0 0 0 var(--focus-ring-w) var(--focus-ring);
    pointer-events: none;
  }

  canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    display: block;
  }

  .overlay {
    position: absolute;
    inset: 0;
    pointer-events: none;
    overflow: visible;
  }

  .crosshair line {
    stroke: var(--accent);
    stroke-width: 1;
    opacity: 0.9;
  }

  .message {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    padding: var(--space-4);
    color: var(--text-muted);
    font-family: var(--font-ui);
    text-align: center;
    pointer-events: none;
  }

  /* Words stay --fg (BRAND 4.2): the alert role and the wording carry the error. */
  .message.error {
    color: var(--fg);
  }
</style>
