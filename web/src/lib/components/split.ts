/**
 * Split button (SplitButton.svelte): the pure part, unit-tested.
 *
 * The main part's accessible name says what it will do with the options in
 * use, as the button shows it: "Capture · 2.0 s", "Autofocus · 2.0 s · 80".
 * A screen reader hears the same sentence the eye reads (BRAND 7 "An action
 * with options").
 */

export function splitMainName(label: string, text?: string, detail?: string): string {
  const head = text && text !== label ? `${label}: ${text}` : label;
  return detail ? `${head} · ${detail}` : head;
}
