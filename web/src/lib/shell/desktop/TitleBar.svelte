<!--
  The desktop app's title bar (W8; Q-G14: a token-drawn title bar in every theme, Tauri
  `decorations: false`; 01 2.4.6): the OS's own title bar and traffic lights draw grey,
  white and green, which Night Red forbids (BRAND 4.3), so the window chrome is ours.

  - Height --titlebar-h (28 px, as macOS's own), --bg-2 like the rail it sits over, one
    --border line under it. The title is the section alone, centred, --text-muted (the
    rail head right below already says ARGOS: the chrome recedes, BRAND 11.1); "ARGOS"
    before a section is shown (start-up).
  - Window controls drawn from tokens: on macOS at the left, where the traffic lights
    live (close, minimise, zoom: 12 px discs at macOS's 20 px pitch, filled --border, or
    --border-soft when the window is not focused, as macOS draws inactive lights: a
    hollow ring means "idle / not connected" in ARGOS, BRAND principle 6; glyphs on
    hover, close fills --danger); elsewhere at the right (minimise, maximise, close:
    40 px cells). Close = Quit (Q-G1: one window; the quit flow asks when something runs).
  - The free area drags the window; a double click does what the system's setting says
    (zoom, minimise or nothing: bridge.titleBarPress, the rule of Tauri's own drag
    script). Presses on the controls never drag. Hidden in full screen (App.svelte).
  - Out of the Tab order and never focused by a click (an Enter on a stray focus must not
    quit; the page keeps its focus); a screen reader reaches them as buttons, the keyboard
    has Mod+Q and the app menu (Minimise, Zoom).
  - Dims when the window loses the focus, as native chrome does. No `title` tooltips: the
    OS draws those in grey (BRAND 4.3); native traffic lights have none either.
  - Above the start-up screen (z), so the window can be moved while ARGOS starts.

  `pin` (gallery): draw the controls' hover state ('controls') or the close hover ('close').
-->
<script lang="ts">
  import { type DoubleClickAction, titleBarPress, type ShellPlatform } from './bridge';

  interface Props {
    platform: ShellPlatform;
    title?: string;
    /** The section on screen ("Observe"). */
    subtitle?: string | null;
    focused?: boolean;
    /** The system's title-bar double-click setting. */
    doubleClick?: DoubleClickAction;
    onclose: () => void;
    onminimize: () => void;
    onzoom: () => void;
    ondrag: () => void;
    pin?: 'controls' | 'close' | null;
  }

  let { platform, title = 'ARGOS', subtitle = null, focused = true, doubleClick = 'zoom', onclose, onminimize, onzoom, ondrag, pin = null }: Props = $props();

  const mac = $derived(platform === 'macos');

  function onmousedown(e: MouseEvent): void {
    const target = e.target instanceof Element ? e.target : null;
    const onControl = !!target?.closest('button');
    // Window controls never take the focus (native ones do not): the page keeps its own.
    if (onControl) e.preventDefault();
    const action = titleBarPress({ button: e.button, detail: e.detail, onControl }, doubleClick);
    if (!action) return;
    e.preventDefault();
    if (action === 'zoom') onzoom();
    else if (action === 'minimize') onminimize();
    else ondrag();
  }
</script>

{#snippet macControls()}
  <div class="mac-controls" class:pin-hover={pin === 'controls' || pin === 'close'} role="group" aria-label="Window">
    <button type="button" class="light close" class:pin-close={pin === 'close'} tabindex="-1" aria-label="Close and quit ARGOS" onclick={onclose}>
      <svg viewBox="0 0 8 8" aria-hidden="true"><path d="M2 2 6 6M6 2 2 6" /></svg>
    </button>
    <button type="button" class="light" tabindex="-1" aria-label="Minimise" onclick={onminimize}>
      <svg viewBox="0 0 8 8" aria-hidden="true"><path d="M1.75 4h4.5" /></svg>
    </button>
    <button type="button" class="light" tabindex="-1" aria-label="Zoom" onclick={onzoom}>
      <svg viewBox="0 0 8 8" aria-hidden="true"><path d="M4 1.75v4.5M1.75 4h4.5" /></svg>
    </button>
  </div>
{/snippet}

{#snippet pcControls()}
  <div class="pc-controls" role="group" aria-label="Window">
    <button type="button" class="cell" class:pin-hover={pin === 'controls'} tabindex="-1" aria-label="Minimise" onclick={onminimize}>
      <svg viewBox="0 0 10 10" aria-hidden="true"><path d="M1 5h8" /></svg>
    </button>
    <button type="button" class="cell" tabindex="-1" aria-label="Maximise" onclick={onzoom}>
      <svg viewBox="0 0 10 10" aria-hidden="true"><path d="M1.5 1.5h7v7h-7z" /></svg>
    </button>
    <button type="button" class="cell close" class:pin-close={pin === 'close'} tabindex="-1" aria-label="Close and quit ARGOS" onclick={onclose}>
      <svg viewBox="0 0 10 10" aria-hidden="true"><path d="M1.5 1.5l7 7M8.5 1.5l-7 7" /></svg>
    </button>
  </div>
{/snippet}

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="titlebar" class:mac class:blurred={!focused} {onmousedown}>
  <div class="side start">{#if mac}{@render macControls()}{/if}</div>
  <p class="title">{subtitle ?? title}</p>
  <div class="side end">{#if !mac}{@render pcControls()}{/if}</div>
</div>

<style>
  .titlebar {
    position: relative;
    z-index: calc(var(--z-modal) + 1);
    display: grid;
    grid-template-columns: minmax(80px, 1fr) auto minmax(80px, 1fr);
    align-items: center;
    height: var(--titlebar-h);
    flex: none;
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg-2);
    color: var(--text-muted);
    user-select: none;
    -webkit-user-select: none;
    cursor: default;
  }

  .side {
    display: flex;
    align-items: center;
    height: 100%;
    min-width: 0;
  }
  .side.end {
    justify-content: flex-end;
  }

  .title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
    margin: 0;
    overflow: hidden;
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    letter-spacing: 0.02em;
    white-space: nowrap;
    pointer-events: none;
  }

  /* -- macOS: three 12 px discs where the traffic lights live (centres 14, 34, 54 px) - */
  .mac-controls {
    display: flex;
    align-items: center;
    height: 100%;
    padding-left: var(--space-1);
  }
  .light {
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: 0;
    background: none;
    color: var(--fg);
    cursor: default;
  }
  .light::before {
    content: '';
    grid-area: 1 / 1;
    width: 12px;
    height: 12px;
    box-sizing: border-box;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-round);
    background: var(--border);
    transition:
      background var(--duration-fast) var(--ease-out),
      border-color var(--duration-fast) var(--ease-out);
  }
  .light svg {
    grid-area: 1 / 1;
    z-index: 1;
    width: 8px;
    height: 8px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.25;
    stroke-linecap: round;
    opacity: 0;
  }
  .blurred .light::before {
    border-color: var(--border-soft);
    background: var(--border-soft);
  }
  /* Hovering the group shows every glyph, as macOS does. */
  .mac-controls:hover .light::before,
  .mac-controls.pin-hover .light::before {
    border-color: var(--fg-muted);
    background: var(--surface);
  }
  .mac-controls:hover .light svg,
  .mac-controls.pin-hover .light svg {
    opacity: 1;
  }
  .light.close:hover::before,
  .light.close.pin-close::before {
    border-color: var(--danger);
    background: var(--danger);
  }
  .light.close:hover,
  .light.close.pin-close {
    color: var(--on-danger);
  }
  .light:active::before {
    background: var(--pressed-bg);
  }

  /* -- Windows / Linux: three cells at the right ------------------------------------ */
  .pc-controls {
    display: flex;
    height: 100%;
  }
  .cell {
    display: grid;
    place-items: center;
    width: 40px;
    height: 100%;
    padding: 0;
    border: 0;
    background: none;
    color: var(--fg-muted);
    cursor: default;
  }
  .cell svg {
    width: 10px;
    height: 10px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1;
  }
  .cell:hover,
  .cell.pin-hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .cell.close:hover,
  .cell.close.pin-close {
    background: var(--danger);
    color: var(--on-danger);
  }
  .blurred .cell {
    color: var(--fg-disabled);
  }

  .light:focus-visible,
  .cell:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: calc(-1 * var(--focus-ring-w));
  }
</style>
