<!--
  "Reveal in Finder" (A12; desktop app only, hidden in a browser: a page served to a
  browser must not open windows on the server's screen; 01 1.10 #8; the Toasts row of
  spec/README.md, "Open, Reveal"): shows a file or folder in the file manager of this computer. The label
  follows the platform ("Show in Explorer", "Show in folder"). Icon + label (a rare
  action, BRAND 7); busy while the call runs; a refusal (no such file, a folder outside
  the allowed ones) stays on the button as its error, in the server's words.
-->
<script lang="ts">
  import Control from '../../components/Control.svelte';

  interface RevealTarget {
    readonly available: boolean;
    readonly revealLabel: string;
    reveal(path: string): Promise<void>;
  }

  interface Props {
    /** The file or folder; nothing is drawn without one. */
    path: string | null | undefined;
    /** The app's desktop side (ArgosApp.desktop). */
    target: RevealTarget;
    variant?: 'secondary' | 'ghost';
    size?: 'xs' | 's' | 'm';
    /** Icon only (a tight row), the label in the tooltip. */
    iconOnly?: boolean;
    /** Gallery: a fixed error. */
    error?: string | null;
  }

  let { path, target, variant = 'secondary', size = 'xs', iconOnly = false, error: pinnedError = null }: Props = $props();

  let busy = $state(false);
  let failure: string | null = $state(null);

  async function reveal(): Promise<void> {
    if (!path || busy) return;
    busy = true;
    failure = null;
    try {
      await target.reveal(path);
    } catch (err) {
      failure = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }
</script>

{#if target.available && path}
  <Control
    icon="open-file"
    label={target.revealLabel}
    showLabel={!iconOnly}
    {variant}
    {size}
    {busy}
    error={pinnedError ?? failure}
    tooltip={iconOnly || pinnedError || failure ? 'top' : 'none'}
    tooltipText={iconOnly ? `${target.revealLabel}: ${path}` : undefined}
    onclick={() => void reveal()}
  />
{/if}
