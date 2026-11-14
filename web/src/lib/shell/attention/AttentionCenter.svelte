<!--
  The status bar's attention item in one piece (wave 6b): the chip (AttentionChip) and,
  anchored on it, the list (AttentionList in a Popover, 440 px: the rule texts need the
  room) bound to the app's AttentionStore. The integrator drops it after the run chip.
  `previewOpen` draws the list in place (component gallery).
-->
<script lang="ts">
  import type { AttentionItem, AttentionTarget } from '../../api/attention';
  import Popover from '../../components/Popover.svelte';
  import type { AttentionStore } from './attention.svelte';
  import AttentionChip from './AttentionChip.svelte';
  import AttentionList from './AttentionList.svelte';
  import type { SoundLevel } from './model';

  interface Props {
    store: AttentionStore;
    compact?: boolean;
    /** The chip headline's room in px (the status bar's measure), else its natural width. */
    textMax?: number | null;
    /** Write the sound level (config key alerts.sound). */
    onsound?: (level: SoundLevel) => void;
    onaction?: (to: AttentionTarget, item: AttentionItem) => void;
    onsettings?: () => void;
    open?: boolean;
    previewOpen?: boolean;
  }
  let { store, compact = false, textMax = null, onsound, onaction, onsettings, open = $bindable(false), previewOpen = false }: Props = $props();

  let anchor = $state<HTMLButtonElement | null>(null);
  const id = `attention-${Math.random().toString(36).slice(2, 8)}`;
  const chip = $derived(store.chip);
</script>

<AttentionChip {chip} {compact} {textMax} expanded={open || previewOpen} controls={id} bind:element={anchor} onclick={() => (open = !open)} />

{#snippet list()}
  <AttentionList
    items={store.items}
    pending={store.pending}
    error={store.error}
    sound={store.prefs.level}
    armed={store.armed}
    unsupported={!store.supported}
    onack={(i) => store.ack(i)}
    onackall={() => store.ackAll()}
    onsound={(v) => {
      store.setPrefs({ ...store.prefs, level: v });
      onsound?.(v);
    }}
    ontest={() => store.test('attention')}
    onaction={(to, it) => {
      open = false;
      onaction?.(to, it);
    }}
    onsettings={onsettings
      ? () => {
          open = false;
          onsettings?.();
        }
      : undefined}
  />
{/snippet}

{#if previewOpen}
  <Popover open preview {id} title="Attention" width={440}>{@render list()}</Popover>
{:else if open}
  <Popover bind:open {anchor} {id} title="Attention" placement="top-end" width={440}>{@render list()}</Popover>
{/if}
