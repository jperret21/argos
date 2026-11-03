<!--
  Checkbox drawn with tokens (native input underneath, visually hidden: the
  keyboard, the label click and screen readers work as usual). The check is
  --fg on --toggled-bg, not brass: checkboxes list visible panels and
  options that are on most of the time, and brass marks "this one" (BRAND 3).

  `disabledReason` makes it unavailable and says why (the second line, the
  tooltip's reason line): since wave 2 with aria-disabled, so it stays
  focusable and a screen reader reaches the reason (BRAND 7); a press does
  not change it. `disabled` (hard) only where there is no reason to give.
-->
<script lang="ts">
  import { tooltip } from './tooltip';

  interface Props {
    label: string;
    checked?: boolean;
    disabled?: boolean;
    disabledReason?: string | null;
    /** Second line, --text-muted. */
    detail?: string | null;
    onchange?: (checked: boolean) => void;
    size?: 's' | 'm';
  }

  let {
    label,
    checked = $bindable(false),
    disabled = false,
    disabledReason = null,
    detail = null,
    onchange,
    size = 'm',
  }: Props = $props();

  const off = $derived(disabled || !!disabledReason);
  const soft = $derived(!disabled && !!disabledReason);
  const detailId = `cb-${Math.random().toString(36).slice(2, 9)}-detail`;
</script>

<label
  class="checkbox size-{size}"
  class:off
  use:tooltip={{ text: label, reason: disabledReason, placement: 'top', disabled: !disabledReason }}
>
  <input
    class="visually-hidden"
    type="checkbox"
    bind:checked
    {disabled}
    aria-disabled={soft || undefined}
    aria-describedby={disabledReason || detail ? detailId : undefined}
    onclick={(e) => {
      if (soft) e.preventDefault(); // unavailable: the press shows the reason, nothing changes
    }}
    onchange={() => onchange?.(checked)}
  />
  <span class="box" aria-hidden="true"></span>
  <span class="text">
    <span class="label">{label}</span>
    {#if disabledReason || detail}<span class="detail" id={detailId}>{disabledReason ?? detail}</span>{/if}
  </span>
</label>

<style>
  .checkbox {
    display: flex;
    width: fit-content;
    align-items: flex-start;
    gap: var(--space-3);
    min-height: 24px;
    padding: 3px 0;
    color: var(--fg);
    font-size: var(--text-m);
    line-height: 18px;
    cursor: pointer;
  }
  .size-s {
    font-size: var(--text-s);
  }

  .box {
    position: relative;
    flex: none;
    width: 14px;
    height: 14px;
    margin-top: 2px;
    border: var(--border-w) solid var(--fg-muted);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    transition:
      background-color var(--duration-fast) var(--ease-standard),
      border-color var(--duration-fast) var(--ease-standard);
  }
  .checkbox:hover:not(.off) .box {
    border-color: var(--fg);
  }
  input:checked + .box {
    border-color: var(--fg);
    background: var(--toggled-bg);
  }
  input:checked + .box::after {
    content: '';
    position: absolute;
    left: 4px;
    top: 1px;
    width: 4px;
    height: 8px;
    border: solid var(--fg);
    border-width: 0 1.5px 1.5px 0;
    transform: rotate(45deg);
  }
  input:focus-visible + .box {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }

  .text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .detail {
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-tight);
  }

  .off {
    cursor: not-allowed;
  }
  .off .label {
    color: var(--fg-disabled);
  }
  .off .box {
    border-color: var(--border-soft);
    background: transparent;
  }
  .off input:checked + .box::after {
    border-color: var(--fg-disabled);
  }
</style>
