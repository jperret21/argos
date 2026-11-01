<!--
  A section drawn as a blueprint of its regions, in the 1440 x 900 reference
  frame (SVG viewBox), so the same drawing serves at full size (a section
  the prototype does not build yet) and as a miniature in the overview.
  Region kinds are told apart by fill and edge (tokens), never by hue alone:
  hero = outlined in --fg-muted, band = a texture of fine lines, new
  regions = a corner tick and "new" in words. Font sizes are in reference
  units: about 11 px on screen at the miniature scale.
-->
<script lang="ts">
  import { SECTIONS, type RegionKind } from './sections';
  import type { Section } from '../model/workspace.svelte';

  interface Props {
    section: Section;
    /** 'window': the whole 1440 x 900 frame; 'section': without rail and status bar. */
    crop?: 'window' | 'section';
    mini?: boolean;
  }

  let { section, crop = 'window', mini = false }: Props = $props();

  const def = $derived(SECTIONS.find((s) => s.id === section)!);
  const vb = $derived(crop === 'window' ? '0 0 1440 900' : '92 0 1348 872');
  const f = $derived(mini ? { title: 40, line: 30, tool: 30 } : { title: 15, line: 13, tool: 12 });
  const maxLines = $derived(mini ? 2 : 6);
  const uid = `bp-${Math.random().toString(36).slice(2, 7)}`;

  const fillClass = (k: RegionKind) => `r-${k}`;
</script>

<svg class="bp" class:mini viewBox={vb} preserveAspectRatio="xMidYMid meet" role="img" aria-label="{def.label}: regions of the section">
  <defs>
    <pattern id="{uid}-lines" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="10" class="hatch" />
    </pattern>
  </defs>

  {#if crop === 'window'}
    <!-- Shared chrome: navigation rail and status bar. -->
    <rect x="0" y="0" width="92" height="900" class="r-chrome" />
    {#each ['connection', 'observe', 'plan', 'review'] as s, i (s)}
      <rect x="18" y={70 + i * 70} width="56" height="46" rx="4" class="nav" class:sel={s === section} />
    {/each}
    <rect x="18" y="810" width="56" height="46" rx="4" class="nav" class:sel={section === 'settings'} />
    <rect x="0" y="872" width="1440" height="28" class="r-chrome" />
    {#if mini}
      <text x="110" y="895" class="t-line" font-size={24}>devices · mount · run chip · attention · Log</text>
    {/if}
  {/if}

  <!-- Toolbar row -->
  <rect x="92" y="0" width="1348" height="44" class="r-toolbar" />
  {#if def.views}
    {#each def.views as v, i (v)}
      <rect x={110 + i * (mini ? 130 : 96)} y="8" width={mini ? 122 : 90} height="28" rx="3" class="seg" class:sel={i === (def.id === 'observe' ? 3 : 1)} />
      {#if !mini}<text x={155 + i * 96} y="27" text-anchor="middle" class="t-tool" font-size={f.tool}>{v}</text>{/if}
    {/each}
  {:else}
    {#each def.actions as a, i (a.icon)}
      <rect x={110 + i * (mini ? 150 : 150)} y="8" width={mini ? 140 : 140} height="28" rx="3" class="seg" />
      {#if !mini}<text x={124 + i * 150} y="27" class="t-tool" font-size={f.tool}>{a.label || a.icon}</text>{/if}
    {/each}
  {/if}
  <!-- Right end, identical in every section: command field, Watch, Arrange, Panels -->
  <rect x="1090" y="8" width="230" height="28" rx="3" class="cmd" />
  {#if !mini}<text x="1104" y="27" class="t-tool" font-size={f.tool}>Find an action…   ⌘K</text>{/if}
  {#each [0, 1, 2] as i (i)}
    <rect x={1330 + i * 36} y="8" width="28" height="28" rx="3" class="seg" />
  {/each}
  {#if !mini}
    <text x="1326" y="58" class="t-line" font-size="11">Watch · Arrange · Panels</text>
  {/if}

  <!-- Regions -->
  {#each def.regions as r, i (i)}
    <rect x={r.x + 1} y={r.y + 1} width={r.w - 2} height={r.h - 2} class={fillClass(r.kind)} />
    {#if r.kind === 'band'}
      <rect x={r.x + 1} y={r.y + 1} width={r.w - 2} height={r.h - 2} fill="url(#{uid}-lines)" />
    {/if}
    {#if r.isNew}
      <path d="M{r.x + r.w - 2} {r.y + 2}v{mini ? 46 : 22}M{r.x + r.w - 2} {r.y + 2}h-{mini ? 46 : 22}" class="new" />
    {/if}
    {@const fs = Math.min(f.title, r.h * 0.62)}
    <text x={r.x + (mini ? 18 : 16)} y={r.y + Math.min(mini ? 48 : 26, r.h / 2 + fs * 0.36)} class="t-title" font-size={fs}>{r.title}{r.isNew ? ' · new' : ''}</text>
    {#if r.lines}
      {#each r.lines.slice(0, maxLines) as line, j (j)}
        {#if !mini || r.h > 160}
          <text x={r.x + (mini ? 18 : 16)} y={r.y + (mini ? 92 : 50) + j * (mini ? 38 : 19)} class="t-line" font-size={f.line}>{line}</text>
        {/if}
      {/each}
    {/if}
  {/each}
</svg>

<style>
  .bp {
    display: block;
    width: 100%;
    height: 100%;
    background: var(--bg);
    font-family: var(--font-ui);
  }
  .r-chrome {
    fill: var(--bg-2);
    stroke: var(--border);
    stroke-width: 1;
  }
  .r-toolbar {
    fill: var(--bg);
    stroke: var(--border);
    stroke-width: 1;
  }
  .nav {
    fill: none;
    stroke: var(--border-soft);
    stroke-width: 1.5;
  }
  .nav.sel {
    fill: var(--surface);
    stroke: var(--fg-muted);
  }
  .seg {
    fill: var(--bg-2);
    stroke: var(--border-soft);
    stroke-width: 1;
  }
  .seg.sel {
    fill: var(--surface);
    stroke: var(--border);
  }
  .cmd {
    fill: var(--bg-2);
    stroke: var(--border);
    stroke-width: 1;
  }
  .r-hero {
    fill: var(--bg-2);
    stroke: var(--fg-muted);
    stroke-width: 1.5;
  }
  .r-band,
  .r-strip {
    fill: var(--bg);
    stroke: var(--border);
    stroke-width: 1;
  }
  .r-rail {
    fill: var(--bg-2);
    stroke: var(--border);
    stroke-width: 1;
  }
  .r-drawer {
    fill: var(--bg);
    stroke: var(--border);
    stroke-width: 1;
    stroke-dasharray: 6 4;
  }
  .r-column {
    fill: var(--bg);
    stroke: var(--border-soft);
    stroke-width: 1;
  }
  .hatch {
    stroke: var(--border-soft);
    stroke-width: 1;
  }
  .new {
    fill: none;
    stroke: var(--fg);
    stroke-width: 3;
  }
  .t-title {
    fill: var(--fg);
    font-weight: 600;
  }
  .t-line,
  .t-tool {
    fill: var(--text-muted);
  }
  .mini .r-hero {
    stroke-width: 3;
  }
</style>
