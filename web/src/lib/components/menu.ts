/**
 * Menu model (context and dropdown menus, README 3.1): items in the
 * observer's words, an optional 16 px icon on the left (BRAND 7 "Menu items:
 * text, with an optional 16 px icon"), the shortcut on the right, and
 * disabled items that say why.
 */

interface MenuItemBase {
  id: string;
  label: string;
  icon?: string;
  /** Shortcut spec shown on the right (from the keymap). */
  shortcut?: string;
  /** Why it is unavailable: the item is disabled (still focusable) and says it. */
  disabledReason?: string | null;
  /** Second line, --text-muted (what it opens, a path). */
  detail?: string;
}

export interface MenuAction extends MenuItemBase {
  kind?: 'item';
  /** Destructive: --danger mark on the left (the confirmation follows). */
  danger?: boolean;
  /** Opens outside the app (the documentation site). */
  external?: boolean;
}

export interface MenuCheck extends MenuItemBase {
  kind: 'checkbox' | 'radio';
  checked: boolean;
}

export interface MenuSeparator {
  kind: 'separator';
  id?: string;
}

export interface MenuHeader {
  kind: 'header';
  id?: string;
  label: string;
}

export type MenuEntry = MenuAction | MenuCheck | MenuSeparator | MenuHeader;
export type MenuChoice = MenuAction | MenuCheck;

export function isChoice(e: MenuEntry): e is MenuChoice {
  return e.kind !== 'separator' && e.kind !== 'header';
}

export function entryLabel(e: MenuEntry): string {
  return e.kind === 'separator' ? '' : e.label;
}
