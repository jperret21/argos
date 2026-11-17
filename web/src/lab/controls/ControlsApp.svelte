<!--
  Lab shell: the control system as a specimen book. One plate at a time on
  a full stage (judged and screenshotted at 1440 x 900 / 1280 x 800), chosen
  by tab or ?plate=<id>. Theme, motion and key hints apply to every plate.

  Shared simulated hardware lives here, so a focuser moved on one plate is
  where it was on the next. Esc stops every motion (D21), even when a field
  or a menu also uses the key (capture phase).
-->
<script lang="ts">
  import type { Component } from 'svelte';
  import Icon from '../../lib/components/Icon.svelte';
  import Ctl from './components/Ctl.svelte';
  import Seg from './components/Seg.svelte';
  import { engineLabel, env, LAB_THEMES, type LabTheme, type MotionPref, setMotion, setTheme, THEME_LABEL, writeUrl } from './env.svelte';
  import { hints, installHints } from './hints.svelte';
  import PlateButtons from './plates/PlateButtons.svelte';
  import PlateConfirm from './plates/PlateConfirm.svelte';
  import PlateFocuser from './plates/PlateFocuser.svelte';
  import PlateMount from './plates/PlateMount.svelte';
  import PlateStatus from './plates/PlateStatus.svelte';
  import PlateToolbar from './plates/PlateToolbar.svelte';
  import PlateValues from './plates/PlateValues.svelte';
  import { ExposureSim, FocuserSim, MountSim } from './sim.svelte';
  import type { Hardware } from './types';

  interface Plate {
    id: string;
    n: string;
    title: string;
    proves: string;
    component: Component<{ hw: Hardware }>;
  }

  const hw: Hardware = { focuser: new FocuserSim(), mount: new MountSim(), exposure: new ExposureSim() };

  const PLATES: Plate[] = [
    { id: 'buttons', n: '01', title: 'Buttons', proves: 'Every variant in every state (rest, hover, pressed, focus, toggled, unavailable, busy, error), the time ring, sizes and the icon / label grammar.', component: PlateButtons },
    { id: 'toolbar', n: '02', title: 'Toolbars', proves: 'Groups, split buttons that show their options, a priority overflow that says how many tools it holds, and key hints while Mod is held.', component: PlateToolbar },
    { id: 'values', n: '03', title: 'Values', proves: 'Fields that scrub, steppers that repeat, sliders with ticks, detents and fine adjustment, segmented choices: one modifier convention, one commit model.', component: PlateValues },
    { id: 'focuser', n: '04', title: 'Focuser', proves: 'A two-scale travel gauge where one tick is one tap, queued taps, Go to that never moves on blur, Halt always available.', component: PlateFocuser },
    { id: 'mount', n: '05', title: 'Mount jog', proves: 'Press-and-hold with a visible dead-man, axes tracked separately, armed arrow keys, the rate in °/s, polled offsets.', component: PlateMount },
    { id: 'confirm', n: '06', title: 'Confirm & progress', proves: 'Hold-to-confirm with a time ring for Park, Pause-and-slew and Stop; the keyboard path; progress and busy inside buttons.', component: PlateConfirm },
    { id: 'status', n: '07', title: 'Status & keys', proves: 'Chips and badges double-coded, attention levels, key caps, focus, and reasons for every unavailable control.', component: PlateStatus },
  ];

  function initialPlate(): string {
    const id = new URLSearchParams(location.search).get('plate');
    return PLATES.some((p) => p.id === id) ? (id as string) : 'buttons';
  }

  let current = $state(initialPlate());
  const plate = $derived(PLATES.find((p) => p.id === current) ?? PLATES[0]);
  const engine = engineLabel();

  if (new URLSearchParams(location.search).get('hints') === '1') hints.pinned = true;

  function choose(id: string): void {
    current = id;
    writeUrl('plate', id);
  }

  function tabKey(e: KeyboardEvent): void {
    const i = PLATES.findIndex((p) => p.id === current);
    let j = i;
    if (e.key === 'ArrowRight') j = (i + 1) % PLATES.length;
    else if (e.key === 'ArrowLeft') j = (i - 1 + PLATES.length) % PLATES.length;
    else return;
    e.preventDefault();
    choose(PLATES[j].id);
    document.getElementById(`lab-tab-${PLATES[j].id}`)?.focus();
  }

  $effect(() => installHints());

  // Esc = abort motion (D21), in the capture phase so a field or menu using
  // the key for itself does not keep the hardware moving.
  $effect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (hw.focuser.moving && !hw.focuser.af) hw.focuser.halt();
      if (hw.mount.rate.primary || hw.mount.rate.secondary) hw.mount.stopAll();
      if (hw.mount.slewToGo !== null) hw.mount.abortSlew();
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  });

  const THEMES = LAB_THEMES.map((t) => ({ value: t, label: THEME_LABEL[t] }));
  const MOTIONS: { value: MotionPref; label: string }[] = [
    { value: 'system', label: 'System' },
    { value: 'reduced', label: 'Reduced' },
  ];
  let theme: LabTheme = $state(env.theme);
  let motion: MotionPref = $state(env.motion);
</script>

<div class="lab">
  <header class="bar">
    <div class="brand">
      <span class="mark"><Icon name="about" size={22} /></span>
      <span class="word">ARGOS</span>
      <span class="divider"></span>
      <span class="lab-eyebrow">Lab · controls</span>
    </div>

    <div class="tabs" role="tablist" aria-label="Plates" tabindex="-1" onkeydown={tabKey}>
      {#each PLATES as p (p.id)}
        <button
          id="lab-tab-{p.id}"
          role="tab"
          aria-selected={p.id === current}
          aria-controls="lab-stage"
          tabindex={p.id === current ? 0 : -1}
          onclick={() => choose(p.id)}
        >
          <span class="n">{p.n}</span>{p.title}
        </button>
      {/each}
    </div>

    <div class="switches">
      <Ctl
        icon="help"
        label="Key hints"
        size="s"
        variant="ghost"
        pressed={hints.pinned}
        layoutToggle
        tooltipText="Show every shortcut on its control (or hold {navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'})"
        onclick={() => (hints.pinned = !hints.pinned)}
      />
      <Seg label="Motion" options={MOTIONS} bind:value={motion} size="s" onchange={(m) => setMotion(m)} />
      <Seg label="Theme" options={THEMES} bind:value={theme} size="s" onchange={(t) => setTheme(t)} />
    </div>
  </header>

  <div class="sub">
    <p class="proves"><span class="n">{plate.n}</span><b>{plate.title}.</b> {plate.proves}</p>
    <span class="engine">{engine}</span>
  </div>

  <div class="stage" id="lab-stage" role="tabpanel" aria-labelledby="lab-tab-{plate.id}">
    {#key plate.id}
      <plate.component {hw} />
    {/key}
  </div>
</div>

<style>
  .lab {
    display: grid;
    grid-template-rows: auto auto 1fr;
    height: 100%;
    min-height: 0;
    background: var(--bg);
  }

  .bar {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    height: 46px;
    padding: 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex: none;
  }
  .mark {
    display: inline-flex;
    color: var(--accent);
  }
  .word {
    color: var(--fg);
    font-family: var(--font-ui);
    font-size: 15px;
    font-weight: var(--weight-semibold);
    letter-spacing: -0.065em;
  }
  .divider {
    width: 1px;
    height: 18px;
    margin: 0 var(--space-2);
    background: var(--border-soft);
  }

  .tabs {
    display: flex;
    align-items: stretch;
    align-self: stretch;
    gap: 2px;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .tabs button {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 0 var(--space-3);
    border: none;
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    white-space: nowrap;
    cursor: pointer;
  }
  .tabs button:hover {
    color: var(--fg);
  }
  .tabs button[aria-selected='true'] {
    color: var(--fg);
  }
  .tabs button[aria-selected='true']::after {
    content: '';
    position: absolute;
    left: var(--space-3);
    right: var(--space-3);
    bottom: -1px;
    height: 2px;
    background: var(--accent);
  }
  .tabs button:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -4px;
  }
  .n {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-variant-numeric: var(--numeric);
  }

  .switches {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-left: auto;
    flex: none;
  }

  .sub {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    min-height: 34px;
    padding: 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
    background: var(--bg-2);
  }
  .proves {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
    line-height: var(--leading-tight);
  }
  .proves b {
    color: var(--fg);
    font-weight: var(--weight-semibold);
    white-space: nowrap;
  }
  .engine {
    margin-left: auto;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    white-space: nowrap;
  }

  .stage {
    min-height: 0;
    overflow: auto;
    padding: var(--space-4);
    scrollbar-gutter: stable;
  }
</style>
