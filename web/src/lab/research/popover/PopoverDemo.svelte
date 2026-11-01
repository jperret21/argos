<!--
  Demo 5: the Catalogue layers popover (spec D12) on an Observe toolbar.

  Three implementations of the same panel, chosen automatically or forced:
  - "native": Popover API (top layer, light dismiss, Esc, no z-index) +
    CSS anchor positioning (position-area, position-try-fallbacks) +
    @starting-style for the 180 ms entry. No placement script.
  - "popover + js": Popover API, placed by lib/components/position.ts
    (engines without anchor positioning: WebKitGTK 2.48, Safari < 26).
  - "js": no Popover API (WKWebView in an app linked on a pre-macOS 14 SDK,
    see stack-capabilities.md): fixed element + manual light dismiss.

  Also: one tooltip element for the whole toolbar, re-anchored to the
  hovered or focused button; token-drawn checkbox and range (native ones
  draw white or grey parts, which Night Red forbids).
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import { placeFloating } from '../../../lib/components/position';

  type Mode = 'native' | 'popover-js' | 'js';
  const hasPopover = typeof HTMLElement !== 'undefined' && Object.hasOwn(HTMLElement.prototype, 'popover');
  const hasAnchor = typeof CSS !== 'undefined' && CSS.supports('anchor-name: --a');
  const hasStarting = typeof window !== 'undefined' && 'CSSStartingStyleRule' in window;
  const auto: Mode = hasPopover ? (hasAnchor ? 'native' : 'popover-js') : 'js';

  let forced = $state<Mode | null>(null);
  const mode = $derived<Mode>(forced ?? auto);

  let trigger: HTMLButtonElement;
  let panel: HTMLDivElement;
  let open = $state(false);
  let jsPos = $state<{ x: number; y: number } | null>(null);
  let lastFocusReturned = $state<string>('—');

  interface Layer {
    id: string;
    label: string;
    count: number;
    icon: string;
    on: boolean;
  }
  let layers = $state<Layer[]>([
    { id: 'gaia', label: 'Field stars (Gaia DR3)', count: 1234, icon: 'field-stars', on: true },
    { id: 'vsx', label: 'Variable stars (VSX)', count: 12, icon: 'variable-star', on: true },
    { id: 'gal', label: 'Galaxies', count: 3, icon: 'galaxy', on: false },
    { id: 'neb', label: 'Nebulae', count: 1, icon: 'nebula', on: false },
    { id: 'exo', label: 'Exoplanet hosts', count: 0, icon: 'exoplanet', on: false },
  ]);
  let depth = $state(15);
  const nf = new Intl.NumberFormat('en-GB');

  function place(): void {
    const a = trigger.getBoundingClientRect();
    const r = placeFloating({
      anchor: { left: a.left, top: a.top, width: a.width, height: a.height },
      floating: { width: panel.offsetWidth || 320, height: panel.offsetHeight || 300 },
      viewport: { width: innerWidth, height: innerHeight },
      placement: 'bottom-end',
      gap: 4,
    });
    jsPos = { x: r.x, y: r.y };
  }

  function show(): void {
    if (mode === 'js') {
      open = true;
      requestAnimationFrame(() => {
        place();
        panel.querySelector<HTMLElement>('input')?.focus();
      });
      return;
    }
    panel.showPopover();
  }
  function hide(returnFocus = true): void {
    if (mode === 'js') {
      open = false;
      if (returnFocus) trigger.focus();
      return;
    }
    panel.hidePopover();
  }
  function toggleOpen(): void {
    if (open) hide();
    else show();
  }

  function onToggle(e: Event): void {
    const t = e as ToggleEvent;
    open = t.newState === 'open';
    if (open) {
      if (mode === 'popover-js') place();
      panel.querySelector<HTMLElement>('input')?.focus();
    } else {
      queueMicrotask(() => {
        const a = document.activeElement as HTMLElement | null;
        lastFocusReturned = a === trigger ? 'trigger' : a?.tagName.toLowerCase() ?? 'none';
      });
    }
  }

  // JS mode: light dismiss and Escape by hand (what the Popover API gives for free).
  $effect(() => {
    if (mode !== 'js' || !open) return;
    const down = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!panel.contains(t) && !trigger.contains(t)) hide(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') hide();
    };
    document.addEventListener('pointerdown', down, true);
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('pointerdown', down, true);
      document.removeEventListener('keydown', key);
    };
  });

  // Mode change: close and reset.
  $effect(() => {
    void mode;
    open = false;
    jsPos = null;
    try {
      if (panel?.matches(':popover-open')) panel.hidePopover();
    } catch {
      /* not a popover in js mode */
    }
  });

  // -- One shared tooltip, re-anchored per control --------------------------------
  let tip: HTMLDivElement;
  let tipText = $state({ label: '', key: '' });
  let tipOwner: HTMLElement | null = null;
  let tipTimer: ReturnType<typeof setTimeout> | null = null;
  let tipFallback = $state<{ x: number; y: number } | null>(null);

  function showTip(el: HTMLElement, immediate: boolean): void {
    if (tipTimer) clearTimeout(tipTimer);
    const go = () => {
      tipOwner?.style.removeProperty('anchor-name');
      tipOwner = el;
      tipText = { label: el.dataset.tip ?? '', key: el.dataset.key ?? '' };
      if (hasAnchor && mode === 'native') {
        // anchor-name is ONE property: keep the element's own anchor (the
        // popover's) or the popover loses its anchor and lands at 0, 0.
        const own = el.dataset.anchor;
        el.style.setProperty('anchor-name', own ? `${own}, --lab-tip` : '--lab-tip');
        tipFallback = null;
      } else {
        const r = el.getBoundingClientRect();
        tipFallback = { x: r.left + r.width / 2, y: r.bottom + 6 };
      }
      if (hasPopover) {
        try {
          tip.showPopover();
        } catch {
          /* already open */
        }
      }
    };
    if (immediate) go();
    else tipTimer = setTimeout(go, 500);
  }
  function hideTip(): void {
    if (tipTimer) clearTimeout(tipTimer);
    if (hasPopover) {
      try {
        tip.hidePopover();
      } catch {
        /* closed */
      }
    }
    tipOwner?.style.removeProperty('anchor-name');
    tipOwner = null;
    tipFallback = null;
  }

  const TOOLS = [
    { icon: 'capture', tip: 'Take one exposure', key: 'E' },
    { icon: 'live', tip: 'Live view', key: 'V' },
    null,
    { icon: 'zoom-out', tip: 'Zoom out', key: '−' },
    { icon: 'zoom-in', tip: 'Zoom in', key: '+' },
    { icon: 'zoom-fit', tip: 'Fit', key: 'F' },
    null,
    { icon: 'stretch-auto', tip: 'Auto stretch', key: 'A' },
    { icon: 'histogram', tip: 'Levels strip', key: 'H' },
    null,
    { icon: 'crosshair', tip: 'Crosshair', key: 'X' },
    { icon: 'plate-solve', tip: 'Identify field (ASTAP plate solve)', key: 'S' },
    { icon: 'sky-grid', tip: 'Coordinate grid', key: 'G' },
    { icon: 'labels', tip: 'Object labels', key: 'N' },
  ];
</script>

<div class="demo">
  <div class="toolbar" role="toolbar" aria-label="Observe tools">
    {#each TOOLS as t, i (i)}
      {#if t}
        <button
          class="lab-btn ghost"
          aria-label={t.tip}
          aria-keyshortcuts={t.key}
          data-tip={t.tip}
          data-key={t.key}
          onpointerenter={(e) => showTip(e.currentTarget, false)}
          onpointerleave={hideTip}
          onfocus={(e) => showTip(e.currentTarget, true)}
          onblur={hideTip}
        >
          <Icon name={t.icon} size={20} />
        </button>
      {:else}
        <span class="sep"></span>
      {/if}
    {/each}
    <button
      bind:this={trigger}
      class="lab-btn ghost cat"
      data-shot="open-popover"
      aria-label="Catalogue layers"
      aria-keyshortcuts="O"
      aria-expanded={open}
      aria-controls="lab-cat-pop"
      aria-pressed={open}
      data-tip="Catalogue layers"
      data-key="O"
      data-anchor="--lab-cat"
      onclick={() => {
        hideTip();
        toggleOpen();
      }}
      onpointerenter={(e) => !open && showTip(e.currentTarget, false)}
      onpointerleave={hideTip}
    >
      <Icon name="catalogue" size={20} /><Icon name="disclosure" size={16} />
    </button>
    <span class="grow"></span>
    <div class="lab-seg" role="radiogroup" aria-label="Implementation">
      <button role="radio" aria-checked={mode === 'native'} disabled={!hasPopover || !hasAnchor} onclick={() => (forced = 'native')}>Native</button>
      <button role="radio" aria-checked={mode === 'popover-js'} disabled={!hasPopover} onclick={() => (forced = 'popover-js')}>Popover + JS</button>
      <button role="radio" data-shot="force-fallback" aria-checked={mode === 'js'} onclick={() => (forced = 'js')}>JS only</button>
    </div>
    <button class="lab-btn ghost" aria-label="Catalogue settings" data-tip="Settings" data-key="" onpointerenter={(e) => showTip(e.currentTarget, false)} onpointerleave={hideTip}>
      <Icon name="arrange" size={20} />
    </button>
  </div>

  <div class="viewer">
    <svg viewBox="0 0 100 50" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      {#each Array.from({ length: 120 }, (_, i) => i) as i (i)}
        <circle cx={(i * 37.7) % 100} cy={(i * 23.3) % 50} r={0.12 + ((i * 7) % 5) * 0.06} />
      {/each}
      {#if layers[1].on}
        <circle class="vsx" cx="61" cy="22" r="1.6" />
        <circle class="vsx" cx="31" cy="35" r="1.6" />
      {/if}
    </svg>
    <ul class="lab-facts facts" data-lab-facts={JSON.stringify({ hasPopover, hasAnchor, hasStarting, mode })}>
      <li class={hasPopover ? 'yes' : 'no'}>Popover API: <b>{hasPopover ? 'yes' : 'no'}</b></li>
      <li class={hasAnchor ? 'yes' : 'no'}>anchor positioning: <b>{hasAnchor ? 'yes' : 'no'}</b></li>
      <li class={hasStarting ? 'yes' : 'no'}>@starting-style: <b>{hasStarting ? 'yes' : 'no'}</b></li>
      <li>in use: <b>{mode === 'native' ? 'Popover API + CSS anchor' : mode === 'popover-js' ? 'Popover API + position.ts' : 'fixed element + position.ts'}</b></li>
      <li>focus after close: <b>{lastFocusReturned}</b></li>
    </ul>
  </div>

  <div
    bind:this={panel}
    id="lab-cat-pop"
    class="pop mode-{mode}"
    class:js-open={mode === 'js' && open}
    popover={mode === 'js' ? undefined : 'auto'}
    role="dialog"
    aria-label="Catalogue layers"
    style:left={mode !== 'native' && jsPos ? `${jsPos.x}px` : undefined}
    style:top={mode !== 'native' && jsPos ? `${jsPos.y}px` : undefined}
    ontoggle={onToggle}
  >
    <p class="lab-eyebrow title">Catalogue layers</p>
    <ul class="layers">
      {#each layers as l (l.id)}
        <li>
          <label>
            <input type="checkbox" class="tick" bind:checked={l.on} />
            <Icon name={l.icon} size={16} />
            <span class="name">{l.label}</span>
            <span class="count num">{nf.format(l.count)}</span>
          </label>
        </li>
      {/each}
    </ul>
    <div class="depth">
      <label for="lab-depth">Gaia depth</label>
      <input id="lab-depth" type="range" min="10" max="19" step="0.5" bind:value={depth} class="range" />
      <span class="num">≤ {depth.toFixed(1)}</span>
    </div>
    <div class="footer">
      <button class="lab-btn ghost wide" onclick={() => hide()}><Icon name="settings" size={16} /> Catalogue settings…</button>
    </div>
  </div>

  <div
    bind:this={tip}
    class="tip"
    class:fallback={!!tipFallback}
    popover={hasPopover ? 'manual' : undefined}
    aria-hidden="true"
    style:left={tipFallback ? `${tipFallback.x}px` : undefined}
    style:top={tipFallback ? `${tipFallback.y}px` : undefined}
  >
    {tipText.label}{#if tipText.key}<kbd>{tipText.key}</kbd>{/if}
  </div>
</div>

<style>
  .demo {
    display: flex;
    flex-direction: column;
    height: 100%;
    border-top: var(--border-w) solid var(--border);
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 2px;
    height: 47px;
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border);
    flex: none;
  }
  .toolbar :global(.lab-btn.ghost) {
    width: var(--control-h-m);
    height: var(--control-h-m);
  }
  .toolbar .cat {
    width: auto;
    padding: 0 var(--space-1) 0 var(--space-2);
    gap: 0;
    anchor-name: --lab-cat;
  }
  .sep {
    width: 1px;
    height: 20px;
    margin: 0 var(--space-2);
    background: var(--border-soft);
  }
  .grow {
    flex: 1;
  }
  .lab-seg {
    margin-right: var(--space-2);
  }
  .lab-seg button:disabled {
    color: var(--fg-disabled);
    cursor: not-allowed;
  }

  .viewer {
    position: relative;
    flex: 1;
    min-height: 0;
    background: var(--viewer-bg);
  }
  .viewer svg {
    width: 100%;
    height: 100%;
    fill: var(--fg-muted);
  }
  .viewer .vsx {
    fill: none;
    stroke: var(--overlay-variable);
    stroke-width: 0.25;
  }
  .facts {
    position: absolute;
    left: var(--space-4);
    bottom: var(--space-4);
    padding: var(--space-2) var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--bg);
  }

  /* -- The popover --------------------------------------------------------- */
  .pop {
    width: 320px;
    margin: 0;
    padding: 0;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    color: var(--fg);
    box-shadow: var(--shadow-2);
    inset: auto;
    position: fixed;
  }
  /* Native: anchored by CSS, flips when there is no room below / right. */
  .pop.mode-native {
    position-anchor: --lab-cat;
    position-area: bottom span-left;
    margin-top: 4px;
    position-try-fallbacks: flip-block, flip-inline;
  }
  .pop[popover] {
    opacity: 1;
    transform: none;
    transition:
      opacity var(--duration-base) var(--ease-out),
      transform var(--duration-base) var(--ease-out),
      overlay var(--duration-base) allow-discrete,
      display var(--duration-base) allow-discrete;
  }
  .pop[popover]:not(:popover-open) {
    opacity: 0;
    transform: translateY(4px);
  }
  @starting-style {
    .pop[popover]:popover-open {
      opacity: 0;
      transform: translateY(4px);
    }
  }
  .pop.mode-js {
    display: none;
    z-index: var(--z-popover);
  }
  .pop.mode-js.js-open {
    display: block;
    animation: enter var(--duration-base) var(--ease-out);
  }
  @keyframes enter {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
  }

  .title {
    padding: var(--space-3) var(--space-4) var(--space-1);
  }
  .layers {
    margin: 0;
    padding: 0 var(--space-2);
    list-style: none;
  }
  .layers label {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 30px;
    padding: 0 var(--space-2);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-m);
    cursor: pointer;
  }
  .layers label:hover {
    background: var(--hover-bg);
  }
  .layers :global(.icon) {
    color: var(--fg-muted);
  }
  .name {
    flex: 1;
  }
  .count {
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  /* Token-drawn checkbox: no engine-drawn white tick (Night Red). */
  .tick {
    appearance: none;
    -webkit-appearance: none;
    display: grid;
    place-content: center;
    width: 16px;
    height: 16px;
    margin: 0;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .tick::after {
    content: '';
    width: 8px;
    height: 4px;
    margin-top: -2px;
    border-left: 1.5px solid var(--on-accent);
    border-bottom: 1.5px solid var(--on-accent);
    transform: rotate(-45deg) scale(0);
  }
  .tick:checked {
    background: var(--accent);
    border-color: var(--accent);
  }
  .tick:checked::after {
    transform: rotate(-45deg) scale(1);
  }

  .depth {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .depth .num {
    color: var(--fg);
  }
  /* Token-drawn range (native thumbs are white / grey). */
  .range {
    appearance: none;
    -webkit-appearance: none;
    height: 16px;
    margin: 0;
    background: transparent;
  }
  .range::-webkit-slider-runnable-track {
    height: 2px;
    background: var(--border);
  }
  .range::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 12px;
    height: 12px;
    margin-top: -5px;
    border-radius: var(--radius-round);
    background: var(--accent);
    border: 0;
  }
  .range::-moz-range-track {
    height: 2px;
    background: var(--border);
  }
  .range::-moz-range-thumb {
    width: 12px;
    height: 12px;
    border-radius: var(--radius-round);
    background: var(--accent);
    border: 0;
  }

  .footer {
    padding: var(--space-1) var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .wide {
    width: auto !important;
    padding: 0 var(--space-3) !important;
    gap: var(--space-2);
    color: var(--fg) !important;
  }

  /* -- The shared tooltip -------------------------------------------------- */
  .tip {
    margin: 0;
    padding: var(--space-1) var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
    inset: auto;
    position: fixed;
    position-anchor: --lab-tip;
    position-area: bottom;
    margin-top: 6px;
    position-try-fallbacks: flip-block;
    pointer-events: none;
  }
  .tip.fallback {
    position-area: none;
    margin-top: 0;
    transform: translateX(-50%);
  }
  .tip:not([popover]) {
    display: none;
  }
  .tip:not([popover]).fallback {
    display: block;
    z-index: var(--z-tooltip);
  }
  kbd {
    margin-left: var(--space-2);
    padding: 0 4px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
  }
</style>
