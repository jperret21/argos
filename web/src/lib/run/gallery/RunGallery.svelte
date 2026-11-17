<!--
  Component gallery, wave 6a, run controls and visibility (development only, part of
  /?gallery=1): the transport, the readiness chip and its Preflight popover, the run strip,
  the Run card, RunProgress and the last-frame age, the VisibilityTimeline and the interlock
  question, each in its states, on deterministic fixtures (fixtures.ts). Sections are
  [data-gallery="w6-<name>"] for element screenshots. Nothing here talks to a server.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import type { Theme } from '../../app/theme';
  import VisibilityTimeline from '../../charts/VisibilityTimeline.svelte';
  import AgeMeter from '../../charts/mini/AgeMeter.svelte';
  import RunProgress from '../../charts/mini/RunProgress.svelte';
  import RunCard from '../../imaging/RunCard.svelte';
  import InterlockDialog from '../InterlockDialog.svelte';
  import { MountInterlock } from '../interlock.svelte';
  import ReadinessChip from '../ReadinessChip.svelte';
  import { startBlock } from '../run';
  import RunStrip from '../RunStrip.svelte';
  import RunTransport from '../RunTransport.svelte';
  import { AF_MARKS, FRAMES, LAST_SAVED, NOW, PRE, RUN_SPAN, SEQ, TRANSIT, TRANSIT_RUN, VIS_NO_SUN, VIS_TRANSIT, VIS_VAR } from './fixtures';

  let theme = $state<Theme>('observatory');
  onMount(() => {
    const read = () => (theme = (document.documentElement.dataset.theme as Theme) || 'observatory');
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  });

  const ok = () => Promise.resolve();
  const lock = new MountInterlock();
  const pending = { action: 'GoTo', verb: 'slew', message: 'A sequence is running — GoTo would move the field under it. Pause the run first.', retry: ok };
  const blocked = startBlock(null, PRE.blocked.checks);
  const offset = 60; // the gallery's local zone (UTC+1), so the shots do not depend on the machine
  const card = { now: NOW, frameTimes: FRAMES, marks: AF_MARKS, onpause: ok, onresume: ok, onstop: ok, onplan: () => undefined };
</script>

<section data-gallery="w6-transport" id="w6-transport">
  <h2>Run transport <span>Start (deliberate; disabled only with the server's reason), its menu "Start at a time…" (Q-P2), Pause ⇄ Resume (Resume already while pausing), Stop… asked first (Q-P7); no key starts or stops a run</span></h2>
  <div class="grid">
    <figure><RunTransport seq={SEQ.idle} now={NOW} onstart={ok} onpause={ok} onresume={ok} onstop={ok} /><figcaption>idle, ready</figcaption></figure>
    <figure><RunTransport seq={SEQ.idle} now={NOW} startReason={blocked} onstart={ok} onpause={ok} onresume={ok} onstop={ok} /><figcaption>blocked: “{blocked}”</figcaption></figure>
    <figure><RunTransport seq={SEQ.idle} now={NOW} draftStartAt={TRANSIT_RUN.start + 86400} onstart={ok} onpause={ok} onresume={ok} onstop={ok} /><figcaption>the draft has a start time: Start says when</figcaption></figure>
    <figure><RunTransport seq={SEQ.running} now={NOW} startReason={startBlock(SEQ.running, PRE.ready.checks)} onstart={ok} onpause={ok} onresume={ok} onstop={ok} /><figcaption>running</figcaption></figure>
    <figure><RunTransport seq={SEQ.pausing} now={NOW} startReason="A sequence is running" onstart={ok} onpause={ok} onresume={ok} onstop={ok} /><figcaption>pausing: Resume cancels the pause</figcaption></figure>
    <figure><RunTransport seq={SEQ.paused} now={NOW} startReason="A sequence is running" onstart={ok} onpause={ok} onresume={ok} onstop={ok} /><figcaption>paused</figcaption></figure>
    <figure><RunTransport seq={SEQ.stopping} now={NOW} startReason="A sequence is running" onstart={ok} onpause={ok} onresume={ok} onstop={ok} /><figcaption>stopping</figcaption></figure>
    <figure><RunTransport seq={SEQ.scheduled} now={NOW} startReason="A start is already scheduled" onstart={ok} onpause={ok} onresume={ok} onstop={ok} /><figcaption>scheduled: Cancel start…</figcaption></figure>
  </div>
  <div class="row top">
    <figure class="pop"><RunTransport seq={SEQ.running} now={NOW} startReason="A sequence is running" onstart={ok} onpause={ok} onresume={ok} onstop={ok} previewStop /><figcaption>Stop… asks: what is discarded, saved and where; the end action not applied</figcaption></figure>
    <figure class="pop"><RunTransport seq={SEQ.idle} now={NOW} suggestedStart={TRANSIT.coverageStart} onstart={ok} onpause={ok} onresume={ok} onstop={ok} previewStartAt="18:40" /><figcaption>Start at a time…: prefilled with the transit's coverage start</figcaption></figure>
    <figure class="pop"><RunTransport seq={SEQ.idle} now={NOW} onstart={ok} onpause={ok} onresume={ok} onstop={ok} previewStartAt="24:70" /><figcaption>an impossible time is refused in words, never clamped</figcaption></figure>
  </div>
</section>

<section data-gallery="w6-readiness" id="w6-readiness">
  <h2>Readiness chip and Preflight <span>levels by mark AND word: OK (dot), Note (the attention mark), Blocks (a no-entry disc); a note never stops Start; the server's sentences verbatim (A64)</span></h2>
  <div class="row">
    <figure><ReadinessChip preflight={PRE.ready} /><figcaption>ready</figcaption></figure>
    <figure><ReadinessChip preflight={PRE.notes} /><figcaption>ready with notes</figcaption></figure>
    <figure><ReadinessChip preflight={PRE.blocked} /><figcaption>blocked</figcaption></figure>
    <figure><ReadinessChip preflight={null} /><figcaption>not checked yet</figcaption></figure>
  </div>
  <div class="row top">
    <figure class="pop"><ReadinessChip preflight={PRE.notes} open preview onrefresh={() => undefined} /><figcaption>Preflight with notes (blocks first, then notes)</figcaption></figure>
    <figure class="pop"><ReadinessChip preflight={PRE.blocked} open preview onrefresh={() => undefined} /><figcaption>Preflight blocked: camera and disk</figcaption></figure>
  </div>
</section>

<section data-gallery="w6-strip" id="w6-strip">
  <h2>Run strip <span>under the Plan toolbar: the progress on a time axis (the fill lags the now marker in a pause), the run in words, the newest sub; after the run, the outcome until dismissed (P14)</span></h2>
  <div class="col">
    <figure><RunStrip seq={SEQ.running} now={NOW} frameTimes={FRAMES} lastSaved={LAST_SAVED} marks={AF_MARKS} onlog={() => undefined} /><figcaption>running</figcaption></figure>
    <figure><RunStrip seq={SEQ.pausing} now={NOW} frameTimes={FRAMES} lastSaved={LAST_SAVED} marks={AF_MARKS} /><figcaption>pausing</figcaption></figure>
    <figure><RunStrip seq={SEQ.pausedMotion} now={NOW} frameTimes={FRAMES} lastSaved={LAST_SAVED} marks={AF_MARKS} /><figcaption>paused for a mount motion, on a cadence step (D2, P16)</figcaption></figure>
    <figure><RunStrip seq={SEQ.autofocus} now={NOW} frameTimes={FRAMES} lastSaved={LAST_SAVED} marks={AF_MARKS} afStep={{ done: 4, total: 9 }} /><figcaption>autofocus pass</figcaption></figure>
    <figure><RunStrip seq={SEQ.stopping} now={NOW} frameTimes={FRAMES} lastSaved={LAST_SAVED} marks={AF_MARKS} /><figcaption>stopping</figcaption></figure>
    <figure><RunStrip seq={SEQ.scheduled} now={NOW} /><figcaption>scheduled (Q-P2)</figcaption></figure>
    <figure><RunStrip seq={SEQ.completed} now={NOW} ondismiss={() => undefined} /><figcaption>ended: completed</figcaption></figure>
    <figure><RunStrip seq={SEQ.stopped} now={NOW} ondismiss={() => undefined} /><figcaption>ended: stopped by the observer</figcaption></figure>
    <figure><RunStrip seq={SEQ.failed} now={NOW} ondismiss={() => undefined} /><figcaption>ended: failed, the server's words</figcaption></figure>
    <figure><RunStrip seq={SEQ.cancelled} now={NOW} ondismiss={() => undefined} /><figcaption>ended: scheduled start cancelled</figcaption></figure>
  </div>
</section>

<section data-gallery="w6-runcard" id="w6-runcard">
  <h2>Run card (Observe) <span>state, n / N, last-frame age against the cadence (hatched and “overdue” past the limit), end time, next autofocus, end of run, Pause, Stop (D2)</span></h2>
  <div class="row top">
    <figure class="rail"><RunCard seq={SEQ.running} {...card} /><figcaption>running</figcaption></figure>
    <figure class="rail"><RunCard seq={SEQ.late} {...card} frameTimes={FRAMES.filter((t) => t <= NOW - 150)} /><figcaption>running, no frame for 2m 30s: overdue</figcaption></figure>
    <figure class="rail"><RunCard seq={SEQ.pausing} {...card} /><figcaption>pausing</figcaption></figure>
    <figure class="rail"><RunCard seq={SEQ.paused} {...card} /><figcaption>paused (no frame expected)</figcaption></figure>
    <figure class="rail"><RunCard seq={SEQ.autofocus} {...card} /><figcaption>autofocus</figcaption></figure>
    <figure class="rail"><RunCard seq={SEQ.stopping} {...card} /><figcaption>stopping</figcaption></figure>
    <figure class="rail"><RunCard seq={SEQ.scheduled} {...card} frameTimes={[]} /><figcaption>scheduled</figcaption></figure>
    <figure class="rail"><RunCard seq={SEQ.completed} {...card} /><figcaption>ended: completed</figcaption></figure>
    <figure class="rail"><RunCard seq={SEQ.stopped} {...card} /><figcaption>ended: stopped</figcaption></figure>
    <figure class="rail"><RunCard seq={SEQ.failed} {...card} /><figcaption>ended: failed</figcaption></figure>
    <figure class="rail"><RunCard seq={SEQ.idle} {...card} frameTimes={[]} /><figcaption>no run</figcaption></figure>
    <figure class="rail pop"><RunCard seq={SEQ.running} {...card} previewStop /><figcaption>Stop… (the spec's dialog, D4)</figcaption></figure>
  </div>
</section>

<section data-gallery="w6-progress" id="w6-progress">
  <h2>RunProgress and the last-frame age <span>frames on a time axis (gaps past the overdue limit split the coverage, autofocus notches, now marker); without frame times, frames as a true proportion; neutral inks</span></h2>
  <div class="row">
    <figure><RunProgress done={FRAMES.length} total={420} start={RUN_SPAN.start} end={RUN_SPAN.end} now={NOW} times={FRAMES} n={FRAMES.length} marks={AF_MARKS} width={240} height={8} /><figcaption>time axis, a pause and an autofocus</figcaption></figure>
    <figure><RunProgress done={FRAMES.length} total={420} width={240} height={8} /><figcaption>no frame times yet: proportion</figcaption></figure>
    <figure><AgeMeter age={12} cadence={32} width={120} /><figcaption>age 12 s, cadence 32 s</figcaption></figure>
    <figure><AgeMeter age={150} cadence={32} width={120} /><figcaption>overdue</figcaption></figure>
  </div>
</section>

<section data-gallery="w6-visibility" id="w6-visibility">
  <h2>Visibility timeline <span>the server's night (A65): twilight washes, altitude in a neutral ink (dashed below the limit), the limit line, the planned run outlined with its subs as a neutral coverage fill, a transit hatched with its baseline edges, now; hover for UTC, local, altitude, airmass</span></h2>
  <div class="col">
    <figure class="viz"><VisibilityTimeline vis={VIS_VAR} target="XX Cyg" run={RUN_SPAN} frames={FRAMES} nFrames={FRAMES.length} now={NOW} offsetMin={offset} {theme} /><figcaption>variable star, run in progress</figcaption></figure>
    <figure class="viz"><VisibilityTimeline vis={VIS_TRANSIT} target="HD 189733" run={TRANSIT_RUN} transit={TRANSIT} now={null} offsetMin={offset} {theme} /><figcaption>transit plan: coverage (baseline edges) and the transit hatched; illustrative times</figcaption></figure>
    <figure class="viz"><VisibilityTimeline vis={VIS_NO_SUN} target="XX Cyg" run={{ start: RUN_SPAN.start - 3600, end: RUN_SPAN.end + 5400 }} now={NOW} offsetMin={offset} {theme} /><figcaption>no Sun samples: one wash outside the night; a run that starts before dusk and runs low, said in words</figcaption></figure>
  </div>
  <div class="row">
    <figure class="viz small"><VisibilityTimeline vis={null} empty={{ kind: 'site' }} onsite={() => undefined} {theme} /><figcaption>no site (never a 0 / 0 curve)</figcaption></figure>
    <figure class="viz small"><VisibilityTimeline vis={null} empty={{ kind: 'source' }} {theme} /><figcaption>no source</figcaption></figure>
    <figure class="viz small"><VisibilityTimeline vis={null} empty={{ kind: 'loading' }} {theme} /><figcaption>loading</figcaption></figure>
    <figure class="viz small"><VisibilityTimeline vis={null} empty={{ kind: 'error', message: 'Set the observing site in Settings to compute altitudes.' }} {theme} /><figcaption>the server's refusal</figcaption></figure>
  </div>
</section>

<section data-gallery="w6-interlock" id="w6-interlock">
  <h2>Mount interlock <span>a mount command refused with 409 run_active during a run: the server's sentence, then the one way through (D2); Cancel sends nothing</span></h2>
  <div class="row top">
    <figure class="pop"><InterlockDialog {lock} preview={pending} /><figcaption>GoTo during a run</figcaption></figure>
    <figure class="pop"><InterlockDialog {lock} preview={{ ...pending, action: 'Park', verb: 'park', message: 'A sequence is running — Park would move the field under it. Pause the run first.' }} /><figcaption>Park during a run</figcaption></figure>
  </div>
</section>

<style>
  section {
    padding: var(--space-5) var(--space-6);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  h2 {
    margin: 0 0 var(--space-4);
    font-size: var(--text-l);
    color: var(--fg);
  }
  h2 span {
    display: block;
    margin-top: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-regular, 400);
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: var(--space-4);
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-5);
    margin-top: var(--space-4);
  }
  .row.top {
    align-items: flex-start;
  }
  .col {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  figure {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  figcaption {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .pop {
    min-height: 240px;
    max-width: 420px;
  }
  .rail {
    width: 400px;
  }
  .viz {
    width: 100%;
  }
  .viz > :global(.vis) {
    flex: none;
    height: 240px;
    border: var(--border-w) solid var(--border-soft);
  }
  .viz.small {
    width: 440px;
  }
  .viz.small > :global(.vis) {
    height: 110px;
  }
</style>
