<!--
  Component gallery, wave 3 (development only, part of /?gallery=1): the
  controls and instruments promoted for "Observe: acquisition"
  (web/lab/PROPOSAL.md 6, W3 rows; web/spec/README.md 7 W3), each in every
  state. Static states are pinned (`pin`, `force`, `data-force`, crafted
  records); the "Live" rows run the real behaviour against local fakes
  (fixtures3.svelte.ts). Sections are [data-gallery="w3-<name>"] for element
  screenshots.
-->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import FilterWheelControl from '../../imaging/instruments/FilterWheelControl.svelte';
  import { focuserBadge } from '../../imaging/instruments/focuser';
  import FocuserControl from '../../imaging/instruments/FocuserControl.svelte';
  import FocuserGauge from '../../imaging/instruments/FocuserGauge.svelte';
  import JogPad from '../../imaging/instruments/JogPad.svelte';
  import type { JogRate } from '../../imaging/instruments/jog';
  import type { AutofocusView, FilterWheelView, FocuserView, MountJogView } from '../../imaging/instruments/types';
  import Card from '../Card.svelte';
  import Control from '../Control.svelte';
  import HoldButton from '../HoldButton.svelte';
  import Icon from '../Icon.svelte';
  import Menu from '../Menu.svelte';
  import type { MenuEntry } from '../menu';
  import NumberField from '../NumberField.svelte';
  import Segmented from '../Segmented.svelte';
  import SplitButton from '../SplitButton.svelte';
  import StatusBadge from '../StatusBadge.svelte';
  import Toolbar from '../Toolbar.svelte';
  import type { ToolDef } from '../toolbar';
  import { FakeFocuser, FakeMount, FakeWheel } from './fixtures3.svelte';

  const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

  // -- Segmented ------------------------------------------------------------------------------
  const SLOTS = ['Dark', 'IR', 'LP'].map((s) => ({ value: s, label: s }));
  let display = $state('linear');
  let manual = $state('IR');
  let manualLog = $state('—');
  const rates = [
    { value: 'slow', label: 'Slow', detail: '0.5°/s' },
    { value: 'normal', label: 'Normal', detail: '2°/s' },
    { value: 'fast', label: 'Fast', detail: '5°/s' },
  ];
  let jogRateDemo = $state('normal');

  // -- Split buttons ----------------------------------------------------------------------------
  let exposure = $state(2);
  let frameType = $state('light');
  const EXPOSURES = [0.5, 1, 2, 5, 10, 30];
  const captureItems = $derived<MenuEntry[]>([
    { kind: 'header', label: 'Exposure' },
    ...EXPOSURES.map((s) => ({ kind: 'radio' as const, id: `exp-${s}`, label: `${s.toFixed(1)} s`, checked: s === exposure })),
    { kind: 'separator' },
    { kind: 'header', label: 'Frame' },
    ...['light', 'dark', 'flat', 'bias'].map((t) => ({
      kind: 'radio' as const,
      id: `type-${t}`,
      label: t[0].toUpperCase() + t.slice(1),
      checked: t === frameType,
      detail: t === 'dark' || t === 'bias' ? 'The wheel turns to Dark first' : undefined,
    })),
  ]);
  const afItems: MenuEntry[] = [
    { kind: 'header', label: 'Sweep' },
    { kind: 'radio', id: 'af-9', label: '±2 000 steps · 9 samples', checked: true },
    { kind: 'radio', id: 'af-13', label: '±3 000 steps · 13 samples', checked: false },
    { kind: 'separator' },
    { id: 'af-settings', label: 'Autofocus settings…', detail: 'Settings › Focus' },
  ];
  let capProgress: number | null = $state(null);
  let capTimer: ReturnType<typeof setInterval> | null = null;
  let lastAction = $state('—');
  function runCapture(): void {
    if (capTimer) return;
    const t0 = performance.now();
    capProgress = 0;
    lastAction = `Capture ${exposure.toFixed(1)} s, ${frameType}`;
    capTimer = setInterval(() => {
      const f = (performance.now() - t0) / (exposure * 1000);
      if (f >= 1) {
        capProgress = null;
        if (capTimer) clearInterval(capTimer);
        capTimer = null;
      } else capProgress = f;
    }, 50);
  }
  function chooseOption(id: string): void {
    if (id.startsWith('exp-')) exposure = Number(id.slice(4));
    if (id.startsWith('type-')) frameType = id.slice(5);
    lastAction = `Option ${id} chosen: nothing ran`;
  }

  // -- Toolbar ------------------------------------------------------------------------------------
  let liveOn = $state(false);
  let crossOn = $state(true);
  const tools = $derived<ToolDef[]>([
    { id: 'capture', group: 'acq', kind: 'split', icon: 'capture', label: 'Capture', shortcut: 'E', priority: Infinity, text: `${exposure.toFixed(1)} s`, items: captureItems },
    { id: 'live', group: 'acq', kind: 'toggle', icon: 'live', label: 'Live view', shortcut: 'V', priority: Infinity, pressed: liveOn },
    { id: 'stop', group: 'acq', kind: 'button', icon: 'stop', label: 'Stop live view', priority: Infinity, glyphTone: 'danger', disabledReason: liveOn ? null : 'Live view is off' },
    { id: 'zoom-out', group: 'zoom', kind: 'button', icon: 'zoom-out', label: 'Zoom out', shortcut: '-', priority: 3 },
    { id: 'zoom', group: 'zoom', kind: 'readout', icon: 'zoom-fit', label: 'Zoom', text: '62 %', priority: 4 },
    { id: 'zoom-in', group: 'zoom', kind: 'button', icon: 'zoom-in', label: 'Zoom in', shortcut: '+', priority: 3 },
    { id: 'zoom-fit', group: 'zoom', kind: 'button', icon: 'zoom-fit', label: 'Fit', shortcut: 'F', priority: 2 },
    { id: 'zoom-1to1', group: 'zoom', kind: 'button', icon: 'zoom-1to1', label: 'Actual size', shortcut: '1', priority: 1 },
    { id: 'stretch-auto', group: 'disp', kind: 'button', icon: 'stretch-auto', label: 'Auto stretch', shortcut: 'A', priority: 2 },
    { id: 'stretch-reset', group: 'disp', kind: 'button', icon: 'stretch-reset', label: 'Reset stretch', priority: 1 },
    { id: 'crosshair', group: 'ovl', kind: 'toggle', icon: 'crosshair', label: 'Crosshair', shortcut: 'X', priority: 1, pressed: crossOn },
    { id: 'autofocus', group: 'focus', kind: 'split', icon: 'autofocus', label: 'Autofocus', priority: 2, text: '2.0 s · 80', items: afItems, disabledReason: 'Connect the focuser first' },
    { id: 'panels', group: 'end', kind: 'toggle', icon: 'panels', label: 'Right panel', shortcut: 'P', priority: Infinity, pressed: true, layoutToggle: true, end: true },
  ]);
  function onTool(id: string): void {
    if (id === 'live') liveOn = !liveOn;
    else if (id === 'crosshair') crossOn = !crossOn;
    else if (id === 'capture') runCapture();
    lastAction = `Tool ${id}`;
  }

  // -- Hold ------------------------------------------------------------------------------------------
  let parkFails = $state(false);
  let parked = $state(false);
  async function park(): Promise<void> {
    await wait(1200);
    if (parkFails) throw new Error('The mount did not answer within 10 s');
    parked = true;
  }
  const PARK = {
    icon: 'park',
    label: 'Park',
    verb: 'park',
    confirmTitle: 'Park the mount?',
    confirmBody: 'Parking physically closes the Seestar arm and stops tracking.',
    busyLabel: 'Parking…',
    doneLabel: 'Parked',
  };

  // -- Action field ---------------------------------------------------------------------------------
  let gotoValue = $state(12_450);
  async function sendGoto(v: number): Promise<void> {
    await wait(500);
    if (v === 13_000) throw new Error('Autofocus owns the focuser.');
  }

  // -- Filter wheel ---------------------------------------------------------------------------------
  const W = (o: Partial<FilterWheelView>): FilterWheelView => ({
    state: 'idle',
    slots: ['Dark', 'IR', 'LP'],
    dark_slot: true,
    position: 1,
    slot: 'IR',
    ...o,
  });
  const wheel = new FakeWheel();
  let metaFilter = $state('IR');

  // -- Focuser ----------------------------------------------------------------------------------------
  const F = (o: Partial<FocuserView>): FocuserView => ({
    state: 'idle',
    name: 'Seestar focuser',
    position: 12_450,
    target: 12_450,
    queued: null,
    temperature_c: 12.3,
    max_step: 100_000,
    absolute: true,
    locked_by: null,
    ...o,
  });
  const samples = [10_450, 10_950, 11_450, 11_950, 12_450, 12_950, 13_450].map((p, i) => ({
    position: p,
    hfd_px: Math.round((2.1 + Math.abs(p - 12_380) / 520) * 100) / 100,
    stage: i < 7 ? 'coarse' : 'fine',
  }));
  const states: { caption: string; f: FocuserView; af?: AutofocusView; temp?: number; pending?: number; result?: string; error?: string }[] = [
    { caption: 'ready · drift since AF', f: F({}), temp: 14.1 },
    { caption: 'moving · taps queued (D9)', f: F({ state: 'moving', position: 12_820, target: 13_450, queued: 13_750 }), pending: 100 },
    {
      caption: 'autofocus running',
      f: F({ state: 'moving', position: 12_950, target: 12_950, locked_by: 'autofocus' }),
      af: { state: 'running', stage: 'coarse', step: 7, total: 14, start_position: 12_450, samples, params: { exposure_s: 2, gain: 80, half_range: 2000, num_steps: 9 } },
    },
    {
      caption: 'Stop AF: returning to the start (S23)',
      f: F({ state: 'moving', position: 12_700, target: 12_450, locked_by: 'autofocus' }),
      af: { state: 'stopping', stage: 'returning', step: 9, total: 14, start_position: 12_450, samples },
    },
    {
      caption: 'done · measured best',
      f: F({ position: 12_380, target: 12_380 }),
      af: { state: 'done', run: 3, best: { position: 12_380, hfd_px: 2.12, fitted_hfd_px: 2.08, method: 'parabola' }, samples },
      temp: 12.4,
    },
    { caption: 'rejected', f: F({}), af: { state: 'rejected', message: 'Flat HFD curve (3.1–3.3 px, span under 15 %): focus unchanged.' } },
    { caption: 'a step clamped at the travel end', f: F({ position: 100_000, target: 100_000 }), result: 'Clamped to 100 000: the end of the travel (MaxStep)' },
    { caption: 'refused', f: F({}), error: 'Position 120000 is outside 0–100000 (the focuser’s MaxStep).' },
    { caption: 'offline', f: { state: 'disconnected', position: null } },
  ];
  const fake = new FakeFocuser();
  let step = $state(100);
  const lb = $derived(focuserBadge(fake.rec, fake.af));

  // -- Jog -----------------------------------------------------------------------------------------------
  const idleJog: MountJogView = { primary: 0, secondary: 0, max_rate_deg_s: 5, deadman_s: 1 };
  const P = { alt_deg: 41.27, az_deg: 182.3 };
  const mount = new FakeMount();
  let liveRate: JogRate = $state('normal');
  let liveArmed = $state(false);
  let liveParked = $state(false);
  let socketUp = $state(true);
  function toggleSocket(): void {
    socketUp = !socketUp;
    // The server stops every axis of a client whose event socket closes (protocol.md A30).
    if (!socketUp) mount.transport.socketStop?.();
  }

  onDestroy(() => {
    if (capTimer) clearInterval(capTimer);
    fake.dispose();
    mount.dispose();
  });
</script>

<!-- ================================================================= Segmented -->
<section data-gallery="w3-segmented" id="w3-segmented">
  <h2>Segmented, wave 3 <span>manual activation for hardware (arrows move focus, Space / Enter choose), the value applied before the block slides, a busy segment</span></h2>
  <div class="row top">
    <figure><Segmented label="Stretch" options={[{ value: 'linear', label: 'Linear' }, { value: 'asinh', label: 'Asinh' }, { value: 'log', label: 'Log' }]} bind:value={display} /><figcaption>display: automatic</figcaption></figure>
    <figure><Segmented label="Filter" options={SLOTS} value="IR" activation="manual" deferred size="s" mono /><figcaption>hardware: manual, deferred</figcaption></figure>
    <figure><Segmented label="Filter" options={SLOTS} value="IR" activation="manual" deferred size="s" mono busyValue="Dark" busyReason="The wheel is turning to Dark" /><figcaption>turning to Dark</figcaption></figure>
    <figure><Segmented label="Filter" options={SLOTS} value="IR" size="s" mono disabledReason="Autofocus owns the camera" /><figcaption>unavailable + reason</figcaption></figure>
    <figure><Segmented label="Filter" options={[...SLOTS.slice(0, 2), { value: 'LP', label: 'LP', disabledReason: 'Not on this wheel' }]} value="IR" size="s" mono /><figcaption>one segment unavailable</figcaption></figure>
    <figure>
      <Segmented
        label="View"
        options={[
          { value: 'a', label: 'Fit', icon: 'zoom-fit', iconOnly: true },
          { value: 'b', label: 'Fill', icon: 'zoom-fill', iconOnly: true },
          { value: 'c', label: 'Actual size', icon: 'zoom-1to1', iconOnly: true },
        ]}
        value="a"
        size="s"
      />
      <figcaption>icon only</figcaption>
    </figure>
    <figure><Segmented label="Jog rate" options={rates} bind:value={jogRateDemo} vertical activation="manual" size="s" /><figcaption>vertical, value in °/s</figcaption></figure>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <Segmented
      label="Filter (manual)"
      options={SLOTS}
      bind:value={manual}
      activation="manual"
      size="s"
      mono
      onchange={(v: string) => (manualLog = `chose ${v}`)}
    />
    <span class="result">Arrows walk the slots without choosing; Space or Enter chooses: {manualLog}</span>
  </div>
</section>

<!-- ================================================================= Split button -->
<section data-gallery="w3-split" id="w3-split">
  <h2>SplitButton <span>the action with its options written on it; the chevron (or ↓) shows them; choosing an option never runs the action</span></h2>
  <div class="grid-states">
    <span class="hd"></span>
    {#each ['rest', 'hover main', 'hover options', 'unavailable', 'options locked', 'busy', 'progress', 'error', 'key hint'] as h (h)}
      <span class="hd">{h}</span>
    {/each}
    {#each ['ghost', 'secondary', 'primary'] as const as v (v)}
      <span class="rowhd">{v}</span>
      <SplitButton icon="capture" label="Capture" detail="2.0 s" variant={v} items={captureItems} shortcut="E" />
      <SplitButton icon="capture" label="Capture" detail="2.0 s" variant={v} items={captureItems} force="main" />
      <SplitButton icon="capture" label="Capture" detail="2.0 s" variant={v} items={captureItems} force="menu" />
      <SplitButton icon="capture" label="Capture" detail="2.0 s" variant={v} items={captureItems} disabledReason="Connect the camera first" />
      <SplitButton icon="capture" label="Capture" detail="2.0 s" variant={v} items={captureItems} optionsReason="The sequence owns the camera" disabledReason="The sequence owns the camera" />
      <SplitButton icon="capture" label="Capture" detail="2.0 s" variant={v} items={captureItems} busy />
      <SplitButton icon="capture" label="Capture" detail="2.0 s" variant={v} items={captureItems} progress={0.4} progressText="0.8 of 2.0 s" />
      <SplitButton icon="capture" label="Capture" detail="2.0 s" variant={v} items={captureItems} error="Camera did not answer within 12 s" />
      <SplitButton icon="capture" label="Capture" detail="2.0 s" variant={v} items={captureItems} shortcut="E" forceKeyHint />
    {/each}
  </div>
  <div class="row top">
    <figure><SplitButton icon="autofocus" label="Autofocus" text="Autofocus" detail="2.0 s · 80" items={afItems} /><figcaption>icon + label + options</figcaption></figure>
    <figure><SplitButton icon="capture" label="Capture" detail="2.0 s" size="s" items={captureItems} /><figcaption>s 30 px</figcaption></figure>
    <figure class="menu-fig">
      <div class="menu-static"><Menu preview open items={captureItems} label="Capture options" /></div>
      <figcaption>the options (checked = in use)</figcaption>
    </figure>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <SplitButton
      icon="capture"
      label="Capture"
      detail="{exposure.toFixed(1)} s"
      items={captureItems}
      progress={capProgress}
      progressText={capProgress === null ? undefined : `${(capProgress * exposure).toFixed(1)} of ${exposure.toFixed(1)} s`}
      onaction={runCapture}
      onselect={(item) => chooseOption(item.id)}
    />
    <span class="result">{lastAction}</span>
  </div>
</section>

<!-- ================================================================= Toolbar -->
<section data-gallery="w3-toolbar" id="w3-toolbar">
  <h2>Toolbar from data <span>priority overflow with a counted trigger; Capture, Live and Stop never leave; one tab stop, ← → move</span></h2>
  <div class="tb-stack">
    <div class="tb" style:width="1100px"><Toolbar label="Image (wide)" {tools} onact={onTool} onoption={(_, item) => chooseOption(item.id)} /></div>
    <span class="tbcap">1100 px: every tool</span>
    <div class="tb" style:width="640px"><Toolbar label="Image (medium)" {tools} onact={onTool} onoption={(_, item) => chooseOption(item.id)} /></div>
    <span class="tbcap">640 px: the lowest priorities in the overflow</span>
    <div class="tb" style:width="380px"><Toolbar label="Image (narrow)" {tools} onact={onTool} size="s" /></div>
    <span class="tbcap">380 px, density s (40 px row): run-critical tools only</span>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <span class="result">Tab enters the toolbar once; ← → walk the tools (both parts of a split), ↓ opens a split's options. Last: {lastAction}</span>
  </div>
</section>

<!-- ================================================================= Hold button -->
<section data-gallery="w3-hold" id="w3-hold">
  <h2>HoldButton <span>Park: 700 ms hold with the time ring, label unchanged; Enter / Space open the inline confirmation (owner D4)</span></h2>
  <div class="row top">
    <figure><HoldButton {...PARK} /><figcaption>rest</figcaption></figure>
    <figure><HoldButton {...PARK} pin={{ phase: 'holding', progress: 0.45 }} /><figcaption>holding 45 %</figcaption></figure>
    <figure><HoldButton {...PARK} pin={{ phase: 'released', progress: 0.3 }} /><figcaption>released early</figcaption></figure>
    <figure><HoldButton {...PARK} pin={{ phase: 'tapped' }} /><figcaption>tapped</figcaption></figure>
    <figure><HoldButton {...PARK} pin={{ phase: 'busy' }} /><figcaption>parking</figcaption></figure>
    <figure><HoldButton {...PARK} pin={{ phase: 'done' }} /><figcaption>done</figcaption></figure>
    <figure><HoldButton {...PARK} pin={{ phase: 'failed', failure: 'The mount did not answer within 10 s' }} /><figcaption>failed</figcaption></figure>
    <figure><HoldButton {...PARK} disabledReason="Connect the mount first" /><figcaption>unavailable</figcaption></figure>
  </div>
  <div class="row top">
    <figure><HoldButton {...PARK} pin={{ phase: 'confirm' }} /><figcaption>keyboard: inline confirmation, focus on Cancel</figcaption></figure>
    <figure><HoldButton {...PARK} size="m" caption={false} /><figcaption>m, no caption (toolbar)</figcaption></figure>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <HoldButton {...PARK} onconfirm={park} disabledReason={parked ? 'Already parked' : null} />
    <Control label={parkFails ? 'Next park succeeds' : 'Next park fails'} size="s" onclick={() => (parkFails = !parkFails)} />
    <Control label="Unpark (reset)" size="s" disabledReason={parked ? null : 'Not parked'} onclick={() => (parked = false)} />
    <span class="result">{parked ? 'Parked' : 'Tracking'}</span>
  </div>
</section>

<!-- ================================================================= Action field -->
<section data-gallery="w3-action" id="w3-action">
  <h2>NumberField action mode <span>the focuser's Go to: only Enter or its button send; never rewritten while edited (Qt P5); out of range refused, never clamped (H10)</span></h2>
  <div class="fields">
    <figure><NumberField label="Go to" value={12_450} integer min={0} max={100_000} range="0–100 000" action={{ icon: 'focus-move', label: 'Move to this position' }} /><figcaption>rest</figcaption></figure>
    <figure><NumberField label="Go to" value={12_450} integer min={0} max={100_000} action={{ icon: 'focus-move', label: 'Move to this position' }} pin={{ phase: 'dirty', text: '13 000' }} /><figcaption>typed, not sent</figcaption></figure>
    <figure><NumberField label="Go to" value={12_450} integer min={0} max={100_000} action={{ icon: 'focus-move', label: 'Move to this position' }} pin={{ phase: 'sending', text: '13 000' }} /><figcaption>sending</figcaption></figure>
    <figure><NumberField label="Go to" value={13_000} integer min={0} max={100_000} action={{ icon: 'focus-move', label: 'Move to this position' }} pin={{ phase: 'applied' }} appliedNote="moving" /><figcaption>applied</figcaption></figure>
    <figure><NumberField label="Go to" value={12_450} integer min={0} max={100_000} action={{ icon: 'focus-move', label: 'Move to this position' }} pin={{ phase: 'invalid', text: '120 000', message: 'Go to must be between 0 and 100 000' }} /><figcaption>invalid</figcaption></figure>
    <figure><NumberField label="Go to" value={12_450} integer min={0} max={100_000} action={{ icon: 'focus-move', label: 'Move to this position' }} pin={{ phase: 'refused', text: '13 000', message: 'Autofocus owns the focuser.' }} /><figcaption>refused</figcaption></figure>
    <figure><NumberField label="Go to" value={12_450} integer min={0} max={100_000} action={{ icon: 'focus-move', label: 'Move to this position' }} disabledReason="Autofocus owns the focuser" /><figcaption>unavailable</figcaption></figure>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <div class="w220"><NumberField label="Go to" bind:value={gotoValue} integer min={0} max={100_000} step={100} scrub range="0–100 000" appliedNote="moving" action={{ icon: 'focus-move', label: 'Move to this position' }} send={sendGoto} /></div>
    <span class="result">Arrows step without sending; blur keeps the draft; Enter or the button sends. 13 000 is refused by the fake.</span>
  </div>
</section>

<!-- ================================================================= Filter wheel -->
<section data-gallery="w3-wheel" id="w3-wheel">
  <h2>Filter wheel <span>the slot the wheel reports; a request spins until it settles; a refused move says where the wheel is (H9); no wheel = FITS metadata (Q-O5)</span></h2>
  <div class="row top">
    <figure class="w300"><FilterWheelControl wheel={W({})} /><figcaption>settled on IR</figcaption></figure>
    <figure class="w300"><FilterWheelControl wheel={W({ state: 'moving', position: null, slot: null, target: 'Dark' })} /><figcaption>turning to Dark</figcaption></figure>
    <figure class="w300"><FilterWheelControl wheel={W({ message: 'Move to LP refused by the driver.' })} /><figcaption>refused (H9)</figcaption></figure>
    <figure class="w300"><FilterWheelControl wheel={W({ state: 'error', position: null, slot: null, message: 'Still turning after 20 s: position unknown' })} /><figcaption>error, position unknown</figcaption></figure>
    <figure class="w300"><FilterWheelControl wheel={W({})} cameraOwner="autofocus" /><figcaption>autofocus owns the camera</figcaption></figure>
    <figure class="w300"><FilterWheelControl wheel={W({ state: 'disconnected', position: null, slot: null })} filter="LP" /><figcaption>no wheel: metadata only</figcaption></figure>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <div class="w300"><FilterWheelControl wheel={wheel.rec} onselect={(n) => wheel.select(n)} /></div>
    <div class="w300"><FilterWheelControl wheel={null} slots={['Dark', 'IR', 'LP']} filter={metaFilter} onselect={async (n) => { await wait(150); metaFilter = n; }} /></div>
    <span class="result">1.4 s per move; the fake driver refuses LP.</span>
  </div>
</section>

<!-- ================================================================= Focuser -->
<section data-gallery="w3-focuser" id="w3-focuser">
  <h2>Focuser <span>polled needle (never interpolated), commanded target, queued taps (D9), Go to as an action, Stop AF with its ring, Halt always (Qt P7, S23, H10)</span></h2>
  <div class="cards">
    {#each states as s (s.caption)}
      {@const b = focuserBadge(s.f, s.af)}
      <figure>
        <div class="card-w">
          <Card title="Focuser" icon="focuser">
            {#snippet status()}<StatusBadge tone={b.tone} label={b.label} />{/snippet}
            <FocuserControl
              focuser={s.f}
              autofocus={s.af ?? null}
              afTemperatureC={s.temp ?? null}
              afFrames={{ exposure_s: 2, gain: 80 }}
              haltShortcut="Escape"
              pinPending={s.pending ?? 0}
              pinResult={s.result ?? null}
              pinError={s.error ?? null}
            />
          </Card>
        </div>
        <figcaption>{s.caption}</figcaption>
      </figure>
    {/each}
  </div>
  <div class="row top">
    <figure class="w380"><FocuserGauge position={12_450} target={13_150} max={100_000} step={50} afBest={12_380} /><figcaption>gauge, step 50: one tick = one tap</figcaption></figure>
    <figure class="w380"><FocuserGauge position={52_000} target={null} max={100_000} step={1000} /><figcaption>step 1 000</figcaption></figure>
    <figure class="w380"><FocuserGauge position={null} max={100_000} step={100} /><figcaption>offline</figcaption></figure>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <div class="card-w">
      <Card title="Focuser" icon="focuser">
        {#snippet status()}<StatusBadge tone={lb.tone} label={lb.label} />{/snippet}
        <FocuserControl
          focuser={fake.rec}
          autofocus={fake.af}
          bind:step
          afFrames={{ exposure_s: 2, gain: 80 }}
          haltShortcut="Escape"
          onstep={(d) => fake.step(d)}
          onmove={(p) => fake.move(p)}
          onhalt={() => fake.halt()}
          onautofocus={() => {
            void fake.startAutofocus();
            return Promise.resolve();
          }}
          onstopautofocus={() => fake.stopAutofocus()}
        />
      </Card>
    </div>
    <span class="result">900 steps/s, polled every 0.5 s. Hold In: taps queue behind the move and go as one. Go to 120 000 is refused. Autofocus: 14 samples; Stop AF returns to the start; Halt stops where it is.</span>
  </div>
</section>

<!-- ================================================================= Jog -->
<section data-gallery="w3-jog" id="w3-jog">
  <h2>Jog pad <span>per-axis (H3), visible dead-man (renewal age), stalled key dashed, J arms the arrows, rate in °/s; Alt / Az words on alt-az, N S W E on EQ</span></h2>
  <div class="cards">
    <figure><div class="card-w pad-w"><JogPad report={idleJog} pointing={P} pin={{}} /></div><figcaption>idle · alt-az words</figcaption></figure>
    <figure><div class="card-w pad-w"><JogPad report={idleJog} pointing={P} pin={{ armed: true }} /></div><figcaption>armed: one brass edge</figcaption></figure>
    <figure>
      <div class="card-w pad-w"><JogPad report={{ ...idleJog, primary: 2, secondary: 2 }} pointing={P} pin={{ pressed: ['north', 'east'], age: 0.18 * 1000 }} /></div>
      <figcaption>diagonal: both axes, as the server reports</figcaption>
    </figure>
    <figure>
      <div class="card-w pad-w"><JogPad report={{ ...idleJog, primary: 2 }} pointing={P} pin={{ pressed: ['east'], age: 720 }} /></div>
      <figcaption>renewals late: the meter drains</figcaption>
    </figure>
    <figure>
      <div class="card-w pad-w">
        <JogPad report={idleJog} pointing={P} pin={{ stalled: ['north'], message: 'Jog stopped by the server: no renewal for 1.0 s. Release and press again.' }} />
      </div>
      <figcaption>stalled: the server stopped the held axis</figcaption>
    </figure>
    <figure><div class="card-w pad-w"><JogPad report={idleJog} pointing={P} alignment="eq" pin={{ held: ['west'] }} /></div><figcaption>EQ words · held, not yet confirmed</figcaption></figure>
    <figure><div class="card-w pad-w"><JogPad report={idleJog} pointing={P} blockedReason="Unpark the mount first" pin={{}} /></div><figcaption>refused: parked</figcaption></figure>
    <figure><div class="card-w pad-w"><JogPad report={idleJog} pointing={P} linked={false} pin={{}} /></div><figcaption>socket lost</figcaption></figure>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <div class="card-w pad-w">
      <JogPad
        report={mount.jog}
        transport={mount.transport}
        pointing={mount.pointing}
        bind:rate={liveRate}
        bind:armed={liveArmed}
        armKey
        linked={socketUp}
        blockedReason={liveParked ? 'Unpark the mount first' : null}
      />
    </div>
    <div class="col">
      <Control label={mount.linkUp ? 'Drop the link' : 'Restore the link'} size="s" onclick={() => (mount.linkUp = !mount.linkUp)} />
      <Control label={liveParked ? 'Unpark' : 'Park'} size="s" onclick={() => (liveParked = !liveParked)} />
      <Control label={socketUp ? 'Close the event socket' : 'Reopen the event socket'} size="s" onclick={toggleSocket} />
      <span class="result">Server: Az {mount.jog.primary}°/s · Alt {mount.jog.secondary}°/s{mount.jog.last_stop ? ` · last stop: ${mount.jog.last_stop.axis}, ${mount.jog.last_stop.reason}` : ''}</span>
      <span class="result">Hold two keys for a diagonal; release one. Drop the link while holding: the dead-man stops the axis within 1 s and the key turns dashed.</span>
    </div>
  </div>
</section>

<!-- ================================================================= Icons -->
<section data-gallery="w3-icons" id="w3-icons">
  <h2>New glyphs <span>watch, attention, inspector (icon-inventory.json; BRAND 6, reviewed at 16 px)</span></h2>
  <div class="row top">
    {#each ['watch', 'attention', 'inspector'] as id (id)}
      <figure>
        <span class="sizes">
          <Icon name={id} size={16} />
          <Icon name={id} size={20} />
          <Icon name={id} size={24} />
          <Icon name={id} size={48} />
        </span>
        <figcaption>{id}</figcaption>
      </figure>
    {/each}
    <span class="vsep"></span>
    <figure><Control icon="watch" label="Watch view" variant="ghost" shortcut="W" /><figcaption>toolbar</figcaption></figure>
    <figure><Control icon="watch" label="Watch view" variant="ghost" pressed /><figcaption>toggled</figcaption></figure>
    <figure><Control icon="attention" label="Attention" variant="ghost" showLabel size="s">{#snippet trailing()}2{/snippet}</Control><figcaption>with a count</figcaption></figure>
    <figure><Control icon="inspector" label="Inspector" variant="ghost" pressed layoutToggle /><figcaption>panel toggle</figcaption></figure>
  </div>
</section>

<style>
  section {
    padding: var(--space-5) 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  h2 {
    margin: 0 0 var(--space-4);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  h2 span {
    margin-left: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-regular);
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-5);
  }
  .row.top {
    align-items: flex-start;
  }
  .row + .row,
  .grid-states + .row,
  .cards + .row {
    margin-top: var(--space-5);
  }
  figure {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
    margin: 0;
  }
  figcaption,
  .hd,
  .rowhd,
  .tbcap {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .grid-states {
    display: grid;
    grid-template-columns: 80px repeat(9, max-content);
    align-items: center;
    justify-items: start;
    gap: var(--space-4) var(--space-5);
  }
  .vsep {
    align-self: stretch;
    width: 1px;
    background: var(--border-soft);
  }
  .fields {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-5);
  }
  .fields figure {
    width: 200px;
  }
  .fields figure > :global(*:first-child) {
    width: 100%;
  }
  .w220 {
    width: 220px;
  }
  .w300 {
    width: 300px;
  }
  .w380 {
    width: 380px;
  }
  .menu-static {
    position: relative;
    width: 240px;
  }
  .tb-stack {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
  }
  .tb {
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    overflow: visible;
  }
  .tbcap {
    margin-bottom: var(--space-3);
  }
  .cards {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: var(--space-5);
  }
  .card-w {
    width: 396px;
  }
  .pad-w {
    padding: var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--surface);
  }
  .sizes {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    color: var(--fg);
  }
  .col {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
    max-width: 360px;
  }
  .live {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
    margin-top: var(--space-4);
    padding: var(--space-2) var(--space-3);
    border: var(--border-w) dashed var(--border);
    border-radius: var(--radius-m);
  }
  .live-label {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .result {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>
