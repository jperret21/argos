<!--
  Plate 05: the mount card with its jog pad, live, beside pinned states and
  the dead-man timing. The lab switches break the link (renewals stop
  reaching the "server") or start a run (motion refused).
-->
<script lang="ts">
  import Ctl from '../components/Ctl.svelte';
  import Panel from '../components/Panel.svelte';
  import MountCard from '../instruments/MountCard.svelte';
  import { DEADMAN_MS, RENEW_MS } from '../jog';
  import { MountSim } from '../sim.svelte';
  import type { Hardware } from '../types';

  let { hw }: { hw: Hardware } = $props();

  let runActive = $state(false);
  let armed = $state(false);

  function snapshot(edit: (s: MountSim) => void): MountSim {
    const s = new MountSim();
    edit(s);
    return s;
  }
  const diagonal = snapshot((s) => {
    s.az = 183.14;
    s.alt = 41.62;
    s.trail = Array.from({ length: 24 }, (_, i) => ({ daz: i * 0.035, dalt: i * 0.015 }));
  });
  const stopped = snapshot((s) => {
    s.az = 182.3;
    s.alt = 42.08;
    s.deadmanStop = `Stopped by the server: no renewal for ${(DEADMAN_MS / 1000).toFixed(1)} s`;
    s.trail = Array.from({ length: 10 }, (_, i) => ({ daz: 0, dalt: i * 0.08 }));
  });

  // Dead-man timing diagram geometry (ms -> px).
  const W = 640;
  const T = 2600;
  const tx = (ms: number) => 56 + (ms / T) * (W - 80);
  const LOSS = 1100;
  const renews = Array.from({ length: Math.floor(LOSS / RENEW_MS) + 1 }, (_, i) => i * RENEW_MS);
  const lastRenew = renews[renews.length - 1];
  const stopAt = lastRenew + DEADMAN_MS;
</script>

<div class="wall">
  <section class="slot" data-shot="jog-live">
    <header><span class="code">E.1</span><b>Live</b><span class="note">hold a key · J arms the arrows · Esc stops</span></header>
    <MountCard sim={hw.mount} {runActive} bind:armed />
    <div class="labsw">
      <span class="lab-eyebrow">Lab</span>
      <span data-shot="link-loss">
        <Ctl
          icon="network"
          label="Break the link"
          showLabel
          size="s"
          variant="secondary"
          pressed={!hw.mount.linkUp}
          tooltipText="Renewals stop reaching the server; it stops the axis after 1.0 s"
          onclick={() => (hw.mount.linkUp = !hw.mount.linkUp)}
        />
      </span>
      <Ctl icon="start" label="Sequence running" showLabel size="s" pressed={runActive} onclick={() => (runActive = !runActive)} />
    </div>
  </section>

  <div class="stack">
    <section class="slot">
      <header><span class="code">E.2</span><b>Armed, Alt + and Az + held</b><span class="note">two axes at once</span></header>
      <MountCard sim={diagonal} pin={{ pressed: ['north', 'east'], armed: true, age: 0.12 * 1000 }} />
    </section>
  </div>

  <div class="stack">
    <section class="slot">
      <header><span class="code">E.3</span><b>Link lost while held</b><span class="note">the server stopped it</span></header>
      <MountCard sim={stopped} pin={{ stalled: ['north'], age: 1020 }} />
    </section>
  </div>



  <section class="slot wide">
    <Panel code="E.4" title="Dead-man timing" note="The client renews a moving axis every 250 ms; the server stops an axis not renewed for 1.0 s, or at once when the event socket closes. Here the link drops at 1.1 s while the key is still held." shot="deadman">
      <svg class="timing" width={W} height="112" viewBox="0 0 {W} 112" role="img" aria-label="Renewals every 250 ms until the link drops at 1.1 s; the server stops the axis 1.0 s after the last renewal">
        <line class="axis" x1={tx(0)} y1="78.5" x2={tx(T)} y2="78.5" />
        {#each [0, 500, 1000, 1500, 2000, 2500] as m (m)}
          <line class="tk" x1={tx(m) + 0.5} y1="78" x2={tx(m) + 0.5} y2="83" />
          <text class="tl" x={tx(m)} y="96" text-anchor="middle">{(m / 1000).toFixed(1)} s</text>
        {/each}

        <!-- Key held -->
        <text class="lane" x="0" y="21">key held</text>
        <rect class="held" x={tx(0)} y="14" width={tx(T - 100) - tx(0)} height="8" rx="1" />

        <!-- Renewals -->
        <text class="lane" x="0" y="44">renew</text>
        {#each renews as r (r)}
          <line class="renew" x1={tx(r) + 0.5} y1="34" x2={tx(r) + 0.5} y2="48" />
        {/each}
        <line class="lost" x1={tx(LOSS)} y1="8" x2={tx(LOSS)} y2="78" />
        <text class="ann" x={tx(LOSS) + 5} y="8">link lost</text>

        <!-- Axis moving -->
        <text class="lane" x="0" y="68">axis</text>
        <rect class="moving" x={tx(0)} y="61" width={tx(stopAt) - tx(0)} height="8" rx="1" />
        <path class="window" d="M{tx(lastRenew)} 56 V52 H{tx(stopAt)} V56" />
        <text class="ann" x={tx(stopAt) - 4} y="48" text-anchor="end">1.0 s without renewal</text>
        <line class="stopline" x1={tx(stopAt)} y1="56" x2={tx(stopAt)} y2="78" />
        <text class="ann strong" x={tx(stopAt) + 5} y="68">server stops the axis</text>
      </svg>
    </Panel>
  </section>
</div>

<style>
  .wall {
    display: grid;
    grid-template-columns: repeat(3, minmax(360px, 396px));
    gap: var(--space-3) var(--space-5);
    align-items: start;
  }
  .slot {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }
  .slot.wide {
    grid-column: span 2;
  }
  .stack {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  header {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    white-space: nowrap;
    overflow: hidden;
  }
  .code {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
  }
  b {
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
  }
  .note {
    overflow: hidden;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-overflow: ellipsis;
  }
  .labsw {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    border: var(--border-w) dashed var(--border);
    border-radius: var(--radius-s);
  }
  .labsw .lab-eyebrow {
    margin-right: var(--space-1);
  }

  .timing {
    display: block;
    max-width: 100%;
  }
  .axis,
  .tk {
    stroke: var(--border);
    stroke-width: 1;
  }
  .tl,
  .lane,
  .ann {
    fill: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 10px;
  }
  .ann.strong {
    fill: var(--fg);
  }
  .held {
    fill: var(--border);
  }
  .renew {
    stroke: var(--fg);
    stroke-width: 1.5;
  }
  .lost {
    stroke: var(--danger);
    stroke-width: 1;
    stroke-dasharray: 3 3;
  }
  .moving {
    fill: var(--fg-muted);
  }
  .window {
    fill: none;
    stroke: var(--fg-muted);
    stroke-width: 1;
  }
  .stopline {
    stroke: var(--fg);
    stroke-width: 1.5;
  }
</style>
