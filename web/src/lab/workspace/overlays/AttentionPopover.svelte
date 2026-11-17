<!--
  Attention list (the notification area for unattended runs, P6): anchored
  on the status-bar chip. Items come from the rules (server-side in the
  product) and state the rule and the numbers. Levels are told apart by a
  word and an outline weight, never by colour alone (Night Red). Sound: off /
  soft / normal; a test tone arms the audio context (autoplay policy).
  No OS notification (BRAND 4.3).
-->
<script lang="ts">
  import Button from '../../../lib/components/Button.svelte';
  import Icon from '../../../lib/components/Icon.svelte';
  import { sim, ws } from '../model/app.svelte';
  import { utc } from '../model/format';
  import LabIcon from '../ui/LabIcon.svelte';

  const SOUND = [
    { id: 'off', label: 'Off' },
    { id: 'soft', label: 'Soft' },
    { id: 'normal', label: 'Normal' },
  ] as const;

  function go(to: 'focus' | 'field' | 'run' | 'watch'): void {
    ws.attentionOpen = false;
    if (to === 'watch') ws.overlay = 'watch';
    else ws.setMode(to);
  }
</script>

<div class="pop" role="dialog" aria-label="Attention">
  <header>
    <LabIcon name="lab-attention" size={16} />
    <h2>Attention</h2>
    <span class="count num">{sim.unacked.length} open</span>
    <div class="sound" role="radiogroup" aria-label="Alert sound">
      <span class="lab-caps">Sound</span>
      {#each SOUND as s (s.id)}
        <button
          type="button"
          role="radio"
          aria-checked={sim.sound === s.id}
          class:on={sim.sound === s.id}
          onclick={() => {
            sim.sound = s.id;
            if (s.id !== 'off') sim.testSound();
          }}>{s.label}</button
        >
      {/each}
    </div>
  </header>
  <ol class="items">
    {#each sim.attention as a (a.id)}
      {@const acked = sim.acked.has(a.id)}
      <li class="item level-{a.level}" class:acked>
        <div class="line">
          <span class="lvl">{a.level}</span>
          <span class="t num">{utc(a.since, false)} UTC{a.frame ? ` · #${a.frame}` : ''}</span>
          {#if acked}<span class="ack">acknowledged</span>{/if}
        </div>
        <p class="title">{a.title}</p>
        <p class="detail">{a.detail}</p>
        {#if !acked && a.level !== 'info'}
          <div class="actions">
            {#if a.action}
              <button type="button" class="link" onclick={() => go(a.action!.to)}>
                <LabIcon name={a.action.icon} size={16} />{a.action.label}
              </button>
            {/if}
            <Button label="Acknowledge" size="s" onclick={() => sim.ack(a.id)} />
          </div>
        {/if}
      </li>
    {:else}
      <li class="empty">Nothing needs you. Rules run on every frame while a run is active.</li>
    {/each}
  </ol>
  <footer>
    <Icon name="settings" size={16} />
    <span>Rules and thresholds: Settings › Alerts (proposed) · acknowledged items stay in the Log</span>
  </footer>
</div>

<style>
  .pop {
    position: absolute;
    right: 0;
    bottom: calc(100% + 6px);
    width: 460px;
    max-height: 560px;
    display: flex;
    flex-direction: column;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--lab-elev-float);
    white-space: normal;
    z-index: var(--z-popover);
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-3) var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg-muted);
  }
  h2 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .count {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .sound {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 2px;
  }
  .sound .lab-caps {
    margin-right: var(--space-1);
  }
  .sound button {
    height: 22px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-xs);
    cursor: pointer;
  }
  .sound button.on {
    background: var(--toggled-bg);
    border-color: var(--border);
    color: var(--fg);
  }
  .items {
    list-style: none;
    margin: 0;
    padding: var(--space-2);
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .item {
    padding: var(--space-3) var(--space-3) var(--space-3) var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-left-width: 3px;
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  /* Level = word + edge weight and tone; never the colour alone. */
  .level-critical {
    border-color: var(--danger);
    border-left-width: 4px;
  }
  .level-attention {
    border-left-color: var(--warning);
  }
  .acked {
    opacity: 1;
    border-left-color: var(--border);
  }
  .acked .title,
  .acked .detail {
    color: var(--text-muted);
  }
  .line {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .lvl {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
    color: var(--fg);
  }
  .level-critical .lvl {
    font-weight: var(--weight-semibold);
  }
  .t,
  .ack {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .ack {
    margin-left: auto;
  }
  .title {
    margin: var(--space-1) 0 0;
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    font-variant-numeric: var(--numeric);
  }
  .detail {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
  .link {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 26px;
    padding: 0 var(--space-2);
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-s);
    cursor: pointer;
  }
  .link:hover {
    background: var(--hover-bg);
  }
  .empty {
    padding: var(--space-4);
    color: var(--text-muted);
  }
  footer {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-4);
    border-top: var(--border-w) solid var(--border-soft);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
