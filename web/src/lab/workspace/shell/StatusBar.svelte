<!--
  Status bar (one 28 px row): device cluster, link, mount geometry and
  pointing (always in view, BRAND 11.1), the run chip (the only home of
  sequence progress outside Observe › Run, D18), the ATTENTION chip of the
  notification area (count and newest item; opens the list), the activity
  text and the Log button. The cursor readout moved to the image HUD (one
  home per value).
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import { tooltip } from '../../../lib/components/tooltip';
  import { sim, ws } from '../model/app.svelte';
  import { formatDec, formatRA } from '../model/format';
  import { duration, utc } from '../model/format';
  import { RUN } from '../model/night';
  import { TARGET_DEC, TARGET_RA_H } from '../model/field';
  import LabIcon from '../ui/LabIcon.svelte';
  import AttentionPopover from '../overlays/AttentionPopover.svelte';

  const DEVICES = [
    { icon: 'mount', label: 'Mount' },
    { icon: 'camera', label: 'Camera' },
    { icon: 'filter-wheel', label: 'Filter wheel' },
    { icon: 'focuser', label: 'Focuser' },
  ];

  const top = $derived(sim.unacked[0] ?? null);
  const count = $derived(sim.unacked.length);
  const remaining = $derived(sim.endsAt - sim.now);
  const activity = $derived.by(() => {
    const lines = sim.log.filter((l) => l.t <= sim.now);
    return lines[lines.length - 1] ?? null;
  });
</script>

<footer class="status" aria-label="Status">
  <div class="seg devices">
    {#each DEVICES as d (d.icon)}
      <span class="dev" use:tooltip={{ text: `${d.label}: ready`, placement: 'top' }}>
        <Icon name={d.icon} size={16} label="{d.label} ready" />
        <span class="dot ok" aria-hidden="true"></span>
      </span>
    {/each}
    <span class="word">Seestar</span>
    <span class="dot ok inline" aria-hidden="true"></span>
  </div>
  <div class="seg">
    <span class="word muted">Alt-Az</span>
    <span class="word">{sim.parked ? 'Parked' : sim.tracking ? 'Tracking' : 'Not tracking'}</span>
  </div>
  <div class="seg num pointing" use:tooltip={{ text: 'Mount pointing (J2000)', placement: 'top' }}>
    <span class="k">RA</span>{formatRA(TARGET_RA_H + 0.0012)}
    <span class="k">Dec</span>{formatDec(TARGET_DEC + 0.06)}
  </div>

  {#if sim.inRun}
    <button
      type="button"
      class="seg chip run"
      onclick={() => ws.setMode('run')}
      use:tooltip={{ text: `Run: open Observe › Run · last frame ${sim.lastAge} s ago`, placement: 'top' }}
    >
      <span class="rec" class:paused={!sim.running} aria-hidden="true"></span>
      <span class="word strong">{sim.running ? 'REC' : sim.runState === 'complete' ? 'Done' : 'Paused'}</span>
      <span class="word">{RUN.object}</span>
      <span class="num">{sim.delivered}/{RUN.frames}</span>
      {#if sim.running && Number.isFinite(remaining)}<span class="num muted">ETA {duration(remaining)}</span>{/if}
    </button>
  {:else if sim.live}
    <span class="seg chip">
      <span class="rec live" aria-hidden="true"></span>
      <span class="word strong">LIVE</span>
      <span class="num">#{sim.source === 'server' ? (sim.frame?.header.seq ?? '—') : sim.liveSeq}</span>
    </span>
  {/if}

  <span class="spacer"></span>

  <div class="attention-anchor">
    <button
      type="button"
      class="seg chip attention"
      class:on={count > 0}
      class:critical={top?.level === 'critical'}
      aria-expanded={ws.attentionOpen}
      aria-haspopup="dialog"
      aria-label="Attention: {count} {count === 1 ? 'item' : 'items'}{top ? `, newest: ${top.rule}` : ''}"
      onclick={() => {
        sim.armSound();
        ws.attentionOpen = !ws.attentionOpen;
      }}
    >
      <LabIcon name="lab-attention" size={16} />
      <span class="num">{count}</span>
      {#if top}<span class="word">{top.rule}</span>{:else}<span class="word muted">Attention</span>{/if}
    </button>
    {#if ws.attentionOpen}
      <AttentionPopover />
    {/if}
  </div>

  {#if activity}
    <span class="seg activity" use:tooltip={{ text: `${utc(activity.t)} UTC · ${activity.text}`, placement: 'top' }}>
      <span class="num muted">{utc(activity.t, false)}</span>
      <span class="word">{activity.text}</span>
    </span>
  {/if}
  <span class="seg lab" use:tooltip={{ text: 'Prototype: every value comes from a seeded synthetic night (lab panel: `)', placement: 'top' }}>
    Synthetic data
  </span>
  <button type="button" class="seg log" onclick={() => ws.toggleDrawer('log')} use:tooltip={{ text: 'Log', shortcut: 'L', placement: 'top' }}>
    <Icon name="log" size={16} />
    <span class="word">Log</span>
  </button>
</footer>

<style>
  .status {
    grid-area: status;
    display: flex;
    align-items: center;
    gap: 0;
    min-width: 0;
    padding: 0 var(--space-2);
    border-top: var(--border-w) solid var(--border);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-s);
    white-space: nowrap;
    position: relative;
    z-index: var(--z-sticky);
  }
  .seg {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 100%;
    padding: 0 var(--space-3);
    border: none;
    border-right: var(--border-w) solid var(--border-soft);
    background: transparent;
    color: inherit;
    font: inherit;
  }
  .devices {
    gap: var(--space-2);
    padding-left: var(--space-1);
    color: var(--fg-muted);
  }
  .dev {
    position: relative;
    display: inline-flex;
    padding-right: 4px;
  }
  .dot {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
    background: var(--status-ok);
  }
  .dev .dot {
    position: absolute;
    right: 0;
    bottom: 0;
    border: 1px solid var(--bg-2);
    box-sizing: content-box;
  }
  .word {
    color: var(--fg);
  }
  .word.strong {
    font-weight: var(--weight-semibold);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    letter-spacing: var(--tracking-caps);
  }
  .muted,
  .k {
    color: var(--text-muted);
  }
  .pointing {
    gap: var(--space-1);
  }
  .pointing .k {
    margin-left: var(--space-2);
  }
  .pointing .k:first-child {
    margin-left: 0;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .chip {
    cursor: pointer;
  }
  button.seg:hover {
    background: var(--hover-bg);
  }
  .rec {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-round);
    background: var(--danger);
  }
  .rec.paused {
    border-radius: 1px;
    background: var(--fg-muted);
  }
  .rec.live {
    background: var(--accent);
  }
  .spacer {
    flex: 1;
  }
  .attention-anchor {
    position: relative;
    height: 100%;
    display: flex;
    border-left: var(--border-w) solid var(--border-soft);
  }
  .attention {
    color: var(--fg-muted);
  }
  /* Attention: --warning outline and glyph, words stay --fg (BRAND 4.2). */
  .attention.on {
    color: var(--fg);
    box-shadow: inset 0 0 0 1px var(--warning);
  }
  .attention.on :global(.icon) {
    color: var(--warning);
  }
  .attention.critical {
    box-shadow: inset 0 0 0 2px var(--danger);
  }
  .attention.critical :global(.icon) {
    color: var(--danger);
  }
  .activity {
    max-width: 380px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .activity .word {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .lab {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .log {
    border-right: none;
    cursor: pointer;
    color: var(--fg-muted);
  }
  .log .word {
    color: var(--fg);
  }
</style>
