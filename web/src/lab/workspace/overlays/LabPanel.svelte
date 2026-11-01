<!--
  Lab controls (not part of the proposed UI): scene, simulated clock speed,
  theme, motion, density, and shortcuts to the states worth reviewing.
  Opened with the ` key; floats top right over the toolbar.
-->
<script lang="ts">
  import { THEMES, THEME_LABELS } from '../../../lib/app/theme';
  import { env, setDensity, setMotion, setTheme, type Density, type Motion } from '../model/env.svelte';
  import { sim, ws } from '../model/app.svelte';
  import type { Scene } from '../model/sim.svelte';
  import { RUN } from '../model/night';

  const SCENES: { id: Scene; label: string; mode: 'framing' | 'focus' | 'field' | 'run' }[] = [
    { id: 'framing', label: 'Framing, live view', mode: 'framing' },
    { id: 'focus', label: 'Autofocus running', mode: 'focus' },
    { id: 'field', label: 'Field identified, roles', mode: 'field' },
    { id: 'run-healthy', label: 'Run, frame 120 (healthy)', mode: 'run' },
    { id: 'run', label: 'Run, frame 160 (HFD rule fired)', mode: 'run' },
    { id: 'run-complete', label: 'Run complete (wrap-up)', mode: 'run' },
  ];
  const SPEEDS = [0, 1, 20, 60];
</script>

<div class="lab" role="dialog" aria-label="Lab controls">
  <header><span class="lab-caps">Lab controls</span><span class="hint">` toggles · not part of the UI</span></header>
  <div class="grp">
    <span class="lab-caps">Scene</span>
    {#each SCENES as s (s.id)}
      <button
        type="button"
        class:on={sim.scene === s.id}
        onclick={() => {
          sim.setScene(s.id);
          ws.setMode(s.mode, false);
        }}>{s.label}</button
      >
    {/each}
  </div>
  <div class="grp row">
    <span class="lab-caps">Clock</span>
    {#each SPEEDS as v (v)}
      <button type="button" class:on={sim.speed === v} onclick={() => (sim.speed = v)}>{v === 0 ? 'frozen' : `x${v}`}</button>
    {/each}
    <span class="hint">frame {sim.delivered}/{RUN.frames}</span>
  </div>
  <div class="grp row">
    <span class="lab-caps">Theme</span>
    {#each THEMES as t (t)}
      <button type="button" class:on={env.theme === t} onclick={() => setTheme(t)}>{THEME_LABELS[t]}</button>
    {/each}
  </div>
  <div class="grp row">
    <span class="lab-caps">Motion</span>
    {#each ['system', 'reduced', 'full'] as m (m)}
      <button type="button" class:on={env.motion === m} onclick={() => setMotion(m as Motion)}>{m}</button>
    {/each}
  </div>
  <div class="grp row">
    <span class="lab-caps">Density</span>
    {#each ['compact', 'comfortable'] as d (d)}
      <button type="button" class:on={env.density === d} onclick={() => setDensity(d as Density)}>{d}</button>
    {/each}
  </div>
  <p class="hint">Source: {sim.source === 'server' ? `server frames (${sim.serverState})` : 'synthetic frames (worker)'} · last synthesis {sim.measured.synthMs.toFixed(0)} ms</p>
</div>

<style>
  .lab {
    position: fixed;
    top: 52px;
    right: 12px;
    z-index: var(--z-popover);
    width: 340px;
    padding: var(--space-3);
    border: 1px dashed var(--border);
    border-radius: var(--radius-m);
    background: var(--bg-2);
    box-shadow: var(--shadow-2);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  .grp {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .grp.row {
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1);
  }
  .grp.row .lab-caps {
    width: 64px;
  }
  button {
    height: 24px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-align: left;
    cursor: pointer;
  }
  button.on {
    background: var(--toggled-bg);
    border-color: var(--border);
    color: var(--fg);
  }
  .hint {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
