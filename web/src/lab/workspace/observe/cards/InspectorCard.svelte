<!--
  Inspector (functional-spaces P5): the selected star's details, so the
  on-image card can stay small. Identity and role, catalogue values, the
  measurements on the frame on screen (peak, SNR), the neighbours inside the
  aperture (blend risk) and an APERTURE THUMBNAIL: the frame's own pixels
  around the star, stretched with the display levels and drawn in the
  viewer tint (red-only in Night Red), with the aperture and the sky
  annulus. The last five selections stay one click away for comparing.
-->
<script lang="ts">
  import { stretchValue } from '../../../../lib/viewer/stretch';
  import { shapePath } from '../../charts/plugins';
  import { env } from '../../model/env.svelte';
  import { resolveColor } from '../../../research/tokens';
  import { sim, ws } from '../../model/app.svelte';
  import { APERTURE_PX, FRAME_H, FRAME_W, NAMED_STARS, neighboursInAperture, sepArcmin, STARS, TARGET_PX } from '../../model/field';
  import { fixed, int, signed } from '../../model/format';
  import Readouts from '../../ui/Readouts.svelte';

  const target = NAMED_STARS.find((s) => s.role === 'target')!;
  const star = $derived(ws.selected !== null ? (STARS.find((s) => s.id === ws.selected) ?? null) : null);
  const peak = $derived(star ? (sim.measured.peaks[star.id] ?? NaN) : NaN);
  const nbrs = $derived(star ? neighboursInAperture(star, APERTURE_PX) : []);

  const items = $derived(
    star
      ? [
          { k: 'V', v: fixed(star.v, 2), unit: 'mag' },
          { k: 'B−V', v: star.bv !== undefined ? fixed(star.bv, 2) : '—', unit: star.bv !== undefined ? `Δ ${signed(star.bv - (target.bv ?? 0), 2)}` : '' },
          { k: 'Separation', v: fixed(sepArcmin(star, TARGET_PX), 1), unit: '′ from target' },
          { k: 'Peak', v: Number.isFinite(peak) ? (peak >= 65535 ? 'clipped' : int(peak)) : '—', unit: 'ADU' },
        ]
      : [],
  );

  let canvas: HTMLCanvasElement | undefined = $state();
  const N = 41; // frame px around the star
  const SIZE = 104; // css px

  $effect(() => {
    void env.theme;
    const f = sim.frame;
    const s = star;
    const lv = ws.autoStretch || !ws.stretch ? ws.display?.auto : ws.stretch;
    if (!canvas || !f || !s || !lv) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = SIZE * dpr;
    canvas.height = SIZE * dpr;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const tint = resolveColor(getComputedStyle(canvas).getPropertyValue('--viewer-tint').trim() || '#fff');
    const img = ctx.createImageData(N, N);
    const cx = Math.round(s.x);
    const cy = Math.round(s.y);
    const h = (N - 1) / 2;
    // The display is turned 90° clockwise: sample so the thumbnail matches the image.
    for (let v = 0; v < N; v++) {
      for (let u = 0; u < N; u++) {
        const x = cx + (v - h);
        const y = cy - (u - h);
        const o = (v * N + u) * 4;
        let val = 0;
        if (x >= 0 && y >= 0 && x < FRAME_W && y < FRAME_H) val = stretchValue(f.pixels[y * FRAME_W + x], lv);
        img.data[o] = val * tint[0];
        img.data[o + 1] = val * tint[1];
        img.data[o + 2] = val * tint[2];
        img.data[o + 3] = 255;
      }
    }
    const tmp = document.createElement('canvas');
    tmp.width = N;
    tmp.height = N;
    tmp.getContext('2d')?.putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(tmp, 0, 0, SIZE * dpr, SIZE * dpr);
  });

  const k = SIZE / 41;
</script>

{#if star}
  <div class="insp">
    <div class="id">
      {#if star.role}
        <svg viewBox="0 0 20 20" class="role {star.role}" aria-label={star.role}><path d={shapePath(star.role === 'target' ? 'circle' : star.role === 'check' ? 'triangle' : 'square')} /></svg>
      {/if}
      <div>
        <p class="name">{star.name ?? 'Field star'}</p>
        <p class="meta">{star.role ? `${star.role} · ` : 'candidate · '}VSP sequence (synthetic)</p>
      </div>
    </div>
    <div class="body">
      <div class="thumb">
        <canvas bind:this={canvas} style:width="{SIZE}px" style:height="{SIZE}px" aria-label="Pixels around {star.name ?? 'the star'}, display levels"></canvas>
        <svg class="ap" viewBox="0 0 {SIZE} {SIZE}" aria-hidden="true">
          <circle cx={SIZE / 2} cy={SIZE / 2} r={APERTURE_PX * k} class="in" />
          <circle cx={SIZE / 2} cy={SIZE / 2} r={20 * k} class="an" />
        </svg>
        <span class="cap num">{APERTURE_PX} px · 31″</span>
      </div>
      <Readouts {items} cols={2} />
    </div>
    <p class="nbr">
      <span class="lab-caps">In the aperture</span>
      {#if nbrs.length}
        {#each nbrs as n (n.id)}<span class="num">V {fixed(n.v, 1)} · {fixed(Math.hypot(n.x - star.x, n.y - star.y) * 2.39, 0)}″ away</span>{/each}
        <span class="warn">blend risk</span>
      {:else}
        <span>no catalogue star brighter than V {fixed(star.v + 3, 1)}</span>
      {/if}
    </p>
    {#if ws.history.length > 1}
      <div class="hist" aria-label="Recent selections">
        {#each ws.history as id (id)}
          {@const h = STARS.find((s) => s.id === id)}
          <button type="button" class:on={id === ws.selected} onclick={() => ws.select(id)}>{h?.name?.slice(-3) ?? `#${id}`}</button>
        {/each}
      </div>
    {/if}
  </div>
{:else}
  <p class="empty">Click a star on the image, or a row of the candidates table. The last five selections stay here.</p>
{/if}

<style>
  .insp {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .id {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .role {
    width: 22px;
    height: 22px;
    flex: none;
  }
  .role path {
    fill: none;
    stroke-width: 1.6;
  }
  .role.target path {
    stroke: var(--role-target);
  }
  .role.comparison path {
    stroke: var(--role-comparison);
  }
  .role.check path {
    stroke: var(--role-check);
  }
  .name {
    margin: 0;
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-l);
    font-weight: var(--weight-medium);
  }
  .meta {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .body {
    display: grid;
    grid-template-columns: 104px 1fr;
    gap: var(--space-4);
    align-items: start;
  }
  .thumb {
    position: relative;
    width: 104px;
  }
  canvas {
    display: block;
    border: var(--border-w) solid var(--border-soft);
    background: var(--viewer-bg);
  }
  .ap {
    position: absolute;
    top: 0;
    left: 0;
    width: 104px;
    height: 104px;
    pointer-events: none;
  }
  .ap .in {
    fill: none;
    stroke: var(--overlay-label);
    stroke-width: 1;
  }
  .ap .an {
    fill: none;
    stroke: var(--overlay-label);
    stroke-width: 1;
    stroke-dasharray: 2 3;
  }
  .cap {
    display: block;
    margin-top: 2px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    text-align: center;
  }
  .nbr {
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1) var(--space-2);
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .nbr .num {
    font-family: var(--font-mono);
  }
  .warn {
    padding: 0 var(--space-1);
    border: var(--border-w) solid var(--warning);
    border-radius: var(--radius-s);
  }
  .hist {
    display: flex;
    gap: var(--space-1);
  }
  .hist button {
    height: 22px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    cursor: pointer;
  }
  .hist button.on {
    border-color: var(--border);
    background: var(--toggled-bg);
    color: var(--fg);
  }
  .empty {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>
