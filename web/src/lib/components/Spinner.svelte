<!--
  Busy mark (BRAND 8): the logo-like arc, 1.5 stroke, 0.9 s per turn, in currentColor; a
  still arc under reduced motion. Decorative: say what is busy in text or aria-busy next to
  it. The same drawing as the busy state of Control.svelte, for places that are not a button
  (a card title while a catalogue identity is looked up, a popover row while catalogues load).
-->
<script lang="ts">
  import { reducedMotion } from './motion.svelte';

  interface Props {
    size?: number;
  }
  let { size = 12 }: Props = $props();
</script>

<svg class="spinner" class:still={reducedMotion()} viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
  <path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" />
</svg>

<style>
  .spinner {
    flex: none;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    stroke-linecap: round;
    animation: spin 0.9s linear infinite;
  }
  .still {
    animation: none;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
