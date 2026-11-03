<!--
  Text-only button (BRAND 7, row 3): dialog OK / Cancel, confirmations, form
  submits. Since wave 2 a thin wrapper over Control.svelte (web/lab/PROPOSAL.md
  6, W2), with the same variants and states as IconButton (BRAND 8).

  - Sizes keep their wave-1 heights: `m` 30 px (--control-h-s), `s` 24 px.
  - `busy` puts the spinner in the left padding (the label stays and the
    width never changes), sets aria-busy and swallows clicks.
  - `disabledReason` makes it unavailable with aria-disabled (still
    focusable); the tooltip's second line says why, and a press says it at once.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';
  import Control from './Control.svelte';
  import type { TooltipPlacement } from './tooltip';

  type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';

  interface Props extends Omit<HTMLButtonAttributes, 'children' | 'disabled'> {
    label?: string;
    children?: Snippet;
    variant?: Variant;
    size?: 's' | 'm';
    busy?: boolean;
    disabled?: boolean;
    disabledReason?: string | null;
    /** v2: what failed on the last attempt (danger outline + corner dot). */
    error?: string | null;
    /** v2: shortcut spec shown in the tooltip and as a key hint. */
    shortcut?: string;
    tooltip?: TooltipPlacement | 'none';
    el?: HTMLButtonElement | null;
  }

  let { size = 'm', tooltip = 'top', el = $bindable(null), ...props }: Props = $props();
</script>

<Control bind:el size={size === 's' ? 'xs' : 's'} {tooltip} {...props} />
