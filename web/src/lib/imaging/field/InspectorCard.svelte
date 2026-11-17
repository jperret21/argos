<!--
  Inspector (promoted from src/lab/workspace/observe/cards/InspectorCard.svelte, web/lab/
  PROPOSAL.md 3.1 "Comparison workspace" and 6, W4): the details of the star picked in the
  candidates table or on the image, so the on-image card stays small.

  - Identity: the role shape (or a dashed candidate square), the name, the role in words.
  - APERTURE THUMBNAIL: the frame's own pixels around the star, turned like the display,
    stretched with the display levels and drawn in the viewer tint (red only in Night Red),
    with the photometry aperture (solid) and the sky annulus (dashed) in --overlay-label.
  - Values in the shared Readouts grid: V, B−V and Δ(B−V), separation from the target, the
    peak on the solved frame (with "clipped" / "non-linear" as words), SNR, and the Gaia
    sources inside the aperture (blend risk). Missing values say "—", never 0.
  - The last five stars inspected stay one click away for comparing.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { resolveColor } from '../../charts/ink';
  import Readouts, { type ReadoutItem } from '../../components/Readouts.svelte';
  import { fixed, int, signed } from '../../format/number';
  import type { Turns } from '../../viewer/rotation';
  import type { StretchParams } from '../../viewer/stretch';
  import type { CandidateRow } from './candidates';
  import RoleGlyph from './RoleGlyph.svelte';
  import type { DecodedFrame } from '../../api/frames';
  import { thumbPixels, thumbSize } from './thumb';

  interface Props {
    row: CandidateRow | null;
    /** The frame on screen and where the star is on it (current-frame px). */
    frame?: DecodedFrame | null;
    at?: { x: number; y: number } | null;
    levels?: StretchParams | null;
    turns?: Turns;
    /** Photometry geometry, frame px. */
    apertureR?: number | null;
    annulusIn?: number | null;
    annulusOut?: number | null;
    /** Plate scale, arcsec per frame px (the aperture in ″). */
    scaleArcsec?: number | null;
    /** Recent stars: a short ID ("BCG-523"), the full name (accessible name) and the role. */
    history?: readonly { key: string; label: string; name?: string; role?: CandidateRow['role'] }[];
    onpick?: (key: string) => void;
    /** Re-read the tint when the theme changes. */
    theme?: unknown;
  }

  let {
    row,
    frame = null,
    at = null,
    levels = null,
    turns = 0,
    apertureR = null,
    annulusIn = null,
    annulusOut = null,
    scaleArcsec = null,
    history = [],
    onpick,
    theme,
  }: Props = $props();

  const SIZE = 108; // CSS px
  let canvas: HTMLCanvasElement | undefined = $state();
  const n = $derived(thumbSize(apertureR, annulusOut));
  const k = $derived(SIZE / n);
  const dash = '—';

  const items: ReadoutItem[] = $derived.by(() => {
    if (!row) return [];
    const peak = row.peak;
    return [
      { k: 'V', v: row.v === null ? dash : fixed(row.v, 2), unit: 'mag' },
      { k: 'B−V', v: row.bv === null ? dash : fixed(row.bv, 2), unit: row.dbv === null ? '' : `Δ ${signed(row.dbv, 2)}`, flag: row.flags.includes('colour') ? 'colour' : undefined },
      { k: 'From target', v: row.sep === null ? dash : `${fixed(row.sep, 1)}′`, flag: row.flags.includes('far') ? 'far' : undefined },
      { k: 'Peak', v: peak === null ? dash : row.clipped ? 'clipped' : int(peak), unit: peak === null || row.clipped ? '' : 'ADU', flag: row.nonlinear ? 'non-linear' : undefined },
      { k: 'SNR', v: row.snr === null ? dash : int(row.snr) },
      { k: 'In aperture', v: row.nbr === null ? dash : int(row.nbr), unit: row.nbr === null ? '' : row.nbr === 1 ? 'Gaia source' : 'Gaia sources', flag: row.nbr ? 'blend risk' : undefined },
      ...(row.source.vsx
        ? [{ k: 'VSX', v: row.source.vsx.name, unit: row.source.vsx.suspected ? 'suspected' : (row.source.vsx.var_type ?? ''), flag: 'variable?' }]
        : []),
    ];
  });

  $effect(() => {
    void theme;
    const c = canvas;
    const f = frame;
    const p = at;
    const lv = levels;
    const size = n;
    if (!c || !f || !p || !lv) return;
    untrack(() => {
      const dpr = window.devicePixelRatio || 1;
      c.width = Math.round(SIZE * dpr);
      c.height = Math.round(SIZE * dpr);
      const ctx = c.getContext('2d');
      if (!ctx) return;
      const css = getComputedStyle(c).getPropertyValue('--viewer-tint').trim() || '#ffffff';
      const t = resolveColor(css);
      const src = { pixels: f.pixels, width: f.header.width, height: f.header.height, channels: f.header.channels };
      const data = thumbPixels(src, p.x, p.y, size, lv, [t[0], t[1], t[2]], turns);
      const tmp = document.createElement('canvas');
      tmp.width = size;
      tmp.height = size;
      tmp.getContext('2d')?.putImageData(new ImageData(data, size, size), 0, 0);
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(tmp, 0, 0, c.width, c.height);
    });
  });

  const apArc = $derived(apertureR !== null && scaleArcsec ? `${fixed(apertureR, 1)} px · ${fixed(apertureR * scaleArcsec, 0)}″` : apertureR !== null ? `${fixed(apertureR, 1)} px` : '');
</script>

{#if row}
  <div class="insp">
    <div class="id">
      <RoleGlyph role={row.role} size={22} />
      <div class="who">
        <p class="name">{row.name}</p>
        <p class="meta">{row.role ? `${row.role} of the set` : 'comparison candidate'}{row.source.label && row.source.label !== row.name ? ` · VSP ${row.source.label}` : ''}</p>
      </div>
    </div>
    <div class="body">
      <figure class="thumb">
        {#if frame && at && levels}
          <canvas bind:this={canvas} style:width="{SIZE}px" style:height="{SIZE}px" aria-label="Pixels around {row.name}, display levels"></canvas>
          <svg class="ap" viewBox="0 0 {SIZE} {SIZE}" aria-hidden="true">
            {#if apertureR}<circle cx={SIZE / 2} cy={SIZE / 2} r={apertureR * k} class="in" />{/if}
            {#if annulusIn}<circle cx={SIZE / 2} cy={SIZE / 2} r={annulusIn * k} class="an" />{/if}
            {#if annulusOut}<circle cx={SIZE / 2} cy={SIZE / 2} r={annulusOut * k} class="an" />{/if}
          </svg>
        {:else}
          <div class="nothumb">{at ? 'No frame on screen' : 'Not on this frame'}</div>
        {/if}
        <figcaption class="num">{apArc}</figcaption>
      </figure>
      <Readouts {items} cols={2} />
    </div>
    {#if history.length > 1}
      <div class="hist" role="group" aria-label="Recent stars">
        {#each history as h (h.key)}
          <button type="button" class:on={h.key === row.key} aria-pressed={h.key === row.key} aria-label={h.name ?? h.label} title={h.name ?? h.label} onclick={() => onpick?.(h.key)}
            ><RoleGlyph role={h.role ?? null} size={12} />{h.label}</button
          >
        {/each}
      </div>
    {/if}
  </div>
{:else}
  <p class="empty">Click a star on the image, or a row of the candidates table. The last five stay here.</p>
{/if}

<style>
  .insp {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    width: 100%;
    min-width: 300px;
  }
  .id {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .who {
    min-width: 0;
  }
  .name {
    margin: 0;
    overflow: hidden;
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-l);
    font-weight: var(--weight-medium);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .meta {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .body {
    display: grid;
    grid-template-columns: 108px minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
  }
  .thumb {
    position: relative;
    width: 108px;
    margin: 0;
  }
  canvas,
  .nothumb {
    display: block;
    width: 108px;
    height: 108px;
    box-sizing: border-box;
    border: var(--border-w) solid var(--border-soft);
    background: var(--viewer-bg);
  }
  .nothumb {
    display: grid;
    place-items: center;
    padding: var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    text-align: center;
  }
  .ap {
    position: absolute;
    top: 0;
    left: 0;
    width: 108px;
    height: 108px;
    pointer-events: none;
  }
  .ap circle {
    fill: none;
    stroke: var(--overlay-label);
    stroke-width: 1;
  }
  .ap .an {
    stroke-dasharray: 2 3;
  }
  figcaption {
    margin-top: 2px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    text-align: center;
  }
  .hist {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
  }
  .hist button {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    height: 22px;
    max-width: 120px;
    padding: 0 var(--space-2);
    overflow: hidden;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
  }
  .hist button:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .hist button.on {
    border-color: var(--border);
    background: var(--toggled-bg);
    color: var(--fg);
  }
  .hist button:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .empty {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>
