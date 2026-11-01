<!--
  Plate 04: the focuser card at rail width (396 px), live, and pinned in
  the states that matter at night. Pinned cards are frozen simulator
  snapshots (no timer runs), so they show exactly one state each.
-->
<script lang="ts">
  import FocuserControl from '../instruments/FocuserControl.svelte';
  import { FocuserSim } from '../sim.svelte';
  import type { Hardware } from '../types';

  let { hw }: { hw: Hardware } = $props();

  function snapshot(edit: (s: FocuserSim) => void): FocuserSim {
    const s = new FocuserSim();
    edit(s);
    return s;
  }

  const moving = snapshot((s) => {
    s.position = 12_520;
    s.target = 12_750;
    s.queued = 300;
    s.moving = true;
    s.temperature = 11.9;
  });
  const af = snapshot((s) => {
    s.position = 12_330;
    s.target = 12_330;
    s.moving = false;
    s.af = { stage: 'fine', step: 11, total: 14 };
    s.temperature = 11.8;
  });
  const offline = snapshot((s) => {
    s.connected = false;
  });
  const refused = snapshot((s) => {
    s.position = 99_850;
    s.afBest = 99_700;
    s.message = 'Out of range: 0 to 100 000. Nothing was sent.';
  });
</script>

<div class="wall">
  <section class="slot live" data-shot="focuser-live">
    <header><span class="code">D.1</span><b>Live</b><span class="note">tap In / Out, hold to repeat, type a target, Esc halts</span></header>
    <FocuserControl sim={hw.focuser} />
  </section>

  <section class="slot">
    <header><span class="code">D.2</span><b>Moving, taps queued</b><span class="note">needle = polled, ▽ = target</span></header>
    <FocuserControl sim={moving} />
  </section>

  <section class="slot">
    <header><span class="code">D.3</span><b>Autofocus running</b><span class="note">Halt stays available</span></header>
    <FocuserControl sim={af} />
  </section>

  <section class="slot">
    <header><span class="code">D.4</span><b>Offline</b><span class="note">readouts “—”, reasons in words</span></header>
    <FocuserControl sim={offline} step="1000" />
  </section>

  <section class="slot">
    <header><span class="code">D.5</span><b>Near the end of travel</b><span class="note">refused, never clamped</span></header>
    <FocuserControl sim={refused} step="500" />
  </section>

  <section class="slot notes">
    <header><span class="code">D.6</span><b>Why it is drawn this way</b></header>
    <ul>
      <li><b>Two scales.</b> 100 000 steps at 1:1 make a 100-step move 0.4 px. The hairline shows the whole travel and the window; the scale below has one tick per step size, so one tap moves the needle one tick.</li>
      <li><b>Truthful needle.</b> It is the polled position (2 Hz while moving), so it jumps between polls. The target triangle and the dashed travel say where it is going; nothing is interpolated.</li>
      <li><b>Taps never lost.</b> Taps during a move are added to a queue shown in words ("+300 queued") and sent as one move: no Move while moving, which some ASCOM drivers refuse.</li>
      <li><b>Go to never moves on blur.</b> It is an action field: only Enter or its Move button send (Qt P5, P6).</li>
      <li><b>Temperature drift.</b> The tube cools during the night; "−1.8 °C since AF" with a warning dot from 1.5 °C says when to refocus, without a modal.</li>
      <li><b>Halt</b> is enabled whenever the focuser is connected, autofocus included (Qt P7); Stop AF returns to the start position.</li>
    </ul>
  </section>
</div>

<style>
  .wall {
    display: grid;
    grid-template-columns: repeat(3, minmax(360px, 396px));
    gap: var(--space-3) var(--space-5);
    justify-content: start;
    align-items: start;
  }
  .slot {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
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
  .notes ul {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: var(--space-3) var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
    list-style: none;
  }
  .notes li b {
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
  }
</style>
