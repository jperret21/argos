<!--
  The sky on the image HUD once the field is identified (web/lab/PROPOSAL.md 3.1 and 6, W4;
  promoted from the compass and scale bar of src/lab/workspace/observe/Viewer.svelte):

  - a N / E compass at the top right of the image: the directions of north and east at the
    frame centre, from the WCS (hud/wcs.ts), turned with the display rotation; the letters
    stay upright (screen space). East is where the solution puts it: on a north-up sky
    image it is on the left, and a mirrored picture says so;
  - an arcminute scale bar at the bottom left: the shortest round length (15″ … 2°) at
    least 56 px long at the current zoom, from the plate scale.
  Neutral overlay inks with a 1 px black halo (BRAND 11): readable over any star field,
  red only in Night Red; nothing takes the pointer.
-->
<script lang="ts">
  import type { Turns } from '../rotation';
  import { COMPASS_SIZE as COMPASS, compassAt, plateScaleArcsec, scaleBar, type TanWcs } from './wcs';

  interface Props {
    wcs: TanWcs;
    /** Frame size as delivered (un-rotated). */
    frame: { width: number; height: number };
    turns: Turns;
    /** CSS px per frame px (the viewer's zoom). */
    scale: number;
    /** Compass box: top right corner, CSS px in the stage. */
    compassTop: number;
    compassRight: number;
    /** Scale bar: bottom left corner, CSS px in the stage. */
    barLeft: number;
    barBottom: number;
  }

  let { wcs, frame, turns, scale, compassTop, compassRight, barLeft, barBottom }: Props = $props();

  const ARM = 18;
  const c = $derived(compassAt(wcs, (frame.width - 1) / 2, (frame.height - 1) / 2, turns));
  const bar = $derived(scaleBar(plateScaleArcsec(wcs), scale));
  const words = (v: { x: number; y: number }) => {
    const a = (Math.atan2(v.x, -v.y) * 180) / Math.PI; // 0 = up, clockwise
    const dirs = ['up', 'up-right', 'right', 'down-right', 'down', 'down-left', 'left', 'up-left'];
    return dirs[((Math.round(a / 45) % 8) + 8) % 8];
  };
  const label = $derived(c ? `North points ${words(c.north)}, east ${words(c.east)}${c.mirrored ? '; the picture is a mirror image of the sky' : ''}` : '');
</script>

{#if c}
  <svg
    class="compass"
    style:top="{compassTop}px"
    style:right="{compassRight}px"
    width={COMPASS}
    height={COMPASS}
    viewBox="{-COMPASS / 2} {-COMPASS / 2} {COMPASS} {COMPASS}"
    role="img"
    aria-label={label}
    data-compass={c.mirrored ? 'mirrored' : 'sky'}
  >
    <title>{label}</title>
    <g class="halo">
      <line x1="0" y1="0" x2={c.north.x * ARM} y2={c.north.y * ARM} />
      <line x1="0" y1="0" x2={c.east.x * ARM * 0.8} y2={c.east.y * ARM * 0.8} />
    </g>
    <line class="arm n" x1="0" y1="0" x2={c.north.x * ARM} y2={c.north.y * ARM} />
    <line class="arm e" x1="0" y1="0" x2={c.east.x * ARM * 0.8} y2={c.east.y * ARM * 0.8} />
    <circle class="hub" r="1.75" />
    <text x={c.north.x * (ARM + 7)} y={c.north.y * (ARM + 7)} class="n">N</text>
    <text x={c.east.x * (ARM * 0.8 + 7)} y={c.east.y * (ARM * 0.8 + 7)}>E</text>
  </svg>
{/if}

{#if bar}
  <div class="scale" style:left="{barLeft}px" style:bottom="{barBottom}px" role="img" aria-label="Scale: the bar is {bar.label} on the sky" data-scale-bar={bar.arcmin}>
    <svg width={Math.ceil(bar.px) + 44} height="14" aria-hidden="true">
      <path class="halo" d="M2 3V11M2 7H{bar.px + 2}M{bar.px + 2} 3V11" />
      <path class="bar" d="M2 3V11M2 7H{bar.px + 2}M{bar.px + 2} 3V11" />
      <text class="len" x={bar.px + 8} y="7">{bar.label}</text>
    </svg>
  </div>
{/if}

<style>
  .compass,
  .scale {
    position: absolute;
    z-index: 2;
    overflow: visible;
    pointer-events: none;
  }
  .halo line,
  path.halo {
    fill: none;
    stroke: var(--viewer-bg);
    stroke-width: 4;
    stroke-linecap: round;
  }
  .arm {
    stroke: var(--overlay-label);
    stroke-width: 1.5;
    stroke-linecap: round;
  }
  .arm.n {
    stroke-width: 2;
  }
  .hub {
    fill: var(--overlay-label);
  }
  text {
    fill: var(--overlay-label);
    stroke: var(--viewer-bg);
    stroke-width: 3;
    paint-order: stroke;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: var(--weight-medium);
    text-anchor: middle;
    dominant-baseline: central;
  }
  text.n {
    font-weight: var(--weight-semibold);
  }
  .scale {
    display: flex;
    align-items: center;
    gap: var(--space-1);
  }
  path.bar {
    fill: none;
    stroke: var(--overlay-label);
    stroke-width: 1.5;
  }
  text.len {
    text-anchor: start;
  }
</style>
