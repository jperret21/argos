<!--
  The marker shape of a photometric role (BRAND 2.6): circle = target,
  square = comparison, triangle = check; `dot` = a neutral sample. Filled in
  the role colour, or hollow / crossed for the flag keys of a legend.
-->
<script lang="ts">
  import { shapePath, type Shape } from '../core/uplot/markers';

  interface Props {
    shape: Shape;
    /** CSS colour (a token: var(--chart-1)). */
    color: string;
    variant?: 'solid' | 'hollow' | 'cross' | 'line' | 'band' | 'dash';
    size?: number;
  }

  let { shape, color, variant = 'solid', size = 12 }: Props = $props();
</script>

<svg class="glyph" viewBox="0 0 20 20" width={size} height={size} aria-hidden="true">
  {#if variant === 'cross'}
    <path d="M5.5 5.5l9 9M14.5 5.5l-9 9" fill="none" stroke={color} stroke-width="2" stroke-linecap="round" />
  {:else if variant === 'line'}
    <path d="M2 10h16" fill="none" stroke={color} stroke-width="2" />
  {:else if variant === 'dash'}
    <path d="M2 10h4M8 10h4M14 10h4" fill="none" stroke={color} stroke-width="2" />
  {:else if variant === 'band'}
    <rect x="2" y="5" width="16" height="10" fill={color} fill-opacity="0.22" />
    <path d="M2 10h16" fill="none" stroke={color} stroke-width="1.5" stroke-dasharray="2 2" />
  {:else if variant === 'hollow'}
    <path d={shapePath(shape)} fill="none" stroke={color} stroke-width="1.6" />
  {:else}
    <path d={shapePath(shape)} fill={color} />
  {/if}
</svg>

<style>
  .glyph {
    flex: none;
    display: block;
  }
</style>
