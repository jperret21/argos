<!--
  Labelled hardware button with hold-to-confirm (Park, Pause in Watch).

  - Hold 700 ms with the pointer: a fill grows from the left (elapsed time,
    linear; four discrete steps under reduced motion), the label says
    "Release to cancel"; at the end the action is sent.
  - Enter / Space open the inline confirmation (two buttons) instead: the
    keyboard and assistive technologies never need a timed hold.
  - `disabledReason` keeps it focusable with the reason in its tooltip.
  Danger tone: --danger outline and glyph, label --fg (BRAND 8).
-->
<script lang="ts">
  import Button from '../../../lib/components/Button.svelte';
  import { tooltip } from '../../../lib/components/tooltip';
  import { reducedMotion } from '../model/env.svelte';
  import { hold } from './hold';
  import LabIcon from './LabIcon.svelte';

  interface Props {
    icon: string;
    label: string;
    /** Inline confirmation text (keyboard path), e.g. "Park the mount?". */
    question: string;
    consequence?: string;
    confirmLabel?: string;
    tone?: 'danger' | 'secondary';
    size?: 'm' | 'l';
    disabledReason?: string | null;
    onconfirm: () => void;
  }

  let {
    icon,
    label,
    question,
    consequence,
    confirmLabel = label,
    tone = 'danger',
    size = 'm',
    disabledReason = null,
    onconfirm,
  }: Props = $props();

  let progress = $state(0);
  let asking = $state(false);
  const shown = $derived(reducedMotion() ? Math.floor(progress * 4) / 4 : progress);
  const holding = $derived(progress > 0 && progress < 1);
</script>

{#if asking}
  <div class="confirm" role="group" aria-label={question}>
    <p><strong>{question}</strong>{#if consequence}<span> {consequence}</span>{/if}</p>
    <div class="row">
      <Button label="Cancel" size="s" onclick={() => (asking = false)} />
      <Button
        label={confirmLabel}
        size="s"
        variant={tone === 'danger' ? 'danger' : 'primary'}
        onclick={() => {
          asking = false;
          onconfirm();
        }}
      />
    </div>
  </div>
{:else}
  <button
    type="button"
    class="hold tone-{tone} size-{size}"
    class:holding
    class:inert={!!disabledReason}
    style:--p={shown}
    aria-disabled={disabledReason ? 'true' : undefined}
    aria-label="{label} (hold to confirm, or press Enter)"
    {@attach hold({
      ms: 700,
      onconfirm,
      onprogress: (f) => (progress = f),
      onkey: () => (asking = true),
      disabled: () => !!disabledReason,
    })}
    use:tooltip={{ text: disabledReason ? `${label}: ${disabledReason}` : `Hold to ${label.toLowerCase()} · Enter to confirm` }}
  >
    <span class="fill" aria-hidden="true"></span>
    <span class="glyph"><LabIcon name={icon} size={size === 'l' ? 24 : 20} /></span>
    <span class="text">{holding ? 'Release to cancel' : label}</span>
  </button>
{/if}

<style>
  .hold {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: var(--control-h-m);
    padding: 0 var(--space-4) 0 var(--space-3);
    overflow: hidden;
    border: var(--border-w) solid var(--btn-border, var(--border));
    border-radius: var(--radius-s);
    background: var(--surface);
    color: var(--fg);
    font-weight: var(--weight-medium);
    white-space: nowrap;
    cursor: pointer;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
    transition: border-color var(--duration-fast) var(--ease-standard);
  }
  .size-l {
    height: 48px;
    padding: 0 var(--space-5) 0 var(--space-4);
    font-size: 20px;
  }
  .tone-danger {
    --btn-border: var(--danger);
  }
  .tone-danger .glyph {
    color: var(--danger);
  }
  .hold:hover:not(.inert) {
    background: var(--hover-bg);
  }
  /* The fill is elapsed time: a 14 % tint of the tone, under the label. */
  .fill {
    position: absolute;
    inset: 0;
    transform-origin: left center;
    transform: scaleX(var(--p));
    background: color-mix(in srgb, var(--danger) 26%, transparent);
  }
  .tone-secondary .fill {
    background: color-mix(in srgb, var(--fg) 14%, transparent);
  }
  .glyph,
  .text {
    position: relative;
    display: inline-flex;
  }
  .inert {
    --btn-border: var(--border-soft);
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  .inert .glyph {
    color: var(--fg-disabled);
  }
  .hold:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }

  .confirm {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    border: var(--border-w) solid var(--danger);
    border-radius: var(--radius-s);
    background: var(--surface);
  }
  .confirm p {
    margin: 0;
    font-size: var(--text-s);
    color: var(--fg);
  }
  .confirm span {
    color: var(--text-muted);
  }
  .row {
    display: flex;
    gap: var(--space-2);
    justify-content: flex-end;
  }
</style>
