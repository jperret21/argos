<!--
  Quit confirmation (01 2.3.7 and 2.4.3, M18; A7's 409 busy): shown only when something
  runs. It says what runs, in the UI's words with what it knows ("A sequence is running:
  SS Cyg, 34 of 120 frames."), and what quitting stops. A confirmation dialog with text
  buttons (BRAND 7, 01 2.4.3 "Quit while busy"; the same pattern as stopping a run, D4):
  Cancel has the initial focus (Escape = Cancel), "Quit ARGOS" is the destructive one
  (outlined in --danger) and forces the shutdown; the button is busy while the forced
  request is in flight. A refusal that is not "busy" is shown in words; Quit ARGOS still
  quits.
-->
<script lang="ts">
  import type { BusyItem } from '../../api/desktop';
  import ConfirmDialog from '../../components/ConfirmDialog.svelte';
  import Icon from '../../components/Icon.svelte';
  import { busyIcon, quitConsequence } from './words';

  interface Props {
    open: boolean;
    items: readonly BusyItem[];
    /** One sentence per item (QuitFlow.sentences). */
    sentences: readonly string[];
    /** The server's refusal text, shown when it named nothing. */
    message?: string | null;
    error?: string | null;
    /** The forced request is in flight. */
    forcing?: boolean;
    oncancel: () => void;
    onforce: () => Promise<unknown> | unknown;
    preview?: boolean;
  }

  let { open, items, sentences, message = null, error = null, forcing = false, oncancel, onforce, preview = false }: Props = $props();

  const consequence = $derived(quitConsequence(items));
  const shownError = $derived(error ? `${error.replace(/\s+$/, '')}${/[.!?]$/.test(error.trim()) ? '' : '.'} Quit ARGOS still quits.` : null);

  /** The forced request: the button stays busy until it settles (the flow then moves on). */
  async function confirm(): Promise<void> {
    await onforce();
  }
</script>

<ConfirmDialog
  {open}
  title="Quit ARGOS?"
  confirmLabel="Quit ARGOS"
  cancelLabel="Cancel"
  destructive
  busy={forcing}
  error={shownError}
  {preview}
  onconfirm={confirm}
  oncancel={() => oncancel()}
>
  <div class="what">
    {#if sentences.length}
      <ul class="busy" aria-label="Running now">
        {#each items as item, i (item.kind)}
          <li><span class="glyph"><Icon name={busyIcon(item.kind)} size="s" /></span><span>{sentences[i]}</span></li>
        {/each}
      </ul>
    {:else if message}
      <p class="lead">{message}</p>
    {/if}
    <p class="consequence">{consequence}</p>
  </div>
</ConfirmDialog>

<style>
  .what {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    color: var(--fg);
  }
  .busy {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .busy li {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
  }
  .glyph {
    display: inline-flex;
    flex: none;
    margin-top: 1px;
    color: var(--fg-muted);
  }
  .lead,
  .consequence {
    margin: 0;
  }
  .consequence {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>
