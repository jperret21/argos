/**
 * Feature probes for the support matrix, run in the engine that opens the
 * page. Each probe tests the behaviour ARGOS would rely on, not a version
 * string. WebKitGTK statuses come from the WebKit sources of each GTK
 * release branch (UnifiedWebPreferences.yaml on webkitglib/2.48 ... 2.54):
 * a feature flagged "stable" with default true is on in every port; a
 * "preview" / "testable" one is off by default.
 */

export type Group = 'Layout' | 'Colour' | 'Motion' | 'Overlays and forms' | 'Input' | 'Graphics' | 'Workers and scheduling' | 'Formatting';

export interface Probe {
  id: string;
  group: Group;
  name: string;
  /** What ARGOS does with it / the fallback, one line. */
  use: string;
  /** WebKitGTK: first release where it is on by default, or a note. */
  gtk?: string;
  test: () => boolean | string | Promise<boolean | string>;
}

const sup = (decl: string) => typeof CSS !== 'undefined' && CSS.supports(decl);

/** Inject CSS + HTML, return a computed property of #lab-probe-target. */
function computed(css: string, html: string, prop: string): string {
  const host = document.createElement('div');
  host.style.cssText = 'position:absolute;left:-9999px;top:0;width:400px';
  host.innerHTML = `<style>${css}</style>${html}`;
  document.body.append(host);
  const el = host.querySelector('#lab-probe-target');
  const v = el ? getComputedStyle(el).getPropertyValue(prop) : '';
  host.remove();
  return v.trim();
}

function canvasAccepts(color: string): boolean {
  const ctx = document.createElement('canvas').getContext('2d');
  if (!ctx) return false;
  ctx.fillStyle = '#010203';
  ctx.fillStyle = color;
  return ctx.fillStyle !== '#010203';
}

function devicePixelBox(): Promise<boolean> {
  return new Promise((resolve) => {
    const el = document.createElement('div');
    el.style.cssText = 'position:absolute;left:-9999px;width:10px;height:10px';
    document.body.append(el);
    const ro = new ResizeObserver((e) => {
      resolve(!!e[0].devicePixelContentBoxSize?.length);
      ro.disconnect();
      el.remove();
    });
    try {
      ro.observe(el, { box: 'device-pixel-content-box' });
    } catch {
      resolve(false);
      el.remove();
    }
    setTimeout(() => resolve(false), 1000);
  });
}

let workerResult: Promise<Record<string, boolean | string>> | null = null;
function workerProbe(): Promise<Record<string, boolean | string>> {
  workerResult ??= new Promise((resolve) => {
    try {
      const w = new Worker(new URL('./probe.worker.ts', import.meta.url), { type: 'module' });
      w.onmessage = (e) => {
        resolve(e.data);
        w.terminate();
      };
      w.onerror = (e) => resolve({ error: e.message });
      setTimeout(() => resolve({ error: 'timeout' }), 3000);
    } catch (e) {
      resolve({ error: String(e) });
    }
  });
  return workerResult;
}

function gl2(): WebGL2RenderingContext | null {
  return document.createElement('canvas').getContext('webgl2');
}

export const PROBES: Probe[] = [
  // -- Layout ---------------------------------------------------------------------
  { id: 'cq', group: 'Layout', name: 'Container queries (size)', use: 'Cards reflow by their own width: rail, drawer, sheet', test: () => sup('container-type: inline-size') },
  {
    id: 'cq-style',
    group: 'Layout',
    name: 'Container style queries',
    use: 'State-driven variants (--density); attribute selectors instead',
    test: () =>
      computed(
        '#c{container-name:c;--d:1}@container c style(--d: 1){#lab-probe-target{color:rgb(1, 2, 3)}}',
        '<div id="c"><span id="lab-probe-target"></span></div>',
        'color',
      ) === 'rgb(1, 2, 3)',
  },
  { id: 'has', group: 'Layout', name: ':has()', use: 'A row marks itself when its field is invalid or busy', test: () => sup('selector(:has(a))') },
  { id: 'subgrid', group: 'Layout', name: 'Subgrid', use: 'One label column across every group of a card', test: () => sup('grid-template-columns: subgrid') },
  {
    id: 'nesting',
    group: 'Layout',
    name: 'CSS nesting (native)',
    use: 'Not needed: Svelte scoped styles; useful in tokens.css only',
    test: () => computed('.lab-n{& #lab-probe-target{color:rgb(4, 5, 6)}}', '<div class="lab-n"><span id="lab-probe-target"></span></div>', 'color') === 'rgb(4, 5, 6)',
  },
  { id: 'scope', group: 'Layout', name: '@scope', use: 'Not needed with Svelte scoping', test: () => 'CSSScopeRule' in window },
  { id: 'field-sizing', group: 'Layout', name: 'field-sizing: content', use: 'Inputs that grow with their text (Object, notes); fixed width fallback', gtk: '2.52 (preview in 2.50)', test: () => sup('field-sizing: content') },
  { id: 'text-box-trim', group: 'Layout', name: 'text-box-trim', use: 'Exact vertical centring of labels in 30 px controls; padding fallback', test: () => sup('text-box-trim: trim-both') },
  { id: 'text-wrap', group: 'Layout', name: 'text-wrap: balance / pretty', use: 'Help text, empty states', gtk: 'pretty: 2.50', test: () => `${sup('text-wrap: balance') ? 'balance' : '-'} ${sup('text-wrap: pretty') ? 'pretty' : '-'}` },
  { id: 'content-visibility', group: 'Layout', name: 'content-visibility: auto', use: 'Skip rendering off-screen facets / settings pages', test: () => sup('content-visibility: auto') },
  { id: 'scrollbar-color', group: 'Layout', name: 'scrollbar-color', use: 'Night Red scrollbars from tokens; ::-webkit-scrollbar fallback', gtk: '2.52 (testable, off in 2.50)', test: () => sup('scrollbar-color: red blue') },
  { id: 'scrollbar-gutter', group: 'Layout', name: 'scrollbar-gutter', use: 'No layout jump when a rail starts to scroll', test: () => sup('scrollbar-gutter: stable') },
  // -- Colour ---------------------------------------------------------------------
  { id: 'color-mix', group: 'Colour', name: 'color-mix()', use: 'Tints from tokens (selection, 14 % brass); in srgb stays inside the hull (Night Red safe)', test: () => sup('color: color-mix(in srgb, red 50%, blue)') },
  { id: 'oklch', group: 'Colour', name: 'oklch() / oklab()', use: 'Perceptual ramps for false-colour LUTs (never in Night Red)', test: () => sup('color: oklch(0.5 0.1 30)') },
  { id: 'relative-color', group: 'Colour', name: 'Relative colour syntax', use: 'rgb(from var(--accent) r g b / 0.3) alpha variants', test: () => sup('color: rgb(from red r g b / 0.5)') },
  { id: 'contrast-color', group: 'Colour', name: 'contrast-color()', use: 'Not used: the --on-* tokens are explicit and audited', test: () => sup('color: contrast-color(red)') },
  { id: 'canvas-color-mix', group: 'Colour', name: 'Canvas fillStyle accepts color-mix()', use: 'If not: resolve via getComputedStyle + 1 px canvas (tokens.ts)', test: () => canvasAccepts('color-mix(in srgb, red 50%, blue)') },
  { id: 'canvas-oklch', group: 'Colour', name: 'Canvas fillStyle accepts oklch()', use: 'Same resolver', test: () => canvasAccepts('oklch(0.6 0.1 30)') },
  {
    id: 'computed-mix',
    group: 'Colour',
    name: 'Computed color-mix() serialisation',
    use: 'Parsers must accept color(srgb ...), not only rgb()',
    test: () => computed('#lab-probe-target{color:color-mix(in srgb, #c49a3c 55%, #191b1f)}', '<span id="lab-probe-target"></span>', 'color'),
  },
  // -- Motion ---------------------------------------------------------------------
  { id: 'starting-style', group: 'Motion', name: '@starting-style', use: 'Entry of popovers / menus without JS; instant where missing', test: () => 'CSSStartingStyleRule' in window },
  { id: 'transition-behavior', group: 'Motion', name: 'transition-behavior: allow-discrete', use: 'Exit fade of popovers (display / overlay)', test: () => sup('transition-behavior: allow-discrete') },
  { id: 'overlay-prop', group: 'Motion', name: 'overlay property', use: 'Keeps a closing popover in the top layer during its fade', test: () => sup('overlay: auto') },
  { id: 'view-transitions', group: 'Motion', name: 'View Transitions (same document)', use: 'Section switch crossfade (180 ms); instant fallback', test: () => 'startViewTransition' in document },
  { id: 'vt-class', group: 'Motion', name: 'view-transition-class', use: 'Group transitions per kind of panel', test: () => sup('view-transition-class: a') },
  { id: 'scroll-driven', group: 'Motion', name: 'Scroll-driven animations', use: 'Sticky header rule appears once a rail scrolls; static rule fallback', gtk: '2.48', test: () => sup('animation-timeline: scroll()') },
  { id: 'property', group: 'Motion', name: '@property (typed custom properties)', use: 'Animatable --hold progress, typed tokens', test: () => 'CSSPropertyRule' in window },
  { id: 'linear-easing', group: 'Motion', name: 'linear() easing', use: 'A spring curve in pure CSS (drawer snap)', test: () => sup('transition-timing-function: linear(0, 0.5 30%, 1)') },
  { id: 'interpolate-size', group: 'Motion', name: 'interpolate-size / calc-size(auto)', use: 'Height: auto animation; grid-rows 0fr/1fr works everywhere', test: () => sup('interpolate-size: allow-keywords') },
  // -- Overlays and forms ------------------------------------------------------
  { id: 'popover', group: 'Overlays and forms', name: 'Popover API', use: 'Top layer, light dismiss, Esc; WKWebView: app linked on macOS 14+ SDK', test: () => Object.hasOwn(HTMLElement.prototype, 'popover') },
  {
    id: 'popover-hint',
    group: 'Overlays and forms',
    name: 'popover="hint"',
    use: 'Tooltips that do not close menus; manual popover fallback',
    gtk: 'not yet (preview in 2.54)',
    test: () => {
      const d = document.createElement('div');
      d.setAttribute('popover', 'hint');
      return (d as HTMLElement & { popover: string | null }).popover === 'hint';
    },
  },
  { id: 'anchor', group: 'Overlays and forms', name: 'CSS anchor positioning', use: 'Popovers, tooltips, segment indicator; position.ts fallback', gtk: '2.50 (testable in 2.48)', test: () => sup('anchor-name: --a') },
  { id: 'position-try', group: 'Overlays and forms', name: 'position-try-fallbacks', use: 'Flip when no room', test: () => sup('position-try-fallbacks: flip-block') },
  { id: 'dialog', group: 'Overlays and forms', name: '<dialog> showModal', use: 'Modal dialogs, inert background', test: () => typeof HTMLDialogElement !== 'undefined' && 'showModal' in HTMLDialogElement.prototype },
  { id: 'closedby', group: 'Overlays and forms', name: 'dialog closedby', use: 'Light dismiss of sheets; manual handler fallback', test: () => typeof HTMLDialogElement !== 'undefined' && 'closedBy' in HTMLDialogElement.prototype },
  { id: 'inert', group: 'Overlays and forms', name: 'inert', use: 'Background of modals (layers.ts already uses it)', test: () => 'inert' in HTMLElement.prototype },
  { id: 'command', group: 'Overlays and forms', name: 'command / commandfor', use: 'Declarative open/close of dialogs and popovers', gtk: '2.52 (preview in 2.50)', test: () => 'command' in HTMLButtonElement.prototype },
  { id: 'closewatcher', group: 'Overlays and forms', name: 'CloseWatcher', use: 'Esc / back handling; layers.ts stack already does it', gtk: '2.54', test: () => 'CloseWatcher' in window },
  { id: 'accent-color', group: 'Overlays and forms', name: 'accent-color', use: 'Native checks tinted; still token-draw them for Night Red', test: () => sup('accent-color: red') },
  { id: 'user-invalid', group: 'Overlays and forms', name: ':user-invalid', use: 'Show a field error only after the observer touched it', test: () => sup('selector(:user-invalid)') },
  { id: 'highlight', group: 'Overlays and forms', name: 'CSS Custom Highlight API', use: 'Search matches in the log and tables without DOM edits; <mark> fallback', test: () => typeof CSS !== 'undefined' && 'highlights' in CSS },
  // -- Input -----------------------------------------------------------------------
  { id: 'pointer-capture', group: 'Input', name: 'Pointer events + capture', use: 'Drag handles, splitters, pan', test: () => 'setPointerCapture' in Element.prototype },
  { id: 'coalesced', group: 'Input', name: 'getCoalescedEvents()', use: 'Smooth region drawing at high pointer rates', test: () => typeof PointerEvent !== 'undefined' && 'getCoalescedEvents' in PointerEvent.prototype },
  { id: 'rawupdate', group: 'Input', name: 'pointerrawupdate', use: 'Not needed (Chromium only)', test: () => 'onpointerrawupdate' in window },
  { id: 'gesture-event', group: 'Input', name: 'GestureEvent (WebKit pinch)', use: 'Trackpad pinch in WebKit; ctrl+wheel elsewhere', test: () => 'GestureEvent' in window },
  { id: 'dpcb', group: 'Input', name: 'ResizeObserver device-pixel-content-box', use: 'Pixel-exact canvas size; rounded fallback', test: devicePixelBox },
  { id: 'wakelock', group: 'Input', name: 'Screen Wake Lock', use: 'Keep the screen on during a run (opt-in)', test: () => 'wakeLock' in navigator },
  { id: 'clipboard', group: 'Input', name: 'Async clipboard writeText', use: 'Copy data (TSV), Copy RA/Dec', test: () => !!navigator.clipboard?.writeText },
  { id: 'keyboard-map', group: 'Input', name: 'navigator.keyboard.getLayoutMap', use: 'Not needed: match key and code (AZERTY digits)', test: () => 'keyboard' in navigator },
  // -- Graphics --------------------------------------------------------------------
  { id: 'webgl2', group: 'Graphics', name: 'WebGL2', use: 'Viewer: R16UI textures, stretch and LUT in shaders', test: () => !!gl2() },
  {
    id: 'gl-renderer',
    group: 'Graphics',
    name: 'WebGL renderer',
    use: 'Information (headless Chrome: SwiftShader, on the CPU)',
    test: () => {
      const g = gl2();
      const ext = g?.getExtension('WEBGL_debug_renderer_info');
      return g ? String(ext ? g.getParameter(ext.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER)) : 'none';
    },
  },
  { id: 'gl-max-tex', group: 'Graphics', name: 'MAX_TEXTURE_SIZE', use: 'A 1080 x 1920 frame fits everywhere', test: () => String(gl2()?.getParameter(WebGL2RenderingContext.MAX_TEXTURE_SIZE) ?? 'none') },
  { id: 'gl-timer', group: 'Graphics', name: 'EXT_disjoint_timer_query_webgl2', use: 'True GPU timings; readPixels sync fallback', test: () => !!gl2()?.getExtension('EXT_disjoint_timer_query_webgl2') },
  { id: 'gl-float-linear', group: 'Graphics', name: 'OES_texture_float_linear', use: 'Smooth float textures (not needed: R16UI + texelFetch)', test: () => !!gl2()?.getExtension('OES_texture_float_linear') },
  { id: 'webgpu', group: 'Graphics', name: 'WebGPU', use: 'Not used: missing on WebKitGTK; WebGL2 covers the viewer', gtk: 'off (no WebGPU by default)', test: () => 'gpu' in navigator },
  { id: 'canvas-filter', group: 'Graphics', name: 'Canvas 2D filter', use: 'Avoid: off in every WebKit (testable flag)', gtk: 'off', test: () => 'filter' in CanvasRenderingContext2D.prototype },
  { id: 'canvas-roundrect', group: 'Graphics', name: 'Canvas roundRect / reset', use: 'Overlay chips on canvas', test: () => `${'roundRect' in CanvasRenderingContext2D.prototype ? 'roundRect' : '-'} ${'reset' in CanvasRenderingContext2D.prototype ? 'reset' : '-'}` },
  { id: 'offscreen-2d', group: 'Graphics', name: 'OffscreenCanvas 2D (worker)', use: 'Render thumbnails / sparklines off the main thread', test: async () => !!(await workerProbe()).offscreen2d },
  { id: 'offscreen-gl', group: 'Graphics', name: 'OffscreenCanvas WebGL2 (worker)', use: 'Viewer in a worker (later, if the main thread ever janks)', test: async () => !!(await workerProbe()).offscreenWebgl2 },
  // -- Workers and scheduling ----------------------------------------------------
  { id: 'module-worker', group: 'Workers and scheduling', name: 'Module workers', use: 'Statistics, decoding, synthesis off the main thread', test: async () => !(await workerProbe()).error },
  { id: 'sab', group: 'Workers and scheduling', name: 'SharedArrayBuffer usable', use: 'Needs COOP/COEP headers; transfer (ping-pong) instead', test: () => (typeof crossOriginIsolated !== 'undefined' && crossOriginIsolated ? 'isolated' : false) },
  { id: 'ric', group: 'Workers and scheduling', name: 'requestIdleCallback', use: 'Off in every WebKit: use setTimeout / scheduler.yield', gtk: 'off', test: () => 'requestIdleCallback' in window },
  { id: 'scheduler-yield', group: 'Workers and scheduling', name: 'scheduler.yield()', use: 'Break long tasks; setTimeout(0) fallback', test: () => 'scheduler' in window && 'yield' in (window as unknown as { scheduler: object }).scheduler },
  { id: 'broadcast', group: 'Workers and scheduling', name: 'BroadcastChannel', use: 'Sync windows of a Tauri multi-window app', test: () => 'BroadcastChannel' in window },
  // -- Formatting ----------------------------------------------------------------
  { id: 'intl-duration', group: 'Formatting', name: 'Intl.DurationFormat', use: 'Not used for ETA: BRAND fixes "1h 05m"; custom formatter', test: () => 'DurationFormat' in Intl },
  {
    id: 'intl-minus',
    group: 'Formatting',
    name: 'Intl sign of −0.5 in en-GB',
    use: 'Hyphen-minus: replace with U+2212 (BRAND 5)',
    test: () => {
      const s = new Intl.NumberFormat('en-GB', { signDisplay: 'always' }).format(-0.5);
      return `U+${s.codePointAt(0)!.toString(16).toUpperCase().padStart(4, '0')}`;
    },
  },
  {
    id: 'intl-utc',
    group: 'Formatting',
    name: 'Intl UTC time with hourCycle h23',
    use: 'Status-bar clock; toISOString slice is simpler',
    test: () => new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(new Date(Date.UTC(2026, 10, 1, 21, 34, 5))),
  },
];

export interface ProbeResult {
  id: string;
  value: boolean | string;
}

export async function runProbes(): Promise<ProbeResult[]> {
  const out: ProbeResult[] = [];
  for (const p of PROBES) {
    let value: boolean | string;
    try {
      value = await p.test();
    } catch (e) {
      value = `error: ${e instanceof Error ? e.message : String(e)}`;
    }
    out.push({ id: p.id, value });
  }
  return out;
}
