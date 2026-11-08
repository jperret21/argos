<!--
  Bottom status bar, one 28 px row (owner D8) on every section (D18; 01 2.3.1, 2.3.2;
  replaces the Qt TopStatusBar, M11):

  - Left, global: the server link when it is not open (warning tone; the
    last state stays, greyed), the device cluster (mount, camera, filter
    wheel, focuser: icon + a mark whose shape says the state; a device that
    is not connected opens the Connection screen on click), the network
    (Seestar reachability, internet: three states each, "—" = not
    configured / not checked, Q-G13), the mount's state and RA / Dec (and
    during a slew the angle still to go with an abort button: BRAND 11.1,
    the Mount card can sit below the fold), the run chip (live view or an
    exposure).
  - Middle, Observe only: the frame on screen (number, and its file name once
    saved or opened: the Qt context bar, M48), its HFD and star count (the
    server's frame_metrics of THAT frame, A26), display rate and latency. The
    cursor readout moved to the image HUD (owner decision D6, one home per
    value).
  - Right: the activity text (the last action started or its outcome, with
    its UTC time; full text in the tooltip), then the Log button with the
    count of unseen warnings and errors. Once nothing runs (no connect, no
    discovery, no exposure, no slew) the text is muted and loses a trailing
    ellipsis: it is a record, not a claim that something is in progress.

  Numbers are mono with tabular figures and fixed widths, so nothing
  jitters. Priority, not width, decides what folds: the Log button and the
  device cluster never hide; the activity text shrinks first; Rate /
  Latency fold into their tooltip at 1280 px, or at any width while the
  server link item or a slew's "to go + Abort" needs the room.
-->
<script lang="ts">
  import { formatFps, formatLatency } from '../app/metrics';
  import { useApp } from '../app/state.svelte';
  import { connectionStatus, mountStatus } from '../app/status';
  import Icon from '../components/Icon.svelte';
  import IconButton from '../components/IconButton.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { tooltip } from '../components/tooltip';
  import DeviceMark from '../connection/DeviceMark.svelte';
  import { deviceTooltip, deviceViews, networkView } from '../connection/model';
  import { formatDec, formatDegrees, formatRA, separationDeg } from '../format/astro';
  import { fixed, int, seconds } from '../format/number';
  import { utcClock, utcFull } from '../app/log';
  import { recent } from '../imaging/modes/exposure';

  const app = useApp();

  const link = $derived(connectionStatus(app.connection, app.events.link));
  const linkDown = $derived(app.events.link !== 'open');
  const devices = $derived(deviceViews(app.devices));
  const net = $derived(networkView(app.network, app.clock, app.connectMode === 'alpaca'));
  // The mount's own device record: with the camera alone, the mount record is a placeholder.
  const mount = $derived(app.mountReady ? app.mount : null);
  const mountBadge = $derived(mountStatus(app.mount, app.mountReady, app.stale));
  const toGo = $derived(
    app.slewing && mount?.target
      ? separationDeg(mount.ra_hours, mount.dec_deg, mount.target.ra_hours, mount.target.dec_deg)
      : null,
  );
  const metrics = $derived(app.liveMetrics);
  const observe = $derived(app.section === 'imaging');
  const activity = $derived(app.events.activity);
  /** Something is in progress, so an activity ending in "…" is true. */
  const working = $derived(
    app.equipment.anyConnecting ||
      app.discovering ||
      app.cameraBusy ||
      app.slewing ||
      !!app.busy.connectAll ||
      !!app.busy.disconnectAll,
  );
  const activityText = $derived(activity ? (working ? activity.text : activity.text.replace(/…$/, '')) : '');
  /** Items that need room: Rate / Latency fold while they are shown. */
  /** Wave 2: the Settings site disagrees with the mount (site check): one warning item, never folded. */
  const siteAlert = $derived(app.siteMismatch && !app.stale);
  const siteTip = $derived(
    app.siteCheck?.separation_deg != null
      ? `The Settings site disagrees with the mount (${fixed(app.siteCheck.separation_deg, 1)}° apart): airmass, BJD and the FITS site would be wrong. Open Settings › Observer & site`
      : 'The Settings site disagrees with the mount: open Settings › Observer & site',
  );
  const run = $derived.by(() => {
    if (app.stale) return null;
    // Wave 3: autofocus owns the camera (README 1.2 run chip "AF").
    const af = app.autofocus;
    if (af && (af.state === 'running' || af.state === 'stopping')) {
      return af.state === 'stopping'
        ? { icon: 'autofocus', text: 'AF returning', tip: 'Autofocus stopped: the focuser returns to its start position (open Observe)' }
        : { icon: 'autofocus', text: `AF ${af.step ?? 0}/${af.total || '…'}`, tip: `Autofocus running, ${af.stage ?? ''} sweep: open Observe` };
    }
    if (app.camera?.waiting_for === 'filterwheel') return { icon: 'filter-wheel', text: 'Wheel → Dark', tip: 'A Dark / Bias shot waits for the wheel to settle on Dark: open Observe' };
    if (app.live) return { icon: 'live', text: 'LIVE', tip: 'Live view running: open Observe' };
    if (app.running.exposing) {
      const s = app.camera?.exposure_s ?? 0;
      return { icon: 'capture', text: `Exposing ${seconds(s)}`, tip: 'One exposure running: open Observe' };
    }
    return null;
  });

  // Wave 3: an autofocus or wheel chip (wider than LIVE, and the rate means little then) folds them too.
  const crowded = $derived(linkDown || toGo !== null || siteAlert || (!!run && run.icon !== 'live' && run.icon !== 'capture'));

  const seestarTip = $derived(
    net.seestar.word === 'not configured'
      ? 'Seestar: no address configured (Connection screen)'
      : `Seestar ${app.network?.host ?? ''}:${app.network?.port ?? ''}: ${net.seestar.word}${net.checked ? `, checked ${net.checked}` : ''}`,
  );
  const internetTip = $derived(
    net.internet.word === 'not checked'
      ? 'Internet: not checked (ARGOS checks it only when you ask, on the Connection screen)'
      : `Internet: ${net.internet.word}${net.internetChecked ? `, checked ${net.internetChecked}` : ''}`,
  );

  /** Integer ADU grouped ("12 450"); float data keeps two decimals. */
  // -- Observe: the frame on screen (M48) and its metrics (A26) ----------------------
  const shownHeader = $derived(
    app.shown?.frame.header as { seq: number; file_name?: string | null; path?: string | null; origin?: string } | undefined,
  );
  const frameSeq = $derived(shownHeader?.seq ?? null);
  const frameFile = $derived.by(() => {
    const h = shownHeader;
    if (!h) return null;
    if (h.origin === 'file' || h.file_name) return h.file_name ?? null;
    return app.lastSaved && app.lastSaved.frame_seq === h.seq ? app.lastSaved.name : null;
  });
  const frameTip = $derived(
    frameFile
      ? `Frame #${frameSeq} · ${(shownHeader?.path ?? app.lastSaved?.path) || frameFile}`
      : 'Frame on screen: not saved (Take shot saves the next frame as FITS)',
  );
  // The frame on screen, or one just before it while this one is measured (never a later or an old one).
  const metricsNow = $derived(app.frameMetrics && recent(app.frameMetrics.seq, frameSeq) ? app.frameMetrics : null);
  const frameHfd = $derived(metricsNow?.hfd_px ?? null);
  const frameStars = $derived(metricsNow?.star_count ?? null);

</script>

<footer class="statusbar" class:crowded class:observe>
  {#if linkDown}
    <span
      class="item server"
      use:tooltip={{
        text:
          app.events.link === 'reconnecting'
            ? `ARGOS server ${app.config.apiBase}: link lost, reconnecting by itself. What is shown is the last state received.`
            : `ARGOS server ${app.config.apiBase}: ${link.label}`,
        placement: 'top',
      }}
    >
      <Icon name="network" size="s" />
      <StatusBadge tone={link.tone} label={app.events.link === 'reconnecting' ? 'Server link lost' : link.label} plain />
    </span>
    <span class="sep" aria-hidden="true"></span>
  {/if}

  <span class="item cluster" class:stale={app.stale} role="group" aria-label="Equipment">
    {#each devices as d (d.id)}
      {#if d.phase === 'connected' && !app.stale}
        <span class="dev" aria-label={deviceTooltip(d)} use:tooltip={{ text: deviceTooltip(d), placement: 'top' }}>
          <Icon name={d.icon} size="s" />
          <DeviceMark mark={d.mark} tone={d.tone} size="s" />
        </span>
      {:else}
        <button
          type="button"
          class="dev link"
          aria-label="{deviceTooltip(d)}. Open the Connection screen"
          use:tooltip={{ text: `${deviceTooltip(d)}. Open the Connection screen`, placement: 'top' }}
          onclick={() => app.go('connection')}
        >
          <Icon name={d.icon} size="s" />
          <DeviceMark mark={app.stale ? 'ring' : d.mark} tone={app.stale ? 'idle' : d.tone} spinning={!app.stale && d.spinning} size="s" />
        </button>
      {/if}
    {/each}
  </span>

  <span class="sep" aria-hidden="true"></span>

  <span class="item net" class:stale={app.stale} role="group" aria-label="Network">
    <span class="reach" aria-label={seestarTip} use:tooltip={{ text: seestarTip, placement: 'top' }}>
      <span class="key">Seestar</span>
      <DeviceMark mark={net.seestar.mark} tone={net.seestar.tone} size="s" />
    </span>
    <span class="reach" aria-label={internetTip} use:tooltip={{ text: internetTip, placement: 'top' }}>
      <span class="key">Net</span>
      <DeviceMark mark={net.internet.mark} tone={net.internet.tone} size="s" />
    </span>
  </span>

  <span class="sep" aria-hidden="true"></span>

  <span class="item mount" class:stale={app.stale} aria-label="Mount">
    <span class="key">Mount</span>
    <span class="badge-w"><StatusBadge tone={mountBadge.tone} label={mountBadge.label} plain /></span>
    {#if mount?.alignment}
      <!-- A29: the mount geometry (Alt-Az or EQ), wave 1 gap of M11. -->
      <span
        class="key geo"
        use:tooltip={{ text: mount.alignment === 'altaz' ? 'Alt-azimuth mount (axis words on the jog pad)' : mount.alignment === 'eq_gem' ? 'German equatorial mount' : 'Equatorial mount', placement: 'top' }}
        >{mount.alignment === 'altaz' ? 'Alt-Az' : 'EQ'}</span
      >
    {/if}
    <span class="key">RA</span>
    <span class="num val" class:w-ra={!!mount}>{mount ? formatRA(mount.ra_hours) : '—'}</span>
    <span class="key">Dec</span>
    <span class="num val" class:w-dec={!!mount}>{mount ? formatDec(mount.dec_deg) : '—'}</span>
    {#if toGo !== null}
      <span class="num val togo">{formatDegrees(toGo)} to go</span>
      <span class="abort">
        <IconButton
          icon="abort"
          label="Abort slew"
          variant="danger"
          size="s"
          shortcut="Escape"
          tooltip="top"
          busy={!!app.busy.mountStop}
          onclick={() => app.stopMount()}
        />
      </span>
    {/if}
  </span>

  {#if siteAlert}
    <span class="sep" aria-hidden="true"></span>
    <button
      type="button"
      class="site-alert"
      aria-label={siteTip}
      use:tooltip={{ text: siteTip, placement: 'top' }}
      onclick={() => app.openSettings('observer_site')}
    >
      <StatusBadge variant="bar" level="attention" label="Site ≠ mount" live={false} />
    </button>
  {/if}

  {#if run}
    <span class="sep" aria-hidden="true"></span>
    <button
      type="button"
      class="run"
      aria-label={run.tip}
      use:tooltip={{ text: run.tip, placement: 'top' }}
      onclick={() => app.go('imaging')}
    >
      <Icon name={run.icon} size="s" />
      <span class="num">{run.text}</span>
    </button>
  {/if}

  {#if observe}
    <span class="sep" aria-hidden="true"></span>

    <span class="item frame" use:tooltip={{ text: frameTip, placement: 'top' }}>
      <span class="key">Frame</span>
      <span class="num val" class:w6={frameSeq !== null}>{frameSeq !== null ? `#${int(frameSeq)}` : '—'}</span>
      {#if frameFile}<span class="file num">{frameFile}</span>{/if}
    </span>

    <span class="sep" aria-hidden="true"></span>

    <span
      class="item"
      class:prev={metricsNow !== null && metricsNow.seq !== frameSeq}
      use:tooltip={{
        text: `Measured by the server on the full frame (green plane): half-flux diameter of the brightest star, stars above 5 σ${metricsNow ? ` · frame #${metricsNow.seq}` : ''}`,
        placement: 'top',
      }}
    >
      <span class="key">HFD</span>
      <span class="num val" class:w6={frameHfd !== null}>{frameHfd !== null ? `${fixed(frameHfd, 2)} px` : '—'}</span>
      <span class="key">Stars</span>
      <span class="num val" class:w4={frameStars !== null}>{frameStars !== null ? int(frameStars) : '—'}</span>
    </span>

    <span class="sep rate-sep" aria-hidden="true"></span>

    <span
      class="item rate"
      use:tooltip={{
        text: `Display rate ${formatFps(metrics.fps)}, latency ${formatLatency(metrics.latencyMs)}: delay from the end of the exposure to the screen (while frames flow)`,
        placement: 'top',
      }}
    >
      <span class="key">Rate</span>
      <span class="num val" class:w7={metrics.fps !== null}>{formatFps(metrics.fps)}</span>
      <span class="key">Latency</span>
      <span class="num val" class:w6={metrics.latencyMs !== null}>{formatLatency(metrics.latencyMs)}</span>
    </span>
  {/if}

  <span
    class="activity"
    aria-live="polite"
    use:tooltip={{
      text: activity ? `${activityText} (${utcFull(activity.t)})` : 'The last action and its outcome appear here.',
      placement: 'top',
    }}
  >
    {#if activity}
      <span class="num when">{utcClock(activity.t)}</span>
      <span class="what" class:done={!working}>{activityText}</span>
    {/if}
  </span>

  <button
    type="button"
    class="log-toggle"
    class:open={app.logShown}
    aria-pressed={app.logShown}
    aria-keyshortcuts="L"
    aria-label={app.unseenProblems > 0
      ? `Activity log, ${app.unseenProblems} new warnings or errors`
      : 'Activity log'}
    use:tooltip={{
      text: 'Activity log',
      // The last action, also here: the activity segment hides when it is too narrow to read.
      hint: activity ? `Last: ${utcClock(activity.t)} ${activityText}` : undefined,
      shortcut: 'L',
      placement: 'top',
    }}
    onclick={() => app.toggleLog()}
  >
    <Icon name="log" size="s" />
    <span>Log</span>
    {#if app.unseenProblems > 0 && !app.logShown}
      <span class="badge num">{int(app.unseenProblems)}</span>
    {/if}
  </button>
</footer>

<style>
  .statusbar {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    height: var(--statusbar-h);
    padding: 0 0 0 var(--space-4);
    border-top: var(--border-w) solid var(--border);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-s);
    white-space: nowrap;
    overflow: hidden;
  }

  .item {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-2);
    min-width: 0;
    flex: none;
  }
  .server,
  .cluster,
  .net,
  .mount {
    align-items: center;
  }
  .server {
    color: var(--warning);
  }

  .cluster {
    gap: var(--space-1);
  }
  .dev {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    height: 24px;
    padding: 0 var(--space-1);
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg-muted);
  }
  .dev.link {
    cursor: pointer;
  }
  .dev.link:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .dev.link:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .stale .dev {
    color: var(--fg-disabled);
  }

  .net {
    gap: var(--space-3);
  }
  .reach {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }

  .badge-w {
    display: inline-flex;
    min-width: 84px;
  }
  .w-ra {
    min-width: 13ch;
  }
  .w-dec {
    min-width: 12ch;
  }
  .togo {
    color: var(--fg);
  }
  .abort {
    display: inline-flex;
  }
  .abort :global(.icon-button) {
    height: 24px;
    min-width: 24px;
    padding: 0 3px;
  }
  .stale .val {
    color: var(--text-muted);
  }

  .site-alert {
    display: inline-flex;
    align-items: center;
    flex: none;
    height: 22px;
    padding: 0 var(--space-1);
    border: none;
    border-radius: var(--radius-s);
    background: none;
    color: var(--fg);
    font: inherit;
    cursor: pointer;
  }
  .site-alert:hover {
    background: var(--hover-bg);
  }
  .site-alert:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .run {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 22px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg);
    color: var(--fg);
    font-size: var(--text-xs);
    flex: none;
    cursor: pointer;
  }
  .run:hover {
    background: var(--hover-bg);
  }

  .key {
    color: var(--text-muted);
  }

  .val {
    color: var(--fg);
  }

  .item.prev .val {
    color: var(--text-muted);
  }
  .frame .file {
    max-width: 22ch;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-muted);
    white-space: nowrap;
  }
  .w4 {
    min-width: 5ch; /* "3 840": grouped from 1 000 (BRAND 5) */
  }
  .w6 {
    min-width: 10ch;
  }
  .w7 {
    min-width: 8ch;
  }

  .sep {
    width: 1px;
    height: 14px;
    flex: none;
    background: var(--border-soft);
  }

  /* The activity text takes what is left and shrinks first (ellipsis). */
  /* Right-aligned while there is room; when narrow the text ellipsizes first and the
     time is never cut on its left (it read ":34:02" at 1280 px with flex-end). */
  .activity {
    display: inline-flex;
    flex: 1 1 0;
    gap: var(--space-2);
    min-width: 0;
    overflow: hidden;
    color: var(--text-muted);
    container: activity / inline-size;
  }
  /* Never a time followed by one letter ("13:36:19 C…", design review W3): below about
     16 characters of text the segment is left empty, and the Log button's tooltip says
     the last action. */
  @container activity (max-width: 190px) {
    .activity .when,
    .activity .what {
      display: none;
    }
  }
  .activity .when {
    flex: none;
    margin-left: auto;
  }
  .activity .what {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--fg);
  }
  .activity .what.done {
    color: var(--text-muted);
  }

  .log-toggle {
    display: inline-flex;
    align-items: center;
    flex: none;
    gap: var(--space-2);
    height: 100%;
    padding: 0 var(--space-4);
    border: none;
    border-left: var(--border-w) solid var(--border-soft);
    background: transparent;
    color: var(--fg-muted);
    font-size: var(--text-s);
    cursor: pointer;
  }
  .log-toggle span {
    color: var(--fg);
  }
  .log-toggle:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .log-toggle.open {
    background: var(--toggled-bg);
    color: var(--toggled-fg);
  }
  .log-toggle.open span {
    color: var(--toggled-fg);
  }
  .log-toggle:focus-visible {
    outline-offset: -2px;
  }

  .badge {
    min-width: 18px;
    padding: 0 var(--space-1);
    border: var(--border-w) solid var(--danger);
    border-radius: var(--radius-round);
    font-size: var(--text-2xs);
    line-height: 14px;
    text-align: center;
  }

  /* Rate / Latency fold into their tooltip at 1280 px (01 2.3.2), and at any
     width while the server link item or a slew's "to go + Abort" is shown. */
  .crowded .rate,
  .crowded .rate-sep {
    display: none;
  }
  @media (max-width: 1400px) {
    .rate,
    .rate-sep {
      display: none;
    }
    /* Observe's frame and HFD segments leave no room for it at 1 280 px: the activity
       is in the log (L) rather than shown as a cut fragment ("13:18:1"). */
    .observe .activity {
      visibility: hidden; /* keeps its flexible space: Log stays at the right end */
    }
  }
</style>
