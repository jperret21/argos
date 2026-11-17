<!--
  The live photometry status in one line (PROPOSAL 6 W5 "the Field band shows the live
  photometry status"; 08 2.3 C sub-states): what the newest solution gave, in words, with
  the newest point's frame and UTC time. Shown at the right of the Field band's tab row and
  in its one-row summary; the text never relies on its tone (BRAND 8).
-->
<script lang="ts">
  import Icon from '../../components/Icon.svelte';
  import NumText from '../../components/NumText.svelte';
  import type { StatusLine } from './present';
  import type { LiveStatus as Live } from './types';

  interface Props {
    line: StatusLine;
    status?: Live | null;
    compact?: boolean;
    /** Open the Light curve tab. */
    onopen?: () => void;
  }

  let { line, status = null, compact = false, onopen }: Props = $props();

  const when = $derived.by(() => {
    const t = status?.last?.t;
    if (!t || line.tone !== 'ok') return null;
    const d = new Date(t);
    return Number.isNaN(d.getTime()) ? null : d.toISOString().slice(11, 19);
  });
  const frame = $derived(line.tone === 'ok' && status?.last ? status.last.frame_seq : null);
  const title = $derived([line.text, frame !== null ? `newest point: frame #${frame}` : null, when ? `${when} UTC` : null].filter(Boolean).join(' · '));
</script>

<button type="button" class="live {line.tone}" class:compact {title} aria-label="Live photometry: {title}. Opens the light curve." onclick={() => onopen?.()} disabled={!onopen}>
  {#if line.icon}<Icon name={line.icon} size={14} />{/if}
  <span class="text"><NumText text={line.text} /></span>
  {#if when}<span class="when num">#{frame} · {when}</span>{/if}
</button>

<style>
  .live {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
    max-width: 100%;
    height: 24px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font: inherit;
    font-size: var(--text-s);
    cursor: pointer;
  }
  .live:disabled {
    cursor: default;
  }
  .live:not(:disabled):hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .live:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: calc(-1 * var(--focus-ring-w));
  }
  .live :global(.icon) {
    flex: none;
    color: var(--fg-muted);
  }
  .live.ok,
  .live.warn {
    color: var(--fg);
  }
  .live.warn :global(.icon) {
    color: var(--warning);
  }
  .text {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .when {
    flex: none;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .compact {
    height: 20px;
    padding: 0 var(--space-1);
  }
</style>
