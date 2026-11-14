<!--
  The attention list (promoted from src/lab/workspace/overlays/AttentionPopover.svelte,
  PROPOSAL §6 W6; functional-spaces §4.10 "Popover"; BRAND §13): the body of the Popover
  anchored on the status-bar chip. Items come from the server's rules and state the rule
  and its numbers. Levels by mark AND word (critical filled disc, attention upright mark,
  info hollow ring; never colour alone, never a triangle); an item still holding is told
  from a cleared one in words. Acknowledge is shared by every client (the server's route);
  Info items are records and need none. The suggested next step (the rule's view) is a
  plain button. Sound Off / Soft / Normal writes the config key (Settings › Alerts);
  choosing Soft or Normal plays the attention tones once, which also arms the audio (a
  gesture). No OS notification (BRAND 4.3).
-->
<script lang="ts">
  import type { AttentionItem, AttentionTarget } from '../../api/attention';
  import Button from '../../components/Button.svelte';
  import Icon from '../../components/Icon.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import { clockUtc } from '../../format/time';
  import { actionOf, LEVEL_WORD, needsObserver, SOUND_LABEL, SOUND_LEVELS, whenLine, type SoundLevel } from './model';
  import AttentionMark from './AttentionMark.svelte';

  interface Props {
    items: readonly AttentionItem[];
    pending?: ReadonlySet<string>;
    error?: string | null;
    sound: SoundLevel;
    /** The audio context runs (a gesture armed it). */
    armed?: boolean;
    /** The server has no attention routes (an older server). */
    unsupported?: boolean;
    onack: (id: string) => Promise<unknown> | void;
    /** Acknowledge every open item (shown with two or more). */
    onackall?: () => Promise<unknown> | void;
    onsound?: (level: SoundLevel) => void;
    ontest?: () => void;
    onaction?: (to: AttentionTarget, item: AttentionItem) => void;
    /** Settings › Alerts. */
    onsettings?: () => void;
  }
  let { items, pending = new Set(), error = null, sound, armed = true, unsupported = false, onack, onackall, onsound, ontest, onaction, onsettings }: Props = $props();

  const CLEARED: Record<string, string> = { resolved: 'cleared', run_ended: 'cleared · run ended', new_run: 'from an earlier run' };

  const open = $derived(items.filter(needsObserver).length);
  const clock = (t: number) => clockUtc(t, false);
  const opts = SOUND_LEVELS.map((v) => ({ value: v, label: SOUND_LABEL[v] }));
</script>

<div class="list">
  <div class="head">
    <span class="count num" role="status">{open === 0 ? 'Nothing needs you' : `${open} open`}</span>
    {#if open > 1 && onackall}<Button label="Acknowledge all" size="s" variant="ghost" onclick={() => void Promise.resolve(onackall?.()).catch(() => undefined)} />{/if}
    <span class="grow"></span>
    <Segmented
      label="Alert sound"
      size="s"
      options={opts}
      value={sound}
      onchange={(v: SoundLevel) => {
        onsound?.(v);
        if (v !== 'off') ontest?.();
      }}
    />
  </div>
  {#if sound !== 'off' && !armed}
    <p class="note"><Icon name="help" size="s" />Sound starts after your first click or key in ARGOS (browser rule).</p>
  {/if}
  {#if error}<p class="note refused" role="alert"><AttentionMark level="critical" size={8} />{error}</p>{/if}

  <ol class="items">
    {#each items as a (a.id)}
      {@const act = actionOf(a)}
      {@const busy = pending.has(a.id)}
      <li class="item l-{a.level}" class:done={!needsObserver(a)}>
        <div class="line">
          <AttentionMark level={a.level} size={10} />
          <span class="lvl">{LEVEL_WORD[a.level]}</span>
          <span class="when num">{whenLine(a, clock)}</span>
          <span class="grow"></span>
          {#if a.acked}
            <span class="state">acknowledged{a.ackedAt !== null ? ` ${clock(a.ackedAt)}` : ''}</span>
          {:else if !a.active && a.level !== 'info'}
            <span class="state">{CLEARED[a.clearedReason ?? 'resolved'] ?? 'cleared'}{a.cleared !== null ? ` ${clock(a.cleared)}` : ''}</span>
          {/if}
          {#if a.occurrences > 1}<span class="state num">×{a.occurrences}</span>{/if}
        </div>
        <p class="title num">{a.title}</p>
        <p class="detail">{a.ruleLabel}{a.detail ? ` · ${a.detail}` : ''}</p>
        {#if needsObserver(a) || (act && onaction)}
          <div class="actions">
            {#if act && onaction}
              <Button label={act.label} size="s" variant="ghost" onclick={() => onaction?.(act.to, a)} />
            {/if}
            {#if needsObserver(a)}
              <Button label="Acknowledge" size="s" {busy} onclick={() => void Promise.resolve(onack(a.id)).catch(() => undefined)} />
            {/if}
          </div>
        {/if}
      </li>
    {:else}
      <li class="empty">
        {#if unsupported}
          This server does not evaluate attention rules (an older version).
        {:else}
          The rules run on every frame while a run is active: no new frame, HFD rise, star-count drop, too few comparisons, tracker lost, altitude limit, disk, run stopped, device lost.
        {/if}
      </li>
    {/each}
  </ol>

  <div class="foot">
    <span>Cleared and acknowledged items stay listed (the server keeps the last 200).</span>
    {#if onsettings}<button type="button" class="link" onclick={onsettings}>Rules and thresholds: Settings › Alerts</button>{/if}
  </div>
</div>

<style>
  .list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .grow {
    flex: 1;
  }
  .count {
    color: var(--fg);
    font-size: var(--text-s);
  }
  .note {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .refused {
    color: var(--fg);
  }
  .items {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 420px;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .item {
    padding: var(--space-2) var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  /* The level is the mark and the word; the edge only repeats it (critical: 2 px --danger). */
  .item.l-critical:not(.done) {
    border: 2px solid var(--danger);
    padding: calc(var(--space-2) - 1px) calc(var(--space-3) - 1px);
  }
  .item.l-attention:not(.done) {
    border-color: var(--border);
  }
  .done .title,
  .done .detail {
    color: var(--text-muted);
  }
  .line {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .lvl {
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .l-critical .lvl {
    font-weight: var(--weight-semibold);
  }
  .when,
  .state {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .title {
    margin: var(--space-1) 0 0;
    color: var(--fg);
    font-size: var(--text-s);
  }
  .detail {
    margin: 2px 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
  .empty {
    padding: var(--space-2) 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
  }
  .foot {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .link {
    padding: 0;
    border: none;
    background: none;
    color: var(--fg);
    font: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;
    cursor: pointer;
  }
  .link:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
</style>
