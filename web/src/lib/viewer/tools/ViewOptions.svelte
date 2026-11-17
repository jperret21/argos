<!--
  View options (web/spec/04-viewer-and-image-tools.md 2.2 rows 1.3 #2-3, 1.5 #6, #8-9, 2.3
  "Rail cards"; README M39, M56): the display choices of the viewer, in one popover opened
  from the task band's header (the Display card of the spec became the Framing band in W3;
  the popover is offered in every mode). Every row is display only: the FITS data and every
  measurement keep the raw values (said once, in the footer).

  - Preview: Colour · Raw · R · G · B on a colour sensor's mosaic (Colour by default, Q-O17;
    RGB frames have no Raw; the row is hidden for a mono frame).
  - Palette: Neutral · Negative · Fire · Ice, with the chosen ramp drawn (D11 data ramp).
    Night Red: Neutral only (D30), the others disabled with the reason.
  - Rotation: Auto · 0° · 90° · 180° · 270° (moved here from the band header, as the spec
    places it).
  - Crosshair: Centre · Cursor (Q-O16). Loupe: 2× · 4× · 8× (Q-O23).
  - Clipping: the saturation highlight (C) and its threshold, the profile's full well.
  Token-drawn controls only (Night Red: no native widget).
-->
<script lang="ts">
  import Checkbox from '../../components/Checkbox.svelte';
  import Icon from '../../components/Icon.svelte';
  import Popover from '../../components/Popover.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import { tooltip } from '../../components/tooltip';
  import { int } from '../../format/number';
  import { PREVIEW_LABELS, previewsFor, effectivePreview, type FrameKind, type Preview } from '../palettes/cfa';
  import { PALETTE_LABELS, PALETTES, effectivePalette, paletteGradient, paletteReason, type Palette } from '../palettes/lut';
  import type { RotationMode } from '../rotation';
  import { LOUPE_MAGS, type CrosshairMode, type LoupeMag, type ViewerTools } from './tools.svelte';

  interface Props {
    tools: ViewerTools;
    /** What the frame on screen is (mono frames have no Preview row). */
    kind: FrameKind;
    rotation: RotationMode;
    onrotation: (r: RotationMode) => void;
    nightRed: boolean;
    /** Saturation threshold, ADU (the profile's full well; null: unknown). */
    threshold: number | null;
    /** Shortcut of the saturation toggle (C). */
    saturationKey?: string;
    /** Draw the open popover in place (gallery). */
    preview?: boolean;
  }

  let { tools, kind, rotation, onrotation, nightRed, threshold, saturationKey, preview = false }: Props = $props();

  let open = $state(false);
  let button: HTMLElement | undefined = $state();
  const id = `view-options-${Math.random().toString(36).slice(2, 9)}`;
  const DISPLAY_ONLY = 'Display only: FITS data and measurements are unchanged.';

  const previews = $derived(previewsFor(kind).map((p) => ({ value: p, label: PREVIEW_LABELS[p] })));
  const shownPreview = $derived(effectivePreview(tools.preview, kind));
  const palettes = $derived(PALETTES.map((p) => ({ value: p, label: PALETTE_LABELS[p], disabledReason: paletteReason(p, nightRed) })));
  const drawnPalette = $derived(effectivePalette(tools.palette, nightRed));
  /** Fire and Ice map the luminance: over the colour preview the hues are not drawn. */
  const falseColour = $derived(drawnPalette === 'fire' || drawnPalette === 'ice');
  const previewOptions = $derived(previews.map((p) => (p.value === 'colour' && falseColour ? { ...p, label: 'Colour (luminance)' } : p)));
  const ROTATIONS: { value: RotationMode; label: string }[] = [
    { value: 'auto', label: 'Auto' },
    { value: '0', label: '0°' },
    { value: '90', label: '90°' },
    { value: '180', label: '180°' },
    { value: '270', label: '270°' },
  ];
  const CROSSHAIR: { value: CrosshairMode; label: string }[] = [
    { value: 'centre', label: 'Centre' },
    { value: 'cursor', label: 'Cursor' },
  ];
  const MAGS = LOUPE_MAGS.map((m) => ({ value: String(m), label: `${m}×` }));
  /** What the trigger says while something is not the default (a glance, no need to open). */
  const changed = $derived(
    [shownPreview !== 'colour' && kind !== 'mono' ? PREVIEW_LABELS[shownPreview] : null, drawnPalette !== 'neutral' ? PALETTE_LABELS[drawnPalette] : null]
      .filter(Boolean)
      .join(' · '),
  );
</script>

{#snippet body()}
  <div class="rows">
    {#if previews.length}
      <span class="k" id="{id}-preview">Preview</span>
      <span class="v" use:tooltip={{ text: `Which samples of the colour sensor are drawn. ${DISPLAY_ONLY}`, placement: 'left' }}>
        <Segmented label="Preview" options={previewOptions} value={shownPreview} size="s" onchange={(v) => tools.setPreview(v as Preview)} />
      </span>
    {/if}
    <span class="k">Palette</span>
    <span class="v col">
      <Segmented label="Palette" options={palettes} value={drawnPalette} size="s" onchange={(v) => tools.setPalette(v as Palette)} />
      <span class="ramp" style:background={nightRed ? 'linear-gradient(90deg, #000000, var(--viewer-tint))' : paletteGradient(drawnPalette)} role="img" aria-label="{PALETTE_LABELS[drawnPalette]} ramp, black to white"></span>
      {#if nightRed && tools.palette !== 'neutral'}
        <span class="note">Your {PALETTE_LABELS[tools.palette]} choice returns outside Night Red.</span>
      {:else if falseColour && previews.length && shownPreview === 'colour'}
        <span class="note">Applies to the luminance: the colour preview is drawn in {PALETTE_LABELS[drawnPalette]}.</span>
      {/if}
    </span>
    <span class="k">Rotation</span>
    <span class="v"><Segmented label="Display rotation (clockwise)" options={ROTATIONS} value={rotation} size="s" mono onchange={(r) => onrotation(r)} /></span>
    <span class="k">Crosshair</span>
    <span class="v"><Segmented label="Crosshair" options={CROSSHAIR} value={tools.crosshairMode} size="s" onchange={(v) => tools.setCrosshairMode(v as CrosshairMode)} /></span>
    <span class="k">Loupe</span>
    <span class="v"><Segmented label="Loupe magnification" options={MAGS} value={String(tools.loupeMag)} size="s" mono onchange={(v) => tools.setLoupeMag(Number(v) as LoupeMag)} /></span>
    <span class="k">Clipping</span>
    <span class="v">
      <Checkbox
        size="s"
        label={threshold !== null ? `Highlight pixels ≥ ${int(threshold)} ADU` : 'Highlight clipped pixels'}
        detail={threshold !== null ? `the profile's full well, tested on raw samples${saturationKey ? ` · ${saturationKey}` : ''}` : 'the profile gives no full well'}
        checked={tools.saturation}
        disabledReason={threshold === null ? 'the telescope profile has no full well' : null}
        onchange={(on) => tools.toggleSaturation(on)}
      />
    </span>
  </div>
{/snippet}

{#snippet footer()}
  <p class="foot">{DISPLAY_ONLY}</p>
{/snippet}

{#if preview}
  <Popover open title="View options" preview width={360} {footer}>{@render body()}</Popover>
{:else}
  <span bind:this={button} class="anchor">
    <button
      type="button"
      class="trigger"
      class:on={open}
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-controls={id}
      onclick={() => (open = !open)}
      use:tooltip={{ text: `View options: preview, palette, rotation, crosshair, loupe, clipping. ${DISPLAY_ONLY}`, placement: 'top', disabled: open }}
    >
      <span>View</span>
      {#if changed}<span class="state num">{changed}</span>{/if}
      <Icon name="disclosure" size={16} />
    </button>
  </span>
  <Popover bind:open anchor={button} title="View options" {id} width={360} placement="top-start" {footer}>{@render body()}</Popover>
{/if}

<style>
  .anchor {
    display: inline-flex;
  }
  .trigger {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 22px;
    padding: 0 var(--space-1) 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
    cursor: pointer;
  }
  .trigger :global(.icon) {
    color: var(--fg-muted);
  }
  .trigger:hover,
  .trigger.on {
    background: var(--hover-bg);
  }
  .trigger:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .state {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
  }
  .rows {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: var(--space-3) var(--space-3);
  }
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .v {
    min-width: 0;
  }
  .col {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .ramp {
    display: block;
    height: 6px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
  }
  .note {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .foot {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
