<!--
  Segmented choice, refreshed (proposal over lib Segmented):

  - Indicator: one raised block that slides to the chosen segment (Tween,
    120 ms, --ease-standard; instant under reduced motion). Orientation only:
    the chosen value is already applied when the block starts to move.
  - Segments: text, icon, or a value with its unit in mono ("2 °/s").
  - activation "manual" for hardware choices (filter wheel, jog rate): the
    arrows move focus, Space / Enter chooses, so walking across the wheel's
    slots with the keyboard never moves the wheel three times. "auto"
    (WAI-ARIA radio default) for display choices.
  - A busy segment (the wheel moving to it) shows the spinner; the others
    are unavailable with the reason.
  Selected = fill --toggled-bg, text --fg, edge --border: a segmented
  choice always holds one value, so no brass (BRAND 8).
-->
<script lang="ts" generics="T extends string">
  import { cubicOut } from 'svelte/easing';
  import { Tween } from 'svelte/motion';
  import Icon from '../../../lib/components/Icon.svelte';
  import { dur, reduced } from '../env.svelte';
  import { tip } from '../tip';
  import type { SegOption } from '../types';

  interface Props {
    label: string;
    options: readonly SegOption<T>[];
    value: T;
    onchange?: (value: T) => void;
    size?: 's' | 'm';
    activation?: 'auto' | 'manual';
    /** The value being applied (spinner on it, the rest unavailable). */
    busyValue?: T | null;
    busyReason?: string;
    /** The whole control is unavailable, with this reason. */
    disabledReason?: string | null;
    vertical?: boolean;
    /** Stretch the segments to the container's width. */
    fill?: boolean;
    mono?: boolean;
  }

  let {
    label,
    options,
    value = $bindable(),
    onchange,
    size = 'm',
    activation = 'auto',
    busyValue = null,
    busyReason = 'Wait for the change to finish',
    disabledReason = null,
    vertical = false,
    fill = false,
    mono = false,
  }: Props = $props();

  let root: HTMLDivElement | undefined = $state();
  let focusIndex = $state(-1);
  const box = new Tween({ x: 0, y: 0, w: 0, h: 0 }, { duration: 120, easing: cubicOut });
  let measured = $state(false);

  const selectedIndex = $derived(options.findIndex((o) => o.value === value));

  function reasonOf(o: SegOption<T>): string | null {
    if (disabledReason) return disabledReason;
    if (busyValue !== null && o.value !== busyValue) return busyReason;
    return o.disabledReason ?? null;
  }

  function measure(instant: boolean): void {
    const btn = root?.querySelector<HTMLElement>(`[data-index="${selectedIndex}"]`);
    if (!btn) return;
    const next = { x: btn.offsetLeft, y: btn.offsetTop, w: btn.offsetWidth, h: btn.offsetHeight };
    void box.set(next, { duration: instant || !measured ? 0 : dur(120) });
    measured = true;
  }

  $effect(() => {
    void selectedIndex;
    void options.length;
    measure(false);
  });

  $effect(() => {
    if (!root || typeof ResizeObserver !== 'function') return;
    const ro = new ResizeObserver(() => measure(true));
    ro.observe(root);
    return () => ro.disconnect();
  });

  function choose(i: number): void {
    const o = options[i];
    if (!o || reasonOf(o) || o.value === value) return;
    value = o.value;
    onchange?.(o.value);
  }

  function onKey(e: KeyboardEvent, i: number): void {
    const prevKeys = vertical ? ['ArrowUp'] : ['ArrowLeft'];
    const nextKeys = vertical ? ['ArrowDown'] : ['ArrowRight'];
    let j = -1;
    if (prevKeys.includes(e.key) || e.key === (vertical ? 'ArrowLeft' : 'ArrowUp')) j = (i - 1 + options.length) % options.length;
    else if (nextKeys.includes(e.key) || e.key === (vertical ? 'ArrowRight' : 'ArrowDown')) j = (i + 1) % options.length;
    else if (e.key === 'Home') j = 0;
    else if (e.key === 'End') j = options.length - 1;
    else if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      choose(i);
      return;
    } else return;
    e.preventDefault();
    focusIndex = j;
    root?.querySelector<HTMLElement>(`[data-index="${j}"]`)?.focus();
    if (activation === 'auto') choose(j);
  }

  const tabIndexOf = (i: number) => (i === (focusIndex >= 0 ? focusIndex : Math.max(0, selectedIndex)) ? 0 : -1);
</script>

<div
  class="seg s-{size}"
  class:vertical
  class:fill
  class:mono
  class:is-off={!!disabledReason}
  role="radiogroup"
  aria-label={label}
  aria-orientation={vertical ? 'vertical' : 'horizontal'}
  bind:this={root}
>
  {#if measured && selectedIndex >= 0}
    <span
      class="indicator"
      aria-hidden="true"
      style:transform="translate({box.current.x}px, {box.current.y}px)"
      style:width="{box.current.w}px"
      style:height="{box.current.h}px"
    ></span>
  {/if}
  {#each options as o, i (o.value)}
    {@const reason = reasonOf(o)}
    {@const busy = busyValue === o.value}
    <button
      type="button"
      role="radio"
      data-index={i}
      class="opt"
      class:icon-only={o.iconOnly}
      class:inert={!!reason}
      aria-checked={o.value === value}
      aria-disabled={reason ? true : undefined}
      aria-busy={busy || undefined}
      aria-label={o.iconOnly ? o.label : undefined}
      tabindex={tabIndexOf(i)}
      onclick={() => choose(i)}
      onkeydown={(e) => onKey(e, i)}
      onfocus={() => (focusIndex = i)}
      use:tip={{ text: o.label, reason, disabled: !o.iconOnly && !reason, placement: vertical ? 'right' : 'bottom' }}
    >
      {#if busy}
        <svg class="spinner" class:still={reduced()} viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
          <path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" />
        </svg>
      {:else if o.icon}
        <Icon name={o.icon} size={size === 's' ? 14 : 16} />
      {/if}
      {#if !o.iconOnly}<span class="label">{o.label}</span>{/if}
      {#if o.detail}<span class="detail">{o.detail}</span>{/if}
    </button>
  {/each}
</div>

<style>
  .seg {
    --seg-h: 26px;
    position: relative;
    display: inline-flex;
    gap: 2px;
    padding: 2px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    isolation: isolate;
  }
  .s-s {
    --seg-h: 20px;
  }
  .vertical {
    flex-direction: column;
  }
  .fill {
    display: flex;
    width: 100%;
  }
  .fill .opt {
    flex: 1 1 0;
  }

  .indicator {
    position: absolute;
    top: 0;
    left: 0;
    z-index: 0;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--toggled-bg);
    pointer-events: none;
  }

  .opt {
    position: relative;
    z-index: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    min-width: var(--seg-h);
    height: var(--seg-h);
    padding: 0 var(--space-3);
    margin: 0;
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    white-space: nowrap;
    cursor: pointer;
    transition: color var(--duration-fast) var(--ease-standard);
    -webkit-tap-highlight-color: transparent;
  }
  .s-s .opt {
    padding: 0 var(--space-2);
    font-size: var(--text-xs);
  }
  .vertical .opt {
    justify-content: space-between;
  }
  .opt.icon-only {
    padding: 0;
  }
  .mono .label,
  .detail {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .detail {
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-regular);
  }
  .opt:hover:not(.inert) {
    color: var(--fg);
  }
  .opt[aria-checked='true'] {
    color: var(--fg);
  }
  .opt[aria-checked='true'] .detail {
    color: var(--fg);
  }
  .opt:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .opt.inert {
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  .opt.inert .detail {
    color: var(--fg-disabled);
  }
  .is-off .indicator {
    border-color: var(--border-soft);
    background: transparent;
  }
  .opt[aria-busy='true'] {
    color: var(--fg);
  }

  .spinner {
    fill: none;
    stroke: currentColor;
    stroke-width: 1.75;
    stroke-linecap: round;
    animation: spin 0.9s linear infinite;
  }
  .spinner.still {
    animation: none;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
