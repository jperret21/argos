/**
 * `use:showTail={value}` on a field's container: its input shows the end of a long path
 * (the file name) rather than its start, unless the observer is editing it (design review
 * W7: "SAVE TO" fields showed /private/tmp/… and hid the name).
 */
export function showTail(node: HTMLElement, _value?: unknown): { update: (v?: unknown) => void } {
  const apply = () => {
    const input = node.querySelector('input');
    if (input && document.activeElement !== input) input.scrollLeft = input.scrollWidth;
  };
  requestAnimationFrame(apply);
  return { update: () => requestAnimationFrame(apply) };
}
