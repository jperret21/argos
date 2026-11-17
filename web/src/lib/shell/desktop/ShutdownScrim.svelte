<!--
  Shutdown progress (01 2.3.7 "then, full-window scrim", 2.4.1 "progress scrim with the
  current stage", M18; A7's WS `shutdown` stages): the --scrim over the whole window and
  one panel. The server's planned stages are listed from the start (a hollow ring until
  reached); each is marked when it ends, with its elapsed time counted up (tenths under
  10 s; honest: no fake bar, no estimate). The server's own bound (budget_s) is said once.
  The marks are the start-up screen's (done: a filled --success dot; pending: a ring); a
  stage cut short has its own mark (BRAND 8's upright attention mark) and the words.

  - stopping: "Shutting down ARGOS…", the stages; past STUCK_MS "Quit now" ends it at
    once (the shell stops the server: SIGTERM, then SIGKILL).
  - closing: the server is done, the window closes; if it does not, say so and offer
    "Close window" (asks the shell again).
  - remote: another client shut the server down; the stages, no action here.
  - stopped: that server is gone ("The ARGOS server was shut down", the crash notice's
    words for the same event: one notice per cause); this page reconnects when it runs
    again (Reconnect), the desktop app offers Restart server.
  Not dismissible (Escape does nothing: the shutdown cannot be undone). The current
  stage is announced politely. `now` freezes the clock (gallery). `delayMs`: a local quit
  is often over in half a second; the panel then shows only if it is still going after
  that long (no modal flash, BRAND 9), while the app is already inert (App.svelte).
-->
<script lang="ts">
  import Button from '../../components/Button.svelte';
  import Dialog from '../../components/Dialog.svelte';
  import Spinner from '../../components/Spinner.svelte';
  import { REQUESTED_TITLE, requestedText } from './desktop.svelte';
  import type { QuitPhase, StageRow } from './quit.svelte';
  import { elapsedText } from './words';

  interface Props {
    phase: QuitPhase;
    stages: readonly StageRow[];
    startedAt?: number | null;
    stuck?: boolean;
    closeStalled?: boolean;
    /** Inside the desktop app (Quit now / Close window exist). */
    desktop?: boolean;
    /** The server's bound for the whole shutdown, s. */
    budgetS?: number | null;
    onquitnow?: () => void;
    onreconnect?: () => void;
    /** "Reconnect" (browser) or "Restart server" (desktop: the shell starts it again). */
    reconnectLabel?: string;
    preview?: boolean;
    /** Gallery: a fixed clock (ms, same base as the stage times). */
    now?: number | null;
    /** Show the panel of a local quit (stopping, closing) only after this long (ms). */
    delayMs?: number;
  }

  let {
    phase,
    stages,
    startedAt = null,
    stuck = false,
    closeStalled = false,
    desktop = true,
    budgetS = null,
    onquitnow,
    onreconnect,
    reconnectLabel = 'Reconnect',
    preview = false,
    now = null,
    delayMs = 0,
  }: Props = $props();

  let tick = $state(Date.now());
  $effect(() => {
    if (now !== null || (phase !== 'stopping' && phase !== 'remote')) return;
    const t = setInterval(() => (tick = Date.now()), 100);
    return () => clearInterval(t);
  });
  const clock = $derived(now ?? tick);

  let delayed = $state(false);
  $effect(() => {
    if (delayMs <= 0) return;
    const t = setTimeout(() => (delayed = true), delayMs);
    return () => clearTimeout(t);
  });
  const local = $derived(phase === 'stopping' || phase === 'closing');
  const open = $derived((local && (delayMs <= 0 || delayed)) || phase === 'remote' || phase === 'stopped');
  const title = $derived(
    phase === 'stopped'
      ? REQUESTED_TITLE
      : phase === 'remote'
        ? 'The ARGOS server is shutting down'
        : phase === 'closing'
          ? 'Closing ARGOS…'
          : 'Shutting down ARGOS…',
  );
  const current = $derived(stages.find((s) => s.from !== null && s.to === null) ?? null);
  const total = $derived(startedAt !== null ? elapsedText(clock - startedAt) : null);
  const STATE_WORDS = { pending: 'not started', active: 'in progress', done: 'done', cut: 'cut short' } as const;
</script>

<Dialog {open} {title} size="s" role="dialog" dismissible={false} closeButton={false} {preview}>
  <div class="scrim-body" aria-busy={phase === 'stopping' || phase === 'remote'}>
    {#if phase === 'remote'}
      <p class="lead">Another ARGOS window or browser tab asked the server to stop. Everything it runs stops with it.</p>
    {:else if phase === 'stopped'}
      <p class="lead">{requestedText(desktop)}</p>
    {/if}
    {#if stages.length}
      <ol class="stages" aria-label="Shutdown stages">
        {#each stages as s (s.id)}
          {@const st = s.from === null ? 'pending' : s.to === null && phase !== 'stopped' ? 'active' : s.to === null ? 'cut' : 'done'}
          <li class="stage {st}">
            <span class="state-mark" aria-hidden="true">
              {#if st === 'active'}<Spinner size={14} />{:else if st === 'cut'}<span class="cut-mark"></span>{:else}<span class="dot"></span>{/if}
            </span>
            <span class="label">{s.label}</span>
            <span class="time num">{#if st === 'cut'}<span class="cut-words">cut short</span>{:else if s.from !== null}{elapsedText((s.to ?? clock) - s.from)}{/if}</span>
            {#if st !== 'cut'}<span class="visually-hidden">: {STATE_WORDS[st]}</span>{/if}
          </li>
        {/each}
      </ol>
    {/if}
    <p class="visually-hidden" aria-live="polite">{current ? current.label : phase === 'closing' ? 'ARGOS server stopped; closing the window' : ''}</p>
    {#if phase === 'closing'}
      <p class="note">{closeStalled ? 'The ARGOS server stopped, but the window did not close.' : 'The ARGOS server stopped. The window closes.'}</p>
    {:else if stuck && total}
      <p class="note">Still stopping after <span class="num">{total}</span>. Quit now ends the server at once; a stage it has not finished is cut short.</p>
    {:else if budgetS && (phase === 'stopping' || phase === 'remote')}
      <p class="note">The server stops within <span class="num">{budgetS} s</span> at most.</p>
    {/if}
  </div>
  {#snippet footer()}
    {#if phase === 'closing' && closeStalled && desktop}
      <Button label="Close window" variant="primary" onclick={() => onquitnow?.()} />
    {:else if (phase === 'stopping' || phase === 'remote') && stuck && desktop}
      <Button label="Quit now" variant="danger" onclick={() => onquitnow?.()} />
    {:else if phase === 'stopped'}
      {#if desktop}<Button label="Quit ARGOS" onclick={() => onquitnow?.()} />{/if}
      <Button label={reconnectLabel} variant="primary" data-autofocus onclick={() => onreconnect?.()} />
    {/if}
  {/snippet}
</Dialog>

<style>
  .scrim-body {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    color: var(--fg);
  }
  .lead,
  .note {
    margin: 0;
  }
  .note {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .stages {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .stage {
    display: grid;
    grid-template-columns: 16px minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-3);
    color: var(--text-muted);
  }
  .stage.active {
    color: var(--fg);
  }
  .stage.pending .dot {
    background: none;
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .stage.done .dot {
    background: var(--success);
  }
  .state-mark {
    display: inline-grid;
    place-items: center;
    width: 16px;
    height: 16px;
  }
  /* The start-up screen's marks (StartupScreen.svelte): same sizes, same done colour. */
  .dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-round);
  }
  /* BRAND 8's attention mark (a bar over a dot, --warning), as StatusBadge draws it. */
  .cut-mark {
    position: relative;
    width: 3px;
    height: 7px;
    margin-bottom: 4px;
    border-radius: 1px;
    background: var(--warning);
  }
  .cut-mark::after {
    content: '';
    position: absolute;
    left: 0;
    top: 8px;
    width: 3px;
    height: 3px;
    border-radius: 1px;
    background: var(--warning);
  }
  .cut-words {
    font-family: var(--font-sans);
  }
  .time {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-s);
  }
</style>
