<!--
  Select (README 3.1: profile, filter, frame type, presets): a token-drawn
  select-only combobox (WAI-ARIA APG), never a native <select>, whose pop-up
  draws grey in Night Red (BRAND 4.3).

  - Closed: ↓ / ↑ / Enter / Space / Alt+↓ open the list on the current
    value; Home / End open it on the first / last option; typing letters
    opens it on the next option that starts with them.
  - Open: ↑ ↓ PageUp PageDown Home End move, typing jumps, Enter / Space
    choose and close, Tab chooses and moves on, Alt+↑ chooses, Escape closes
    without change. Focus stays on the combobox (aria-activedescendant).
  - Options may carry a second line (`detail`) and be disabled with the
    reason in words; disabled options are skipped by the keyboard.
  - `disabledReason` disables the whole control and says why (tooltip);
    `error` outlines it in --danger and says why under it.
  - `preview` draws the open list in place (component gallery).
-->
<script lang="ts" generics="T extends string">
  import Icon from './Icon.svelte';
  import { type CloseReason, floating, layer, portal } from './layers';
  import { isTypeaheadKey, navTarget, Typeahead } from './listnav';
  import { tooltip } from './tooltip';

  interface Option {
    value: T;
    label: string;
    detail?: string;
    /** The detail is data (sensor, plate scale): Plex Mono (BRAND 5). */
    detailMono?: boolean;
    disabledReason?: string | null;
  }

  interface Props {
    label: string;
    hideLabel?: boolean;
    options: readonly Option[];
    value: T | null;
    onchange?: (value: T) => void;
    placeholder?: string;
    disabled?: boolean;
    disabledReason?: string | null;
    error?: string | null;
    hint?: string | null;
    mono?: boolean;
    /** Width of the control (CSS), default 100 % of its container. */
    width?: string;
    preview?: boolean;
    previewActive?: number;
  }

  let {
    label,
    hideLabel = false,
    options,
    value = $bindable(),
    onchange,
    placeholder = 'Choose…',
    disabled = false,
    disabledReason = null,
    error = null,
    hint = null,
    mono = false,
    width,
    preview = false,
    previewActive = -1,
  }: Props = $props();

  const uid = `sel-${Math.random().toString(36).slice(2, 9)}`;
  let open = $state(false);
  let active = $state(-1);
  let button: HTMLButtonElement | undefined = $state();
  let listEl: HTMLElement | undefined = $state();
  const typeahead = new Typeahead();
  /**
   * The last interaction was the pointer (a click on the field or an
   * option): no focus ring until a key is pressed (BRAND 8: the ring is
   * for keyboard focus).
   */
  let pointerFocus = $state(false);

  const inert = $derived(disabled || !!disabledReason);
  const selectedIndex = $derived(options.findIndex((o) => o.value === value));
  const selected = $derived(selectedIndex >= 0 ? options[selectedIndex] : null);
  const skip = (i: number) => !!options[i]?.disabledReason;

  function show(at: number): void {
    if (inert) return;
    open = true;
    active = at >= 0 ? at : (navTarget('Home', options.length, -1, skip) ?? -1);
    queueMicrotask(scrollActive);
  }

  function close(): void {
    open = false;
    typeahead.reset();
  }

  function onLayerClose(_reason: CloseReason): void {
    close();
  }

  function pick(i: number): void {
    const o = options[i];
    if (!o || o.disabledReason) return;
    close();
    if (o.value !== value) {
      value = o.value;
      onchange?.(o.value);
    }
  }

  function scrollActive(): void {
    listEl?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' });
  }

  function onKeydown(e: KeyboardEvent): void {
    pointerFocus = false;
    if (inert) return;
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        e.stopPropagation();
        show(selectedIndex >= 0 && !skip(selectedIndex) ? selectedIndex : -1);
      } else if (e.key === 'Home' || e.key === 'End') {
        e.preventDefault();
        e.stopPropagation();
        show(navTarget(e.key, options.length, -1, skip) ?? -1);
      } else if (isTypeaheadKey(e)) {
        e.preventDefault();
        e.stopPropagation();
        const i = typeahead.push(e.key, options.map((o) => o.label), selectedIndex, skip);
        show(i >= 0 ? i : selectedIndex);
      }
      return;
    }
    if (e.key === 'Escape') return; // the layer stack closes the list
    if (e.altKey && e.key === 'ArrowUp') {
      e.preventDefault();
      e.stopPropagation();
      pick(active);
      return;
    }
    const target = navTarget(e.key, options.length, active, skip, { wrap: false });
    if (target !== null) {
      e.preventDefault();
      e.stopPropagation();
      active = target;
      scrollActive();
      return;
    }
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      e.stopPropagation();
      pick(active);
      return;
    }
    if (e.key === 'Tab') {
      pick(active); // and let Tab move on
      return;
    }
    if (isTypeaheadKey(e)) {
      e.preventDefault();
      e.stopPropagation();
      const i = typeahead.push(e.key, options.map((o) => o.label), active, skip);
      if (i >= 0) {
        active = i;
        scrollActive();
      }
    }
  }

  function onClick(e: MouseEvent): void {
    // detail > 0: a real click (Enter / Space on a button also fire click, with detail 0).
    if (e.detail > 0) pointerFocus = true;
    if (inert) return;
    if (open) close();
    else show(selectedIndex >= 0 && !skip(selectedIndex) ? selectedIndex : -1);
  }

  const activeId = $derived(open && active >= 0 ? `${uid}-opt-${active}` : undefined);
</script>

{#snippet listbox(live: boolean)}
  <ul
    class="listbox"
    class:mono
    class:preview={!live}
    id="{uid}-list"
    role="listbox"
    aria-labelledby="{uid}-label"
    tabindex="-1"
    bind:this={listEl}
  >
    {#each options as o, i (o.value)}
      {@const isActive = live ? active === i : previewActive === i}
      <!-- The keyboard drives the options from the combobox, which keeps the
           focus (aria-activedescendant, APG select-only combobox). -->
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <li
        id="{uid}-opt-{i}"
        class="option"
        class:active={isActive}
        class:disabled={!!o.disabledReason}
        role="option"
        aria-selected={o.value === value}
        aria-disabled={o.disabledReason ? true : undefined}
        data-index={i}
        onpointerdown={(e) => e.preventDefault()}
        onclick={() => {
          if (!live) return;
          pointerFocus = true;
          pick(i);
        }}
        onpointermove={() => {
          if (live && !o.disabledReason) active = i;
        }}
      >
        <span class="tick" class:on={o.value === value} aria-hidden="true"></span>
        <span class="text">
          <span class="opt-label">{o.label}</span>
          {#if o.disabledReason || o.detail}<span class="detail" class:num={!o.disabledReason && o.detailMono}>{o.disabledReason ?? o.detail}</span>{/if}
        </span>
      </li>
    {/each}
  </ul>
{/snippet}

<div class="field" class:invalid={!!error} style:width>
  <span class="label" class:visually-hidden={hideLabel} id="{uid}-label">{label}</span>
  <button
    bind:this={button}
    type="button"
    class="control"
    class:mono
    class:open={open || (preview && previewActive >= 0)}
    class:is-inert={inert}
    class:quiet={pointerFocus}
    role="combobox"
    aria-labelledby="{uid}-label {uid}-value"
    aria-haspopup="listbox"
    aria-expanded={open}
    aria-controls="{uid}-list"
    aria-activedescendant={activeId}
    aria-invalid={!!error || undefined}
    aria-disabled={disabledReason ? true : undefined}
    aria-describedby={error || hint ? `${uid}-help` : undefined}
    {disabled}
    onclick={onClick}
    onkeydown={onKeydown}
    use:tooltip={{ text: `${label}: ${disabledReason ?? ''}`, placement: 'top', disabled: !disabledReason }}
  >
    <span class="value" class:placeholder={!selected} id="{uid}-value">{selected?.label ?? placeholder}</span>
    <span class="chevron" aria-hidden="true"><Icon name="disclosure" size="s" /></span>
  </button>
  {#if error}
    <span class="help error" id="{uid}-help">{error}</span>
  {:else if hint}
    <span class="help" id="{uid}-help">{hint}</span>
  {/if}
  {#if preview && previewActive >= 0}
    <div class="preview-list">{@render listbox(false)}</div>
  {/if}
</div>

{#if open && !preview}
  <div
    class="float"
    use:portal
    use:floating={{ anchor: button, placement: 'bottom-start', gap: 2, matchWidth: true }}
    use:layer={{ kind: 'listbox', anchor: button, onclose: onLayerClose }}
  >
    {@render listbox(true)}
  </div>
{/if}

<style>
  .field {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .label {
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  .control {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    height: var(--input-h);
    padding: 0 var(--space-1) 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-m);
    text-align: left;
    cursor: pointer;
    transition: border-color var(--duration-fast) var(--ease-standard);
  }
  .control.mono .value {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .control:hover:not(.is-inert) {
    border-color: var(--fg-muted);
  }
  /* BRAND 8: a 2 px ring with a 2 px offset, the border untouched; keyboard only. */
  .control:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }
  .control.quiet:focus-visible {
    outline: none;
  }
  .control.open {
    border-color: var(--fg-muted);
  }
  .control.is-inert {
    border-color: var(--border-soft);
    background: transparent;
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  .invalid .control {
    border-color: var(--danger);
  }

  .value {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .value.placeholder {
    color: var(--text-muted);
  }
  .is-inert .value {
    color: var(--fg-disabled);
  }

  .chevron {
    display: inline-flex;
    color: var(--fg-muted);
    transition: transform var(--duration-fast) var(--ease-standard);
  }
  .open .chevron {
    transform: rotate(180deg);
  }

  .help {
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

  .float {
    z-index: var(--z-popover);
  }
  .preview-list {
    margin-top: 2px;
  }

  .listbox {
    max-height: 280px;
    margin: 0;
    padding: var(--space-1) 0;
    overflow-y: auto;
    list-style: none;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--shadow-2);
    color: var(--fg);
    font-size: var(--text-m);
  }
  .listbox.preview {
    box-shadow: none;
  }
  .listbox:focus {
    outline: none;
  }

  .option {
    display: grid;
    grid-template-columns: 12px minmax(0, 1fr);
    align-items: center;
    gap: var(--space-2);
    min-height: 28px;
    padding: var(--space-1) var(--space-4) var(--space-1) var(--space-3);
    cursor: pointer;
  }
  .option.active {
    background: var(--hover-bg);
  }
  .option.disabled {
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  .mono .opt-label {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }

  /* Drawn tick for the selected option (no Unicode glyph). */
  .tick {
    position: relative;
    width: 12px;
    height: 12px;
  }
  .tick.on::after {
    content: '';
    position: absolute;
    left: 3px;
    top: 0;
    width: 4px;
    height: 8px;
    border: solid var(--fg);
    border-width: 0 1.5px 1.5px 0;
    transform: rotate(45deg);
  }

  .text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .opt-label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .detail {
    color: var(--text-muted);
    font-family: var(--font-ui);
    font-size: var(--text-xs);
    line-height: var(--leading-tight);
  }
  .detail.num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
</style>
