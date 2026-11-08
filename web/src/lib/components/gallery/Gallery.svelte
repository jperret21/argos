<!--
  Component gallery (development only: /?gallery=1, stripped from the
  production build by main.ts). Every shared component of wave 1 in every
  state, in the current theme, for design review and screenshots. Static
  states are drawn with `preview` (in place, no layer); the "live" buttons
  open the real overlays (focus trap, Escape, outside click, focus return).

  ?theme=observatory|charcoal|night-red selects the theme; each section is
  [data-gallery="<name>"] for element screenshots.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { KEYMAP } from '../../app/keymap';
  import { LogFilter, LogStore } from '../../app/log.svelte';
  import { SectionLayout } from '../../app/layout.svelte';
  import { ShortcutRegistry } from '../../app/shortcuts';
  import { type StartupStage } from '../../app/startup';
  import { isTheme, saveTheme, THEME_LABELS, THEMES, type Theme } from '../../app/theme';
  import FieldGallery from '../../imaging/field/gallery/FieldGallery.svelte';
  import WorkspaceGallery from '../../imaging/modes/gallery/WorkspaceGallery.svelte';
  import ToolsGallery from '../../viewer/tools/gallery/ToolsGallery.svelte';
  import RailFooter from '../../shell/RailFooter.svelte';
  import ShortcutSheet from '../../shell/ShortcutSheet.svelte';
  import StartupScreen from '../../shell/StartupScreen.svelte';
  import Button from '../Button.svelte';
  import Checkbox from '../Checkbox.svelte';
  import ConfirmDialog from '../ConfirmDialog.svelte';
  import Dialog from '../Dialog.svelte';
  import Drawer from '../Drawer.svelte';
  import Icon from '../Icon.svelte';
  import IconButton from '../IconButton.svelte';
  import JobProgress from '../JobProgress.svelte';
  import LogControls from '../LogControls.svelte';
  import LogPanel from '../LogPanel.svelte';
  import LogView from '../LogView.svelte';
  import Menu from '../Menu.svelte';
  import type { MenuEntry } from '../menu';
  import PanelsPopover, { type PanelGroup } from '../PanelsPopover.svelte';
  import Popover from '../Popover.svelte';
  import SearchField from '../SearchField.svelte';
  import Segmented from '../Segmented.svelte';
  import Select from '../Select.svelte';
  import StatusBadge from '../StatusBadge.svelte';
  import Table from '../Table.svelte';
  import type { Column } from '../table';
  import TextField from '../TextField.svelte';
  import { DEVICES, type DeviceRow, NOW, SAMPLE_JOBS, sampleLogLines, VARIABLES, type VariableRow } from './fixtures';
  import Wave2 from './Wave2.svelte';
  import Wave3 from './Wave3.svelte';

  // -- Theme --------------------------------------------------------------------------
  const params = new URLSearchParams(location.search);
  const fromUrl = params.get('theme');
  let theme: Theme = $state(
    isTheme(fromUrl) ? fromUrl : isTheme(document.documentElement.dataset.theme) ? (document.documentElement.dataset.theme as Theme) : 'observatory',
  );
  $effect(() => {
    document.documentElement.dataset.theme = theme;
  });

  onMount(() => {
    document.documentElement.classList.add('gallery-mode');
    return () => document.documentElement.classList.remove('gallery-mode');
  });

  // -- Shared fixtures ------------------------------------------------------------------
  const registry = new ShortcutRegistry(KEYMAP, { desktop: false });

  const log = new LogStore();
  for (const line of sampleLogLines()) log.ingest(line);
  const logFilter = new LogFilter();
  const pausedLog = new LogStore();
  for (const line of sampleLogLines(40)) pausedLog.ingest(line);
  const pausedFilter = new LogFilter();
  const emptyLog = new LogStore();
  const emptyFilter = new LogFilter();
  const debugFilter = new LogFilter({ level: 'all' });
  debugFilter.debug = true;
  debugFilter.query = 'mount';

  let liveCount = $state(0);
  function addLiveLine(level: 'info' | 'warning' | 'error' | 'ok' | 'cmd'): void {
    liveCount++;
    log.push(level, `Gallery line ${liveCount} (${level})`, { topic: 'connection', source: 'web' });
  }

  // -- Dialogs ------------------------------------------------------------------------------
  let dlgOpen = $state(false);
  let confirmOpen = $state(false);
  let dangerOpen = $state(false);
  let sheetOpen = $state(false);
  let dlgName = $state('Home observatory');
  let lastAction = $state('—');

  function slowConfirm(): Promise<void> {
    return new Promise((resolve, reject) =>
      setTimeout(() => (Math.random() < 2 ? reject(new Error('Device busy: an exposure is running (409 busy)')) : resolve()), 800),
    );
  }

  // -- Popover / menus ------------------------------------------------------------------------------
  let popOpen = $state(false);
  let popAnchor: HTMLElement | undefined = $state();
  let menuOpen = $state(false);
  let menuAnchor: HTMLElement | undefined = $state();
  let ctxOpen = $state(false);
  let ctxPoint: { x: number; y: number } | null = $state(null);
  let crosshair = $state(true);
  let palette = $state('neutral');

  const menuItems = $derived<MenuEntry[]>([
    { kind: 'header', label: 'View' },
    { id: 'fit', label: 'Fit the whole frame', icon: 'zoom-fit', shortcut: 'F' },
    { id: 'fill', label: 'Fill the viewer (crops)', icon: 'zoom-fill', shortcut: 'Shift+F' },
    { id: 'one', label: 'Actual pixels (1:1)', icon: 'zoom-1to1', shortcut: '1' },
    { kind: 'separator', id: 's1' },
    { id: 'cross', kind: 'checkbox', label: 'Crosshair', checked: crosshair, shortcut: 'X' },
    { kind: 'header', label: 'Palette' },
    { id: 'neutral', kind: 'radio', label: 'Neutral', checked: palette === 'neutral' },
    {
      id: 'negative',
      kind: 'radio',
      label: 'Negative',
      checked: palette === 'negative',
      disabledReason: theme === 'night-red' ? 'false colour is off in Night Red' : null,
    },
    { kind: 'separator', id: 's2' },
    { id: 'save', label: 'Save view as PNG…', icon: 'save', disabledReason: 'no frame on screen yet' },
    { id: 'remove', label: 'Remove comparison', icon: 'remove', danger: true },
  ]);

  function onMenu(item: { id: string }): void {
    lastAction = item.id;
    if (item.id === 'cross') crosshair = !crosshair;
    if (item.id === 'neutral' || item.id === 'negative') palette = item.id;
  }

  // -- Select -----------------------------------------------------------------------------------------
  type Profile = 's30pro' | 's30' | 's50';
  const PROFILES = [
    { value: 's30pro' as const, label: 'ZWO Seestar S30 Pro', detail: '30 mm · f/5.3 · IMX585 · 3.74″/px · validated' },
    { value: 's30' as const, label: 'ZWO Seestar S30', detail: '30 mm · f/5 · IMX662 · 4.85″/px · not validated' },
    { value: 's50' as const, label: 'ZWO Seestar S50', detail: '50 mm · f/5 · IMX462 · 2.39″/px · not validated' },
  ];
  let profile: Profile | null = $state('s30pro');
  type Frame = 'light' | 'dark' | 'bias' | 'flat';
  const FRAMES = [
    { value: 'light' as const, label: 'Light' },
    { value: 'dark' as const, label: 'Dark', disabledReason: 'needs a filter wheel with an opaque slot' },
    { value: 'bias' as const, label: 'Bias' },
    { value: 'flat' as const, label: 'Flat' },
  ];
  let frame: Frame | null = $state(null);

  // -- Tables -------------------------------------------------------------------------------------------
  const STATE_TONE = { connected: 'ok', error: 'error', disconnected: 'idle', connecting: 'busy', busy: 'busy' } as const;
  const STATE_WORD = { connected: 'Ready', error: 'Error', disconnected: 'Off', connecting: 'Connecting', busy: 'Busy' } as const;
  const deviceColumns: Column<DeviceRow>[] = [
    { id: 'name', label: 'Device', value: (d) => d.name, width: '150px' },
    { id: 'state', label: 'State', value: (d) => STATE_WORD[d.state], width: '120px' },
    { id: 'detail', label: 'Detail', value: (d) => d.detail, sortable: false, wrap: true },
    { id: 'action', label: 'Action', hideLabel: true, sortable: false, width: '140px' },
  ];
  const varColumns: Column<VariableRow>[] = [
    { id: 'name', label: 'Name', value: (v) => v.name },
    { id: 'type', label: 'Type', value: (v) => v.type },
    { id: 'mag', label: 'Mag', numeric: true, value: (v) => v.mag, format: (v) => (v.mag === null ? '—' : v.mag.toFixed(3)), title: 'Brightest magnitude (VSX)' },
    {
      id: 'period',
      label: 'Period (d)',
      numeric: true,
      value: (v) => v.period,
      format: (v) => (v.period === null ? '—' : v.period.toFixed(4)),
    },
    { id: 'sep', label: 'Sep. (′)', numeric: true, value: (v) => v.sep, format: (v) => v.sep.toFixed(1) },
  ];
  let selectedDevice: string | null = $state('camera');
  let selectedVar: string | null = $state('V0402 Cyg');
  let varSort = $state<{ column: string; dir: 'asc' | 'desc' } | null>({ column: 'mag', dir: 'asc' });
  let activated = $state('—');

  // -- Drawer --------------------------------------------------------------------------------------------
  let drawerTab = $state('log');
  let drawerHeight = $state(260);
  const drawerTabs = $derived([
    { id: 'curve', label: 'Light curve', icon: 'light-curve' },
    { id: 'conditions', label: 'Conditions', icon: 'session-metrics' },
    { id: 'log', label: 'Log', icon: 'log', badge: drawerTab === 'log' ? null : log.unseenProblems || null },
  ]);

  // -- Panels -----------------------------------------------------------------------------------------------
  const layout = new SectionLayout(
    'gallery',
    {
      panels: { camera: true, display: true, statistics: false, photometry: true, mount: true, focuser: true, curve: true, conditions: false, log: true },
      drawer: { tab: 'log' },
    },
    null,
  );
  const panelGroups: PanelGroup[] = [
    {
      title: 'Right rail',
      panels: [
        { id: 'camera', label: 'Camera' },
        { id: 'display', label: 'Display' },
        { id: 'statistics', label: 'Statistics' },
        { id: 'photometry', label: 'Photometry' },
        { id: 'mount', label: 'Mount' },
        { id: 'focuser', label: 'Focuser', disabledReason: 'no focuser connected' },
      ],
    },
    {
      title: 'Bottom drawer',
      panels: [
        { id: 'curve', label: 'Light curve' },
        { id: 'conditions', label: 'Conditions' },
        { id: 'log', label: 'Log', disabledReason: 'the Log tab is in every drawer' },
      ],
    },
  ];
  let resetCount = $state(0);

  // -- Startup ------------------------------------------------------------------------------------------------
  const browserStages: StartupStage[] = [{ id: 'link', label: 'Connecting to the ARGOS server…', state: 'active' }];
  const desktopStages: StartupStage[] = [
    { id: 'server', label: 'ARGOS server started', state: 'done' },
    { id: 'link', label: 'Connecting to the ARGOS server…', state: 'active' },
  ];
  const failure = {
    title: 'ARGOS could not start',
    message: 'The ARGOS server stopped during start-up.',
    detail: "Traceback (most recent call last):\n  File \"argos/server/__main__.py\", line 12, in <module>\nModuleNotFoundError: No module named 'astropy'",
    logPath: '~/Library/Logs/Argos/argos.log',
  };

  let themeChoice: Theme = $state('observatory');
  let checkA = $state(true);
  let checkB = $state(false);
  let search = $state('Mauna');
  let fieldText = $state('192.168.1.42');
  let seg = $state('all');
</script>

<div class="gallery">
  <header class="top">
    <span class="mark"><Icon name="about" size="l" /></span>
    <h1>ARGOS · component gallery</h1>
    <span class="note">development only · shared components of waves 1 to 3 · reference 1440 × 900</span>
    <span class="spacer"></span>
    <Segmented
      label="Theme"
      options={THEMES.map((t) => ({ value: t, label: THEME_LABELS[t] }))}
      bind:value={theme}
      onchange={(t: Theme) => saveTheme(t)}
    />
  </header>

  <!-- Wave 4, field and overlays: overlay, star card, Catalogue layers popover, Field band, Inspector, virtual table. -->
  <FieldGallery />

  <!-- Wave 4, viewer tools and palettes: palettes, View options, Statistics card, context menu, compass. -->
  <ToolsGallery />

  <!-- Wave 3: the controls and instruments of Observe: acquisition. -->
  <Wave3 />
  <!-- Wave 3, workspace / viewer / charts: task modes, HUD, histogram, exposure check, V-curve, conditions. -->
  <WorkspaceGallery />

  <!-- Wave 2: the components promoted from the design lab and the Settings components. -->
  <Wave2 />

  <!-- ===================================================================== Buttons -->
  <section data-gallery="buttons" id="buttons">
    <h2>Buttons <span>Button (text only, BRAND 7 row 3) and IconButton: since wave 2 thin wrappers over Control</span></h2>
    <div class="row">
      <figure><Button label="Park" variant="primary" /><figcaption>primary</figcaption></figure>
      <figure><Button label="Cancel" /><figcaption>secondary</figcaption></figure>
      <figure><Button label="Clear cache" variant="danger" /><figcaption>danger</figcaption></figure>
      <figure><Button label="Restore defaults" variant="ghost" /><figcaption>ghost</figcaption></figure>
      <figure><Button label="Create bundle" variant="primary" busy /><figcaption>busy</figcaption></figure>
      <figure><Button label="Export" variant="primary" disabledReason="set the observer code in Settings" /><figcaption>disabled + reason</figcaption></figure>
      <figure><Button label="Retry" size="s" /><figcaption>small</figcaption></figure>
      <span class="vsep"></span>
      <figure><IconButton icon="connect" label="Connect all" showLabel variant="primary" /><figcaption>icon + label</figcaption></figure>
      <figure><IconButton icon="disconnect" label="Disconnect all" showLabel variant="danger" /><figcaption>danger</figcaption></figure>
      <figure><IconButton icon="crosshair" label="Crosshair" shortcut="X" variant="ghost" pressed={true} /><figcaption>toggled</figcaption></figure>
      <figure><IconButton icon="arrange" label="Panels" variant="ghost" /><figcaption>ghost</figcaption></figure>
      <figure><IconButton icon="discover" label="Discover" showLabel busy /><figcaption>busy</figcaption></figure>
    </div>
  </section>

  <!-- ===================================================================== Dialogs -->
  <section data-gallery="dialogs" id="dialogs">
    <h2>Dialog and ConfirmDialog <span>modal, focus trapped, Esc = Cancel, focus returns to the opener</span></h2>
    <div class="row top">
      <figure class="wide">
        <Dialog open preview title="Save the preset" subtitle="Plan · 4 steps · 1h 12m">
          <TextField label="Name" bind:value={dlgName} hint="Saved in ~/Argos/sequences" />
          {#snippet footer()}
            <Button label="Cancel" /><Button label="Save" variant="primary" />
          {/snippet}
        </Dialog>
        <figcaption>form dialog (560)</figcaption>
      </figure>
      <figure class="wide">
        <ConfirmDialog
          open
          preview
          title="Park the mount?"
          message="Parking physically closes the Seestar arm and stops tracking."
          confirmLabel="Park"
          onconfirm={() => {}}
        />
        <figcaption>confirmation (480), focus on Cancel</figcaption>
      </figure>
    </div>
    <div class="row top">
      <figure class="wide">
        <ConfirmDialog
          open
          preview
          destructive
          title="Clear the Gaia cache?"
          message="Deletes 214 files (38.2 MB) in ~/.argos/cache/gaia. Catalogue stars are downloaded again on the next solve."
          confirmLabel="Clear cache"
          onconfirm={() => {}}
        />
        <figcaption>destructive (alertdialog)</figcaption>
      </figure>
      <figure class="wide">
        <ConfirmDialog
          open
          preview
          destructive
          busy
          title="Disconnect all devices?"
          message="A sequence is running: SS Cyg, 34 of 120 frames. Disconnecting stops it."
          confirmLabel="Disconnect"
          onconfirm={() => {}}
        />
        <figcaption>busy (cannot be dismissed)</figcaption>
      </figure>
      <figure class="wide">
        <ConfirmDialog
          open
          preview
          title="Stop the sequence?"
          message="Frames already saved stay in the session folder; the frame being exposed is discarded."
          confirmLabel="Stop"
          cancelLabel="Keep running"
          error="Device busy: an exposure is running (409 busy)"
          onconfirm={() => {}}
        />
        <figcaption>error after confirm</figcaption>
      </figure>
    </div>
    <div class="live">
      <span class="live-label">Live</span>
      <Button label="Open dialog" data-testid="open-dialog" onclick={() => (dlgOpen = true)} />
      <Button label="Open confirmation" data-testid="open-confirm" onclick={() => (confirmOpen = true)} />
      <Button label="Open destructive (fails)" data-testid="open-danger" onclick={() => (dangerOpen = true)} />
      <span class="result" data-testid="dialog-result">last: {lastAction}</span>
    </div>
    <Dialog bind:open={dlgOpen} title="Save the preset" subtitle="Plan · 4 steps · 1h 12m" onclose={(r) => (lastAction = `dialog closed (${r})`)}>
      <TextField label="Name" bind:value={dlgName} hint="Saved in ~/Argos/sequences" />
      <div style="height: 8px"></div>
      <Select label="Telescope" options={PROFILES} bind:value={profile} />
      {#snippet footer()}
        <Button label="Cancel" data-testid="dlg-cancel" onclick={() => ((dlgOpen = false), (lastAction = 'dialog cancel'))} />
        <Button label="Save" variant="primary" data-testid="dlg-save" onclick={() => ((dlgOpen = false), (lastAction = `saved ${dlgName}`))} />
      {/snippet}
    </Dialog>
    <ConfirmDialog
      bind:open={confirmOpen}
      title="Park the mount?"
      message="Parking physically closes the Seestar arm and stops tracking."
      confirmLabel="Park"
      onconfirm={() => {
        lastAction = 'parked';
      }}
      oncancel={() => (lastAction = 'park cancelled')}
    />
    <ConfirmDialog
      bind:open={dangerOpen}
      destructive
      title="Clear the Gaia cache?"
      message="Deletes 214 files (38.2 MB). This confirmation fails on purpose after 0.8 s to show the inline error."
      confirmLabel="Clear cache"
      onconfirm={slowConfirm}
      oncancel={() => (lastAction = 'clear cancelled')}
    />
  </section>

  <!-- ===================================================================== Popover / Menu -->
  <section data-gallery="menus" id="menus">
    <h2>Popover and Menu <span>anchored, Esc and outside click close, ↑ ↓ Home End, type-ahead</span></h2>
    <div class="row top">
      <figure>
        <Popover open preview title="Catalogue layers" width={300}>
          <Checkbox label="Field stars (Gaia DR3)" detail="1 204 stars to G 15.0" checked />
          <Checkbox label="Variable stars (VSX)" detail="12 in the field" checked />
          <Checkbox label="Galaxies" checked={false} />
          <Checkbox label="Exoplanet hosts" disabledReason="identify the field first (S)" />
          {#snippet footer()}
            <Button label="Catalogue settings…" variant="ghost" size="s" />
          {/snippet}
        </Popover>
        <figcaption>popover with footer</figcaption>
      </figure>
      <figure>
        <Menu open preview items={menuItems} label="Image" previewActive={2} minWidth={260} />
        <figcaption>menu: header, icons, shortcuts, check, radio, disabled + reason, danger</figcaption>
      </figure>
      <figure>
        <PanelsPopover preview groups={panelGroups} {layout} />
        <figcaption>PanelsPopover + Reset layout</figcaption>
      </figure>
    </div>
    <div class="live">
      <span class="live-label">Live</span>
      <span bind:this={popAnchor} class="inline">
        <IconButton
          icon="catalogue"
          label="Catalogue layers"
          shortcut="O"
          variant="ghost"
          data-testid="open-popover"
          aria-expanded={popOpen}
          onclick={() => (popOpen = !popOpen)}
        />
      </span>
      <span bind:this={menuAnchor} class="inline">
        <Button label="Image menu" data-testid="open-menu" aria-haspopup="menu" aria-expanded={menuOpen} onclick={() => (menuOpen = !menuOpen)} />
      </span>
      <PanelsPopover groups={panelGroups} {layout} section="Gallery" onreset={() => resetCount++} />
      <div
        class="ctx"
        role="img"
        aria-label="Right-click area for the context menu"
        data-testid="ctx-area"
        oncontextmenu={(e) => {
          e.preventDefault();
          ctxPoint = { x: e.clientX, y: e.clientY };
          ctxOpen = true;
        }}
      >
        Right-click here
      </div>
      <span class="result" data-testid="menu-result">last: {lastAction} · crosshair {crosshair ? 'on' : 'off'} · palette {palette} · resets {resetCount}</span>
    </div>
    <Popover bind:open={popOpen} anchor={popAnchor} title="Catalogue layers" placement="bottom-start">
      <Checkbox label="Field stars (Gaia DR3)" detail="1 204 stars to G 15.0" checked />
      <Checkbox label="Variable stars (VSX)" checked />
      <Checkbox label="Galaxies" />
      {#snippet footer()}
        <Button label="Catalogue settings…" variant="ghost" size="s" />
      {/snippet}
    </Popover>
    <Menu bind:open={menuOpen} anchor={menuAnchor} items={menuItems} label="Image" onselect={onMenu} minWidth={260} />
    <Menu bind:open={ctxOpen} point={ctxPoint} items={menuItems} label="Image" onselect={onMenu} minWidth={260} />
  </section>

  <!-- ===================================================================== Select -->
  <section data-gallery="select" id="select">
    <h2>Select <span>token-drawn select-only combobox, never a native &lt;select&gt;</span></h2>
    <div class="row top">
      <figure class="field-w">
        <Select label="Telescope" options={PROFILES} bind:value={profile} />
        <figcaption>closed, with value</figcaption>
      </figure>
      <figure class="field-w">
        <Select label="Frame type" options={FRAMES} bind:value={frame} placeholder="Choose a frame type…" />
        <figcaption>placeholder</figcaption>
      </figure>
      <figure class="field-w">
        <Select label="Telescope" options={PROFILES} value="s30pro" disabledReason="disconnect the equipment before changing the telescope" />
        <figcaption>disabled + reason (D28)</figcaption>
      </figure>
      <figure class="field-w">
        <Select label="Filter" options={[{ value: 'L', label: 'L' }]} value={null} error="the wheel reports no filter names" />
        <figcaption>error</figcaption>
      </figure>
      <figure class="field-w tall">
        <Select label="Frame type" options={FRAMES} value="light" preview previewActive={2} />
        <figcaption>open: active, selected, disabled option</figcaption>
      </figure>
    </div>
  </section>

  <!-- ===================================================================== Tables -->
  <section data-gallery="tables" id="tables">
    <h2>Table <span>24 px rows, sticky header, sortable, one selected row, Enter activates, ⌘/Ctrl+C copies TSV</span></h2>
    <div class="row top">
      <figure class="table-w">
        <Table
          label="Devices"
          columns={deviceColumns}
          rows={DEVICES}
          rowKey={(d) => d.id}
          bind:selected={selectedDevice}
          problem={(d) => d.state === 'error'}
          density="comfortable"
          onactivate={(d) => (activated = d.name)}
        >
          {#snippet cell(d, col)}
            {#if col.id === 'name'}
              <span class="dev"><Icon name={d.icon} size="s" />{d.name}</span>
            {:else if col.id === 'state'}
              <StatusBadge tone={STATE_TONE[d.state]} label={STATE_WORD[d.state]} plain />
            {:else if col.id === 'detail'}
              <span class:muted={d.state === 'disconnected'}>{d.detail}</span>
            {:else if col.id === 'action'}
              {#if d.state === 'connected'}
                <IconButton icon="disconnect" label="Disconnect" showLabel size="s" tooltip="none" />
              {:else if d.state === 'error'}
                <IconButton icon="refresh" label="Retry" showLabel size="s" tooltip="none" />
              {:else if d.state === 'connecting'}
                <IconButton icon="connect" label="Connect" showLabel size="s" busy tooltip="none" />
              {:else}
                <IconButton icon="connect" label="Connect" showLabel size="s" tooltip="none" />
              {/if}
            {/if}
          {/snippet}
        </Table>
        <figcaption>custom cells, comfortable density, problem row, selection</figcaption>
      </figure>
      <figure class="table-w">
        <Table
          label="Variable stars in the field"
          columns={varColumns}
          rows={VARIABLES}
          rowKey={(v) => v.name}
          bind:selected={selectedVar}
          bind:sort={varSort}
          onactivate={(v) => (activated = v.name)}
        />
        <figcaption data-testid="table-result">sorted by Mag ascending (missing last) · activated: {activated}</figcaption>
      </figure>
    </div>
    <div class="row top">
      <figure class="table-w">
        <Table label="Sessions" columns={varColumns} rows={[]} rowKey={(v) => v.name} empty="No sessions in ~/Argos/sessions yet. Open folder… or Import CSV… to review one." />
        <figcaption>empty state</figcaption>
      </figure>
      <figure class="table-w">
        <Table label="Sessions" columns={varColumns} rows={[]} rowKey={(v) => v.name} loading />
        <figcaption>loading (skeleton rows, aria-busy)</figcaption>
      </figure>
    </div>
  </section>

  <!-- ===================================================================== Drawer and Log -->
  <section data-gallery="drawer" id="drawer">
    <h2>Drawer with tabs and the Log <span>levels, filter, search, follow / pause, 5 000 lines, UTC (local time in the tooltip)</span></h2>
    <div class="drawer-frame" style:height="{drawerHeight + 40}px">
      <div class="drawer-host">
        <Drawer
          label="Observe drawer"
          tabs={drawerTabs}
          bind:tab={drawerTab}
          bind:height={drawerHeight}
          maxHeight={420}
          closeShortcut="L"
          onclose={() => (lastAction = 'drawer closed')}
        >
          {#snippet tools(id)}
            {#if id === 'log'}<LogControls store={log} filter={logFilter} />{/if}
          {/snippet}
          {#snippet children(id)}
            {#if id === 'log'}
              <LogView store={log} filter={logFilter} markSeen />
            {:else}
              <p class="placeholder">The {id === 'curve' ? 'light curve' : 'conditions timeline'} comes with wave {id === 'curve' ? 5 : 3}.</p>
            {/if}
          {/snippet}
        </Drawer>
      </div>
    </div>
    <div class="live">
      <span class="live-label">Live</span>
      <Button label="Add INFO" size="s" data-testid="log-info" onclick={() => addLiveLine('info')} />
      <Button label="Add WARN" size="s" data-testid="log-warn" onclick={() => addLiveLine('warning')} />
      <Button label="Add ERROR" size="s" data-testid="log-error" onclick={() => addLiveLine('error')} />
      <Button label="Add 50" size="s" data-testid="log-50" onclick={() => { for (let i = 0; i < 50; i++) addLiveLine('cmd'); }} />
      <span class="result" data-testid="log-result">{log.length} lines held · unseen problems {log.unseenProblems} · drawer {drawerHeight} px</span>
    </div>
    <div class="row top">
      <figure class="log-w">
        <div class="log-frame"><LogView store={pausedLog} filter={pausedFilter} previewPaused={12} /></div>
        <figcaption>paused (the observer scrolled up): count + Jump to latest</figcaption>
      </figure>
      <figure class="log-w">
        <div class="log-frame"><LogView store={log} filter={debugFilter} /></div>
        <figcaption>debug shown, search "mount"</figcaption>
      </figure>
      <figure class="log-w">
        <div class="log-frame"><LogView store={emptyLog} filter={emptyFilter} /></div>
        <figcaption>empty</figcaption>
      </figure>
    </div>
    <div class="row top">
      <figure class="panel-w">
        <div class="panel-frame">
          <LogPanel store={log} title="Connection log" topics={['connection', 'discovery', 'planetarium']} />
        </div>
        <figcaption>LogPanel: the Connection log (topics connection · discovery · planetarium)</figcaption>
      </figure>
    </div>
  </section>

  <!-- ===================================================================== Jobs -->
  <section data-gallery="jobs" id="jobs">
    <h2>JobProgress <span>job model of README 4.2: progress, cancel, error, done</span></h2>
    <div class="jobs">
      {#each SAMPLE_JOBS as s (s.job.id)}
        <figure class="job-w">
          <JobProgress job={s.job} title={s.title} resultText={s.result ?? null} now={NOW} oncancel={() => {}} ondismiss={() => {}} onretry={s.job.state === 'failed' ? () => {} : undefined}>
            {#snippet actions()}
              <Button label="Use 192.168.1.42" size="s" variant="primary" />
            {/snippet}
          </JobProgress>
          <figcaption>{s.caption}</figcaption>
        </figure>
      {/each}
      <figure class="job-w">
        <JobProgress job={SAMPLE_JOBS[1].job} title="Re-run photometry" variant="strip" now={NOW} oncancel={() => {}} />
        <figcaption>strip variant (Review toolbar)</figcaption>
      </figure>
    </div>
  </section>

  <!-- ===================================================================== Rail footer -->
  <section data-gallery="rail" id="rail">
    <h2>Rail footer <span>theme quick toggle (D15) and the Help menu (D14)</span></h2>
    <div class="row top">
      <figure>
        <div class="mini-rail">
          <RailFooter theme={themeChoice} ontheme={(t) => (themeChoice = t)} version="0.4.2" api={2} onshortcuts={() => (sheetOpen = true)} />
          <div class="mini-entry"><Icon name="nav-configuration" size="l" /><span>Settings</span></div>
        </div>
        <figcaption>footer (live: click theme, right-click it, open Help)</figcaption>
      </figure>
      <figure>
        <RailFooter theme={themeChoice} ontheme={() => {}} version="0.4.2" api={2} onshortcuts={() => {}} preview="help" />
        <figcaption>Help menu (browser build)</figcaption>
      </figure>
      <figure>
        <RailFooter theme={themeChoice} ontheme={() => {}} version="0.4.2" api={2} onshortcuts={() => {}} onabout={() => {}} onsupportbundle={() => {}} onquit={() => {}} preview="help" />
        <figcaption>Help menu (desktop app)</figcaption>
      </figure>
      <figure>
        <RailFooter theme="night-red" ontheme={() => {}} onshortcuts={() => {}} preview="theme" />
        <figcaption>theme list (right-click / long press)</figcaption>
      </figure>
    </div>
  </section>

  <!-- ===================================================================== Shortcuts sheet -->
  <section data-gallery="sheet" id="sheet">
    <h2>Keyboard shortcuts sheet <span>generated from the registry; planned keys are not listed</span></h2>
    <div class="row top">
      <figure class="sheet-w">
        <ShortcutSheet open preview {registry} />
      </figure>
    </div>
    <div class="live">
      <span class="live-label">Live</span>
      <Button label="Open the sheet" data-testid="open-sheet" onclick={() => (sheetOpen = true)} />
    </div>
    <ShortcutSheet bind:open={sheetOpen} {registry} />
  </section>

  <!-- ===================================================================== Startup -->
  <section data-gallery="startup" id="startup">
    <h2>StartupScreen <span>honest stages; a failure stays until the observer acts</span></h2>
    <div class="row top">
      <figure class="startup-w">
        <div class="startup-frame"><StartupScreen contained stages={browserStages} version="0.4.2" /></div>
        <figcaption>browser: connecting</figcaption>
      </figure>
      <figure class="startup-w">
        <div class="startup-frame"><StartupScreen contained stages={desktopStages} version="0.4.2" /></div>
        <figcaption>desktop: server started, connecting</figcaption>
      </figure>
      <figure class="startup-w">
        <div class="startup-frame">
          <StartupScreen contained stages={desktopStages} version="0.4.2" {failure} onretry={() => {}} onopenlogs={() => {}} />
        </div>
        <figcaption>failure: message, exact text, log path, Copy / Open log folder / Retry</figcaption>
      </figure>
    </div>
  </section>

  <!-- ===================================================================== Atoms -->
  <section data-gallery="atoms" id="atoms">
    <h2>Supporting atoms <span>Checkbox, SearchField, compact Segmented</span></h2>
    <div class="row top">
      <figure><Checkbox label="Camera" bind:checked={checkA} /><figcaption>checked</figcaption></figure>
      <figure><Checkbox label="Statistics" bind:checked={checkB} /><figcaption>unchecked</figcaption></figure>
      <figure><Checkbox label="Focuser" checked disabledReason="no focuser connected" /><figcaption>disabled + reason</figcaption></figure>
      <figure><SearchField label="Search the log" bind:value={search} count="3 of 14" /><figcaption>search with count</figcaption></figure>
      <figure><SearchField label="Filter settings" value="" /><figcaption>search empty</figcaption></figure>
      <figure>
        <Segmented label="Level" size="s" bind:value={seg} options={[{ value: 'all', label: 'All' }, { value: 'w', label: 'Warnings' }, { value: 'e', label: 'Errors' }]} />
        <figcaption>segmented s</figcaption>
      </figure>
      <figure class="field-w"><TextField label="Address" mono bind:value={fieldText} /><figcaption>text field (existing)</figcaption></figure>
    </div>
  </section>
</div>

<style>
  :global(html.gallery-mode body) {
    overflow: auto;
  }
  :global(html.gallery-mode #app) {
    height: auto;
    min-height: 100%;
  }

  .gallery {
    min-height: 100vh;
    padding: 0 var(--space-6) var(--space-6);
    background: var(--bg);
    color: var(--fg);
  }

  /* Not sticky: element screenshots would catch it mid-section. */
  .top {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin: 0 calc(-1 * var(--space-6));
    padding: var(--space-3) var(--space-6);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg-2);
  }
  .mark {
    display: inline-flex;
    color: var(--accent);
  }
  h1 {
    margin: 0;
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .note {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .spacer {
    flex: 1;
  }

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
  .row + .row {
    margin-top: var(--space-5);
  }

  figure {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
    margin: 0;
  }
  figcaption {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .wide {
    width: 480px;
  }
  .wide :global(.dialog) {
    width: 100%;
  }
  .field-w {
    width: 260px;
  }
  .field-w > :global(*:first-child) {
    width: 100%;
  }
  .tall {
    min-height: 220px;
  }
  .table-w {
    width: 640px;
  }
  .table-w > :global(.table-wrap) {
    width: 100%;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
  }
  .log-w {
    width: 440px;
  }
  .log-frame {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 200px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--bg-2);
    overflow: hidden;
  }
  .panel-w {
    width: 1000px;
  }
  .panel-frame {
    width: 100%;
    height: 220px;
  }
  .job-w {
    min-width: 0;
  }
  .job-w > :global(.job) {
    width: 100%;
  }
  .jobs {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 620px));
    gap: var(--space-4) var(--space-5);
  }
  .sheet-w {
    width: 640px;
  }
  .sheet-w :global(.dialog) {
    width: 100%;
  }
  .startup-w {
    width: 440px;
  }
  .startup-frame {
    width: 100%;
    height: 420px;
    overflow: hidden;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
  }

  .vsep {
    align-self: stretch;
    width: 1px;
    background: var(--border-soft);
  }

  .drawer-frame {
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    max-width: 1100px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--viewer-bg);
    overflow: hidden;
  }
  .drawer-host {
    display: flex;
    flex-direction: column;
  }
  .placeholder {
    margin: 0;
    padding: var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-s);
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
  .inline {
    display: inline-flex;
  }
  .ctx {
    padding: var(--space-2) var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--viewer-bg);
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  .dev {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .dev :global(.icon) {
    color: var(--fg-muted);
  }
  .muted {
    color: var(--text-muted);
  }

  .mini-rail {
    display: flex;
    flex-direction: column;
    width: var(--sidebar-w);
    padding-bottom: var(--space-3);
    border: var(--border-w) solid var(--border);
    background: var(--bg-2);
  }
  .mini-entry {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-1);
    padding: var(--space-3) var(--space-1) var(--space-2);
    color: var(--fg-muted);
  }
  .mini-entry span {
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
  }
</style>
