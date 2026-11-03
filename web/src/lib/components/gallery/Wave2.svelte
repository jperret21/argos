<!--
  Component gallery, wave 2 (development only, part of /?gallery=1): the
  components promoted from the design lab (web/lab/PROPOSAL.md 6, W2) and
  the Settings components of web/spec/README.md 7 W2, each in every state.
  Static states are pinned (`pin`, `preview`, `data-force`); the "Live" rows
  run the real behaviour against local fakes (fixtures2.ts).
  Sections are [data-gallery="w2-<name>"] for element screenshots.
-->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { keyHints } from '../../app/keyhints.svelte';
  import Control from '../Control.svelte';
  import FilePicker from '../FilePicker.svelte';
  import { FITS_FILTER, ZIP_FILTER } from '../filepicker';
  import NumberField from '../NumberField.svelte';
  import Readouts, { type ReadoutItem } from '../Readouts.svelte';
  import SettingsForm from '../SettingsForm.svelte';
  import Sheet from '../Sheet.svelte';
  import Slider from '../Slider.svelte';
  import StatusBadge from '../StatusBadge.svelte';
  import Stepper from '../Stepper.svelte';
  import SupportBundleDialog from '../SupportBundleDialog.svelte';
  import TooltipStatic from '../TooltipStatic.svelte';
  import { UndoQueue } from '../undo.svelte';
  import UndoToast from '../UndoToast.svelte';
  import UndoToasts from '../UndoToasts.svelte';
  import { EXPOSURE_LADDER } from '../values';
  import { fakeBundle, fakeList, fakePatch, HOME_DIR, initialValues, listing, META, SESSIONS } from './fixtures2';

  // -- Live controls -----------------------------------------------------------------------
  let liveToggle = $state(true);
  let liveBusy = $state(false);
  let liveError: string | null = $state(null);
  let progress = $state(0.37);
  function slowAction(): void {
    liveBusy = true;
    liveError = null;
    setTimeout(() => {
      liveBusy = false;
      liveError = 'The mount did not answer within 5 s';
    }, 1200);
  }

  // -- Number fields -----------------------------------------------------------------------
  let radius = $state(30);
  let exposure = $state(2);
  let gain = $state(80);
  let aperture = $state(7.25);
  let fullWell: number | null = $state(null);
  const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
  async function sendRadius(v: number): Promise<void> {
    await wait(600);
    if (v > 120) throw new Error('ASTAP refuses a radius above 120 ° for this database');
  }
  async function sendGain(v: number): Promise<void> {
    await wait(400);
    if (v === 0) throw new Error('Driver refused gain 0 (device_error)');
  }

  // -- Settings ------------------------------------------------------------------------------
  const values = $state(initialValues());
  const patch = fakePatch(values);
  // The pinned plate-solving form has its own values: a database folder is set
  // there, so "Database set" shows its Q-C9 reason.
  const pinnedValues = $state({ ...initialValues(), 'astrometry.database_path': `${HOME_DIR}/astap/d50` });
  const pinnedPatch = fakePatch(pinnedValues);
  const undo = new UndoQueue();
  // A frozen clock for the specimens: 2.5 s into a 6 s window, nothing expires.
  let frozenNow = 0;
  const pinnedUndo = new UndoQueue({ now: () => frozenNow, setTimeout: () => 0, clearTimeout: () => {} });
  let sheetOpen = $state(false);
  let pickerOpen = $state(false);
  let saveOpen = $state(false);
  let bundleOpen = $state(false);
  let picked = $state('—');
  let savedKey = $state('—');
  let filter = $state('');

  // Undo specimens, frozen (paused) so the screenshot shows each state.
  const u1 = pinnedUndo.push({ title: 'Removed the saved site “Backyard”', detail: '+43.93167 °, +5.71333 °, 650.0 m', undo: () => wait(400) });
  const u2 = pinnedUndo.push({ title: 'Search radius reset to the default', detail: 'Was 45 °', undo: () => Promise.reject(new Error('not writable: ~/.argos/config.json')) });
  const u3 = pinnedUndo.push({ title: 'Removed step 3 (Darks · 20 × 60 s)', undo: () => wait(400) });
  frozenNow = 2500;
  pinnedUndo.pause(u3);
  void u1;
  void pinnedUndo.undo(u2); // -> failed, with the server's words
  const uEntries = $derived(pinnedUndo.entries);

  onDestroy(() => {
    undo.dispose();
    pinnedUndo.dispose();
    keyHints.pinned = false;
  });

  const readouts: ReadoutItem[] = [
    { k: 'HFD', v: '3.42', unit: 'px', key: true },
    { k: 'Stars', v: '1 204' },
    { k: 'Sky', v: '1 812', unit: 'ADU' },
    { k: 'Peak', v: '61 204', unit: 'ADU', flag: 'near full well' },
    { k: 'Airmass', v: '1.27', note: 'alt 51.9°' },
    { k: 'Temp', v: '18.4', unit: '°C', muted: true, note: 'last frame 21:04 UTC' },
  ];

  const detents = [
    { value: 5.8, label: '2×' },
    { value: 7.25, label: '2.5×' },
    { value: 8.7, label: '3×' },
  ];
</script>

<!-- ================================================================= Control -->
<section data-gallery="w2-control" id="w2-control">
  <h2>Control <span>one button for icon, icon + label and text (IconButton and Button wrap it); every state</span></h2>
  <div class="grid-states">
    <span class="hd"></span>
    {#each ['rest', 'hover', 'pressed', 'focus', 'toggled', 'unavailable', 'busy', 'error', 'progress', 'hold ring', 'key hint'] as h (h)}
      <span class="hd">{h}</span>
    {/each}
    {#each ['ghost', 'secondary', 'primary', 'danger'] as const as v (v)}
      <span class="rowhd">{v}</span>
      <Control icon="capture" label="Capture" variant={v} shortcut="C" />
      <Control icon="capture" label="Capture" variant={v} data-force="hover" />
      <Control icon="capture" label="Capture" variant={v} data-force="hover active" />
      <Control icon="capture" label="Capture" variant={v} data-force="focus" />
      {#if v === 'ghost' || v === 'secondary'}
        <Control icon="crosshair" label="Crosshair" variant={v} pressed />
      {:else}
        <span class="na">n/a</span>
      {/if}
      <Control icon="goto" label="GoTo" variant={v} disabledReason="Unpark the mount first" />
      <Control icon="capture" label="Capture" variant={v} busy />
      <Control icon="goto" label="GoTo" variant={v} error="The mount did not answer within 5 s" />
      <Control icon="capture" label="Capture" variant={v} progress={0.37} progressText="3.7 of 10.0 s" />
      <Control icon="park" label="Park" variant={v} holdRing />
      <Control icon="capture" label="Capture" variant={v} shortcut="C" forceKeyHint />
    {/each}
  </div>
  <div class="row top">
    <figure><Control icon="connect" label="Connect all" showLabel variant="primary" /><figcaption>icon + label m</figcaption></figure>
    <figure><Control icon="park" label="Park" showLabel size="l" holdRing hint="Hold to park" /><figcaption>l 40 px, hold ring</figcaption></figure>
    <figure><Control icon="park" label="Park" showLabel size="l" progress={0.62} /><figcaption>hold 62 %</figcaption></figure>
    <figure><Control icon="live" label="Live" variant="ghost" pressed progress={0.25} /><figcaption>live + exposure ring</figcaption></figure>
    <figure><Control icon="stop" label="Stop live view" glyphTone="danger" /><figcaption>routine stop</figcaption></figure>
    <figure><Control icon="panels" label="Right panel" variant="ghost" pressed layoutToggle /><figcaption>layout toggle</figcaption></figure>
    <figure><Control icon="zoom-in" label="Zoom in" size="s" variant="ghost" /><figcaption>s 30 px</figcaption></figure>
    <span class="vsep"></span>
    <figure><Control label="Save" variant="primary" size="s" /><figcaption>text s</figcaption></figure>
    <figure><Control label="Cancel" size="s" /><figcaption>text s</figcaption></figure>
    <figure><Control label="Create bundle" variant="primary" size="s" busy /><figcaption>text busy</figcaption></figure>
    <figure><Control label="Export" variant="primary" size="s" disabledReason="set the observer code in Settings" /><figcaption>text unavailable</figcaption></figure>
    <figure><Control label="Retry" size="xs" error="Connection refused" /><figcaption>xs 24 px, error</figcaption></figure>
    <figure><Control icon="log" label="Log" showLabel variant="ghost" size="s">{#snippet trailing()}3{/snippet}</Control><figcaption>trailing count</figcaption></figure>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <Control icon="crosshair" label="Crosshair" variant="ghost" shortcut="X" pressed={liveToggle} onclick={() => (liveToggle = !liveToggle)} />
    <Control icon="goto" label="GoTo" showLabel busy={liveBusy} error={liveError} onclick={slowAction} />
    <Control icon="goto" label="Slew" showLabel disabledReason="Unpark the mount first" />
    <Control icon="capture" label="Capture" variant="ghost" shortcut="C" progress={progress} progressText="{(progress * 10).toFixed(1)} of 10.0 s" onclick={() => (progress = (progress + 0.25) % 1)} />
    <Control label={keyHints.pinned ? 'Hide key hints' : 'Pin key hints'} size="s" onclick={() => (keyHints.pinned = !keyHints.pinned)} />
    <span class="result">Hold ⌘ (Ctrl) alone for 450 ms to see the caps; press the unavailable “Slew” to see its reason at once.</span>
  </div>
</section>

<!-- ================================================================= Tooltip -->
<section data-gallery="w2-tooltip" id="w2-tooltip">
  <h2>Tooltip v2 <span>label + key caps, then one muted line: why (reason, failure) or how (gesture)</span></h2>
  <div class="row top">
    <figure><TooltipStatic text="Zoom in" shortcut="+" /><figcaption>label + key</figcaption></figure>
    <figure><TooltipStatic text="Jog" shortcut={['ArrowUp', 'ArrowDown']} /><figcaption>several keys</figcaption></figure>
    <figure><TooltipStatic text="Slew" shortcut="G" reason="Unpark the mount first" /><figcaption>unavailable: reason (no key)</figcaption></figure>
    <figure><TooltipStatic text="GoTo" error="The mount did not answer within 5 s" /><figcaption>last attempt failed</figcaption></figure>
    <figure><TooltipStatic text="Park" hint="Hold to park · Enter opens the confirmation" /><figcaption>how to use it</figcaption></figure>
    <figure><TooltipStatic text="Capture · 3.7 of 10.0 s" shortcut="C" /><figcaption>with progress</figcaption></figure>
  </div>
</section>

<!-- ================================================================= Badges -->
<section data-gallery="w2-badges" id="w2-badges">
  <h2>StatusBadge with the Chip variants <span>a shape or a word for every state; attention levels by mark and word, never a triangle</span></h2>
  <div class="row top">
    <figure><StatusBadge tone="idle" label="Off" /><figcaption>idle (hollow)</figcaption></figure>
    <figure><StatusBadge tone="ok" label="Ready" /><figcaption>ok</figcaption></figure>
    <figure><StatusBadge tone="busy" label="Connecting" /><figcaption>busy</figcaption></figure>
    <figure><StatusBadge tone="error" label="Error" /><figcaption>error</figcaption></figure>
    <figure><StatusBadge tone="active" label="Live" /><figcaption>active (brass)</figcaption></figure>
    <figure><StatusBadge tone="stale" label="Last frame · 21:04:12 UTC" /><figcaption>stale (dashed)</figcaption></figure>
    <figure><StatusBadge tone="ok" label="Exposure" value="2.0 s" /><figcaption>with value</figcaption></figure>
    <figure><StatusBadge tone="ok" label="Ready" plain /><figcaption>plain (wave 1)</figcaption></figure>
  </div>
  <div class="row top">
    <figure class="hud-frame">
      <span class="hud-row">
        <StatusBadge variant="hud" label="#0412" />
        <StatusBadge variant="hud" label="2.0 s · g80" />
        <StatusBadge variant="hud" tone="active" label="LIVE" />
        <StatusBadge variant="hud" tone="stale" label="Last frame" />
      </span>
      <figcaption>hud (over the image: opaque, mono)</figcaption>
    </figure>
    <figure>
      <span class="bar-row">
        <StatusBadge variant="bar" tone="ok" label="Mount" value="Tracking" />
        <StatusBadge variant="bar" label="Alt" value="51.9°" tone="none" />
        <StatusBadge variant="bar" tone="busy" label="Run" value="34 / 120" />
      </span>
      <figcaption>bar (status bar, no box)</figcaption>
    </figure>
  </div>
  <div class="row top">
    <figure><StatusBadge variant="alert" level="critical" label="No frame for 4m 12s" /><figcaption>critical: filled disc</figcaption></figure>
    <figure><StatusBadge variant="alert" level="attention" label="HFD rose 2.4× baseline" /><figcaption>attention: bar over a dot</figcaption></figure>
    <figure><StatusBadge variant="alert" level="info" label="Meridian in 25m" /><figcaption>info: ring</figcaption></figure>
    <figure><StatusBadge variant="alert" level="attention" label="Attention" count={3} /><figcaption>with count</figcaption></figure>
    <figure><StatusBadge variant="alert" level="critical" label="Alerts" count={1} countTone="critical" /><figcaption>critical count</figcaption></figure>
    <figure><StatusBadge label="Watch" keys="W" tone="none" /><figcaption>with key cap</figcaption></figure>
  </div>
</section>

<!-- ================================================================= NumberField -->
<section data-gallery="w2-number" id="w2-number">
  <h2>NumberField v2 <span>one commit model: not sent, sending, applied, refused, invalid (never clamped), unavailable, changed elsewhere</span></h2>
  <div class="fields">
    <NumberField label="Search radius" value={30} unit="°" min={0} max={180} integer reserve />
    <NumberField label="Search radius" value={30} unit="°" min={0} max={180} integer reserve pin={{ phase: 'dirty', text: '45' }} />
    <NumberField label="Search radius" value={30} unit="°" min={0} max={180} integer reserve pin={{ phase: 'sending', text: '45' }} />
    <NumberField label="Exposure" value={2} unit="s" min={0.001} max={600} decimals={1} reserve appliedNote="from the next frame" pin={{ phase: 'applied' }} />
    <NumberField label="Gain" value={80} min={0} max={240} integer reserve pin={{ phase: 'refused', text: '0', message: 'Driver refused gain 0 (device_error)' }} />
    <NumberField label="Latitude" value={43.93167} unit="°" min={-90} max={90} decimals={5} signed reserve pin={{ phase: 'invalid', text: '93.5', message: 'Latitude must be between −90° and +90°' }} />
    <NumberField label="Gaia depth" value={18} unit="mag" min={3} max={20} decimals={1} reserve disabledReason="Turn on Gaia DR3 identification first" />
    <NumberField label="Elevation" value={650} unit="m" min={-500} max={9000} decimals={1} reserve pin={{ phase: 'elsewhere', text: '655.0' }} />
    <NumberField label="Saturation (full well)" value={null} nullable unit="ADU" min={0} max={65535} integer group placeholder="Profile: 60 000 ADU" reserve />
  </div>
  <div class="row top">
    <figure class="compact-row">
      <span class="key">Black</span>
      <NumberField label="Black level" hideLabel value={1204} unit="ADU" min={0} max={65535} integer />
      <span class="key">Black</span>
      <NumberField label="Black level (not sent)" hideLabel value={1204} unit="ADU" min={0} max={65535} integer pin={{ phase: 'dirty', text: '1300' }} />
      <figcaption>compact (wave-1 rows: no reserved line)</figcaption>
    </figure>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <div class="live-field"><NumberField label="Search radius" bind:value={radius} unit="°" min={0} max={180} integer reserve send={sendRadius} hint="Above 120 the fake server refuses" /></div>
    <div class="live-field"><NumberField label="Exposure (ladder)" bind:value={exposure} unit="s" min={0.01} max={600} ladder={EXPOSURE_LADDER} reserve scrub send={() => wait(300)} appliedNote="from the next frame" /></div>
    <div class="live-field"><NumberField label="Saturation (nullable)" bind:value={fullWell} nullable unit="ADU" min={0} max={65535} integer group placeholder="Profile: 60 000 ADU" reserve send={() => wait(300)} /></div>
    <span class="result">radius {radius} · exposure {exposure} · full well {fullWell ?? 'profile'}</span>
  </div>
</section>

<!-- ================================================================= Stepper + Slider -->
<section data-gallery="w2-stepper" id="w2-stepper">
  <h2>Stepper and Slider <span>hold to repeat (×10 after 1.6 s), one value after release; ticks, detents, Alt fine drag, Esc to the start</span></h2>
  <div class="fields">
    <Stepper label="Gain" value={80} min={0} max={240} step={10} />
    <Stepper label="Gain" value={240} min={0} max={240} step={10} />
    <Stepper label="Gain" value={120} min={0} max={240} step={10} pin={{ held: 'plus', accelerating: true, phase: 'dirty' }} />
    <Stepper label="Gain" value={80} min={0} max={240} step={10} pin={{ phase: 'sending' }} />
    <Stepper label="Gain" value={0} min={0} max={240} step={10} pin={{ phase: 'refused', message: 'Driver refused gain 0' }} />
    <Stepper label="Frames" value={20} min={1} max={9999} limitSource="plan" disabledReason="Locked while the sequence runs" />
  </div>
  <div class="sliders">
    <Slider label="Aperture radius" value={7.25} min={4} max={12} step={0.05} minor={0.5} major={2} unit="px" {detents} detentLegend="× FWHM 2.9 px" />
    <Slider label="Aperture radius" value={7.6} min={4} max={12} step={0.05} minor={0.5} major={2} unit="px" pin={{ dragging: true, start: 6.2 }} />
    <Slider label="Aperture radius" value={7.62} min={4} max={12} step={0.05} minor={0.5} major={2} unit="px" pin={{ dragging: true, fine: true, start: 7.5, focus: true }} />
    <Slider label="Display depth" value={15} min={3} max={20} step={0.1} minor={1} major={5} unit="mag" disabledReason="Identify the field first" />
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <div class="live-field"><Stepper label="Gain" bind:value={gain} min={0} max={240} step={10} send={sendGain} /></div>
    <div class="live-slider"><Slider label="Aperture radius" bind:value={aperture} min={4} max={12} step={0.05} minor={0.5} major={2} unit="px" {detents} detentLegend="× FWHM 2.9 px" /></div>
    <span class="result">gain {gain} · aperture {aperture}</span>
  </div>
</section>

<!-- ================================================================= Readouts -->
<section data-gallery="w2-readouts" id="w2-readouts">
  <h2>Readouts <span>rail readouts at --readout; Comfortable density lifts readouts and rows (tokens, never a zoom)</span></h2>
  <div class="row top">
    <figure class="ro-w"><Readouts items={readouts} cols={4} /><figcaption>compact (17 / 17 px), 400 px rail</figcaption></figure>
    <figure class="ro-w comfortable"><Readouts items={readouts} cols={4} /><figcaption>comfortable (20 / 26 px), 400 px rail</figcaption></figure>
  </div>
</section>

<!-- ================================================================= SettingsForm -->
<section data-gallery="w2-settings" id="w2-settings">
  <h2>SettingsForm <span>generated from the config meta; one PATCH per commit; changed-from-default bar and Reset; reasons; advanced</span></h2>
  <div class="row top">
    <figure class="form-w">
      <SettingsForm
        meta={META}
        values={pinnedValues}
        patch={pinnedPatch}
        category="plate_solving"
        title="Plate solving · states pinned"
        list={fakeList}
        showAdvanced
        pins={{
          'astrometry.search_radius_deg': { phase: 'refused', text: '200', message: 'must be between 0 and 180' },
          'astrometry.astap_path': { phase: 'dirty', text: '/opt/astap/astap_cli' },
          'astrometry.database_path': { phase: 'applied' },
        }}
      />
      <figcaption>refused, not saved, saved; Database set unavailable while a folder is set (Q-C9)</figcaption>
    </figure>
    <figure class="form-w">
      <SettingsForm
        meta={META}
        {values}
        {patch}
        keys={['observer.obscode', 'site.latitude', 'site.longitude', 'site.elevation', 'hardware.profile', 'hardware.overrides.full_well_adu', 'catalog.field_stars_enabled', 'catalog.field_stars_mag_limit', 'catalog.identification_max_objects', 'ui.log_level']}
        title="Mixed keys · live"
        reasons={{ 'hardware.profile': 'Changed on Connection › Instrument, locked while equipment is connected' }}
        placeholders={{ 'hardware.overrides.full_well_adu': 'Profile: 60 000 ADU' }}
        list={fakeList}
        {undo}
        query={filter}
        onsaved={(k) => (savedKey = k)}
      />
      <figcaption>live against a fake server · last saved: {savedKey}</figcaption>
    </figure>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <input class="filter" type="text" placeholder="Filter settings" aria-label="Filter settings" bind:value={filter} />
    <Control label="Open the catalogue sheet" size="s" onclick={() => (sheetOpen = true)} />
    <span class="result">Reset a changed key to see its Undo toast (bottom right).</span>
  </div>
  <UndoToasts queue={undo} />
  <Sheet bind:open={sheetOpen} title="Catalogue settings" subtitle="Settings › Catalogues">
    <SettingsForm meta={META} {values} {patch} category="catalogues" {undo} />
    {#snippet footer()}
      <span class="result">Changes apply at once</span>
      <Control label="All settings" size="s" variant="ghost" />
    {/snippet}
  </Sheet>
</section>

<!-- ================================================================= Sheet -->
<section data-gallery="w2-sheet" id="w2-sheet">
  <h2>Sheet <span>right side, 560 px, modal; hosts the same SettingsForm (immediate apply on commit)</span></h2>
  <div class="row top">
    <figure class="sheet-frame">
      <Sheet open preview title="Plate-solving settings" subtitle="Settings › Plate solving">
        <SettingsForm meta={META} {values} {patch} category="plate_solving" />
        {#snippet status()}<span class="saved">Saved</span>{/snippet}
        {#snippet footer()}
          <span class="result">Changes apply at once</span>
          <Control label="All settings" size="s" variant="ghost" />
        {/snippet}
      </Sheet>
      <figcaption>preview (in place)</figcaption>
    </figure>
  </div>
</section>

<!-- ================================================================= FilePicker -->
<section data-gallery="w2-filepicker" id="w2-filepicker">
  <h2>FilePicker <span>in-app, over the server's read-only listing; places = the allowed roots; keyboard: ↑ ↓ Enter Backspace, type-ahead</span></h2>
  <div class="row top">
    <figure class="picker-w">
      <FilePicker
        open
        preview
        mode="open-folder"
        title="Choose the sessions folder"
        list={fakeList}
        countFits
        previewListing={listing(`${HOME_DIR}/Argos/sessions`)}
        previewSelected="20261031T200453Z_SS_Cyg"
      />
      <figcaption>open folder, FITS counts</figcaption>
    </figure>
    <figure class="picker-w">
      <FilePicker
        open
        preview
        mode="open-file"
        title="Open FITS image"
        list={fakeList}
        filters={[FITS_FILTER]}
        previewListing={listing(`${HOME_DIR}/Argos/sessions/20261031T200453Z_SS_Cyg`)}
        previewError="/Volumes/data is outside the folders ARGOS may browse (home and the ARGOS data folders)"
      />
      <figcaption>open file, a refused typed path</figcaption>
    </figure>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <Control label="Open FITS image…" size="s" onclick={() => (pickerOpen = true)} />
    <Control label="Save support bundle as…" size="s" onclick={() => (saveOpen = true)} />
    <span class="result">chosen: {picked}</span>
  </div>
  <FilePicker bind:open={pickerOpen} mode="open-file" title="Open FITS image" start="{HOME_DIR}/Argos/sessions" list={fakeList} filters={[FITS_FILTER]} countFits onchoose={(p) => (picked = p)} />
  <FilePicker
    bind:open={saveOpen}
    mode="save-file"
    title="Save the support bundle"
    start="{HOME_DIR}/Desktop"
    defaultName="argos-support-0.4.2-20261101T213405Z.zip"
    list={fakeList}
    filters={[ZIP_FILTER]}
    onchoose={(p) => (picked = p)}
  />
</section>

<!-- ================================================================= Undo -->
<section data-gallery="w2-undo" id="w2-undo">
  <h2>Undo toast <span>the change is applied; Undo for 6 s (a neutral time ring), paused while pointed at or focused</span></h2>
  <div class="toasts-col">
    {#each uEntries as entry (entry.id)}
      <UndoToast queue={pinnedUndo} {entry} preview />
    {/each}
  </div>
</section>

<!-- ================================================================= Support bundle -->
<section data-gallery="w2-bundle" id="w2-bundle">
  <h2>SupportBundleDialog <span>what the ZIP holds, session metadata off by default (Q-G17), nothing uploaded</span></h2>
  <div class="row top">
    <figure class="dlg-w">
      <SupportBundleDialog open preview version="0.5.0" folder="{HOME_DIR}/Desktop" sessions={SESSIONS} create={fakeBundle} list={fakeList} />
      <figcaption>default: no session</figcaption>
    </figure>
    <figure class="dlg-w">
      <SupportBundleDialog
        open
        preview
        version="0.5.0"
        folder="/Volumes/locked"
        sessions={SESSIONS}
        create={fakeBundle}
        pin={{ includeSession: true, sessionDir: SESSIONS[0].path, error: "Permission denied: '/Volumes/locked'" }}
      />
      <figcaption>session included, failure inline</figcaption>
    </figure>
  </div>
  <div class="live">
    <span class="live-label">Live</span>
    <Control icon="support-bundle" label="Create support bundle…" showLabel size="s" onclick={() => (bundleOpen = true)} />
  </div>
  <SupportBundleDialog
    bind:open={bundleOpen}
    version="0.5.0"
    folder="{HOME_DIR}/Desktop"
    sessions={SESSIONS}
    create={fakeBundle}
    list={fakeList}
    oncreated={(r) => (picked = `${r.path} (${r.files.length} files)`)}
  />
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
  .fields + .row,
  .fields + .sliders {
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
  .rowhd {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .grid-states {
    display: grid;
    grid-template-columns: 80px repeat(11, max-content);
    align-items: center;
    justify-items: start;
    gap: var(--space-4) var(--space-5);
  }
  .na {
    color: var(--fg-disabled);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
  }
  .vsep {
    align-self: stretch;
    width: 1px;
    background: var(--border-soft);
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
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .fields {
    display: grid;
    grid-template-columns: repeat(5, 200px);
    gap: var(--space-4) var(--space-5);
    align-items: start;
  }
  .sliders {
    display: grid;
    grid-template-columns: repeat(2, 340px);
    gap: var(--space-4) var(--space-6);
  }
  .live-field {
    width: 220px;
  }
  .live-slider {
    width: 340px;
  }
  .compact-row {
    display: grid;
    grid-template-columns: auto 130px auto 130px;
    align-items: start;
    gap: var(--space-2) var(--space-3);
  }
  .compact-row figcaption {
    grid-column: 1 / -1;
  }
  .key {
    padding-top: 6px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .hud-frame .hud-row {
    display: inline-flex;
    gap: var(--space-2);
    padding: var(--space-3);
    border-radius: var(--radius-s);
    background: var(--viewer-bg);
  }
  .bar-row {
    display: inline-flex;
    gap: var(--space-4);
    padding: 4px var(--space-3);
    border-top: var(--border-w) solid var(--border);
    background: var(--bg-2);
  }
  .ro-w {
    width: 400px;
    padding: var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--surface);
  }
  /* The Comfortable token set (tokens.css :root[data-density='comfortable']), scoped to the specimen. */
  .comfortable {
    --readout: 20px;
    --readout-key: 26px;
    --row-h: 28px;
  }
  .form-w {
    width: 640px;
  }
  .form-w > :global(.settings-form) {
    width: 100%;
  }
  .sheet-frame {
    width: 560px;
    height: 640px;
  }
  .sheet-frame > :global(.sheet) {
    border: var(--border-w) solid var(--border);
  }
  .saved {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .picker-w {
    width: 640px;
  }
  .picker-w :global(.dialog) {
    width: 100%;
  }
  .dlg-w {
    width: 560px;
  }
  .dlg-w :global(.dialog) {
    width: 100%;
  }
  .toasts-col {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .filter {
    width: 220px;
    height: var(--input-h);
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font: inherit;
    font-size: var(--text-s);
  }
  .filter::placeholder {
    color: var(--text-muted);
    opacity: 1;
  }
</style>
