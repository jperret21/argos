<!--
  Segmented choice (radio group) drawn with tokens: no native <select>, whose
  pop-up would draw grey in Night Red (BRAND 4.3). Extended in wave 3 from
  src/lab/controls/components/Seg.svelte (web/lab/PROPOSAL.md 3.3, 6):

  - Indicator: one raised block that slides to the chosen segment for
    --duration-fast (instant under reduced motion, through the tokens), AFTER
    the value is applied: orientation only, never a preview of the choice.
  - Segments: text, icon + text, icon only (the label is the accessible name
    and the tooltip), or a value with its unit in mono ("2°/s").
  - activation "manual" for hardware (filter wheel, jog rate): the arrows
    move focus, Space / Enter chooses, so walking across the wheel's slots
    never moves it three times. "auto" (the WAI-ARIA radio default, the
    wave-1 behaviour) for display choices.
  - `deferred`: choosing only REQUESTS the value (onchange); the block stays
    on `value` until the caller applies it (the wheel reports its slot).
  - `busyValue`: the value being applied shows a spinner (aria-busy); the
    other segments are unavailable with `busyReason`.
  - Unavailable (`disabledReason`, or one option's own reason): aria-disabled,
    still focusable, the reason in the tooltip and shown on press.
  Selected = fill --toggled-bg, text --fg, edge --border: a segmented choice
  always holds one value, so no brass (BRAND 8). One tab stop (roving).
  The pure rules live in segmented.ts (unit-tested).
-->
<script lang="ts" generics="T extends string">
  import { untrack } from 'svelte';
  import Icon from './Icon.svelte';
  import { reducedMotion } from './motion.svelte';
  import { canChoose, choosesOnMove, segmentKey, segmentReason, tabStop, type Activation, type SegmentOption } from './segmented';
  import { tooltip } from './tooltip';

  interface Props {
    label: string;
    options: readonly SegmentOption<T>[];
    value: T;
    /** Hard-disabled (no reason to give, not focusable). Prefer `disabledReason`. */
    disabled?: boolean;
    /** Called with a chosen value (with `deferred`, the request). */
    onchange?: (value: T) => void;
    /** 's': 20 px segments for drawer headers, toolbars and dense rows. */
    size?: 's' | 'm';
    activation?: Activation;
    /** Choosing requests the value; `value` changes only when the caller applies it. */
    deferred?: boolean;
    /** The value being applied (spinner on it, the others wait). */
    busyValue?: T | null;
    busyReason?: string;
    /** The whole control is unavailable now, with this reason (still focusable). */
    disabledReason?: string | null;
    vertical?: boolean;
    /** Stretch the segments over the container's width (default: size m, horizontal). */
    fill?: boolean;
    /** Labels in Plex Mono (numbers, slot codes). */
    mono?: boolean;
  }

  let {
    label,
    options,
    value = $bindable(),
    disabled = false,
    onchange,
    size = 'm',
    activation = 'auto',
    deferred = false,
    busyValue = null,
    busyReason,
    disabledReason = null,
    vertical = false,
    fill,
    mono = false,
  }: Props = $props();

  let root: HTMLDivElement | undefined = $state();
  let focusIndex = $state(-1);
  let box: { x: number; y: number; w: number; h: number } | null = $state(null);
  let glide = $state(false);

  const stretch = $derived(fill ?? (size === 'm' && !vertical));
  const selectedIndex = $derived(options.findIndex((o) => o.value === value));
  const ctx = $derived({ disabledReason, busyValue, busyReason });
  const off = $derived(disabled || !!disabledReason);

  function reasonOf(o: SegmentOption<T>): string | null {
    return segmentReason(o, ctx);
  }

  /** Place the block under the selected segment. Reads `box` untracked: the effects that call it must not depend on what it writes. */
  function measure(animate: boolean): void {
    const btn = root?.querySelector<HTMLElement>(`[data-index="${selectedIndex}"]`);
    const prev = untrack(() => box);
    if (!btn) {
      if (prev !== null) box = null;
      return;
    }
    const next = { x: btn.offsetLeft, y: btn.offsetTop, w: btn.offsetWidth, h: btn.offsetHeight };
    if (prev && prev.x === next.x && prev.y === next.y && prev.w === next.w && prev.h === next.h) return;
    glide = animate && prev !== null && !untrack(reducedMotion);
    box = next;
  }

  // The value changed (applied): the block slides there.
  $effect(() => {
    void selectedIndex;
    void options.length;
    measure(true);
  });

  // Layout changes (fonts, rail width): the block follows at once.
  $effect(() => {
    if (!root || typeof ResizeObserver !== 'function') return;
    const ro = new ResizeObserver(() => measure(false));
    ro.observe(root);
    return () => ro.disconnect();
  });

  function choose(i: number): void {
    const o = options[i];
    if (!o || disabled || !canChoose(o, value, ctx)) return;
    if (!deferred) value = o.value;
    onchange?.(o.value);
  }

  function onKey(e: KeyboardEvent, i: number): void {
    if (disabled) return;
    const r = segmentKey(e.key, i, options.length);
    if (!r) return;
    e.preventDefault();
    if ('choose' in r) {
      choose(i);
      return;
    }
    focusIndex = r.move;
    root?.querySelector<HTMLElement>(`[data-index="${r.move}"]`)?.focus();
    if (choosesOnMove(activation)) choose(r.move);
  }

  const stop = $derived(tabStop(focusIndex, selectedIndex, options.length));
</script>

<div
  class="segmented size-{size}"
  class:vertical
  class:stretch
  class:mono
  class:is-off={off}
  class:measured={box !== null}
  role="radiogroup"
  aria-label={label}
  aria-orientation={vertical ? 'vertical' : 'horizontal'}
  aria-disabled={off || undefined}
  aria-busy={busyValue !== null || undefined}
  bind:this={root}
  onfocusout={(e) => {
    if (!root?.contains(e.relatedTarget as Node | null)) focusIndex = -1;
  }}
>
  {#if box}
    <span
      class="indicator"
      class:glide
      aria-hidden="true"
      style:transform="translate({box.x}px, {box.y}px)"
      style:width="{box.w}px"
      style:height="{box.h}px"
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
      class:inert={!!reason || disabled}
      aria-checked={o.value === value}
      aria-disabled={reason ? true : undefined}
      aria-busy={busy || undefined}
      aria-label={o.iconOnly ? o.label : undefined}
      tabindex={i === stop ? 0 : -1}
      {disabled}
      onclick={() => choose(i)}
      onkeydown={(e) => onKey(e, i)}
      onfocus={() => (focusIndex = i)}
      use:tooltip={{
        text: o.label,
        reason,
        disabled: !o.iconOnly && !reason,
        placement: vertical ? 'right' : 'bottom',
      }}
    >
      {#if busy}
        <svg class="spinner" class:still={reducedMotion()} viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
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
  .segmented {
    --seg-h: 24px;
    position: relative;
    display: inline-flex;
    gap: 2px;
    padding: 2px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    isolation: isolate;
  }
  .size-s {
    --seg-h: 20px;
  }
  .stretch {
    display: flex;
  }
  .vertical {
    flex-direction: column;
  }

  /* The raised block: placed under the selected segment, slides after the value is applied. */
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
  .indicator.glide {
    transition:
      transform var(--duration-fast) var(--ease-standard),
      width var(--duration-fast) var(--ease-standard),
      height var(--duration-fast) var(--ease-standard);
  }

  .opt {
    position: relative;
    z-index: 1;
    display: inline-flex;
    flex: 0 0 auto;
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
    font-family: var(--font-ui);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    line-height: 1;
    white-space: nowrap;
    cursor: pointer;
    transition: color var(--duration-fast) var(--ease-standard);
    -webkit-tap-highlight-color: transparent;
  }
  /* Equal shares of a wide container, never less than the label: a cut hardware choice is worse than a wider row. */
  .stretch .opt {
    flex: 1 1 0;
    min-width: max-content;
  }
  .size-s .opt {
    padding: 0 var(--space-2);
    font-size: var(--text-xs);
  }
  .vertical .opt {
    justify-content: space-between;
  }
  .opt.icon-only {
    padding: 0;
  }
  .label {
    overflow: hidden;
    text-overflow: ellipsis;
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
  .opt[aria-checked='true'],
  .opt[aria-checked='true'] .detail,
  .opt[aria-busy='true'] {
    color: var(--fg);
  }
  /* Before the first measure (and without script) the chosen segment draws its own block. */
  .segmented:not(.measured) .opt[aria-checked='true'] {
    border-color: var(--border);
    background: var(--toggled-bg);
  }
  .opt:focus-visible {
    z-index: 2;
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
  /* The checked segment of an unavailable control keeps --fg-disabled text on a flat block. */
  .is-off .indicator,
  .is-off:not(.measured) .opt[aria-checked='true'] {
    border-color: var(--border-soft);
    background: transparent;
  }

  .spinner {
    flex: none;
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
  @media (prefers-reduced-motion: reduce) {
    .spinner {
      animation: none;
    }
  }
</style>
