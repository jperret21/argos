<!--
  Inline SVG icon from the design system (web/src/design/icons/<name>.svg).

  Icons are bundled at build time (import.meta.glob, eager, raw): no runtime
  fetch, works offline, and they inherit `color` (currentColor), so every
  theme including Night Red applies without per-icon variants.
  Decorative by default (aria-hidden); pass `label` for a standalone,
  meaningful icon. An unknown name renders a visible dashed "?" placeholder.
-->
<script lang="ts" module>
  const modules = import.meta.glob('../../design/icons/*.svg', {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>;

  const ICONS: Record<string, string> = {};
  for (const [path, svg] of Object.entries(modules)) {
    ICONS[path.slice(path.lastIndexOf('/') + 1, -'.svg'.length)] = svg;
  }

  /** Every icon id available in this build, sorted. */
  export const ICON_IDS: readonly string[] = Object.keys(ICONS).sort();

  export function hasIcon(name: string): boolean {
    return Object.hasOwn(ICONS, name);
  }

  export type IconSize = number | 's' | 'm' | 'l';

  const warned = new Set<string>();
</script>

<script lang="ts">
  interface Props {
    /** Icon id (kebab-case file name without .svg). */
    name: string;
    /** Pixels, or a design token size: s (16), m (20), l (24). */
    size?: IconSize;
    /** Accessible name; omit for decorative icons. */
    label?: string;
    class?: string;
  }

  let { name, size = 20, label, class: className = '' }: Props = $props();

  const svg = $derived(hasIcon(name) ? ICONS[name] : undefined);
  const dimension = $derived(typeof size === 'number' ? `${size}px` : `var(--icon-${size})`);

  $effect(() => {
    if (!svg && import.meta.env.DEV && !warned.has(name)) {
      warned.add(name);
      console.warn(`[Icon] unknown icon "${name}" (no web/src/design/icons/${name}.svg)`);
    }
  });
</script>

{#if svg}
  <span
    class="icon {className}"
    style:--icon-size={dimension}
    role={label ? 'img' : undefined}
    aria-label={label}
    aria-hidden={label ? undefined : 'true'}
  >
    {@html svg}
  </span>
{:else}
  <span
    class="icon missing {className}"
    style:--icon-size={dimension}
    role={label ? 'img' : undefined}
    aria-label={label}
    aria-hidden={label ? undefined : 'true'}
    title={`missing icon: ${name}`}
    data-missing-icon={name}
  >
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <rect x="3.5" y="3.5" width="17" height="17" rx="2" stroke-dasharray="3 2.2" />
      <path d="M9.6 9.4a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.2.9-1.2 1.7v.4" stroke-linecap="round" />
      <circle cx="12" cy="16.6" r="0.4" fill="currentColor" />
    </svg>
  </span>
{/if}

<style>
  .icon {
    display: inline-flex;
    flex: none;
    width: var(--icon-size);
    height: var(--icon-size);
    line-height: 0;
    color: inherit;
  }

  .icon :global(svg) {
    display: block;
    width: 100%;
    height: 100%;
    overflow: visible;
  }

  .missing {
    color: var(--danger);
  }
</style>
