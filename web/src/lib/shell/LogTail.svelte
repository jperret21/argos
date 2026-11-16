<!--
  The server's last lines (start-up failure, crash notice): mono, columns kept (no wrap:
  argparse usage lines and tracebacks keep their alignment; long lines scroll sideways),
  and the box opens at its END, where a traceback names the cause (design review W8).
-->
<script lang="ts">
  interface Props {
    text: string;
    label?: string;
    /** CSS max-height of the box. */
    maxHeight?: string;
  }

  let { text, label = "The server's last lines", maxHeight = '168px' }: Props = $props();

  let box: HTMLElement | undefined = $state();

  // On mount, whenever the text changes, and when the box gets its size (a dialog shows it
  // after this runs): the newest line in view.
  $effect(() => {
    void text;
    const el = box;
    if (!el) return;
    const toEnd = () => {
      el.scrollTop = el.scrollHeight;
    };
    toEnd();
    const raf = typeof requestAnimationFrame === 'undefined' ? null : requestAnimationFrame(toEnd);
    const sized = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(toEnd);
    sized?.observe(el);
    return () => {
      if (raf !== null) cancelAnimationFrame(raf);
      sized?.disconnect();
    };
  });
</script>

<pre class="log-tail" bind:this={box} aria-label={label} style:max-height={maxHeight}>{text}</pre>

<style>
  .log-tail {
    /* Long lines scroll inside the box: they never widen the dialog or the column (the
       box's own width does not depend on its text). */
    box-sizing: border-box;
    width: 100%;
    min-width: 0;
    max-width: 100%;
    contain: inline-size;
    margin: 0;
    padding: var(--space-3);
    overflow: auto;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    line-height: 1.45;
    white-space: pre;
  }
</style>
