<!--
  Electron gain table (`camera.egain_table`, Instrument › Advanced; Q-C4):
  measured e⁻/ADU per gain setting, first in the photometric noise model's
  e⁻/ADU chain: then the observer's photon-transfer file, the telescope
  profile's photon transfer (S73), the driver's value and the sensor
  reference (hardware/egain.py). While a sequence runs it is unavailable,
  with the server's sentence (`locked`, settings/runlock.ts, S84).
  Rows are read-only facts with [remove] (Undo); a new row is added with
  its gain and value. Each change is one PATCH of the whole object; the
  server validates it (gain 0…10 000, e⁻/ADU in (0, 100]) and its words
  are shown under the row.
-->
<script lang="ts">
  import type { ConfigValue } from '../api/types';
  import { useApp } from '../app/state.svelte';
  import Control from '../components/Control.svelte';
  import { fixed, int, parseNumber } from '../format/number';

  interface Props {
    value: ConfigValue | undefined;
    /** Why the table cannot change now (a run is active: S84), else null. */
    locked?: string | null;
  }
  let { value, locked = null }: Props = $props();

  const app = useApp();
  const rows = $derived(
    value && typeof value === 'object' && !Array.isArray(value)
      ? Object.entries(value as Record<string, unknown>)
          .filter(([, v]) => typeof v === 'number')
          .map(([g, v]) => ({ gain: Number(g), egain: v as number }))
          .sort((a, b) => a.gain - b.gain)
      : [],
  );

  let gainText = $state('');
  let egainText = $state('');
  let busy = $state(false);
  let error: string | null = $state(null);

  const toObject = (list: { gain: number; egain: number }[]) =>
    Object.fromEntries(list.map((r) => [String(r.gain), r.egain])) as Record<string, number>;

  async function write(list: { gain: number; egain: number }[]): Promise<void> {
    await app.patchConfig({ 'camera.egain_table': toObject(list) });
  }

  async function add(): Promise<void> {
    if (locked) return;
    const gain = parseNumber(gainText);
    const egain = parseNumber(egainText);
    if (gain === null || !Number.isInteger(gain) || gain < 0) {
      error = 'The gain must be a whole number (0 or more)';
      return;
    }
    if (egain === null || !(egain > 0)) {
      error = 'e⁻/ADU must be a positive number';
      return;
    }
    busy = true;
    error = null;
    try {
      await write([...rows.filter((r) => r.gain !== gain), { gain, egain }]);
      gainText = '';
      egainText = '';
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }

  async function remove(gain: number): Promise<void> {
    if (locked) return;
    const before = rows;
    busy = true;
    error = null;
    try {
      await write(before.filter((r) => r.gain !== gain));
      app.undo.push({ title: `Removed the electron gain of gain ${int(gain)}`, undo: () => write(before) });
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }
</script>

<div class="egain">
  {#if rows.length}
    <ul class="rows" aria-label="Electron gain per gain setting">
      {#each rows as r (r.gain)}
        <li>
          <span class="num">Gain {int(r.gain)}</span>
          <span class="num">{fixed(r.egain, 3)} e⁻/ADU</span>
          <Control
            icon="remove"
            label="Remove gain {int(r.gain)}"
            size="xs"
            variant="ghost"
            tooltip="top"
            tooltipText="Remove (Undo for 6 s)"
            disabledReason={locked ?? (busy ? 'saving' : null)}
            onclick={() => void remove(r.gain)}
          />
        </li>
      {/each}
    </ul>
  {:else}
    <p class="empty">
      Empty: the next sources in the help above, in its order.
    </p>
  {/if}
  <div class="add">
    <input class="num" type="text" inputmode="numeric" placeholder="Gain" aria-label="Gain setting" readonly={!!locked} aria-disabled={!!locked || undefined} bind:value={gainText} />
    <input class="num" type="text" inputmode="decimal" placeholder="e⁻/ADU" aria-label="Electrons per ADU" readonly={!!locked} aria-disabled={!!locked || undefined} bind:value={egainText}
      onkeydown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          if (!locked) void add();
        }
      }} />
    <Control icon="add" label="Add" showLabel size="xs" variant="secondary" busy={busy} disabledReason={locked} onclick={() => void add()} />
  </div>
  {#if locked}<p class="locked">{locked}</p>{/if}
  {#if error}<p class="error" role="alert">{error}</p>{/if}
</div>

<style>
  .egain {
    min-width: 0;
  }
  .rows {
    margin: 0 0 var(--space-2);
    padding: 0;
    list-style: none;
  }
  .rows li {
    display: grid;
    grid-template-columns: 96px minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-3);
    min-height: var(--row-h);
    font-size: var(--text-s);
  }
  .rows li + li {
    border-top: var(--border-w) solid var(--border-soft);
  }
  .empty {
    margin: 0 0 var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--input-h);
  }
  /* Unavailable with a reason (a run, S84): muted, read-only, still focusable (NumberField). */
  .add input[aria-disabled='true'] {
    border-color: var(--border-soft);
    background: transparent;
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  /* The run lock's reason, as a settings row's (hollow ring, never cut: BRAND 8). */
  .locked {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: 16px;
    overflow-wrap: anywhere;
  }
  .locked::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: 6px;
    border-radius: var(--radius-round);
    vertical-align: 1px;
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .add {
    display: grid;
    grid-template-columns: 80px 96px auto;
    gap: var(--space-2);
    align-items: center;
  }
  .add input {
    height: var(--input-h);
    min-width: 0;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .add input::placeholder {
    color: var(--text-muted);
  }
  .add input:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .error {
    margin: var(--space-1) 0 0;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .error::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: 6px;
    border-radius: var(--radius-round);
    background: var(--danger);
  }
</style>
