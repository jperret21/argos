<!--
  Side sheet (web/spec/README.md 3.1 and 3.2, D12): edit settings without
  leaving the image. Right side, 560 px by default, modal, hosting the same
  SettingsForm as the Settings screen (same immediate apply on commit, same
  `config` event).

  - Modal: drawn in <body> over the --scrim; the app behind is inert until it
    closes (layers.ts, kind "sheet": one modal at a time, a ConfirmDialog may
    stack once over it).
  - Focus: moves in on open (`initialFocus`, then [data-autofocus], then the
    first control of the body), Tab cycles inside, focus returns to the
    opener on close.
  - Escape closes it, unless a field inside holds a draft or a refusal: that
    field takes the first Escape (it reverts), the next one closes the sheet.
    The registry still sees every Escape (it aborts mount motion, D21).
  - No OK button: every control applies on commit. `status` (a snippet in the
    header) carries "Saved" and the like; `footer` is for a link such as
    "All settings".
  - Motion: opacity and a 4 px move, --duration-base (BRAND 9), none under
    reduced motion (the tokens are 0).
  - `preview` draws it in place, without scrim or trap (gallery).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import Control from './Control.svelte';
  import { FocusReturn, focusableIn, handleTrapKey, keepKeysInside } from './focus';
  import { type CloseReason, layer, portal } from './layers';

  interface Props {
    open?: boolean;
    title: string;
    subtitle?: string;
    /** Width in px (README 3.1: 560). */
    width?: number;
    children: Snippet;
    /** Right side of the header, before the close button ("Saved"). */
    status?: Snippet;
    footer?: Snippet;
    initialFocus?: string;
    returnFocus?: HTMLElement | null;
    onclose?: (reason: CloseReason) => void;
    preview?: boolean;
  }

  let {
    open = $bindable(false),
    title,
    subtitle,
    width = 560,
    children,
    status,
    footer,
    initialFocus,
    returnFocus = null,
    onclose,
    preview = false,
  }: Props = $props();

  const uid = `sheet-${Math.random().toString(36).slice(2, 9)}`;

  function close(reason: CloseReason): void {
    open = false;
    onclose?.(reason);
  }

  function firstFocus(panel: HTMLElement): HTMLElement {
    const pick = (sel: string | undefined) => (sel ? panel.querySelector<HTMLElement>(sel) : null);
    const body = panel.querySelector<HTMLElement>('.body');
    return pick(initialFocus) ?? pick('[data-autofocus]') ?? (body ? focusableIn(body)[0] : null) ?? panel;
  }

  function modal(node: HTMLElement) {
    const nowhere = !document.activeElement || document.activeElement === document.body;
    let back = new FocusReturn(document, returnFocus);
    const panel = node.querySelector<HTMLElement>('[aria-modal="true"]') ?? node;
    queueMicrotask(() => {
      if (nowhere && !returnFocus) back = new FocusReturn(document);
      firstFocus(panel).focus({ preventScroll: true });
    });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Tab') handleTrapKey(e, focusableIn(panel), document.activeElement, panel);
    };
    node.addEventListener('keydown', onKey);
    // Keys typed in the sheet stay in it ("E" in a field is not an exposure),
    // stopped at the document after the controls' own handlers ran; Escape
    // travels on (abort motion, D21).
    const release = keepKeysInside(node);
    return {
      destroy() {
        node.removeEventListener('keydown', onKey);
        release();
        queueMicrotask(() => back.restore());
      },
    };
  }
</script>

{#snippet panel(isModal: boolean)}
  <div
    class="sheet"
    class:preview={!isModal}
    style:--sheet-w="{width}px"
    role={isModal ? 'dialog' : 'group'}
    aria-modal={isModal ? 'true' : undefined}
    aria-labelledby="{uid}-title"
    tabindex="-1"
  >
    <header>
      <div class="titles">
        <h2 id="{uid}-title">{title}</h2>
        {#if subtitle}<p class="subtitle">{subtitle}</p>{/if}
      </div>
      {#if status}<div class="status">{@render status()}</div>{/if}
      <Control icon="close" label="Close" variant="ghost" size="s" shortcut="Escape" onclick={() => close('close')} />
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
    <div class="layer" use:portal use:layer={{ kind: 'sheet', modal: true, onclose: close }} use:modal>
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
  }
  .scrim {
    position: absolute;
    inset: 0;
    background: var(--scrim);
  }

  .sheet {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    width: min(var(--sheet-w), 100vw);
    border-left: var(--border-w) solid var(--border);
    background: var(--bg);
    box-shadow: var(--shadow-2);
    color: var(--fg);
    animation: enter var(--duration-base) var(--ease-out);
  }
  .sheet:focus {
    outline: none;
  }
  .sheet.preview {
    position: relative;
    height: 100%;
    animation: none;
  }

  header {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: var(--toolbar-h);
    padding: var(--space-2) var(--space-3) var(--space-2) var(--space-5);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .titles {
    flex: 1;
    min-width: 0;
  }
  h2 {
    margin: 0;
    overflow: hidden;
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
    line-height: var(--leading-tight);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .subtitle {
    margin: 2px 0 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .status {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  .body {
    flex: 1;
    min-height: 0;
    padding: var(--space-4) var(--space-5);
    overflow: auto;
    overscroll-behavior: contain;
  }

  footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-5);
    border-top: var(--border-w) solid var(--border-soft);
  }

  @keyframes enter {
    from {
      opacity: 0;
      transform: translateX(4px);
    }
  }
</style>
