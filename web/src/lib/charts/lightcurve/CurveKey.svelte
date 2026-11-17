<!--
  A light-curve legend glyph, drawn as the plot draws it (BRAND 10: the legend
  is in the header, never over the data): the role shape filled (measured),
  hollow (suspect), an x (saturated), a band swatch (trailing mean ± 1 sigma) or
  a dashed line (a reference). Decorative: the key's text names it.
-->
<script lang="ts">
  import { shapePath, type Shape } from '../uplot/markers';

  interface Props {
    shape: Shape;
    /** A CSS colour, normally var(--chart-1..3). */
    color: string;
    variant?: 'filled' | 'hollow' | 'cross' | 'band' | 'line';
    size?: number;
  }
  let { shape, color, variant = 'filled', size = 10 }: Props = $props();
</script>

<svg class="key-glyph" viewBox="0 0 20 20" width={size} height={size} aria-hidden="true" style:--c={color}>
  {#if variant === 'cross'}
    <path class="stroke" d="M5 5 15 15M5 15 15 5" stroke-width="2.4" stroke-linecap="round" />
  {:else if variant === 'band'}
    <rect class="band" x="1" y="5" width="18" height="10" rx="1" />
    <path class="stroke" d="M1 10h18" stroke-width="1.6" stroke-dasharray="3 2.5" />
  {:else if variant === 'line'}
    <path class="stroke" d="M1 10h18" stroke-width="2" stroke-dasharray="4 3" />
  {:else if variant === 'hollow'}
    <path class="stroke" d={shapePath(shape)} stroke-width="1.8" stroke-linejoin="round" />
  {:else}
    <path class="fill" d={shapePath(shape)} />
  {/if}
</svg>

<style>
  .key-glyph {
    display: block;
    flex: none;
    overflow: visible;
  }
  .fill {
    fill: var(--c);
  }
  .stroke {
    fill: none;
    stroke: var(--c);
  }
  .band {
    fill: var(--c);
    opacity: 0.28;
  }
</style>
