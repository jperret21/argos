<!--
  Save… popover (06 §2.2 rows 1.8 #1, 1.10, §2.3.4; M75, M77): the toolbar's [save Save…]
  (Mod+S on the Plan screen).

  - A name, then Save: the server writes `<presets>/<name>.json` in Qt's format (A60). When
    the preset exists the server refuses (409 file_exists) and the popover asks in place:
    "Replace “name”?" [Replace] [Cancel] (spec 2.4 confirmations). A refused name keeps the
    text with the server's words under it.
  - [save Save as file…]: the FilePicker (A61 export), outside the presets folder.
  - Saving stays available during a run (Q-P9: only the plan is locked).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { ApiError } from '../api/client';
  import Button from '../components/Button.svelte';
  import Control from '../components/Control.svelte';
  import Popover from '../components/Popover.svelte';
  import TextField from '../components/TextField.svelte';

  interface Props {
    /** Proposed name (the preset last opened, else the object). */
    suggested: string;
    /** Save; rejects with the ApiError (409 file_exists asks to replace). */
    onsave: (name: string, overwrite: boolean) => Promise<unknown>;
    onfile: () => void;
    open?: boolean;
    preview?: boolean;
    /** Gallery: a frozen state. */
    pin?: { name?: string; replace?: boolean; error?: string } | null;
    /** The trigger, for the screen's Mod+S. */
    trigger?: HTMLElement | null;
  }

  let { suggested, onsave, onfile, open = $bindable(false), preview = false, pin = null, trigger = $bindable(null) }: Props = $props();

  const id = `save-${Math.random().toString(36).slice(2, 8)}`;
  let name = $state(untrack(() => pin?.name ?? suggested));
  let replace = $state(untrack(() => !!pin?.replace));
  let error: string | null = $state(untrack(() => pin?.error ?? null));
  let busy = $state(false);

  $effect(() => {
    if (open && !preview) {
      untrack(() => {
        name = suggested;
        replace = false;
        error = null;
      });
    }
  });

  async function save(overwrite: boolean): Promise<void> {
    const n = name.trim();
    if (!n) {
      error = 'Give the preset a name';
      return;
    }
    busy = true;
    error = null;
    try {
      await onsave(n, overwrite);
      replace = false;
      open = false;
    } catch (err) {
      if (err instanceof ApiError && err.code === 'file_exists' && !overwrite) replace = true;
      else error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }
</script>

{#snippet body()}
  <form
    class="body"
    onsubmit={(e) => {
      e.preventDefault();
      void save(false);
    }}
  >
    <TextField label="Name" value={name} {error} maxlength={100} oninput={(e) => {
      name = (e.currentTarget as HTMLInputElement).value;
      replace = false;
      error = null;
    }} />
    {#if replace}
      <div class="confirm" role="alertdialog" aria-label="Replace the preset">
        <p>Replace “{name.trim()}”? The preset with this name is overwritten.</p>
        <div class="row">
          <Button label="Cancel" size="s" variant="secondary" onclick={() => (replace = false)} />
          <Button label="Replace" size="s" variant="danger" {busy} onclick={() => void save(true)} />
        </div>
      </div>
    {:else}
      <div class="row">
        <Button label="Save" type="submit" size="s" variant="secondary" {busy} />
      </div>
    {/if}
  </form>
{/snippet}

{#snippet footer()}
  <Control icon="save" label="Save as file…" showLabel size="s" variant="ghost" onclick={onfile} />
{/snippet}

{#if preview}
  <Popover open title="Save preset" preview width={320} {footer}>{@render body()}</Popover>
{:else}
  <span bind:this={trigger} class="anchor">
    <Control
      icon="save"
      label="Save…"
      showLabel
      size="s"
      variant="ghost"
      tooltip="bottom"
      tooltipText="Save the plan as a preset"
      shortcut="Mod+S"
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-controls={id}
      onclick={() => (open = !open)}
    />
  </span>
  <Popover bind:open anchor={trigger} title="Save preset" {id} width={320} placement="bottom-start" {footer}>{@render body()}</Popover>
{/if}

<style>
  .anchor {
    display: inline-flex;
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .row {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
  }
  .confirm p {
    margin: 0 0 var(--space-2);
    color: var(--fg);
    font-size: var(--text-s);
    line-height: var(--leading-relaxed);
  }
</style>
