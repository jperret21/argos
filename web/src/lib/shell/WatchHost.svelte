<!--
  Watch bound to the app (wave 6b, owner D3): the WatchData mapped from the app's stores, so
  App only mounts it while Watch is open.
  - The run: the sequence record (state, n / N, the step, the end), the last-frame age
    against the observed cadence (SequenceStore).
  - The target and check: the SERVER's points (the newest finite target point and its
    comparisons, the σ of the check's last 15 points): Watch never computes a magnitude.
    The curve has its own light-curve store fed from the photometry stream (as the drawer's).
  - HFD and stars: the run's subs from the conditions store; the HFD rule's line (hfdRule, with
    the server's baseline for the run).
  - Altitude (the mount's, when connected) against site.min_altitude_deg (30° unset).
  - The links (camera, mount, server) in words, the server's keep-awake record.
  - The most urgent open attention item replaces the first row; Acknowledge is the server's.
  The attention store and the keep-awake record come as props (the app state holds them).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { useApp } from '../app/state.svelte';
  import type { Tone } from '../app/status';
  import LightCurvePlot from '../charts/lightcurve/LightCurvePlot.svelte';
  import { LiveCurveStore } from '../charts/lightcurve/store';
  import { filterLabel } from '../format/filter';
  import { newestCurve, trailingStats } from '../imaging/photometry/present';
  import { pickBaseline } from '../imaging/run/runband';
  import type { LcPoint } from '../imaging/photometry/types';
  import { endAt, isEngaged } from '../run/run';
  import type { AttentionStore } from './attention/attention.svelte';
  import Watch from './Watch.svelte';
  import { endedWord, hfdRule, runSeries, type DimLevel, type WatchData, type WatchLink } from './watch';

  interface Props {
    attention: AttentionStore;
    /** The server's keep-awake record (checkKeepAwake(status.keep_awake)). */
    keepAwake?: WatchData['computer'];
    onclose: () => void;
  }
  let { attention, keepAwake = null, onclose }: Props = $props();
  const app = useApp();
  let dim = $state<DimLevel>(100);

  /** The plot's own store, fed by the validated stream (the drawer's pattern: subscribed once). */
  const curveStore = new LiveCurveStore();
  $effect(() => untrack(() => app.photometry.feed({ load: (s) => curveStore.load(s), apply: (ev) => curveStore.apply(ev), reset: (ev) => curveStore.reset(ev) })));
  $effect(() => {
    const stars = app.field.targets?.stars ?? [];
    const band = app.photometry.live?.band ?? null;
    untrack(() => curveStore.applyTargets(stars, band));
  });

  const VERDICT: Record<string, string> = { live_preview_consistent: 'consistent', not_ready: 'not ready', insufficient_data: 'too few points' };

  const seq = $derived(app.sequence.state);
  const engaged = $derived(isEngaged(seq));
  const now = $derived(app.clock / 1000);
  const curves = $derived(app.photometry.curves);
  // S49: one curve per (star, filter); Watch shows the filter of the newest frame.
  const targetCurve = $derived(newestCurve(curves.filter((c) => c.role === 'target')));
  const checkCurve = $derived(newestCurve(curves.filter((c) => c.role === 'check' && (!targetCurve?.filter || c.filter === targetCurve.filter))));
  const lastPoint = $derived.by((): LcPoint | null => {
    const pts = targetCurve?.points ?? [];
    for (let i = pts.length - 1; i >= 0; i--) if (typeof pts[i].mag === 'number' && Number.isFinite(pts[i].mag)) return pts[i];
    return null;
  });
  const series = $derived.by(() => {
    void app.conditions.version;
    const c = app.conditions.cols;
    const from = engaged ? (seq?.started_t ?? null) : null;
    return { hfd: runSeries(c.cols.t, c.cols.hfd, c.n, from), stars: runSeries(c.cols.t, c.cols.stars, c.n, from) };
  });
  const hfdOpen = $derived(attention.open.some((a) => a.rule === 'hfd_rise'));

  function link(label: string, state: string | undefined): WatchLink {
    const on = state === 'connected' || state === 'busy';
    const tone: Tone = on ? 'ok' : state === 'error' ? 'error' : 'idle';
    return { label, tone, word: on ? 'connected' : state === 'error' ? 'error' : state === 'connecting' ? 'connecting' : 'not connected' };
  }

  const data = $derived.by((): WatchData => {
    const s = seq;
    const r = s?.last_result ?? null;
    const d = app.events.devices;
    const mountOn = d?.mount.state === 'connected' || d?.mount.state === 'busy';
    const limit = app.configValues?.['site.min_altitude_deg'];
    const st = checkCurve ? trailingStats(checkCurve, 0, 15) : null;
    const comps = curves.filter((c) => c.role === 'comparison').length;
    const quality = app.photometry.quality;
    return {
      state: engaged && s ? s.state : null,
      object: (engaged ? s?.object_name : null) ?? app.photometry.live?.object_name ?? null,
      framesDone: engaged && s ? s.frames_done : (r?.frames_saved ?? null),
      framesTotal: engaged && s ? s.frames_total : (r?.frames_total ?? null),
      lastFrameAt: app.sequence.lastFrameAt,
      cadence: app.sequence.cadence,
      expecting: !!s && (s.state === 'running' || s.state === 'pausing'),
      target: lastPoint && targetCurve ? { name: targetCurve.name, mag: lastPoint.mag, err: lastPoint.mag_err, band: app.photometry.live?.band ?? null, filter: filterLabel(targetCurve.filter) || null } : null,
      check: checkCurve && st ? { name: checkCurve.name, sigma: st.sd, n: st.n } : null,
      comps: lastPoint ? { used: lastPoint.comps_used, total: comps || null, verdict: quality ? (VERDICT[String(quality.selection_status)] ?? null) : null } : null,
      end: engaged && s ? endAt(s, now) : null,
      stars: series.stars,
      hfd: series.hfd,
      hfdRef: hfdRule(attention.items, attention.thresholds, series.hfd, pickBaseline(attention.baselines, s?.current?.filter)),
      hfdFlag: hfdOpen,
      alt: mountOn ? (app.events.mount?.alt_deg ?? null) : null,
      altLimit: typeof limit === 'number' && Number.isFinite(limit) ? limit : 30,
      links: [link('Camera', d?.camera.state), link('Mount', d?.mount.state), { label: 'Server', tone: app.stale ? 'error' : 'ok', word: app.stale ? 'link lost' : 'linked' }],
      computer: keepAwake,
      ended: !engaged && r ? { word: endedWord(r.reason), at: r.ended_t } : null,
      sound: { level: attention.prefs.level, armed: attention.armed },
    };
  });
</script>

<Watch
  {data}
  {now}
  top={attention.top}
  ackBusy={!!attention.top && attention.pending.has(attention.top.id)}
  onack={(id) => attention.ack(id)}
  bind:dim
  {onclose}
  onpause={() => app.sequence.pause(app.client)}
  onhelp={() => (app.shortcutSheetOpen = true)}
  onpalette={() => (app.paletteOpen = true)}
  onarm={() => attention.arm()}
  moreOpen={Math.max(0, attention.open.length - 1)}
  onsound={(level) => {
    attention.arm();
    app.setAlertSound(level);
  }}
  theme={app.theme}
>
  {#snippet curve()}
    {#if curves.length}
      <LightCurvePlot store={curveStore} facets={checkCurve ? ['target', 'check'] : ['target']} variant="watch" toolbar={false} expecting={data.expecting} theme={app.theme} label="Live light curve" />
    {:else}
      <p class="none">No light curve yet: it appears with the first measured frame.</p>
    {/if}
  {/snippet}
</Watch>

<style>
  .none {
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0;
    color: var(--text-muted);
    font-size: var(--watch-s);
  }
</style>
