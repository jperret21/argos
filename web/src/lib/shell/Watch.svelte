<!--
  Watch: the run read from 2 m (owner D3; functional-spaces §4.7; promoted from
  src/lab/workspace/overlays/WatchView.svelte with the pulse fix, PROPOSAL §2.3 and §6 W6).
  A full-window view inside the one window (D27), a modal layer over the app: W, the
  toolbar or the palette opens it; W or Esc returns (Esc still aborts a slew, D21). Only W,
  Esc, ? and Mod+K act here: the app's other shortcuts are held by the layer (a key pressed
  to wake the screen never takes a shot); ? and Mod+K open the sheet and the palette above.

  Fixed positions teach meaning from afar: state, frames, last-frame age; the target's
  magnitude, the check star, the end; the curve; stars, HFD, altitude. Sizes (tokens):
  primary values 88 px, secondary 66 px, conditions 48 px, labels 30 px; long values are
  fitted to their tile (container units), never ellipsised. Truthful: values change when
  a frame arrives; the age ticks once a second (a clock); past 1.5 cadences the age and
  the values it dates turn muted with "as of". An open attention item replaces the first
  row and KEEPS the pulse (age, n / N) at its right end (WatchAlert).
  Dim 100 / 60 / 30 % multiplies the whole view's luminance with a CSS brightness filter:
  hue is kept, so Night Red stays red. Pause is hold-to-confirm (D4); no Stop, no mount
  action (they need the observer at the table, in Run mode).
  The screen wake lock is held while Watch is shown (second layer after the server's OS
  assertion) and released on leaving; its state is said in the footer.
  `embedded` (gallery) draws it in its parent: no layer, no keys, no wake lock.
-->
<script lang="ts">
  import { onMount, type Snippet } from 'svelte';
  import type { AttentionItem } from '../api/attention';
  import { detectMac } from '../app/shortcuts';
  import Sparkline from '../charts/mini/Sparkline.svelte';
  import type { SparkSpec } from '../charts/mini/spark';
  import type { ChartInks } from '../charts/ink';
  import HoldButton from '../components/HoldButton.svelte';
  import type { HoldPhase } from '../components/hold';
  import Icon from '../components/Icon.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { FocusReturn } from '../components/focus';
  import { isTopLayer, layer, portal } from '../components/layers';
  import { fixed, int } from '../format/number';
  import WatchAlert from './attention/WatchAlert.svelte';
  import { keepScreenOn, WAKE_SHORT, WAKE_WORDS, type WakeState } from './wakelock';
  import { clockUtc } from '../format/time';
  import { ageView, altLine, altValue, canPause, compsLine, computerLine, DIM_LEVELS, endsView, errLine, framesText, linksView, nextSound, soundLine, stateWord, watchKey, type DimLevel, type WatchData } from './watch';

  interface Props {
    data: WatchData;
    /** Unix s, ticking once per second. */
    now: number;
    /** The most urgent open attention item (AttentionStore.top). */
    top?: AttentionItem | null;
    ackBusy?: boolean;
    onack?: (id: string) => Promise<unknown> | void;
    dim?: DimLevel;
    onclose: () => void;
    /** Pause at the end of this frame (hold-to-confirm). */
    onpause?: () => Promise<unknown> | unknown;
    onhelp?: () => void;
    onpalette?: () => void;
    /** Called once on open (a gesture opened Watch: arm the alert sound). */
    onarm?: () => void;
    /** The live light curve (LightCurvePlot), sized by its row. */
    curve?: Snippet;
    /** Changes with the theme (sparklines redraw). */
    theme?: unknown;
    embedded?: boolean;
    /** Keep the display on while shown (navigator.wakeLock). */
    wakeLock?: boolean;
    /** Gallery: the wake-lock state to show (embedded only). */
    previewWake?: WakeState;
    /** Gallery: freeze the Pause hold in a phase. */
    pinPause?: { phase: HoldPhase; progress?: number } | null;
    /** Open attention items besides `top` (the alert row says "+n more"). */
    moreOpen?: number;
    /** A click on the footer's sound line: Off → Soft → Normal (Settings › Alerts). */
    onsound?: (level: 'off' | 'soft' | 'normal') => void;
  }
  let {
    data,
    now,
    top = null,
    ackBusy = false,
    onack,
    dim = $bindable(100),
    onclose,
    onpause,
    onhelp,
    onpalette,
    onarm,
    curve,
    theme,
    embedded = false,
    wakeLock = true,
    previewWake = 'held',
    pinPause = null,
    moreOpen = 0,
    onsound,
  }: Props = $props();

  let root: HTMLDivElement | null = $state(null);
  let wake = $state<WakeState>('pending');
  const mac = detectMac();

  const age = $derived(ageView(data.lastFrameAt, now, data.cadence, data.expecting));
  const frames = $derived(framesText(data.framesDone, data.framesTotal));
  const ends = $derived(endsView(data.end, now, !data.state ? data.ended : null));
  // A run that just ended says how (D2: its wrap-up waits in Observe), never "IDLE".
  const word = $derived(!data.state && data.ended ? data.ended.word : stateWord(data.state));
  const sound = $derived(soundLine(data.sound));
  const links = $derived(linksView(data.links));
  const hfdNow = $derived(data.hfd.length ? data.hfd[data.hfd.length - 1] : null);
  const starsNow = $derived(data.stars.length ? data.stars[data.stars.length - 1] : null);
  const label = $derived(`Watch: ${data.object ?? 'no run'}, ${word.toLowerCase()}`);
  const wakeShown = $derived(embedded ? previewWake : wake);
  const computer = $derived(computerLine(data.computer));
  // Width of a text in em for the fit: mono digits 0.6 em, Sans capitals about 0.66 em.
  const monoEm = (s: string) => Math.max(4, s.length * 0.6);
  const capsEm = (s: string) => Math.max(4, s.length * 0.68);

  let starsW = $state(0);
  let hfdW = $state(0);
  const spark =
    (ys: readonly number[], ref: number | null) =>
    (ink: ChartInks): SparkSpec | null => {
      const n = ys.length;
      if (n < 2) return null;
      const xs = Array.from({ length: n }, (_, i) => i);
      return { xs, ys: ys as number[], n, color: ink.fg.a(), lastDot: true, width: 2, ...(ref !== null ? { ref, markOut: true, refColor: ink.warning.a(0.9) } : {}) };
    };

  onMount(() => {
    if (embedded) return;
    onarm?.();
    const back = new FocusReturn();
    root?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (e.isComposing || !root || !isTopLayer(root)) return;
      const t = e.target as HTMLElement | null;
      if (t && root.contains(t) && (t.tagName === 'INPUT' || t.isContentEditable)) return;
      const what = watchKey(e, mac);
      if (!what) return;
      // Escape is the layer's (it closes Watch; the registry still aborts a slew, D21).
      if (what === 'close' && e.key === 'Escape') return;
      e.preventDefault();
      e.stopPropagation();
      if (what === 'close') onclose();
      else if (what === 'help') onhelp?.();
      else if (what === 'palette') onpalette?.();
    };
    window.addEventListener('keydown', onKey);
    const stop = wakeLock ? keepScreenOn(navigator as never, document, (s) => (wake = s)) : () => undefined;
    if (!wakeLock) wake = 'released';
    return () => {
      window.removeEventListener('keydown', onKey);
      stop();
      queueMicrotask(() => back.restore());
    };
  });

  /** The layer and the portal only outside the gallery. */
  function attach(node: HTMLElement) {
    if (embedded) return {};
    const p = portal(node);
    const l = layer(node, { kind: 'dialog', modal: true, onclose: () => onclose() });
    return {
      destroy() {
        l?.destroy?.();
        p?.destroy?.();
      },
    };
  }
</script>

<div
  bind:this={root}
  use:attach
  class="watch"
  class:embedded
  style:filter={dim < 100 ? `brightness(${dim / 100})` : undefined}
  role="dialog"
  aria-modal={embedded ? undefined : 'true'}
  aria-label={label}
  tabindex="-1"
>
  <div class="grid">
    <div class="row1">
      {#if top}
        <WatchAlert item={top} {age} {frames} state={data.state && data.state !== 'running' ? word : null} more={moreOpen} busy={ackBusy} {onack} />
      {:else}
        <div class="tiles">
          <div class="tile fit">
            <span class="w-state" style:--em={capsEm(word)}>{word}</span>
            <span class="w-s muted one">{data.object ?? 'No run'}{data.stepLine ? ` · ${data.stepLine}` : ''}</span>
          </div>
          <div class="tile fit">
            <span class="w-l num" style:--em={monoEm(frames)}>{frames}</span>
            <span class="w-s muted">frames</span>
          </div>
          {#if !data.state && data.ended}
            <div class="tile fit">
              <span class="w-l num" style:--em={monoEm('00:00')}>{data.ended.at !== null ? clockUtc(data.ended.at, false) : '—'}</span>
              <span class="w-s muted one">ended UTC · wrap-up in Observe</span>
            </div>
          {:else}
            <div class="tile fit" class:late={age.late}>
              <span class="w-l num age" style:--em={monoEm(age.value)}>{age.value}</span>
              <span class="w-s muted one">{age.note}</span>
            </div>
          {/if}
        </div>
      {/if}
    </div>

    <div class="row2 tiles">
      <div class="tile fit" class:late={age.late}>
        <span class="w-s muted one">TARGET · {data.target?.name ?? data.object ?? '—'}{data.target?.filter ? ` · ${data.target.filter}` : ''}</span>
        <span class="w-xl num val" style:--em={monoEm(fixed(data.target?.mag ?? null, 3))}>{fixed(data.target?.mag ?? null, 3)}</span>
        {#if data.target}<span class="w-m num muted one">{errLine(data.target.err, data.target.band)}</span>{:else}<span class="w-s muted one">no measurement yet</span>{/if}
      </div>
      <div class="tile fit" class:late={age.late}>
        {#if data.check}
          <span class="w-s muted one" title={data.check.name}>CHECK · σ, last {data.check.n}</span>
          <span class="w-l num val">{fixed(data.check.sigma, 3)}</span>
          <span class="w-s muted one">{compsLine(data.comps)}</span>
        {:else}
          <span class="w-s muted">CHECK STAR</span>
          <span class="w-m">No check star</span>
          <span class="w-s muted one">{compsLine(data.comps)}</span>
        {/if}
      </div>
      <div class="tile fit">
        <span class="w-s muted">ENDS</span>
        <span class="w-xl num" style:--em={monoEm(ends.value)}>{ends.value}</span>
        <span class="w-m muted one">{ends.note}</span>
      </div>
    </div>

    <div class="row3">
      {#if curve}
        {@render curve()}
      {:else}
        <p class="nocurve w-s muted">No light curve yet: it appears with the first measured frame.</p>
      {/if}
    </div>

    <div class="row4 tiles">
      <div class="tile cond">
        <span class="pair"><span class="w-s muted">STARS</span><span class="w-cond num">{int(starsNow)}</span></span>
        <span class="sp" bind:clientWidth={starsW}>
          {#if starsW > 0}<Sparkline spec={spark(data.stars, null)} width={starsW} height={56} version={data.stars.length} {theme} label="Star count over the run" />{/if}
        </span>
      </div>
      <div class="tile cond">
        <span class="pair">
          <span class="w-s muted">HFD{#if data.hfdFlag}<span class="flag">rule</span>{/if}</span>
          <span class="w-cond num">{fixed(hfdNow, 2)}<span class="w-s muted unit">px</span></span>
        </span>
        <span class="sp" bind:clientWidth={hfdW}>
          {#if hfdW > 0}<Sparkline spec={spark(data.hfd, data.hfdRef ?? null)} width={hfdW} height={56} version={`${data.hfd.length}|${data.hfdRef}`} {theme} label="HFD over the run{data.hfdRef != null ? `, rule threshold ${fixed(data.hfdRef, 2)} px` : ''}" />{/if}
        </span>
      </div>
      <div class="tile cond">
        <span class="pair"><span class="w-s muted">ALT</span><span class="w-cond num">{altValue(data.alt)}</span></span>
        <span class="w-s muted alt">{altLine(data.alt, data.altLimit, data.altUntil)}</span>
      </div>
    </div>

    <div class="row5">
      <!-- By name and shape (the word in the tooltip): never a word cut at 1 280 px. -->
      <span class="links">
        {#each links as l (l.label)}
          <span class="link" title={l.group ? l.word : `${l.label} ${l.word}`} aria-label={l.group ? l.word : `${l.label} ${l.word}`}><StatusBadge variant="bar" tone={l.tone} label={l.group || l.tone === 'ok' ? l.label : `${l.label} ${l.word}`} live={false} /></span>
        {/each}
      </span>
      <span class="dim" role="radiogroup" aria-label="Dim the view">
        <span class="muted">Dim</span>
        {#each DIM_LEVELS as d (d)}
          <button type="button" role="radio" aria-checked={dim === d} class:on={dim === d} onclick={() => (dim = d)}>{d} %</button>
        {/each}
      </span>
      <span class="wake muted" class:warn={wakeShown === 'refused' || wakeShown === 'unsupported' || computer?.warn} title="{computer ? `${computer.text}. ` : ''}{WAKE_WORDS[wakeShown]}">{computer ? `${computer.text} · ${WAKE_SHORT[wakeShown]}` : WAKE_SHORT[wakeShown].replace(/^./, (c) => c.toUpperCase())}</span>
      {#if sound}
        {#if onsound && data.sound}
          <button type="button" class="sound" class:warn={sound.warn} title="Alert sound (Settings › Alerts): a click goes Off → Soft → Normal" onclick={() => onsound?.(nextSound(data.sound!.level))}>{sound.text}</button>
        {:else}
          <span class="sound" class:warn={sound.warn}>{sound.text}</span>
        {/if}
      {/if}
      <span class="grow"></span>
      {#if canPause(data.state) && onpause}
        <HoldButton icon="pause" label="Pause" size="l" verb="pause" confirmTitle="Pause the run?" confirmBody="It holds at the end of this frame; Resume continues it at the table." confirmAction="Pause" onconfirm={onpause} caption={false} pin={pinPause} />
      {:else if data.state === 'pausing'}
        <span class="muted">Pausing after this frame</span>
      {:else if data.state === 'paused'}
        <span class="muted">Paused · resume at the table</span>
      {/if}
      <button type="button" class="back" onclick={onclose} aria-keyshortcuts="W Escape"><Icon name="close" size={20} />W or Esc: back</button>
    </div>
  </div>
</div>

<style>
  /* The view is a size container: its rows and the alert row follow the window it fills
     (1 440 × 900, 1 280 × 800), the same in the gallery's frames. */
  .watch {
    position: fixed;
    inset: 0;
    z-index: var(--z-modal);
    container: watch / size;
    background: var(--bg-2);
    color: var(--fg);
    font-family: var(--font-ui);
    --watch-cond: calc(var(--watch-m) * 1.2);
  }
  .grid {
    display: grid;
    grid-template-rows: 124px 214px minmax(0, 1fr) 128px 56px;
    grid-template-columns: minmax(0, 1fr);
    height: 100%;
  }
  .watch:focus {
    outline: none;
  }
  .watch.embedded {
    position: absolute;
    z-index: auto;
  }
  .row1,
  .row2,
  .row4 {
    border-bottom: var(--border-w) solid var(--border-soft);
    min-height: 0;
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    height: 100%;
  }
  .tile {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 2px;
    min-width: 0;
    padding: 0 var(--space-6);
    border-right: var(--border-w) solid var(--border-soft);
    overflow: hidden;
  }
  .tile:last-child {
    border-right: none;
  }
  /* Values fit their tile (container units): never ellipsised, never below the floor. */
  .fit {
    container-type: inline-size;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .w-state {
    font-size: max(40px, min(72px, calc(100cqi / var(--em))));
    font-weight: var(--weight-semibold);
    letter-spacing: 0.02em;
    line-height: 1;
    white-space: nowrap;
  }
  .w-xl {
    font-size: max(56px, min(var(--watch-xl), calc(100cqi / var(--em, 5))));
    font-weight: var(--weight-medium);
    line-height: 1;
    letter-spacing: -0.01em;
    white-space: nowrap;
  }
  .w-l {
    font-size: max(44px, min(var(--watch-l), calc(100cqi / var(--em, 5))));
    font-weight: var(--weight-medium);
    line-height: 1.05;
    white-space: nowrap;
  }
  .w-m {
    font-size: var(--watch-m);
    line-height: 1.15;
  }
  .w-s {
    font-size: var(--watch-s);
    line-height: 1.2;
  }
  .w-cond {
    font-size: var(--watch-cond);
    font-weight: var(--weight-medium);
    line-height: 1;
    white-space: nowrap;
  }
  .muted {
    color: var(--text-muted);
  }
  .one {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .late .age,
  .late .val {
    color: var(--text-muted);
  }
  .row3 {
    display: flex;
    flex-direction: column;
    min-height: 0;
    padding: var(--space-2) var(--space-4) 0;
    background: var(--chart-surface);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .row3 > :global(*) {
    flex: 1;
    min-height: 0;
  }
  .nocurve {
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0;
  }
  .cond {
    flex-direction: row;
    align-items: center;
    gap: var(--space-5);
  }
  .pair {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: none;
  }
  .sp {
    flex: 1;
    min-width: 0;
    display: block;
  }
  .alt {
    flex: 1;
    min-width: 0;
  }
  .flag {
    margin-left: var(--space-2);
    padding: 0 var(--space-2);
    border: 2px solid var(--warning);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: 20px;
    vertical-align: middle;
  }
  .row5 {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    padding: 0 var(--space-6);
    font-size: 20px;
    min-width: 0;
  }
  .row5 :global(.badge.v-bar) {
    font-size: 18px;
  }
  /* Pause, Dim and Back keep their size; the links and the wake line give way (ellipsis). */
  .row5 > :global(*) {
    flex: none;
  }
  .links {
    display: inline-flex;
    align-items: center;
    gap: var(--space-4);
    flex: 0 1 auto;
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
  }
  .dim {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .dim button {
    white-space: nowrap;
    height: 36px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 18px;
    cursor: pointer;
  }
  .dim button.on {
    background: var(--toggled-bg);
    color: var(--fg);
    border-color: var(--fg-muted);
  }
  .wake {
    flex: 0 1 auto;
    font-size: 16px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }
  .wake.warn {
    color: var(--fg);
  }
  .link {
    display: inline-flex;
    min-width: 0;
    overflow: hidden;
  }
  .link :global(.badge) {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .unit {
    margin-left: 0.25em;
  }
  .sound {
    flex: none;
    height: 36px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-family: var(--font-ui);
    font-size: 18px;
    white-space: nowrap;
  }
  button.sound {
    border-color: var(--border);
    cursor: pointer;
  }
  button.sound:hover {
    background: var(--hover-bg);
  }
  button.sound:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }
  .sound.warn {
    color: var(--fg);
  }
  /* Pause reads as Back and Dim (18 px), not the 13 px of a table control. */
  .row5 :global(.hold .text) {
    font-size: 18px;
  }
  .grow {
    flex: 1;
  }
  .back {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: var(--control-h-l);
    padding: 0 var(--space-4);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: 18px;
    white-space: nowrap;
    cursor: pointer;
  }
  .back:hover,
  .dim button:hover {
    background: var(--hover-bg);
  }
  .back:focus-visible,
  .dim button:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }

  @container watch (max-height: 820px) {
    .grid {
      grid-template-rows: 112px 192px minmax(0, 1fr) 116px 52px;
    }
    .w-state {
      font-size: max(40px, min(64px, calc(100cqi / var(--em))));
    }
  }
</style>
