<!--
  Text input in the instrument style (same box as NumberField). `mono` for
  coordinates and addresses. `error` outlines the field in --danger and says
  why in words; `hint` is the help line otherwise.
-->
<script lang="ts">
  import type { HTMLInputAttributes } from 'svelte/elements';

  interface Props extends Omit<HTMLInputAttributes, 'value' | 'class'> {
    label: string;
    value: string;
    mono?: boolean;
    error?: string | null;
    hint?: string | null;
    hideLabel?: boolean;
  }

  let {
    label,
    value = $bindable(),
    mono = false,
    error = null,
    hint = null,
    hideLabel = false,
    ...rest
  }: Props = $props();

  const id = `tf-${Math.random().toString(36).slice(2, 9)}`;
</script>

<div class="field" class:invalid={!!error}>
  <label for={id} class:visually-hidden={hideLabel}>{label}</label>
  <input
    {...rest}
    {id}
    type="text"
    class:mono
    autocomplete="off"
    spellcheck="false"
    bind:value
    aria-invalid={!!error || undefined}
    aria-describedby={error || hint ? `${id}-help` : undefined}
  />
  {#if error}
    <span class="help error" id="{id}-help">{error}</span>
  {:else if hint}
    <span class="help" id="{id}-help">{hint}</span>
  {/if}
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  label {
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  input {
    width: 100%;
    height: var(--input-h);
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-m);
    transition: border-color var(--duration-fast) var(--ease-standard);
  }
  input.mono {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  /* Placeholders are words: --text-muted (AA), never --fg-disabled. */
  input::placeholder {
    color: var(--text-muted);
    opacity: 1;
  }
  input:hover:not(:disabled) {
    border-color: var(--fg-muted);
  }
  input:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 0;
    border-color: var(--focus-ring);
  }
  input:disabled {
    color: var(--fg-disabled);
    border-color: var(--border-soft);
    background: transparent;
  }

  .invalid input {
    border-color: var(--danger);
  }

  .help {
    min-height: 1.4em;
    color: var(--text-muted);
    font-size: var(--text-xs);
    overflow-wrap: anywhere;
  }
  .help.error {
    color: var(--fg);
  }
  .help.error::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: var(--space-1);
    border-radius: var(--radius-round);
    background: var(--danger);
    vertical-align: 1px;
  }
</style>
