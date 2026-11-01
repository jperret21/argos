<!--
  Modal dialog (web/spec/README.md section 3.2; replaces every QMessageBox):
  480 px (confirm), 560 px (form) or 640 px (pickers), title = the question
  or the task, body text --fg, text-only buttons in the footer, primary on
  the right.

  - Modal: drawn in <body> over a --scrim; the app behind is inert (no
    focus, no clicks, hidden from screen readers) until it closes.
  - Focus: moves in on open (initialFocus selector, then [data-autofocus],
    then the first control), Tab and Shift+Tab cycle inside, and focus
    returns to the control that opened it when it closes.
  - Escape = Cancel (the shortcut registry still aborts mount motion, D21);
    `dismissible={false}` keeps it open while a submit runs.
  - `preview` draws the dialog in place, without scrim or trap (gallery).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { FocusReturn, focusableIn, handleTrapKey } from './focus';
  import IconButton from './IconButton.svelte';
  import { type CloseReason, layer, portal } from './layers';

  interface Props {
    open?: boolean;
    title: string;
    /** One line under the title, --text-muted. */
    subtitle?: string;
    size?: 's' | 'm' | 'l';
    role?: 'dialog' | 'alertdialog';
    children: Snippet;
    footer?: Snippet;
    /** CSS selector of the first control to focus. */
    initialFocus?: string;
    /** Where focus goes when it closes (default: what was focused when it opened). */
    returnFocus?: HTMLElement | null;
    /** false: Escape and the close button do nothing (a submit is running). */
    dismissible?: boolean;
    /** Show the [x] in the header. */
    closeButton?: boolean;
    onclose?: (reason: CloseReason) => void;
    /** Draw in place, not as a modal layer (component gallery). */
    preview?: boolean;
    /** id of the element that describes the dialog (alertdialog message). */
    describedby?: string;
  }

  let {
    open = $bindable(false),
    title,
    subtitle,
    size = 'm',
    role = 'dialog',
    children,
    footer,
    initialFocus,
    returnFocus = null,
    dismissible = true,
    closeButton = true,
    onclose,
    preview = false,
    describedby,
  }: Props = $props();

  const uid = `dlg-${Math.random().toString(36).slice(2, 9)}`;

  function close(reason: CloseReason): void {
    if (!dismissible && reason !== 'action') return;
    open = false;
    onclose?.(reason);
  }

  /**
   * First focus: the `initialFocus` selector, then [data-autofocus], then the
   * first control of the body, then of the footer, then the dialog itself
   * (never the header's close button when there is anything else).
   */
  function firstFocus(dialog: HTMLElement): HTMLElement {
    const pick = (sel: string | undefined) => (sel ? dialog.querySelector<HTMLElement>(sel) : null);
    const inPart = (sel: string) => {
      const part = dialog.querySelector<HTMLElement>(sel);
      return part ? (focusableIn(part)[0] ?? null) : null;
    };
    return pick(initialFocus) ?? pick('[data-autofocus]') ?? inPart('.body') ?? inPart('footer') ?? dialog;
  }

  /**
   * The modal layer's behaviour: focus in on open; Tab and Shift+Tab cycle
   * inside; keys typed in the modal stay in it (the section behind must not
   * take "E" as an exposure; Escape still travels, the registry aborts mount
   * motion, D21); focus back out on close, once the layer stack has lifted
   * `inert` from the app.
   */
  function modal(node: HTMLElement) {
    // When nothing holds focus yet (a menu that opened this dialog is closing
    // in the same update), remember the opener once that settles.
    const nowhere = !document.activeElement || document.activeElement === document.body;
    let back = new FocusReturn(document, returnFocus);
    const dialog = node.querySelector<HTMLElement>('[aria-modal="true"]') ?? node;
    queueMicrotask(() => {
      if (nowhere && !returnFocus) back = new FocusReturn(document);
      firstFocus(dialog).focus({ preventScroll: true });
    });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Tab') handleTrapKey(e, focusableIn(dialog), document.activeElement, dialog);
      if (e.key !== 'Escape') e.stopPropagation();
    };
    node.addEventListener('keydown', onKey);
    return {
      destroy() {
        node.removeEventListener('keydown', onKey);
        queueMicrotask(() => back.restore());
      },
    };
  }
</script>

{#snippet panel(isModal: boolean)}
  <div
    class="dialog size-{size}"
    class:preview={!isModal}
    role={isModal ? role : 'group'}
    aria-modal={isModal ? 'true' : undefined}
    aria-labelledby="{uid}-title"
    aria-describedby={describedby}
    tabindex="-1"
  >
    <header>
      <div class="titles">
        <h2 id="{uid}-title">{title}</h2>
        {#if subtitle}<p class="subtitle">{subtitle}</p>{/if}
      </div>
      {#if closeButton}
        <IconButton
          icon="close"
          label="Close"
          variant="ghost"
          size="s"
          shortcut="Escape"
          tooltip="bottom"
          disabledReason={dismissible ? null : 'wait until it finishes'}
          onclick={() => close('close')}
        />
      {/if}
    </header>
    <div class="body">
      {@render children()}
    </div>
    {#if footer}
      <footer>{@render footer()}</footer>
    {/if}
  </div>
{/snippet}

{#if open}
  {#if preview}
    {@render panel(false)}
  {:else}
    <div
      class="layer"
      use:portal
      use:layer={{ kind: 'dialog', modal: true, onclose: close }}
      use:modal
    >
      <div class="scrim" aria-hidden="true"></div>
      {@render panel(true)}
    </div>
  {/if}
{/if}

<style>
  .layer {
    position: fixed;
    inset: 0;
    z-index: var(--z-modal);
    display: grid;
    place-items: center;
    padding: var(--space-6);
  }

  .scrim {
    position: absolute;
    inset: 0;
    background: var(--scrim);
  }

  .dialog {
    position: relative;
    display: flex;
    flex-direction: column;
    width: min(var(--dlg-w), 100%);
    max-height: calc(100vh - 2 * var(--space-6));
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--shadow-2);
    color: var(--fg);
    animation: enter var(--duration-base) var(--ease-out);
  }
  .dialog:focus {
    outline: none;
  }
  .dialog.preview {
    max-height: none;
    animation: none;
  }
  .size-s {
    --dlg-w: 480px;
  }
  .size-m {
    --dlg-w: 560px;
  }
  .size-l {
    --dlg-w: 640px;
  }

  header {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-3) var(--space-2) var(--space-5);
  }
  .titles {
    flex: 1;
    min-width: 0;
    padding-top: var(--space-1);
  }
  h2 {
    margin: 0;
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
    line-height: var(--leading-tight);
  }
  .subtitle {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  .body {
    min-height: 0;
    padding: var(--space-2) var(--space-5) var(--space-4);
    overflow: auto;
    font-size: var(--text-m);
    line-height: var(--leading-normal);
  }
  .body :global(p) {
    margin: 0 0 var(--space-3);
  }
  .body :global(p:last-child) {
    margin-bottom: 0;
  }

  footer {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-5) var(--space-4);
  }

  @keyframes enter {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
  }
</style>
