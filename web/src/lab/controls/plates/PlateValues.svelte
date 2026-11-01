<!--
  Plate 03: value controls. Live controls on the left of each panel, the
  same control pinned in each state beside it.
-->
<script lang="ts">
  import type { ComponentProps } from 'svelte';
  import { detectMac } from '../../../lib/app/shortcuts';
  import Panel from '../components/Panel.svelte';
  import ScrubField from '../components/ScrubField.svelte';
  import Seg from '../components/Seg.svelte';
  import Slider from '../components/Slider.svelte';
  import Stepper from '../components/Stepper.svelte';
  import { fixed } from '../format';
  import type { Hardware, SegOption } from '../types';
  import { EXPOSURE_LADDER } from '../values';

  let { hw }: { hw: Hardware } = $props();

  const wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

  // -- Live values ---------------------------------------------------------------------
  let exposure = $state(2);
  let offset = $state(20);
  let gain = $state(80);
  let frames = $state(120);
  let depth = $state(14.5);
  let aperture = $state(9.4);
  let frameType = $state<'light' | 'dark' | 'flat' | 'bias'>('light');
  let filter = $state<'ir' | 'lp' | 'dark'>('ir');
  let filterMoving: 'ir' | 'lp' | 'dark' | null = $state(null);
  let rotation = $state<'auto' | '0' | '90' | '180' | '270'>('auto');
  let rate = $state<'sidereal' | 'lunar' | 'solar'>('sidereal');

  async function sendExposure(v: number): Promise<void> {
    await wait(450);
    if (v > 300) throw new Error('Camera refused: live view is limited to 300 s');
    hw.exposure.seconds = v;
  }

  async function sendQuick(): Promise<void> {
    await wait(350);
  }

  const FRAME: SegOption<'light' | 'dark' | 'flat' | 'bias'>[] = [
    { value: 'light', label: 'Light' },
    { value: 'dark', label: 'Dark' },
    { value: 'flat', label: 'Flat' },
    { value: 'bias', label: 'Bias' },
  ];
  const FILTER: SegOption<'ir' | 'lp' | 'dark'>[] = [
    { value: 'ir', label: 'IR' },
    { value: 'lp', label: 'LP' },
    { value: 'dark', label: 'Dark' },
  ];
  const ROTATION: SegOption<'auto' | '0' | '90' | '180' | '270'>[] = [
    { value: 'auto', label: 'Auto' },
    { value: '0', label: '0°' },
    { value: '90', label: '90°' },
    { value: '180', label: '180°' },
    { value: '270', label: '270°' },
  ];
  const RATE: SegOption<'sidereal' | 'lunar' | 'solar'>[] = [
    { value: 'sidereal', label: 'Sidereal' },
    { value: 'lunar', label: 'Lunar' },
    { value: 'solar', label: 'Solar', disabledReason: 'Not offered by this driver' },
  ];

  function moveWheel(v: 'ir' | 'lp' | 'dark'): void {
    const target = v;
    filter = target;
    filterMoving = target;
    setTimeout(() => (filterMoving = null), 1800);
  }

  type Pin = NonNullable<ComponentProps<typeof ScrubField>['pin']>;
  const PINS: { title: string; pin: Pin | null; reason?: string; value?: number }[] = [
    { title: 'Rest', pin: null },
    { title: 'Scrubbing · tape', pin: { phase: 'scrub', text: '5.0' }, value: 5 },
    { title: 'Not sent (dashed)', pin: { phase: 'dirty', text: '5.0' } },
    { title: 'Sending', pin: { phase: 'sending', text: '5.0' } },
    { title: 'Applied', pin: { phase: 'applied' } },
    { title: 'Refused by the device', pin: { phase: 'refused', text: '480', message: 'Live view is limited to 300 s' } },
    { title: 'Invalid, never clamped', pin: { phase: 'invalid', text: '900', message: 'Range 0.01–600 s' } },
    { title: 'Unavailable', pin: null, reason: 'The sequence owns the camera' },
  ];

  const mac = detectMac();
  const SHIFT = mac ? '⇧' : 'Shift';
  const ALT = mac ? '⌥' : 'Alt';
</script>

<div class="cols">
  <div class="col">
    <Panel
      code="C.1"
      title="Numeric field with scrubbing"
      note="Drag the label (or across the field before clicking in) to scrub; a click edits. One value is sent on release, Enter or blur, never per pixel or keystroke. The dial tape shows the neighbours; the number never animates."
      shot="scrub"
    >
      <div class="live" data-shot="scrub-live">
        <ScrubField
          label="Exposure"
          bind:value={exposure}
          unit="s"
          min={0.01}
          max={600}
          step={0.01}
          ladder={EXPOSURE_LADDER}
          range="0.01–600 s · driver"
          appliedNote="from the next frame"
          oncommit={sendExposure}
        />
        <ScrubField label="Offset" bind:value={offset} min={0} max={100} step={1} integer range="0–100 · driver" oncommit={sendQuick} />
      </div>
      <div class="pins">
        {#each PINS as p (p.title)}
          <div class="pin">
            <span class="lab-eyebrow">{p.title}</span>
            <ScrubField
              label="Exposure"
              value={p.value ?? 2}
              unit="s"
              min={0.01}
              max={600}
              step={0.01}
              ladder={EXPOSURE_LADDER}
              range="0.01–600 s · driver"
              appliedNote="from the next frame"
              pin={p.pin}
              disabledReason={p.reason ?? null}
            />
          </div>
        {/each}
      </div>
    </Panel>
  </div>

  <div class="col">
    <Panel
      code="C.2"
      title="Slider with ticks, detents and fine adjustment"
      note="The thumb is under the pointer, no easing. Shift snaps to the ticks; Alt goes FINE (1/10 of the pointer, from where it began). A mark holds the start value and Esc returns to it. The readout is a field."
      shot="sliders"
    >
      <div class="sliders">
        <div data-shot="slider-live">
          <Slider
            label="Aperture radius"
            bind:value={aperture}
            min={2}
            max={30}
            step={0.1}
            minor={1}
            major={5}
            unit="px"
            detents={[
              { value: 5.8, label: '2×' },
              { value: 8.7, label: '3×' },
            ]}
            detentLegend="× FWHM 2.9 px"
          />
        </div>
        <Slider label="Catalogue depth" bind:value={depth} min={8} max={18} step={0.1} minor={0.5} major={2} unit="mag" readoutWidth={100} format={(v) => `≤ ${fixed(v, 1)}`} />
        <div class="pinned">
          <span class="lab-eyebrow">Pinned · fine drag from 12.0</span>
          <Slider label="Aperture radius" value={12.6} min={2} max={30} step={0.1} minor={1} major={5} unit="px" pin={{ dragging: true, fine: true, start: 12 }} />
        </div>
        <div class="pinned">
          <span class="lab-eyebrow">Pinned · keyboard focus / unavailable</span>
          <Slider label="Catalogue depth" value={16} min={8} max={18} step={0.1} minor={0.5} major={2} unit="mag" pin={{ focus: true }} />
          <Slider label="Catalogue depth" value={16} min={8} max={18} step={0.1} minor={0.5} major={2} unit="mag" disabledReason="Identify the field first" />
        </div>
      </div>
    </Panel>
  </div>

  <div class="col">
    <Panel code="C.3" title="Stepper" note="Hold − or + to repeat: 400 ms, then 12.5 steps/s, ×10 after 1.6 s. One value is sent 400 ms after release. At a limit the button says which." shot="steppers">
      <div class="steppers">
        <Stepper label="Gain" bind:value={gain} min={0} max={600} oncommit={sendQuick} />
        <Stepper label="Frames" bind:value={frames} min={1} max={999} limitSource="plan" />
        <Stepper label="Gain · holding +, ×10" value={140} min={0} max={600} pin={{ accelerating: true, pressed: 'plus' }} />
        <Stepper label="Gain · at the limit" value={600} min={0} max={600} />
      </div>
    </Panel>

    <Panel code="C.4" title="Segmented choices" note="The raised block slides to the choice (120 ms, after the value is applied). Hardware choices use manual activation: arrows move focus, Space chooses." shot="segmented">
      <div class="segs">
        <div class="sg"><span class="k">Frame</span><Seg label="Frame type" options={FRAME} bind:value={frameType} /></div>
        <div class="sg">
          <span class="k">Filter</span>
          <Seg label="Filter" options={FILTER} value={filter} activation="manual" busyValue={filterMoving} busyReason="The wheel is turning" onchange={moveWheel} />
          <span class="aside">{filterMoving ? 'Turning…' : 'manual'}</span>
        </div>
        <div class="sg"><span class="k">Rotation</span><Seg label="Display rotation" options={ROTATION} bind:value={rotation} size="s" mono /></div>
        <div class="sg"><span class="k">Rate</span><Seg label="Tracking rate" options={RATE} bind:value={rate} size="s" activation="manual" /></div>
      </div>
    </Panel>

    <Panel code="C.5" title="One convention" note="Every value control, the same keys." shot="convention">
      <table class="conv">
        <tbody>
          <tr><td><kbd class="cap">↑</kbd><kbd class="cap">↓</kbd> · drag</td><td>one step</td></tr>
          <tr><td><kbd class="cap">{SHIFT}</kbd> + step</td><td>×10, or snap to ticks</td></tr>
          <tr><td><kbd class="cap">{ALT}</kbd> + step</td><td>fine ×0.1</td></tr>
          <tr><td>wheel</td><td>only while focused</td></tr>
          <tr><td><kbd class="cap">↵</kbd> · release · blur</td><td>sends one value</td></tr>
          <tr><td><kbd class="cap">Esc</kbd></td><td>back to the device value</td></tr>
        </tbody>
      </table>
    </Panel>
  </div>
</div>

<style>
  .cols {
    display: grid;
    grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr) minmax(0, 0.95fr);
    gap: var(--space-4);
    align-items: start;
  }
  .col {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-width: 0;
  }
  .live {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-4);
    padding-bottom: var(--space-3);
    margin-bottom: var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .pins {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3) var(--space-4);
  }
  .pin {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .sliders {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .pinned {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding-top: var(--space-3);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .steppers {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-2) var(--space-4);
  }
  .segs {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .sg {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .k {
    width: 56px;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .aside {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .conv {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-xs);
  }
  .conv td {
    height: 24px;
    padding: 0;
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg);
  }
  .conv tr:last-child td {
    border-bottom: none;
  }
  .conv td:last-child {
    color: var(--text-muted);
    text-align: right;
  }
  .conv :global(kbd.cap) {
    margin-right: 3px;
  }
</style>
