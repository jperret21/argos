<!--
  Rail footer (README 1.1, D14, D15; 01 sections 2.3.3 and 2.3.4): two
  32 px icon buttons above the Settings entry.

  - [theme]: one click cycles Observatory > Charcoal > Night Red, so Night
    Red is one click away from every section; a right-click, a long press,
    Shift+F10 or the context-menu key opens the three themes as a list
    (Q-G3). No single-key shortcut (Q-G3).
  - [help]: the Help menu: version line, Documentation & website (opens in
    the browser, the only network use, on request), Keyboard shortcuts (?),
    Command palette (Mod+K), Create support bundle…, About ARGOS
    (Settings › About, D14), and Quit ARGOS in the desktop app. Items whose screen is not built yet are shown
    disabled with the reason, not hidden.
-->
<script lang="ts">
  import { THEME_LABELS, THEMES, type Theme, nextTheme } from '../app/theme';
  import IconButton from '../components/IconButton.svelte';
  import KeyHint from '../components/KeyHint.svelte';
  import Menu from '../components/Menu.svelte';
  import type { MenuChoice, MenuEntry } from '../components/menu';

  interface Props {
    theme: Theme;
    ontheme: (theme: Theme) => void;
    /** ARGOS (server) version and API level, when known. */
    version?: string | null;
    api?: number | null;
    docsUrl?: string;
    onshortcuts: () => void;
    /** Command palette (Mod+K, wave 2). */
    onpalette?: () => void;
    onabout?: () => void;
    onsupportbundle?: () => void;
    /** Desktop app only. */
    onquit?: () => void;
    /** Gallery: draw one menu open in place. */
    preview?: 'help' | 'theme' | null;
  }

  let {
    theme,
    ontheme,
    version = null,
    api = null,
    docsUrl = 'https://perretjules.com/argos/',
    onshortcuts,
    onpalette,
    onabout,
    onsupportbundle,
    onquit,
    preview = null,
  }: Props = $props();

  let helpOpen = $state(false);
  let themeOpen = $state(false);
  let helpAnchor: HTMLElement | undefined = $state();
  let themeAnchor: HTMLElement | undefined = $state();
  /** The menus open beside the rail, not over it. */
  let row: HTMLElement | undefined = $state();
  let pressTimer: ReturnType<typeof setTimeout> | undefined;
  let longPressed = false;

  const NOT_YET = 'not available in this version yet';
  const docsHost = $derived(docsUrl.replace(/^https?:\/\//, '').replace(/\/$/, ''));

  const helpItems = $derived<MenuEntry[]>([
    {
      id: 'docs',
      label: 'Documentation & website',
      icon: 'help',
      detail: `${docsHost} · opens in your browser`,
    },
    { id: 'shortcuts', label: 'Keyboard shortcuts', shortcut: '?' },
    ...(onpalette ? ([{ id: 'palette', label: 'Command palette', icon: 'search', shortcut: 'Mod+K' }] as MenuEntry[]) : []),
    {
      id: 'bundle',
      label: 'Create support bundle…',
      icon: 'support-bundle',
      disabledReason: onsupportbundle ? null : NOT_YET,
    },
    { id: 'about', label: 'About ARGOS', icon: 'about', disabledReason: onabout ? null : NOT_YET },
    ...(onquit
      ? ([
          { kind: 'separator', id: 'sep' },
          { id: 'quit', label: 'Quit ARGOS', icon: 'quit', shortcut: 'Mod+Q' },
        ] as MenuEntry[])
      : []),
  ]);

  const themeItems = $derived<MenuEntry[]>(
    THEMES.map((t) => ({ kind: 'radio', id: t, label: THEME_LABELS[t], checked: t === theme })),
  );

  function onHelp(item: MenuChoice): void {
    switch (item.id) {
      case 'docs':
        window.open(docsUrl, '_blank', 'noopener,noreferrer');
        break;
      case 'shortcuts':
        onshortcuts();
        break;
      case 'palette':
        onpalette?.();
        break;
      case 'bundle':
        onsupportbundle?.();
        break;
      case 'about':
        onabout?.();
        break;
      case 'quit':
        onquit?.();
        break;
    }
  }

  function cycle(): void {
    if (longPressed) {
      longPressed = false;
      return;
    }
    ontheme(nextTheme(theme));
  }

  function openThemes(e?: Event): void {
    e?.preventDefault();
    themeOpen = true;
  }

  function onThemeDown(e: PointerEvent): void {
    if (e.button !== 0) return;
    longPressed = false;
    clearTimeout(pressTimer);
    pressTimer = setTimeout(() => {
      longPressed = true;
      themeOpen = true;
    }, 550);
  }

  function onThemeUp(): void {
    clearTimeout(pressTimer);
  }

  function onThemeKey(e: KeyboardEvent): void {
    if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) {
      e.stopPropagation();
      openThemes(e);
    }
  }

  const versionLine = $derived(
    version ? `ARGOS ${version}${api !== null ? ` · API ${api}` : ''}` : 'ARGOS · server not reached yet',
  );
</script>

{#snippet versionHeader()}
  <span class="num">{versionLine}</span>
{/snippet}

<div class="footer-tools" bind:this={row}>
  <span class="anchor" bind:this={helpAnchor}>
    <!-- Key hints: "?" (Keyboard shortcuts, a Help item) on the Help button. -->
    <KeyHint keys="?" />
    <IconButton
      icon="help"
      label="Help"
      variant="ghost"
      tooltip="right"
      aria-haspopup="menu"
      aria-expanded={helpOpen}
      onclick={() => (helpOpen = !helpOpen)}
    />
  </span>
  <span class="anchor" bind:this={themeAnchor}>
    <IconButton
      icon="theme"
      label="Theme: {THEME_LABELS[theme]}"
      tooltipText="Theme: {THEME_LABELS[theme]}. Click for {THEME_LABELS[nextTheme(theme)]}; right-click to choose"
      variant="ghost"
      tooltip="right"
      onclick={cycle}
      oncontextmenu={openThemes}
      onpointerdown={onThemeDown}
      onpointerup={onThemeUp}
      onpointerleave={onThemeUp}
      onkeydown={onThemeKey}
    />
  </span>
</div>

<Menu
  bind:open={helpOpen}
  anchor={helpAnchor}
  placeAt={row}
  items={helpItems}
  label="Help"
  header={versionHeader}
  placement="right-end"
  minWidth={280}
  onselect={onHelp}
/>
<Menu
  bind:open={themeOpen}
  anchor={themeAnchor}
  placeAt={row}
  items={themeItems}
  label="Theme"
  placement="right-end"
  minWidth={180}
  start="checked"
  onselect={(item) => ontheme(item.id as Theme)}
/>

{#if preview === 'help'}
  <div class="preview">
    <Menu open preview items={helpItems} label="Help" header={versionHeader} minWidth={280} previewActive={1} />
  </div>
{:else if preview === 'theme'}
  <div class="preview">
    <Menu open preview items={themeItems} label="Theme" minWidth={180} previewActive={2} />
  </div>
{/if}

<style>
  .footer-tools {
    display: flex;
    justify-content: center;
    gap: var(--space-1);
    padding: var(--space-1) 0;
  }
  .anchor {
    position: relative;
    display: inline-flex;
  }
  .footer-tools :global(.icon-button) {
    width: 32px;
    min-width: 32px;
    height: 32px;
    padding: 0;
  }
  .preview {
    margin-top: var(--space-3);
  }
</style>
