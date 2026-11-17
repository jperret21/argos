<!--
  A role's shape, as on the image (BRAND 6.8, 10): target circle, comparison square, check
  upright triangle, each in its role token; a candidate (no role yet) a dashed square in
  --overlay-other. Decorative unless `label` is given (then role="img").
-->
<script lang="ts">
  import type { Role } from '../../viewer/overlay/layers';

  interface Props {
    role: Role | null;
    size?: number;
    label?: string;
  }
  let { role, size = 14, label }: Props = $props();

  const d = $derived(
    role === 'target'
      ? 'M10 3.5a6.5 6.5 0 1 0 0.001 0Z'
      : role === 'check'
        ? 'M10 2.6 17.6 15.8H2.4Z'
        : 'M4.25 4.25h11.5v11.5H4.25Z',
  );
</script>

<svg
  class="glyph {role ?? 'candidate'}"
  viewBox="0 0 20 20"
  width={size}
  height={size}
  role={label ? 'img' : undefined}
  aria-label={label}
  aria-hidden={label ? undefined : 'true'}
><path {d} /></svg>

<style>
  .glyph {
    display: block;
    flex: none;
  }
  path {
    fill: none;
    stroke-width: 1.6;
    stroke-linejoin: round;
  }
  .target path {
    stroke: var(--role-target);
  }
  .comparison path {
    stroke: var(--role-comparison);
  }
  .check path {
    stroke: var(--role-check);
  }
  .candidate path {
    stroke: var(--overlay-other);
    stroke-dasharray: 2 2;
  }
</style>
