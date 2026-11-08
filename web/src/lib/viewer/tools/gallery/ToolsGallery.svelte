<!--
  Component gallery, wave 4, viewer tools and palettes (development only, part of
  /?gallery=1): the display palettes (OKLCH Fire and Ice, lightness = the stretched value),
  View options, the Statistics card, the viewer's context menu, the HUD compass and scale
  bar, on deterministic synthetic data. Sections are [data-gallery="w4-<name>"].
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import Menu from '../../../components/Menu.svelte';
  import type { FrameMetricsRecord } from '../../../imaging/modes/exposure';
  import SkyHud from '../../hud/SkyHud.svelte';
  import type { TanWcs } from '../../hud/wcs';
  import { PALETTE_LABELS, PALETTES, paletteGradient } from '../../palettes/lut';
  import { histogram16 } from '../../stretch';
  import { regionStats } from '../region';
  import StatisticsCard from '../StatisticsCard.svelte';
  import { ViewerTools } from '../tools.svelte';
  import { viewerMenuItems } from '../viewermenu';
  import ViewOptions from '../ViewOptions.svelte';
  import { cfaSites } from '../../palettes/cfa';

  let nightRed = $state(false);
  onMount(() => {
    const read = () => (nightRed = document.documentElement.dataset.theme === 'night-red');
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  });

  // A deterministic 12-bit-in-16 GRBG frame: sky 1 800 ± noise, a few stars, one clipped.
  const W = 120;
  const H = 80;
  const px = new Uint16Array(W * H);
  let seed = 7;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const site = (y % 2) * 2 + (x % 2);
      const sky = site === 1 ? 1500 : site === 2 ? 1300 : 1800;
      let v = sky + (rnd() - 0.5) * 120;
      for (const [sx, sy, a] of [
        [30, 20, 9000],
        [80, 50, 30000],
        [60, 30, 90000],
      ]) {
        v += a * Math.exp(-((x - sx) ** 2 + (y - sy) ** 2) / 6);
      }
      px[y * W + x] = Math.min(65520, Math.round(v / 16) * 16);
    }
  }
  const histogram = histogram16(px);
  const metrics: FrameMetricsRecord = { seq: 1284, hfd_px: 2.31, fwhm_px: 2.8, eccentricity: 0.142, star_count: 212, n_detected: 187, plane: 'green' };
  const region = regionStats(px, W, H, 1, { x0: 40, y0: 10, x1: 100, y1: 70 }, { sites: cfaSites('GRBG'), threshold: 60000 });

  const memory = () => {
    const m = new Map<string, string>();
    return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
  };
  const tools = new ViewerTools(memory());
  const toolsFire = new ViewerTools(memory());
  toolsFire.setPalette('fire');
  toolsFire.setPreview('r');

  const menuItems = viewerMenuItems({
    pixel: { x: 512, y: 1033 },
    sky: { raHours: 5.5881, decDeg: -5.3911 },
    keys: { fit: 'F', one: '1', region: 'R' },
    canIdentify: true,
    hasSelection: false,
  });

  // Seestar-like solutions: 3.7″/px, north down / east right on the un-rotated frame (as a raw frame reads).
  const WCS: TanWcs = { crval: [300.78, 58.91], crpix: [1080.5, 1920.5], cd: [1.0191e-3, 3.52e-5, -3.55e-5, 1.0194e-3] };
  const FRAME = { width: 2160, height: 3840 };
</script>

<section data-gallery="w4-palettes" id="w4-palettes">
  <h2>Display palettes <span>OKLab lightness of every entry = the stretched value (Fire, Ice); Night Red draws Neutral only (D30)</span></h2>
  <div class="row">
    {#each PALETTES as p (p)}
      <figure>
        <span class="ramp" style:background={nightRed ? 'linear-gradient(90deg, #000000, var(--viewer-tint))' : paletteGradient(p, 17)}></span>
        <figcaption>{PALETTE_LABELS[p]}{nightRed && p !== 'neutral' ? ' · off in Night Red' : ''}</figcaption>
      </figure>
    {/each}
  </div>
</section>

<section data-gallery="w4-view-options" id="w4-view-options">
  <h2>View options <span>preview, palette, rotation, crosshair, loupe, clipping; display only</span></h2>
  <div class="row top">
    <figure><ViewOptions {tools} kind="cfa" rotation="auto" onrotation={() => {}} {nightRed} threshold={60000} saturationKey="C" preview /><figcaption>colour sensor, defaults</figcaption></figure>
    <figure><ViewOptions tools={toolsFire} kind="cfa" rotation="90" onrotation={() => {}} {nightRed} threshold={60000} saturationKey="C" preview /><figcaption>R plane, Fire (Neutral in Night Red)</figcaption></figure>
    <figure><ViewOptions {tools} kind="mono" rotation="0" onrotation={() => {}} {nightRed} threshold={null} preview /><figcaption>mono frame, no full well</figcaption></figure>
  </div>
</section>

<section data-gallery="w4-statistics" id="w4-statistics">
  <h2>Statistics card <span>D9: hidden by default, I shows it; raw samples, ADC depth from the quantization step</span></h2>
  <div class="row top">
    <figure class="card">
      <StatisticsCard histogram={histogram} seq={1284} cfa metrics={metrics} {region} regionOn starRadius={5} onradius={async () => {}} />
      <figcaption>region on, metrics of this frame</figcaption>
    </figure>
    <figure class="card">
      <StatisticsCard histogram={histogram} seq={1285} cfa metrics={metrics} region={null} regionOn={false} starRadius={5} onregion={() => {}} />
      <figcaption>metrics one frame behind, region off</figcaption>
    </figure>
  </div>
</section>

<section data-gallery="w4-menu" id="w4-menu">
  <h2>Viewer context menu <span>right-click, Shift+F10, Menu key; token-drawn (Night Red holds)</span></h2>
  <div class="row top">
    <figure><Menu open preview previewActive={2} items={menuItems} label="Image" minWidth={300} /><figcaption>field identified</figcaption></figure>
  </div>
</section>

<section data-gallery="w4-sky" id="w4-sky">
  <h2>HUD compass and scale bar <span>from the WCS, turned with the display; letters upright; the shortest round length ≥ 56 px</span></h2>
  <div class="row">
    {#each [0, 1] as turns (turns)}
      <figure>
        <div class="sky-demo">
          <SkyHud wcs={WCS} frame={FRAME} turns={turns as 0 | 1} scale={turns ? 0.25 : 0.12} compassTop={8} compassRight={8} barLeft={8} barBottom={8} />
        </div>
        <figcaption>{turns ? 'auto rotation (90°), 25 %' : 'no rotation, 12 %'}</figcaption>
      </figure>
    {/each}
  </div>
</section>

<style>
  section {
    padding: var(--space-5) 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  h2 {
    margin: 0 0 var(--space-4);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  h2 span {
    margin-left: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-regular);
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-5);
  }
  .row.top {
    align-items: flex-start;
  }
  figure {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
    margin: 0;
  }
  figcaption {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .ramp {
    display: block;
    width: 220px;
    height: 16px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
  }
  .card {
    width: 400px;
  }
  .sky-demo {
    position: relative;
    width: 260px;
    height: 120px;
    border: var(--border-w) solid var(--border);
    background: var(--viewer-bg);
  }
</style>
