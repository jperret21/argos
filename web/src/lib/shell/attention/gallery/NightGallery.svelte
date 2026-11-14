<!--
  Component gallery, wave 6b, the night (development only, part of /?gallery=1): the
  attention levels, the status-bar chip and its list, the Run card's items, Watch at
  1 440 × 900 and 1 280 × 800 in its states (the frames are size containers, so Watch
  lays out as in a window of that size), and the end-of-night wrap-up. Deterministic
  fixtures (fixtures.ts, synthetic). Sections are [data-gallery="w6b-<name>"] for element
  screenshots; each Watch frame is [data-gallery="w6b-watch-<state>"].
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import type { Theme } from '../../../app/theme';
  import LightCurvePlot from '../../../charts/lightcurve/LightCurvePlot.svelte';
  import { makeRun } from '../../../charts/lightcurve/gallery/fixtures';
  import Card from '../../../components/Card.svelte';
  import Popover from '../../../components/Popover.svelte';
  import StatusBadge from '../../../components/StatusBadge.svelte';
  import WrapUp from '../../../run/wrapup/WrapUp.svelte';
  import Watch from '../../Watch.svelte';
  import { AttentionStore } from '../attention.svelte';
  import AttentionCenter from '../AttentionCenter.svelte';
  import AttentionChip from '../AttentionChip.svelte';
  import AttentionList from '../AttentionList.svelte';
  import AttentionMark from '../AttentionMark.svelte';
  import { chipView, LEVEL_WORD } from '../model';
  import RunAttention from '../RunAttention.svelte';
  import { AlertSound } from '../sound';
  import { CADENCE, ITEMS, LIST_ALL, NOW, NOW_SILENT, RESULT, WATCH, WATCH_HFD, WATCH_IDLE, WATCH_PAUSED, WATCH_SILENT, WRAP } from './fixtures';

  let theme = $state<Theme>('observatory');
  onMount(() => {
    const read = () => (theme = (document.documentElement.dataset.theme as Theme) || 'observatory');
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  });

  const ok = () => Promise.resolve();
  const none = () => undefined;
  // A store fed with the fixtures (no server; a silent sound so nothing plays).
  const silent = new AlertSound(() => {
    throw new Error('gallery: no audio');
  });
  const store = new AttentionStore({ sound: silent, clock: () => NOW });
  store.seed(LIST_ALL);
  store.armed = true;

  // One light-curve store per Watch frame (a plot owns its store's view).
  const curve = () => makeRun({ n: 160, seed: 3, cadence: CADENCE, phase0: 0.82 });
  const runs = { running: curve(), hfd: curve(), hfd1280: curve(), silent: curve(), paused: makeRun({ n: 160, seed: 3, cadence: CADENCE, phase0: 0.82, check: null }) };
  const clockAt = (t: number) => () => t;
  const LEVELS = ['critical', 'attention', 'info'] as const;
  // The real overlay (layer, portal, keys, wake lock), opened from a button.
  let live = $state(false);
  let liveDim = $state<100 | 60 | 30>(100);
  let liveLog = $state<string[]>([]);
  const note = (s: string): void => {
    liveLog = [...liveLog.slice(-5), s];
  };
</script>

<section data-gallery="w6b-levels" id="w6b-levels">
  <h2>Attention levels <span>BRAND §8: one SHAPE per level, always with the word — Critical a filled --danger disc, Attention an upright mark (a bar over a dot), Info a hollow ring; never a triangle (the check star). Drawn in CSS at any size.</span></h2>
  <div class="row">
    {#each [10, 16, 44] as size (size)}
      <figure>
        <div class="levels">
          {#each LEVELS as l (l)}
            <span class="lv"><AttentionMark level={l} {size} /><span style:font-size="{Math.max(12, size * 0.6)}px">{LEVEL_WORD[l]}</span></span>
          {/each}
        </div>
        <figcaption>{size} px</figcaption>
      </figure>
    {/each}
  </div>
</section>

<section data-gallery="w6b-chip" id="w6b-chip">
  <h2>Status-bar attention chip <span>the most urgent open item's mark and word, the count of items needing the observer, its headline; a quiet glyph when everything is acknowledged; nothing with no item. Critical: a 2 px --danger edge, never a red fill, no blinking.</span></h2>
  <div class="bars">
    <figure><div class="bar"><span class="key">Run 160 / 195</span><AttentionChip chip={chipView([ITEMS.hfd, ITEMS.started])} /></div><figcaption>one Attention item</figcaption></figure>
    <figure><div class="bar"><span class="key">Run 160 / 195</span><AttentionChip chip={chipView(LIST_ALL)} /></div><figcaption>Critical first, 2 open (the HFD rise behind it; a cleared and an acknowledged item need nobody)</figcaption></figure>
    <figure><div class="bar"><span class="key">Run 160 / 195</span><AttentionChip chip={chipView(LIST_ALL)} compact /></div><figcaption>compact (1 280 px with a run chip): the headline folds into the tooltip</figcaption></figure>
    <figure><div class="bar"><span class="key">Run 160 / 195</span><AttentionChip chip={chipView([ITEMS.starsAcked, ITEMS.started])} /></div><figcaption>everything acknowledged: the list stays one click away</figcaption></figure>
    <figure><div class="bar"><span class="key">Run 1 / 195</span><AttentionChip chip={chipView([])} /><span class="key">(no chip: no item yet)</span></div><figcaption>no item</figcaption></figure>
    <figure><div class="bar"><span class="key">Run 160 / 195</span><AttentionChip chip={chipView([ITEMS.hfd])} expanded /></div><figcaption>expanded (its list open)</figcaption></figure>
  </div>
</section>

<section data-gallery="w6b-list" id="w6b-list">
  <h2>Attention list <span>anchored on the chip (440 px): level by mark and word, when and which frame, the rule's numbers, still holding or cleared, the suggested view, Acknowledge (shared by every client); Info needs none; sound Off / Soft / Normal (choosing Soft or Normal plays the tones and arms the audio)</span></h2>
  <div class="row top">
    <figure class="pop"><AttentionCenter {store} previewOpen onsettings={none} onaction={none} /><figcaption>the run's list: a Critical (no new frame), the HFD rise, a cleared comparisons item, an acknowledged one, the run's start</figcaption></figure>
    <figure class="pop">
      <Popover open preview title="Attention" width={440}>
        <AttentionList items={[ITEMS.tracker, ITEMS.hfd]} pending={new Set([ITEMS.hfd.id])} sound="soft" armed={false} error="No attention item 'comps_low-r20260925T200453Z-9'." onack={ok} onaction={none} onsettings={none} />
      </Popover>
      <figcaption>sound on but not armed yet (browser rule); an acknowledgement on its way; a refusal in the server's words; the tracker lost item (S48 lock check)</figcaption>
    </figure>
    <figure class="pop">
      <Popover open preview title="Attention" width={440}>
        <AttentionList items={[]} sound="off" onack={ok} onsettings={none} />
      </Popover>
      <figcaption>empty: the rules it runs, in words</figcaption>
    </figure>
    <figure class="pop">
      <Popover open preview title="Attention" width={440}>
        <AttentionList items={[]} sound="normal" unsupported onack={ok} />
      </Popover>
      <figcaption>an older server without the rules</figcaption>
    </figure>
  </div>
</section>

<section data-gallery="w6b-runcard" id="w6b-runcard">
  <h2>Run card items <span>the open items, most urgent first, at most three; each with its view and Acknowledge; "n more" opens the list; nothing when the run is fine</span></h2>
  <div class="row top">
    <figure class="rail"><Card title="Run" icon="nav-sequencer"><RunAttention items={[ITEMS.hfd, ITEMS.started]} onack={ok} onaction={none} onlist={none} /></Card><figcaption>one item</figcaption></figure>
    <figure class="rail"><Card title="Run" icon="nav-sequencer"><RunAttention items={[ITEMS.silence, ITEMS.deviceLost, ITEMS.tracker, ITEMS.hfd, ITEMS.comps, ITEMS.started]} pending={new Set([ITEMS.silence.id])} max={3} onack={ok} onaction={none} onlist={none} /></Card><figcaption>four open (two Critical): three shown, "1 more"; an acknowledgement on its way; the cleared comparisons item is not shown</figcaption></figure>
  </div>
</section>

<section data-gallery="w6b-watch" id="w6b-watch">
  <h2>Watch <span>owner D3, read from 2 m: 88 / 66 / 48 / 30 px, values fitted to their tile; the attention row keeps the pulse (age, n / N); dim 100 / 60 / 30 % by a brightness filter (red stays red); Pause by hold; only W, Esc, ? and Mod+K act; the screen wake lock while shown</span></h2>
  <div class="row live">
    <button type="button" class="open-live" onclick={() => (live = true)}>Open Watch (live overlay)</button>
    <span class="log" data-watch-log>{liveLog.join(' · ') || 'keys: W or Esc close, ? help, Mod+K palette; any other key does nothing'}</span>
  </div>
  {#if live}
    <Watch data={WATCH_HFD} now={NOW} top={ITEMS.hfd} onack={() => note('ack')} bind:dim={liveDim} onclose={() => ((live = false), note('closed'))} onpause={() => note('pause')} onhelp={() => note('help')} onpalette={() => note('palette')} onarm={() => note('armed')} {theme} />
  {/if}
  <div class="frames">
    <figure data-gallery="w6b-watch-running"><div class="frame f1440"><Watch embedded data={WATCH} now={NOW} onclose={none} onpause={ok} {theme}>{#snippet curve()}<LightCurvePlot store={runs.running.store} variant="watch" toolbar={false} expecting={true} clock={clockAt(runs.running.last + 12)} {theme} />{/snippet}</Watch></div><figcaption>1 440 × 900 · running, nothing open</figcaption></figure>
    <figure data-gallery="w6b-watch-attention"><div class="frame f1440"><Watch embedded data={WATCH_HFD} now={NOW} top={ITEMS.hfd} onack={ok} onclose={none} onpause={ok} {theme}>{#snippet curve()}<LightCurvePlot store={runs.hfd.store} variant="watch" toolbar={false} expecting={true} clock={clockAt(runs.hfd.last + 12)} {theme} />{/snippet}</Watch></div><figcaption>1 440 × 900 · the HFD rule: the item replaces the first row, the pulse stays at its right end</figcaption></figure>
    <figure data-gallery="w6b-watch-attention-1280"><div class="frame f1280"><Watch embedded data={WATCH_HFD} now={NOW} top={ITEMS.hfd} onack={ok} onclose={none} onpause={ok} {theme} pinPause={{ phase: 'holding', progress: 0.45 }}>{#snippet curve()}<LightCurvePlot store={runs.hfd1280.store} variant="watch" toolbar={false} expecting={true} clock={clockAt(runs.hfd1280.last + 12)} {theme} />{/snippet}</Watch></div><figcaption>1 280 × 800 · the same: the headline whole (fitted), Pause held at 45 %</figcaption></figure>
    <figure data-gallery="w6b-watch-critical-1280"><div class="frame f1280"><Watch embedded data={WATCH_SILENT} now={NOW_SILENT} top={ITEMS.silence} ackBusy onack={ok} onclose={none} onpause={ok} {theme}>{#snippet curve()}<LightCurvePlot store={runs.silent.store} variant="watch" toolbar={false} expecting={true} clock={clockAt(runs.silent.last + 140)} {theme} />{/snippet}</Watch></div><figcaption>1 280 × 800 · Critical, no new frame: a 4 px outline, no fill; the age muted (late), Acknowledge on its way</figcaption></figure>
    <figure data-gallery="w6b-watch-paused"><div class="frame f1440"><Watch embedded data={WATCH_PAUSED} now={NOW} dim={60} onclose={none} {theme}>{#snippet curve()}<LightCurvePlot store={runs.paused.store} variant="watch" toolbar={false} expecting={false} clock={clockAt(runs.paused.last + 12)} {theme} />{/snippet}</Watch></div><figcaption>1 440 × 900 · paused, no check star, dimmed to 60 %</figcaption></figure>
    <figure data-gallery="w6b-watch-idle"><div class="frame f1280"><Watch embedded data={WATCH_IDLE} now={NOW} dim={30} onclose={none} {theme} previewWake="unsupported" /></div><figcaption>1 280 × 800 · no run, dimmed to 30 %, a browser without a wake lock</figcaption></figure>
  </div>
</section>

<section data-gallery="w6b-wrapup" id="w6b-wrapup">
  <h2>End-of-night wrap-up <span>owner D2: the outcome, what the mount does now, darks and biases of tonight's lights with the time at tonight's measured cost per frame and "Prepare in Plan", Park by hold, the session folder</span></h2>
  <div class="row top">
    <figure class="rail">
      <Card title="Run" icon="nav-sequencer" status={complete}>
        <WrapUp result={RESULT.completed} wrap={WRAP.completed} onprepare={ok} onpark={ok} oncopy={none} onattention={none} onplan={none} ondismiss={none} />
      </Card>
      <figcaption>complete, tracking still on: 20 darks and 30 biases at tonight's cost per frame, Park by hold, the folder's size</figcaption>
    </figure>
    <figure class="rail">
      <Card title="Run" icon="nav-sequencer" status={failed}>
        <WrapUp result={RESULT.failed} wrap={WRAP.failed} onprepare={ok} onpark={ok} oncopy={none} onattention={none} ondismiss={none} pinPark={{ phase: 'holding', progress: 0.6 }} />
      </Card>
      <figcaption>stopped on an error (the server's sentence verbatim); two exposures: two dark groups; Park held at 60 %</figcaption>
    </figure>
    <figure class="rail">
      <Card title="Run" icon="nav-sequencer" status={stopped}>
        <WrapUp result={RESULT.stopped} wrap={WRAP.stopped} onprepare={() => Promise.reject(new Error('The plan is locked while the sequence runs.'))} oncopy={none} ondismiss={none} />
      </Card>
      <figcaption>stopped by the observer, parked by the end action; no Dark slot (the server's note: the lid on); 20 darks already taken tonight; a refused Prepare in the server's words (press it)</figcaption>
    </figure>
    <figure class="rail">
      <Card title="Run" icon="nav-sequencer" status={complete}>
        <WrapUp result={RESULT.completed} wrap={null} onprepare={ok} onpark={ok} mount={{ state: 'tracking', tracking: true }} ondismiss={none} />
      </Card>
      <figcaption>the first moment of the end: the server still measures the last frames</figcaption>
    </figure>
  </div>
</section>

{#snippet complete()}<StatusBadge tone="ok" label="Complete" />{/snippet}
{#snippet failed()}<StatusBadge tone="error" label="Failed" />{/snippet}
{#snippet stopped()}<StatusBadge tone="idle" label="Stopped" />{/snippet}

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
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-5);
  }
  .row.top {
    align-items: flex-start;
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
    max-width: 440px;
  }
  .levels {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    padding: var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .lv {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--fg);
  }
  .bars {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(460px, 1fr));
    gap: var(--space-4);
  }
  .bar {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: var(--statusbar-h);
    padding: 0 var(--space-3);
    border-top: var(--border-w) solid var(--border-soft);
    background: var(--bg-2);
    font-size: var(--text-xs);
  }
  .key {
    color: var(--text-muted);
    white-space: nowrap;
  }
  .pop {
    min-height: 240px;
  }
  .rail {
    width: 400px;
  }
  .live {
    align-items: center;
    margin-bottom: var(--space-4);
  }
  .open-live {
    height: var(--control-h-s);
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--surface);
    color: var(--fg);
    cursor: pointer;
  }
  .log {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .frames {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }
  .frame {
    position: relative;
    overflow: hidden;
    border: var(--border-w) solid var(--border-soft);
  }
  .f1440 {
    width: 1440px;
    height: 900px;
  }
  .f1280 {
    width: 1280px;
    height: 800px;
  }
</style>
