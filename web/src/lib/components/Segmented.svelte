<!--
  Segmented choice (radio group) drawn with tokens: no native <select>, whose
  pop-up would draw grey in Night Red (BRAND 4.3). Native radios underneath,
  so arrow keys and screen readers work as expected.
-->
<script lang="ts" generics="T extends string">
  interface Option {
    value: T;
    label: string;
  }

  interface Props {
    label: string;
    options: readonly Option[];
    value: T;
    disabled?: boolean;
    onchange?: (value: T) => void;
    /** 's': 20 px segments for drawer headers and toolbars. */
    size?: 's' | 'm';
  }

  let { label, options, value = $bindable(), disabled = false, onchange, size = 'm' }: Props = $props();
  const name = `seg-${Math.random().toString(36).slice(2, 9)}`;
</script>

<div class="segmented size-{size}" role="radiogroup" aria-label={label}>
  {#each options as option (option.value)}
    <label class:checked={value === option.value} class:disabled>
      <input
        class="visually-hidden"
        type="radio"
        {name}
        value={option.value}
        checked={value === option.value}
        {disabled}
        onchange={() => {
          value = option.value;
          onchange?.(option.value);
        }}
      />
      <span>{option.label}</span>
    </label>
  {/each}
</div>

<style>
  .segmented {
    display: flex;
    padding: 2px;
    gap: 2px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }

  label {
    position: relative;
    flex: 1 1 0;
    min-width: 0;
  }

  span {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 24px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    white-space: nowrap;
    cursor: pointer;
    transition:
      background-color var(--duration-fast) var(--ease-standard),
      color var(--duration-fast) var(--ease-standard);
  }

  .size-s span {
    height: 20px;
    padding: 0 var(--space-2);
    font-size: var(--text-xs);
  }
  /* Compact (log headers): each segment as wide as its word, with the 2 px gap,
     so "All" never touches "Warnings" while "Errors" floats away. */
  .size-s label {
    flex: 0 0 auto;
  }
  .size-s {
    display: inline-flex;
  }

  label:hover:not(.disabled) span {
    color: var(--fg);
  }

  /* Selected: raised fill, --fg text and a neutral edge. A segmented choice
     always has one selection: brass would mark every control (BRAND 3). */
  .checked span {
    border-color: var(--border);
    background: var(--toggled-bg);
    color: var(--fg);
  }

  input:focus-visible + span {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }

  .disabled span {
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  .disabled.checked span {
    border-color: var(--border-soft);
    background: transparent;
  }
</style>
