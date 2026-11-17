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

  Wave 4 (web/spec/04-viewer-and-image-tools.md 2.2-2.5): the CFA preview
  (`preview`: Colour, Raw, R, G, B on a colour sensor's mosaic; the automatic
  levels follow the view, as in Qt), the palettes (`palette`; Night Red draws
  Neutral whatever is asked, D30), the saturation highlight on raw samples
  (`saturation`), the crosshair through the pointer (`crosshairMode`), the
  loupe inset (`loupe`, tools/Loupe.svelte), and `ongeometry` for the
  screen-space tools over the viewer (tools/geometry.ts). `snapshot()` draws
  now and returns a copy of the picture (Save view as PNG).
-->
<script lang="ts">
  import { onMount, untrack, type Snippet } from 'svelte';
  import type { DecodedFrame } from '../api/frames';
  import { cfaPlanes, cfaSites, frameKind, previewStats, rgbPlanes, type Preview, type PreviewStats } from './palettes/cfa';
  import { effectivePalette, type Palette } from './palettes/lut';
  import { ImageRenderer, type DrawOptions } from './renderer';
  import type { ViewerGeometry } from './tools/geometry';
  import Loupe from './tools/Loupe.svelte';
  import type { Histogram16 } from './stretch';
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
  import type { FrameHeaderV3 } from './hud';
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
    /** Show a crosshair (at the image centre, or through the pointer: `crosshairMode`). */
    crosshair?: boolean;
    /** Crosshair through the image centre (default) or lines through the pointer (Q-O16). */
    crosshairMode?: 'centre' | 'cursor';
    /** Display palette (palettes/lut.ts); Night Red draws Neutral whatever is asked (D30). */
    palette?: Palette;
    /** CFA preview (palettes/cfa.ts): ignored for a mono frame. */
    preview?: Preview;
    /** CFA pattern when the frame header carries none (the camera profile's). */
    bayer?: string | null;
    /** Paint pixels whose RAW samples reach `threshold` ADU in `colour` (0..1 RGB; black in Night Red). */
    saturation?: { threshold: number; colour: readonly [number, number, number] } | null;
    /** Loupe inset at the top right: magnification (CSS px per frame px) and its top offset. */
    loupe?: { mag: number; top?: number } | null;
    /** Where the image is (pan, zoom, rotation, sizes), for screen-space tools; null without a frame. */
    ongeometry?: (g: ViewerGeometry | null) => void;
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
    crosshairMode = 'centre',
    palette = 'neutral',
    preview = 'colour',
    bayer = null,
    saturation = null,
    loupe = null,
    ongeometry,
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
  /** The pointer over the viewer (CSS px), for the cursor crosshair and the loupe. */
  let hover: { x: number; y: number } | null = $state.raw(null);
  /** What the current preview draws (gains, plane) and the frame it was computed for. */
  let pstats: PreviewStats | null = $state.raw(null);
  /** Bumped when the frame on screen changes (the loupe re-uploads). */
  let shownVersion = $state(0);

  /** Re-fit on resize until the user pans or zooms. */
  let fitted = true;
  /** Last frame drawn (CPU copy for pixel readout; same buffer as the texture source). */
  let shown: DecodedFrame | null = $state.raw(null);
  let pending: DecodedFrame | null = null;
  let autoParams: StretchParams = { ...NEUTRAL_STRETCH };
  let raf = 0;
  let lastPointer: { x: number; y: number } | null = null;
  /** The last DisplayInfo sent, re-sent with new levels when the preview changes. */
  let lastInfo: DisplayInfo | null = null;
  /** CFA / RGB planes of the frame on screen, computed on demand (a non-raw preview). */
  let planes: { frame: DecodedFrame; value: ReturnType<typeof rgbPlanes> | null } | null = null;

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

  /**
   * Draw now and return a copy of the picture (device px), or null without a
   * frame: the drawing buffer is only readable in the task that drew it.
   */
  export function snapshot(): HTMLCanvasElement | null {
    if (!renderer || !shown) return null;
    renderer.draw(drawOptions());
    const out = document.createElement('canvas');
    out.width = canvas.width;
    out.height = canvas.height;
    const ctx = out.getContext('2d');
    if (!ctx) return null;
    ctx.fillStyle = getComputedStyle(container).getPropertyValue('--viewer-bg').trim() || '#000000';
    ctx.fillRect(0, 0, out.width, out.height);
    ctx.drawImage(canvas, 0, 0);
    return out;
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

  function bayerOf(f: DecodedFrame): string | null {
    const h = f.header as FrameHeaderV3;
    return h.bayer !== undefined ? (h.bayer ?? null) : bayer;
  }

  /** The preview of the frame on screen: gains, plane, and the samples its auto levels use. */
  function computePreview(f: DecodedFrame): PreviewStats {
    const h = f.header;
    const kind = frameKind(h.channels, bayerOf(f));
    const first = previewStats(preview, kind, null);
    if (first.code === 0) return first;
    if (!planes || planes.frame !== f) {
      const sites = cfaSites(bayerOf(f));
      planes = { frame: f, value: kind === 'cfa' && sites ? cfaPlanes(f.pixels, h.width, h.height, sites) : kind === 'rgb' ? rgbPlanes(f.pixels) : null };
    }
    return previewStats(preview, kind, planes.value);
  }

  function autoFor(histogram: Histogram16, p: PreviewStats): StretchParams {
    return autoStf(p.view ?? histogram);
  }

  /** Everything the renderer needs for the frame on screen (the loupe draws with the same). */
  function drawOptions(): DrawOptions {
    const f = shown;
    const sites = f ? cfaSites(bayerOf(f)) : null;
    const p = pstats;
    return {
      view,
      stretch: effectiveStretch(),
      nightTint,
      tint,
      rotation: turns,
      dpr,
      palette: effectivePalette(palette, nightTint),
      preview:
        p && p.code !== 0
          ? { code: p.code, r: sites?.r ?? [0, 0], b: sites?.b ?? [0, 0], g1: sites?.g1 ?? [0, 0], g2: sites?.g2 ?? [0, 0], gains: p.gains }
          : undefined,
      saturation,
    };
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
      const p = computePreview(next);
      autoParams = autoFor(histogram, p);
      statsMs = performance.now() - t0;
      shown = next;
      pstats = p;
      shownVersion++;
      info = { frame: next, histogram, auto: autoParams, preview: p.preview };
      applyGeometry(h.width, h.height);
      error = null;
      if (lastPointer) emitPointer(lastPointer.x, lastPointer.y);
    }

    const drawMs = renderer.draw(drawOptions(), syncTiming);
    if (info) {
      lastInfo = {
        ...info,
        timing: {
          seq: info.frame.header.seq,
          decodeMs: info.frame.decodeMs ?? null,
          uploadMs,
          statsMs,
          drawMs,
        },
      };
      ondisplay?.(lastInfo);
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
    void palette;
    if (saturation) void [saturation.threshold, saturation.colour[0], saturation.colour[1], saturation.colour[2]];
    else void saturation;
    schedule();
  });

  $effect(() => {
    // The preview (or the fallback CFA pattern) changed: new gains and automatic levels for
    // the frame on screen, sent again (redisplay) so the levels shown follow.
    void preview;
    void bayer;
    untrack(() => {
      const f = shown;
      const info = lastInfo;
      if (!f || !info || info.frame !== f) return;
      const p = computePreview(f);
      if (pstats && p.code === pstats.code && p.gains.every((g, i) => g === pstats!.gains[i])) return;
      pstats = p;
      autoParams = autoFor(info.histogram, p);
      lastInfo = { ...info, auto: autoParams, preview: p.preview, redisplay: true };
      ondisplay?.(lastInfo);
      schedule();
    });
  });

  $effect(() => {
    // Screen-space tools follow the view (pan, zoom, resize, rotation, frame size).
    if (!ongeometry) return;
    const f = frameSize;
    const g: ViewerGeometry | null = f && imageSize ? { view, frame: f, turns, viewport, dpr } : null;
    untrack(() => ongeometry?.(g));
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
      hover = p;
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
      hover = null;
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
    if (crosshairMode === 'cursor') {
      // Lines through the pointer while it is over the image (Qt's cursor lines, Q-O16).
      const p = hover;
      if (!p || p.x < x0 || p.x >= x1 || p.y < y0 || p.y >= y1) return null;
      return { x0, y0, x1, y1, cx: p.x, cy: p.y };
    }
    const cx = view.tx + (imageSize.width / 2) * view.scale;
    const cy = view.ty + (imageSize.height / 2) * view.scale;
    return { x0, y0, x1, y1, cx, cy };
  });

  // -- Loupe: the display pixel under the pointer, magnified (tools/Loupe.svelte) ---------
  const LOUPE_SIZE = 168;
  const loupeAt = $derived.by(() => {
    const p = hover;
    if (!loupe || !p || !imageSize || dragging) return null;
    const u = Math.floor((p.x - view.tx) / view.scale);
    const v = Math.floor((p.y - view.ty) / view.scale);
    if (u < 0 || v < 0 || u >= imageSize.width || v >= imageSize.height) return null;
    return { u, v };
  });
  /** Top right; it steps to the top left when the pointer comes under it. */
  const loupeBox = $derived.by(() => {
    if (!loupe) return null;
    const top = loupe.top ?? 8;
    const right = { left: viewport.width - LOUPE_SIZE - 8, top };
    const p = hover;
    const under = p && p.x >= right.left - 16 && p.y <= top + LOUPE_SIZE + 16;
    return under ? { left: 8, top: Math.max(top, 40) } : right;
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

  <!-- Mounted while the tool is on (one WebGL context, kept), shown while the pointer is on the image. -->
  {#if loupe && loupeBox && shown}
    <Loupe
      frame={shown}
      version={shownVersion}
      at={loupeAt}
      mag={loupe.mag}
      size={LOUPE_SIZE}
      left={loupeBox.left}
      top={loupeBox.top}
      options={drawOptions()}
    />
  {/if}

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
