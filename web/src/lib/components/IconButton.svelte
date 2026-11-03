<!--
  Icon-first button: the symbol is the control, the text is its accessible
  name and its tooltip (BRAND.md sections 7 and 8).

  Since wave 2 a thin wrapper over Control.svelte (web/lab/PROPOSAL.md 6, W2),
  so every existing screen gets the v2 states without being edited: the
  reason of an unavailable button on the tooltip's second line and on press,
  the pressed inset, the error outline and corner dot, the progress ring and
  the key-hint cap while Cmd / Ctrl is held alone. New code may use Control
  directly; the props below are unchanged.

  - `label` is required: it becomes aria-label and the tooltip (and the
    visible text with `showLabel`).
  - `shortcut` (spec such as "E", "Shift+A", "Escape") is shown in the tooltip
    and exposed as aria-keyshortcuts. Wiring the key itself is the caller's job.
  - `pressed` (boolean) makes it a toggle button (aria-pressed).
  - `busy` swaps the glyph for the spinner, sets aria-busy, swallows clicks.
  - `disabledReason` makes it unavailable with aria-disabled (still
    focusable); the tooltip says why, and a press says it at once.
  - `glyphTone="danger"`: only the glyph in --danger (a routine stop).
  - `layoutToggle`: a toggle of the layout, neutral on state (no brass).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';
  import Control from './Control.svelte';
  import type { TooltipPlacement } from './tooltip';

  type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';
  type Size = 's' | 'm' | 'l';

  interface Props extends Omit<HTMLButtonAttributes, 'children' | 'aria-pressed' | 'disabled'> {
    icon: string;
    label: string;
    shortcut?: string;
    showLabel?: boolean;
    variant?: Variant;
    size?: Size;
    /** Toggle state; leave undefined for a plain push button. */
    pressed?: boolean;
    busy?: boolean;
    disabled?: boolean;
    /** Why the action is unavailable: aria-disabled, the tooltip's second line. */
    disabledReason?: string | null;
    /** Tooltip side, or 'none'. Labelled buttons only get one when it adds something. */
    tooltip?: TooltipPlacement | 'none';
    /** Tooltip text when it should differ from the accessible name. */
    tooltipText?: string;
    /** Colour of the glyph alone (the outline and label keep the variant's). */
    glyphTone?: 'danger';
    /** Toggle of the layout, not of the instrument: neutral on state. */
    layoutToggle?: boolean;
    /** v2: what failed on the last attempt (danger outline + corner dot). */
    error?: string | null;
    /** v2: elapsed fraction of a timed operation (time ring). */
    progress?: number | null;
    progressText?: string;
    /** v2: how to use it when it is not a plain click. */
    hint?: string | null;
    trailing?: Snippet;
    el?: HTMLButtonElement | null;
  }

  let { el = $bindable(null), ...props }: Props = $props();
</script>

<Control bind:el {...props} />
