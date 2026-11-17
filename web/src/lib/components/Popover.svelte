<!--
  Popover (README 3.2): a small non-modal panel anchored to its trigger,
  260-360 px wide. No OK button: what it changes applies at once; it never
  holds a destructive action without a confirmation.

  - Opens next to `anchor` (flips and clamps to stay on screen), drawn in
    <body> so no card or toolbar clips it.
  - Focus moves into it on open (first control, or the panel); Escape closes
    it and gives focus back to the trigger; a press outside closes it (focus
    stays where the observer clicked); Tab out of it closes it.
  - The trigger should carry aria-expanded and aria-controls={id}.
  - `preview` draws it in place (component gallery).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { focusableIn, FocusReturn, focusTargetOf, keepKeysInside } from './focus';
  import { type CloseReason, floating, layer, portal } from './layers';
  import type { Placement } from './position';

  interface Props {
    open?: boolean;
    anchor?: HTMLElement | null;
    /** Accessible name; also the visible title unless `hideTitle`. */
    title: string;
    hideTitle?: boolean;
    placement?: Placement;
    /** 260-360 px (README 1.1). */
    width?: number;
    children: Snippet;
    /** A row under the body, separated by a rule (e.g. "Reset layout"). */
    footer?: Snippet;
    onclose?: (reason: CloseReason) => void;
    preview?: boolean;
    id?: string;
  }

  let {
    open = $bindable(false),
    anchor = null,
    title,
    hideTitle = false,
    placement = 'bottom-end',
    width = 300,
    children,
    footer,
    onclose,
    preview = false,
    id = `pop-${Math.random().toString(36).slice(2, 9)}`,
  }: Props = $props();

  function close(reason: CloseReason): void {
    open = false;
    onclose?.(reason);
  }

  function behaviour(node: HTMLElement) {
    const back = new FocusReturn(document, focusTargetOf(anchor));
    let restore = true;
    queueMicrotask(() => (focusableIn(node)[0] ?? node).focus({ preventScroll: true }));
    // Keys used in the popover stay in it (a checkbox's Space is not a
    // shortcut), stopped at the document after the controls' own delegated
    // handlers ran (focus.ts keepKeysInside).
    const release = keepKeysInside(node);
    const onFocusOut = (e: FocusEvent) => {
      const next = e.relatedTarget as Node | null;
      if (!next || node.contains(next) || anchor?.contains(next)) return;
      restore = false;
      close('tab');
    };
    node.addEventListener('focusout', onFocusOut);
    return {
      destroy() {
        release();
        node.removeEventListener('focusout', onFocusOut);
        // A press outside leaves focus where the observer clicked.
        const active = document.activeElement;
        if (restore && (!active || active === document.body || !active.isConnected)) {
          queueMicrotask(() => back.restore());
        }
      },
    };
  }
</script>

{#snippet panel(live: boolean)}
  <div
    class="popover"
    class:preview={!live}
    {id}
    role={live ? 'dialog' : 'group'}
    aria-label={title}
    style:width="{width}px"
    tabindex="-1"
  >
    {#if !hideTitle}<h2 class="title">{title}</h2>{/if}
    <div class="body">{@render children()}</div>
    {#if footer}<div class="footer">{@render footer()}</div>{/if}
  </div>
{/snippet}

{#if open}
  {#if preview}
    {@render panel(false)}
  {:else}
    <div
      class="float"
      use:portal
      use:floating={{ anchor, placement, gap: 4 }}
      use:layer={{ kind: 'popover', anchor, onclose: close }}
      use:behaviour
    >
      {@render panel(true)}
    </div>
  {/if}
{/if}

<style>
  .float {
    z-index: var(--z-popover);
  }

  .popover {
    display: flex;
    flex-direction: column;
    max-width: calc(100vw - 16px);
    max-height: calc(100vh - 16px);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--shadow-2);
    color: var(--fg);
    font-size: var(--text-m);
    animation: enter var(--duration-base) var(--ease-out);
  }
  .popover:focus {
    outline: none;
  }
  .popover.preview {
    animation: none;
  }

  .title {
    margin: 0;
    padding: var(--space-3) var(--space-4) 0;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }

  .body {
    min-height: 0;
    padding: var(--space-2) var(--space-4) var(--space-3);
    overflow: auto;
  }

  .footer {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }

  @keyframes enter {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
  }
</style>
