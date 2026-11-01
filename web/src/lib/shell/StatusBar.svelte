<!--
  Bottom status strip: always visible, so the observer never wonders whether
  the equipment is connected, where the mount points or whether frames are
  flowing. Numbers are mono with tabular figures and fixed widths, so
  nothing jitters while values change.

  One home per value: frame number and exposure are on the image's chips,
  zoom on the toolbar, the theme in its button's tooltip, the device name in
  the connection badge's tooltip. The mount (state, RA / Dec, and during a
  slew the angle to go with an abort button) is here because the Mount card
  can sit below the fold.
-->
<script lang="ts">
  import { formatFps, formatLatency } from '../app/metrics';
  import { useApp } from '../app/state.svelte';
  import { connectionStatus, mountStatus } from '../app/status';
  import Icon from '../components/Icon.svelte';
  import IconButton from '../components/IconButton.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { tooltip } from '../components/tooltip';
  import { formatDec, formatDegrees, formatRA, separationDeg } from '../format/astro';

  const app = useApp();

  const conn = $derived(connectionStatus(app.connection, app.events.link));
  const device = $derived(
    app.linkOpen && app.connection?.state === 'connected' ? app.connection.device_name : null,
  );
  const mount = $derived(app.connected ? app.mount : null);
  const mountBadge = $derived(mountStatus(app.mount, app.connected, app.stale));
  const toGo = $derived(
    app.slewing && mount?.target
      ? separationDeg(mount.ra_hours, mount.dec_deg, mount.target.ra_hours, mount.target.dec_deg)
      : null,
  );
  const metrics = $derived(app.liveMetrics);

  function adu(v: number | [number, number, number]): string {
    return Array.isArray(v) ? v.join(' / ') : String(v);
  }
</script>

<footer class="statusbar">
  <span
    class="item conn"
    use:tooltip={{
      text: device ? `${device} · ${app.config.apiBase.replace(/^https?:\/\//, '')}` : conn.label,
      placement: 'top',
      disabled: !device,
    }}
  >
    <StatusBadge tone={conn.tone} label={conn.label} plain />
  </span>

  <span class="sep" aria-hidden="true"></span>

  <span class="item mount" class:stale={app.stale} aria-label="Mount">
    <span class="key">Mount</span>
    <span class="badge-w"><StatusBadge tone={mountBadge.tone} label={mountBadge.label} plain /></span>
    <span class="key">RA</span>
    <span class="num val w-ra">{mount ? formatRA(mount.ra_hours) : '—'}</span>
    <span class="key">Dec</span>
    <span class="num val w-dec">{mount ? formatDec(mount.dec_deg) : '—'}</span>
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

  <span class="sep" aria-hidden="true"></span>

  <span class="item">
    <span class="key">X</span><span class="num val w4">{app.pointer ? app.pointer.x : '—'}</span>
    <span class="key">Y</span><span class="num val w4">{app.pointer ? app.pointer.y : '—'}</span>
    <span class="key">Value</span>
    <span class="num val w6">{app.pointer ? `${adu(app.pointer.value)} ADU` : '—'}</span>
  </span>

  <span class="sep" aria-hidden="true"></span>

  <span
    class="item"
    use:tooltip={{
      text: 'Display rate, and delay from the end of the exposure to the screen (while frames flow)',
      placement: 'top',
    }}
  >
    <span class="key">Rate</span>
    <span class="num val w7">{formatFps(metrics.fps)}</span>
    <span class="key">Latency</span>
    <span class="num val w6">{formatLatency(metrics.latencyMs)}</span>
  </span>

  <span class="spacer"></span>

  <button
    type="button"
    class="log-toggle"
    class:open={app.logOpen}
    aria-pressed={app.logOpen}
    aria-label={app.unseenProblems > 0
      ? `Activity log, ${app.unseenProblems} new warnings or errors`
      : 'Activity log'}
    onclick={() => app.setLogOpen(!app.logOpen)}
  >
    <Icon name="log" size="s" />
    <span>Log</span>
    {#if app.unseenProblems > 0 && !app.logOpen}
      <span class="badge num">{app.unseenProblems}</span>
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
  }
  .conn,
  .mount {
    align-items: center;
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

  .key {
    color: var(--text-muted);
  }

  .val {
    color: var(--fg);
  }

  .w4 {
    min-width: 4ch;
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
    background: var(--border-soft);
  }

  .spacer {
    flex: 1;
  }

  .log-toggle {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 100%;
    padding: 0 var(--space-4);
    border: none;
    border-left: var(--border-w) solid transparent;
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
</style>
