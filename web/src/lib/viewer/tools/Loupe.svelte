<!--
  Loupe (web/spec/04-viewer-and-image-tools.md 2.1 E3, 2.2 row 1.5 #11, 2.4; Qt
  fits_viewer.py:184-188, 923-955): a 168 px inset at the top right of the viewer that
  magnifies the pixels under the pointer, nearest neighbour, so every sensor pixel is a
  visible square (Qt: 42 px of the picture at 4x). Magnification 2x / 4x / 8x is in View
  options (Q-O23); 4x by default.

  It draws the SAME picture as the viewer (stretch, palette, CFA preview, saturation,
  Night Red), with its own WebGL2 context fed the same frame: the frame is uploaded again
  only when a new one is shown while the loupe is visible, and drawing is a uniform change.
  The centre pixel is outlined (neutral ink: brass is for the selection), the magnification
  sits in a corner chip. Hidden when the pointer leaves the image (FitsViewer decides).
  Display only, no values (Q15): the HUD readout carries them.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import type { DecodedFrame } from '../../api/frames';
  import { ImageRenderer, type DrawOptions } from '../renderer';

  interface Props {
    frame: DecodedFrame;
    /** Changes with every frame shown (re-upload). */
    version: number;
    /** Display pixel under the pointer (rotated picture); null: hidden (the pointer is off the image). */
    at: { u: number; v: number } | null;
    /** CSS px per frame px. */
    mag: number;
    size: number;
    left: number;
    top: number;
    /** The viewer's draw options (its view and dpr are replaced). */
    options: DrawOptions;
  }

  let { frame, version, at, mag, size, left, top, options }: Props = $props();

  let canvas: HTMLCanvasElement;
  let renderer: ImageRenderer | null = null;
  let failed = $state(false);
  let uploaded = -1;

  function draw(): void {
    if (!renderer || !at) return;
    const dpr = window.devicePixelRatio || 1;
    renderer.resize(size * dpr, size * dpr);
    if (uploaded !== version) {
      try {
        renderer.upload({ width: frame.header.width, height: frame.header.height, channels: frame.header.channels, pixels: frame.pixels });
        uploaded = version;
      } catch {
        failed = true;
        return;
      }
    }
    // The pointer's pixel centred: its centre (u + 0.5) sits at size / 2.
    const scale = mag;
    renderer.draw({
      ...options,
      dpr,
      view: { scale, tx: size / 2 - (at.u + 0.5) * scale, ty: size / 2 - (at.v + 0.5) * scale },
    });
  }

  onMount(() => {
    try {
      renderer = new ImageRenderer(canvas, draw);
    } catch {
      failed = true;
    }
    return () => {
      renderer?.dispose();
      renderer = null;
      // Free the context now: browsers cap live WebGL contexts and drop the OLDEST one (the viewer's).
      canvas.getContext('webgl2')?.getExtension('WEBGL_lose_context')?.loseContext();
    };
  });

  $effect(() => {
    void [version, at?.u, at?.v, mag, size, options];
    draw();
  });

  const box = $derived(mag); // the centre pixel's side, CSS px
</script>

<div class="loupe" class:hidden={!at} style:left="{left}px" style:top="{top}px" style:width="{size}px" style:height="{size}px" aria-hidden="true" data-loupe={at ? mag : undefined}>
  <canvas bind:this={canvas} style:width="{size}px" style:height="{size}px"></canvas>
  {#if !failed}
    <svg class="mark" width={size} height={size}>
      <rect x={size / 2 - box / 2 - 0.5} y={size / 2 - box / 2 - 0.5} width={box + 1} height={box + 1} />
      <line x1={size / 2} y1="0" x2={size / 2} y2={size / 2 - box / 2 - 4} />
      <line x1={size / 2} y1={size / 2 + box / 2 + 4} x2={size / 2} y2={size} />
      <line x1="0" y1={size / 2} x2={size / 2 - box / 2 - 4} y2={size / 2} />
      <line x1={size / 2 + box / 2 + 4} y1={size / 2} x2={size} y2={size / 2} />
    </svg>
    <span class="zoom num">{mag}×</span>
  {/if}
</div>

<style>
  .loupe {
    position: absolute;
    z-index: 4;
    overflow: hidden;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--viewer-bg);
    box-shadow: var(--shadow-2);
    pointer-events: none;
  }
  .loupe.hidden {
    visibility: hidden;
  }
  canvas,
  .mark {
    position: absolute;
    inset: 0;
    display: block;
  }
  .mark rect,
  .mark line {
    fill: none;
    stroke: var(--fg-muted);
    stroke-width: 1;
    shape-rendering: crispEdges;
  }
  .mark line {
    stroke-opacity: 0.6;
  }
  .zoom {
    position: absolute;
    right: 4px;
    bottom: 4px;
    padding: 0 var(--space-1);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    line-height: 16px;
  }
</style>
