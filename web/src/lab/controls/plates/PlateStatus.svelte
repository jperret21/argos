<!--
  Plate 07: status chips and badges, attention levels, counts, key caps,
  focus, and unavailable controls that explain themselves on a press.
-->
<script lang="ts">
  import { formatShortcut } from '../../../lib/app/shortcuts';
  import Icon from '../../../lib/components/Icon.svelte';
  import Chip from '../components/Chip.svelte';
  import Ctl from '../components/Ctl.svelte';
  import Panel from '../components/Panel.svelte';
  import Seg from '../components/Seg.svelte';
  import TipStatic from '../components/TipStatic.svelte';
  import type { Hardware } from '../types';

  let { hw }: { hw: Hardware } = $props();

  let seg = $state<'a' | 'b' | 'c'>('b');
  const KEYS: [string, string][] = [
    ['Mod+K', 'Command palette'],
    ['Shift+F', 'Fill the viewer'],
    ['Escape', 'Abort motion, close the top layer'],
    ['E', 'One exposure'],
    ['?', 'Keyboard shortcuts'],
    ['Alt+ArrowLeft', 'Back to the session'],
    ['Mod+Shift+O', 'Review sessions'],
  ];
</script>

<div class="cols">
  <div class="col">
    <Panel code="G.1" title="Device states" note="A dot for the tone, the state in words. Idle is a hollow ring, so it reads without colour; Night Red dots sit under 3:1 and the word carries the state." shot="badges">
      <div class="chips">
        <Chip tone="idle" label="Offline" />
        <Chip tone="ok" label="Ready" />
        <Chip tone="ok" label="Tracking" />
        <Chip tone="busy" label="Moving" />
        <Chip tone="busy" label="Slewing" value="12.4°" />
        <Chip tone="active" label="Live" />
        <Chip tone="active" label="Autofocus" value="7/14" />
        <Chip tone="error" label="Lost" />
      </div>
      <div class="chips">
        <Chip tone="stale" label="Last frame · 21:34:05 UTC" />
        <Chip tone="ok" label="Camera" value="−10.0 °C" />
        <Chip tone="none" label="Filter" value="LP" />
      </div>
    </Panel>

    <Panel code="G.2" title="Over the image" note="Frame chips sit in a corner, opaque, mono, one row; a crop or a kept zoom is never silent." shot="hud">
      <div class="canvas">
        <div class="hud tl">
          <Chip variant="hud" tone="active" label="LIVE" />
          <Chip variant="hud" label="#128" />
          <Chip variant="hud" label="2.0 s" />
          <Chip variant="hud" label="M 42" />
        </div>
        <div class="hud tr">
          <Chip variant="hud" label="Fill · cropped" keys="F" />
        </div>
        <div class="hud bl">
          <Chip variant="hud" label="Manual zoom kept" keys="F" />
          <Chip variant="hud" tone="stale" label="Last frame · 21:34:05 UTC" />
        </div>
        <span class="star" style="left: 38%; top: 46%; --r: 3px"></span>
        <span class="star" style="left: 62%; top: 30%; --r: 2px"></span>
        <span class="star" style="left: 24%; top: 70%; --r: 1.5px"></span>
        <span class="star" style="left: 71%; top: 64%; --r: 2.5px"></span>
        <span class="star" style="left: 52%; top: 58%; --r: 1.5px"></span>
      </div>
    </Panel>


  </div>

  <div class="col">
    <Panel code="G.4" title="Attention levels" note="Three shapes, three words: a filled disc for critical, an upright mark for attention (never a triangle: that is the check star), a ring for information. Critical repeats until acknowledged." shot="attention">
      <div class="levels">
        <div class="lv"><Chip variant="alert" level="critical" label="Critical" /><span>No new frame for 4 m 12 s (cadence 51 s)</span></div>
        <div class="lv"><Chip variant="alert" level="attention" label="Attention" /><span>HFD 8.4 px, 1.5 × the first 20 frames, 3 frames running</span></div>
        <div class="lv"><Chip variant="alert" level="info" label="Info" /><span>Comparisons used 4 of 5 on this frame</span></div>
      </div>
      <div class="chips counts">
        <span class="lab-eyebrow">Counts</span>
        <Chip label="Log" count={5} />
        <Chip label="Conditions" count={2} countTone="critical" />
        <Chip label="Issues" count={12} />
      </div>
    </Panel>

    <Panel code="G.5" title="Keys" note="One key cap, everywhere: tips, hints, help lines, menus. Platform glyphs on macOS (⌘ ⇧ ⌥), words elsewhere." shot="keys">
      <table class="keys">
        <thead><tr><th>macOS</th><th>Windows, Linux</th><th></th></tr></thead>
        <tbody>
          {#each KEYS as [k, what] (k)}
            <tr><td><kbd class="cap">{formatShortcut(k, true)}</kbd></td><td><kbd class="cap">{formatShortcut(k, false)}</kbd></td><td>{what}</td></tr>
          {/each}
        </tbody>
      </table>
      <div class="tips">
        <TipStatic text="Fit the whole frame" shortcut="F" />
        <TipStatic text="Jog Altitude +" shortcut="ArrowUp" hint="Hold to move, release to stop" />
        <TipStatic text="Park" hint="Hold 0.7 s to park · Enter to confirm" />
      </div>
    </Panel>
  </div>

  <div class="col">
    <Panel code="G.6" title="Focus" note="2 px ring in --focus-ring, 2 px off the edge, on top of any state; never removed. Shown here pinned on each kind of control." shot="focus">
      <div class="focus">
        <Ctl icon="crosshair" label="Crosshair" variant="ghost" data-force="focus" />
        <Ctl icon="crosshair" label="Crosshair" variant="ghost" pressed data-force="focus" />
        <Ctl icon="goto" label="Slew" showLabel variant="primary" data-force="focus" />
        <Ctl icon="abort" label="Abort" showLabel variant="danger" data-force="focus" />
        <div class="segfocus"><Seg label="Demo" options={[{ value: 'a', label: 'Light' }, { value: 'b', label: 'Dark' }, { value: 'c', label: 'Flat' }]} bind:value={seg} /></div>
      </div>
    </Panel>

    <Panel code="G.7" title="Press an unavailable control" note="It says why at once (a press on a control that does nothing is when the reason is needed). Hover shows it after 500 ms, Tab at once." shot="press-reason">
      <div class="press">
        <Ctl icon="goto" label="Slew" showLabel variant="primary" disabledReason={hw.mount.parked ? 'Unpark the mount first' : 'The sequence is running: slewing now breaks the time series'} />
        <Ctl icon="autofocus" label="Autofocus" showLabel disabledReason="Connect the focuser and the camera first" />
        <Ctl icon="export-aavso" label="Export AAVSO" showLabel disabledReason="Set your observer code in Settings first" />
        <Ctl icon="plate-solve" label="Identify field" variant="ghost" disabledReason="Take or open a full-resolution frame" />
      </div>
    </Panel>

    <Panel code="G.8" title="Roles" note="Shape first, colour second, as on the image and in the plots." shot="roles">
      <div class="roles">
        <span class="role t"><Icon name="target-star" size={16} /><span>Target</span><span class="num">RR Lyr</span></span>
        <span class="role c"><Icon name="comparison-star" size={16} /><span>Comparison</span><span class="num">000-BCG-512</span></span>
        <span class="role k"><Icon name="check-star" size={16} /><span>Check</span><span class="num">000-BCG-498</span></span>
      </div>
    </Panel>
  </div>
</div>
<div class="wide">
    <Panel code="G.3" title="Status bar" note="One row of 32 px. The attention chip leads with the most severe level and counts the others; the device word carries the state, the dot repeats it." shot="bar">
    <div class="statusbar">
      <span class="sbi"><Icon name="mount" size={14} /><Chip variant="bar" tone="ok" label="Mount" value="Tracking" /></span>
      <span class="sbi num">RA 05h 35m 17.3s Dec −05° 23′ 28″</span>
      <span class="sep"></span>
      <Chip variant="alert" level="critical" label="No frame for 4 m 12 s" count={3} countTone="critical" />
      <span class="sep"></span>
      <span class="sbi"><Icon name="camera" size={14} /><Chip variant="bar" tone="active" label="Live" value="#128 · 2.0 s" /></span>
      <span class="grow"></span>
      <span class="sbi num muted">x 512 y 960 · 2 034 ADU</span>
      <span class="sep"></span>
      <span class="sbi"><Icon name="log" size={14} /><span>Log</span><span class="cnt num">5</span></span>
    </div>
  </Panel>
</div>

<style>
  .cols {
    display: grid;
    grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr) minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
  }
  .col {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-width: 0;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
  }
  .chips + .chips {
    margin-top: var(--space-3);
  }
  .counts {
    margin-top: var(--space-4);
  }

  .canvas {
    position: relative;
    height: 170px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--viewer-bg);
    overflow: hidden;
  }
  .hud {
    position: absolute;
    display: flex;
    gap: 4px;
  }
  .tl {
    top: 8px;
    left: 8px;
  }
  .tr {
    top: 8px;
    right: 8px;
  }
  .bl {
    bottom: 8px;
    left: 8px;
  }
  .star {
    position: absolute;
    width: calc(var(--r) * 2);
    height: calc(var(--r) * 2);
    border-radius: var(--radius-round);
    background: var(--viewer-tint);
  }

  .statusbar {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 32px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg);
    color: var(--fg);
    font-size: var(--text-s);
    white-space: nowrap;
    overflow: hidden;
  }
  .sbi {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--fg);
    font-size: var(--text-s);
  }
  .sbi :global(.icon) {
    color: var(--fg-muted);
  }
  .sep {
    width: 1px;
    height: 16px;
    background: var(--border-soft);
  }
  .grow {
    flex: 1;
  }
  .cnt {
    padding: 0 5px;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-round);
    font-size: var(--text-2xs);
    line-height: 14px;
  }

  .levels {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .lv {
    display: grid;
    grid-template-columns: 104px minmax(0, 1fr);
    justify-items: start;
    align-items: center;
    gap: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }

  .keys {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-xs);
  }
  .keys th {
    padding: 0 0 4px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-align: left;
    text-transform: uppercase;
  }
  .keys td {
    height: 22px;
    padding: 0;
    border-top: var(--border-w) solid var(--border-soft);
    color: var(--text-muted);
  }
  .keys td:last-child {
    color: var(--fg);
  }
  .wide {
    margin-top: var(--space-4);
  }
  .muted {
    color: var(--text-muted);
  }
  .tips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    margin-top: var(--space-4);
  }

  .focus {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-4);
    padding: 4px;
  }
  .segfocus :global(.opt[aria-checked='true']) {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }

  .press {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .roles {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .role {
    display: grid;
    grid-template-columns: 16px 96px minmax(0, 1fr);
    align-items: center;
    gap: var(--space-2);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .role .num {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .role.t :global(.icon) {
    color: var(--role-target);
  }
  .role.c :global(.icon) {
    color: var(--role-comparison);
  }
  .role.k :global(.icon) {
    color: var(--role-check);
  }
</style>
