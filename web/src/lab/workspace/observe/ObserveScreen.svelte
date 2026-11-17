<!--
  Observe: the same regions in every mode (toolbar, image, band, drawer,
  right panel); the mode decides what they hold.

  - The image is the hero: the band under it takes EXACTLY the space a
    fitted 16:9 frame leaves (BRAND 11.1, bandLayout), so there are no black
    bands at 1440 x 900 or 1280 x 800. Dragging the band's edge overrides
    that per mode; double-click returns to "fits the image".
  - Separators are 1 px lines with a 7 px hit area, WAI-ARIA splitters
    (arrows, Shift+arrows, Home / End, Enter or double-click resets). While
    one is dragged, the cost is shown on the image: band height, image size,
    black margins (what the layout costs, in pixels).
  - The drawer sits under the image column only, so the right panel keeps
    its full height.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { splitter } from '../../research/space/splitter';
  import { bandLayout, type BandLayout } from '../model/layout';
  import { sim, ws } from '../model/app.svelte';
  import Toolbar from './Toolbar.svelte';
  import Viewer from './Viewer.svelte';
  import Band from './Band.svelte';
  import RightPanel from './RightPanel.svelte';
  import Drawer from './Drawer.svelte';

  const FRAME = { width: 1920, height: 1080 }; // displayed (portrait S50 frame turned)

  let centre: HTMLDivElement;
  let size = $state({ w: 0, h: 0 });
  let dragging = $state<'rail' | 'band' | 'drawer' | null>(null);

  const drawerH = $derived(ws.layout.drawerOpen ? Math.min(ws.layout.drawerH, Math.max(120, size.h - 240)) : 0);
  const bl: BandLayout = $derived(
    bandLayout({ width: size.w, height: size.h }, FRAME, drawerH, ws.layout.bandOpen, ws.layout.bandH),
  );
  const auto = $derived(bandLayout({ width: size.w, height: size.h }, FRAME, drawerH, true, null).height);

  const readout = $derived.by(() => {
    if (!dragging) return null;
    const img = `image ${Math.round(bl.image.width)} × ${Math.round(bl.image.height)}`;
    const margins = bl.sideBands.x >= 1 ? ` · side margins ${Math.round(bl.sideBands.x)} px` : bl.sideBands.y >= 1 ? ` · top and bottom margins ${Math.round(bl.sideBands.y)} px` : ' · no black margin';
    if (dragging === 'rail') return `Right panel ${ws.layout.railW} px · ${img}${margins}`;
    if (dragging === 'band') return `Band ${bl.height} px${ws.layout.bandH === null ? ' (fits the image)' : ''} · ${img}${margins}`;
    return `Drawer ${drawerH} px · band ${bl.compact ? 'one row' : `${bl.height} px`} · ${img}`;
  });

  $effect(() => {
    ws.dragReadout = readout;
  });

  onMount(() => {
    const ro = new ResizeObserver(() => {
      const r = centre.getBoundingClientRect();
      size = { w: Math.floor(r.width), h: Math.floor(r.height) };
    });
    ro.observe(centre);
    return () => ro.disconnect();
  });

  const railW = $derived(ws.layout.railOpen ? ws.layout.railW : 0);
</script>

<div class="observe" data-mode={ws.mode} data-frame-seq={sim.frame?.header.seq ?? ''}>
  <Toolbar />
  <div class="body" style:--rail-w="{railW}px">
    <div class="centre" bind:this={centre}>
      <div class="viewer-cell" style:height="{bl.viewer}px">
        <Viewer />
      </div>
      {#if ws.layout.bandOpen && bl.height > 0}
        <!-- svelte-ignore a11y_no_noninteractive_tabindex (a focusable separator is the WAI-ARIA window splitter) -->
        <div
          class="hsep"
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize the band under the image"
          aria-valuenow={bl.height}
          aria-valuemin={36}
          aria-valuemax={Math.max(36, size.h - drawerH - 200)}
          tabindex="0"
          class:active={dragging === 'band'}
          {@attach splitter({
            axis: 'y',
            invert: true,
            get: () => bl.height,
            set: (v) => ws.edit((l) => (l.bandH = Math.abs(v - auto) <= 6 ? null : v)),
            min: 36,
            max: () => Math.max(36, size.h - drawerH - 200),
            reset: auto,
            snaps: [auto],
            ondrag: (a) => (dragging = a ? 'band' : null),
          })}
        ></div>
        <div class="band-cell" style:height="{bl.height - 1}px">
          <Band compact={bl.compact} height={bl.height} />
        </div>
      {/if}
      {#if ws.layout.drawerOpen}
        <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
        <div
          class="hsep strong"
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize the drawer"
          aria-valuenow={drawerH}
          aria-valuemin={120}
          aria-valuemax={Math.max(120, size.h - 240)}
          tabindex="0"
          class:active={dragging === 'drawer'}
          {@attach splitter({
            axis: 'y',
            invert: true,
            get: () => drawerH,
            set: (v) => ws.edit((l) => (l.drawerH = v)),
            min: 120,
            max: () => Math.max(120, size.h - 240),
            reset: 216,
            snaps: [216],
            ondrag: (a) => (dragging = a ? 'drawer' : null),
          })}
        ></div>
        <div class="drawer-cell" style:height="{drawerH - 1}px">
          <Drawer />
        </div>
      {/if}
    </div>
    {#if ws.layout.railOpen}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div
        class="vsep"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize the right panel"
        aria-valuenow={ws.layout.railW}
        aria-valuemin={340}
        aria-valuemax={580}
        tabindex="0"
        class:active={dragging === 'rail'}
        {@attach splitter({
          axis: 'x',
          invert: true,
          get: () => ws.layout.railW,
          set: (v) => ws.edit((l) => (l.railW = v)),
          min: 340,
          max: () => 580,
          reset: 400,
          snaps: [400, 480],
          ondrag: (a) => (dragging = a ? 'rail' : null),
        })}
      ></div>
      <RightPanel />
    {/if}
  </div>
</div>

<style>
  .observe {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .body {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto var(--rail-w);
  }
  .centre {
    position: relative;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .viewer-cell {
    flex: none;
    min-height: 0;
    position: relative;
  }
  .band-cell,
  .drawer-cell {
    flex: none;
    min-height: 0;
  }

  /* 1 px lines with a 7 px hit area, centred on the line. */
  .hsep,
  .vsep {
    position: relative;
    flex: none;
    background: var(--border);
    z-index: var(--z-dock);
  }
  .hsep {
    height: 1px;
    cursor: row-resize;
  }
  .vsep {
    width: 1px;
    cursor: col-resize;
  }
  .hsep::after,
  .vsep::after {
    content: '';
    position: absolute;
  }
  .hsep::after {
    left: 0;
    right: 0;
    top: calc(var(--lab-splitter-hit) / -2);
    height: var(--lab-splitter-hit);
  }
  .vsep::after {
    top: 0;
    bottom: 0;
    left: calc(var(--lab-splitter-hit) / -2);
    width: var(--lab-splitter-hit);
  }
  /* Hover / drag: the line thickens to 3 px in --fg-muted (no brass: layout). */
  .hsep:hover,
  .hsep.active,
  .hsep:focus-visible {
    box-shadow: 0 0 0 1px var(--fg-muted);
    background: var(--fg-muted);
    outline: none;
  }
  .vsep:hover,
  .vsep.active,
  .vsep:focus-visible {
    box-shadow: 0 0 0 1px var(--fg-muted);
    background: var(--fg-muted);
    outline: none;
  }
</style>
