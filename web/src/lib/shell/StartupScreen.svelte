<!--
  Start-up screen (01 section 2.3.8, M1-M2): inside the window, themed
  before the first paint (index.html applies data-theme), so Night Red
  never flashes white or gold.

  - Honest stages: each line is marked when it really completes (a spinner
    while it runs, a filled mark when done); no fake progress bar.
  - Failure: the screen stays until the observer acts. It says what failed,
    the exact text in mono, the log folder, and offers Copy details, Open log
    folder (desktop app only) and Retry. It never hides an error.
  - The mark comes from brand/argos-mark.svg (the generator's output,
    currentColor), never redrawn; the wordmark is "ARGOS" in Plex Sans 600.
  - `leaving` fades it out (--duration-base; instant with reduced motion).
-->
<script lang="ts">
  import mark from '../../design/brand/argos-mark.svg?raw';
  import { failureReport, type StartupFailure, type StartupStage } from '../app/startup';
  import Button from '../components/Button.svelte';

  interface Props {
    stages: readonly StartupStage[];
    version?: string | null;
    failure?: StartupFailure | null;
    onretry?: () => void;
    /** Desktop app only: reveal the log folder. */
    onopenlogs?: () => void;
    leaving?: boolean;
    /** Fill the parent instead of the window (component gallery). */
    contained?: boolean;
  }

  let {
    stages,
    version = null,
    failure = null,
    onretry,
    onopenlogs,
    leaving = false,
    contained = false,
  }: Props = $props();

  let copied = $state(false);
  let root: HTMLElement | undefined = $state();

  // A failure takes the keyboard focus to Retry, so Enter retries.
  $effect(() => {
    if (failure && !contained) root?.querySelector<HTMLElement>('[data-startup-retry]')?.focus();
  });

  async function copyDetails(): Promise<void> {
    if (!failure) return;
    try {
      await navigator.clipboard.writeText(failureReport(failure, version));
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      copied = false;
    }
  }

  const STATE_WORDS: Record<StartupStage['state'], string> = {
    pending: 'waiting',
    active: 'in progress',
    done: 'done',
    failed: 'failed',
  };
</script>

<div class="startup" class:contained class:leaving role="main" aria-busy={!failure && !leaving} bind:this={root}>
  <div class="center">
    <div class="mark" aria-hidden="true">{@html mark}</div>
    <h1 class="wordmark">ARGOS</h1>
    {#if version}<p class="version num">Version {version}</p>{/if}

    {#if failure}
      <section class="failure" role="alert" aria-labelledby="startup-fail-title">
        <h2 id="startup-fail-title"><span class="x" aria-hidden="true"></span>{failure.title}</h2>
        <p class="message">{failure.message}</p>
        {#if failure.detail}<pre class="detail">{failure.detail}</pre>{/if}
        {#if failure.logPath}
          <p class="logpath"><span class="key">Log folder</span> <span class="num">{failure.logPath}</span></p>
        {/if}
        <div class="actions">
          <Button label={copied ? 'Copied' : 'Copy details'} onclick={() => void copyDetails()} />
          {#if onopenlogs}<Button label="Open log folder" onclick={() => onopenlogs?.()} />{/if}
          <span class="spacer"></span>
          {#if onretry}<Button label="Retry" variant="primary" data-startup-retry onclick={() => onretry?.()} />{/if}
        </div>
      </section>
    {:else}
      <ol class="stages" aria-label="Start-up">
        {#each stages as s (s.id)}
          <li class="stage {s.state}">
            <span class="state-mark" aria-hidden="true">
              {#if s.state === 'active'}
                <svg class="spinner" viewBox="0 0 24 24"><path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" /></svg>
              {:else}
                <span class="dot"></span>
              {/if}
            </span>
            <span>{s.label}</span>
            <span class="visually-hidden">: {STATE_WORDS[s.state]}</span>
          </li>
        {/each}
      </ol>
    {/if}
  </div>
  <p class="footer">GNU GPL v3 or later · free software with no warranty · Developed by Jules Perret</p>
</div>

<style>
  .startup {
    position: fixed;
    inset: 0;
    z-index: var(--z-modal);
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: var(--space-6) 0 var(--space-5);
    overflow: auto;
    background: var(--bg);
    color: var(--fg);
    transition: opacity var(--duration-base) var(--ease-out);
  }
  .startup.contained {
    position: relative;
    inset: auto;
    z-index: auto;
    height: 100%;
  }
  .startup.leaving {
    opacity: 0;
    pointer-events: none;
  }

  /* The mark sits at a fixed height (its top at about 30 % of the window):
     stages or a failure panel grow downward, so the mark never jumps. */
  .center {
    display: flex;
    flex: 1;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    width: min(560px, calc(100% - 48px));
    padding-top: max(0px, calc(30vh - var(--space-6)));
  }

  .mark {
    width: 96px;
    height: 96px;
    color: var(--accent);
  }
  .mark :global(svg) {
    display: block;
    width: 100%;
    height: 100%;
  }

  .wordmark {
    margin: var(--space-4) 0 0;
    font-size: var(--text-2xl);
    font-weight: var(--weight-semibold);
    letter-spacing: -0.065em;
    line-height: var(--leading-tight);
  }

  .version {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  .stages {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: var(--space-6) 0 0;
    padding: 0;
    list-style: none;
    font-size: var(--text-m);
  }
  .stage {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    color: var(--fg);
  }
  .stage.pending {
    color: var(--text-muted);
  }

  .state-mark {
    display: inline-flex;
    width: 16px;
    height: 16px;
    align-items: center;
    justify-content: center;
    color: var(--fg-muted);
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-round);
  }
  .pending .dot {
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .done .dot {
    background: var(--success);
  }
  .failed .dot {
    background: var(--danger);
  }

  .spinner {
    width: 16px;
    height: 16px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    stroke-linecap: round;
    animation: spin 0.9s linear infinite;
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

  .failure {
    width: 100%;
    margin-top: var(--space-6);
  }
  .failure h2 {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .x {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-round);
    background: var(--danger);
  }
  .message {
    margin: var(--space-2) 0 0;
  }
  .detail {
    max-height: 200px;
    margin: var(--space-3) 0 0;
    padding: var(--space-3);
    overflow: auto;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .logpath {
    margin: var(--space-3) 0 0;
    font-size: var(--text-s);
    overflow-wrap: anywhere;
  }
  .key {
    color: var(--text-muted);
  }
  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-top: var(--space-5);
  }
  .spacer {
    flex: 1;
  }

  .footer {
    margin: var(--space-5) var(--space-5) 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-align: center;
  }
</style>
