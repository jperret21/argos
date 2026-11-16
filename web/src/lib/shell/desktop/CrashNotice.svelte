<!--
  Crash notice (W8; 01 2.4.1 "Start-up failure" and "Crash last time", 2.4.6): the ARGOS
  server ended while the UI ran. The shell used to replace the whole UI with its own
  failure page (not themed: Night Red would flash grey); the UI now says it in its theme,
  over the last state it holds (inert behind the scrim, "Last known" as everywhere).

  - What happened in words, the exit status, the server's last lines in mono, the log
    folder; Copy details, Open log folder (the shell opens it: no server is needed).
  - Restart server (initial focus): the shell starts it again and the window reloads on
    it; Quit ARGOS closes the app (nothing is left to stop).
  - restarting: a spinner, no action but Quit; failed: the start-up failure's words and
    Retry. Never dismissible: there is no server behind it.
  - requested (another window or tab shut the server down, shown when the scrim is not
    up): the scrim's words, no error mark (BRAND 4.1: --danger is for errors), no log;
    Quit ARGOS and Restart server only. The error mark and the log are for crash and
    failed only; the log box opens at its end (LogTail).
-->
<script lang="ts">
  import { failureReport } from '../../app/startup';
  import Button from '../../components/Button.svelte';
  import Dialog from '../../components/Dialog.svelte';
  import Spinner from '../../components/Spinner.svelte';
  import LogTail from '../LogTail.svelte';
  import PathText from '../PathText.svelte';
  import type { CrashView } from './desktop.svelte';

  interface Props {
    view: CrashView | null;
    version?: string | null;
    onrestart: () => void;
    onopenlogs?: () => void;
    onquit: () => void;
    preview?: boolean;
  }

  let { view, version = null, onrestart, onopenlogs, onquit, preview = false }: Props = $props();

  const uid = `crash-${Math.random().toString(36).slice(2, 9)}`;
  let copied = $state(false);
  /** An error (crash, failed start): the --danger mark, the log and its actions. */
  const error = $derived(view?.kind === 'crash' || view?.kind === 'failed');

  async function copyDetails(): Promise<void> {
    if (!view) return;
    try {
      await navigator.clipboard.writeText(failureReport({ title: view.title, message: view.message, detail: view.detail, logPath: view.logPath }, version));
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      copied = false;
    }
  }
</script>

<Dialog open={!!view} title={view?.title ?? ''} size="m" role="alertdialog" describedby="{uid}-msg" dismissible={false} closeButton={false} {preview}>
  {#if view}
    <div class="crash" aria-busy={view.kind === 'restarting'}>
      <p class="message" id="{uid}-msg">
        {#if view.kind === 'restarting'}<span class="spin"><Spinner size={14} /></span>{:else if error}<span class="x" aria-hidden="true"></span>{/if}
        <span>{view.message}</span>
      </p>
      {#if error && view.detail}<LogTail text={view.detail} />{/if}
      {#if error && view.logPath}
        <p class="logpath"><span class="key">Log folder</span> <PathText path={view.logPath} /></p>
      {/if}
    </div>
  {/if}
  {#snippet footer()}
    {#if view && error}
      <Button label={copied ? 'Copied' : 'Copy details'} onclick={() => void copyDetails()} />
      {#if onopenlogs}<Button label="Open log folder" onclick={() => onopenlogs?.()} />{/if}
    {/if}
    <span class="spacer"></span>
    <Button label="Quit ARGOS" onclick={() => onquit()} />
    {#if view?.kind !== 'restarting'}
      <Button label={view?.kind === 'failed' ? 'Retry' : 'Restart server'} variant="primary" data-autofocus onclick={() => onrestart()} />
    {/if}
  {/snippet}
</Dialog>

<style>
  .crash {
    display: flex;
    flex-direction: column;
    min-width: 0;
    gap: var(--space-3);
    color: var(--fg);
  }
  .message {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    margin: 0;
  }
  .x,
  .spin {
    flex: none;
  }
  .x {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-round);
    background: var(--danger);
    transform: translateY(-1px);
  }
  .spin {
    display: inline-flex;
    align-self: center;
    color: var(--fg-muted);
  }
  .logpath {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
  }
  .key {
    color: var(--text-muted);
  }
  .spacer {
    flex: 1;
  }
</style>
