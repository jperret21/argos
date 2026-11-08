<!--
  Exposure check (promoted from the exposure part of
  src/lab/workspace/observe/bands/FramingBand.svelte, web/lab/PROPOSAL.md 3.1 and 6, W3):
  "check the peak, not the picture". The peaks of the brightest stars of the frame on
  screen (frame worker, viewer/framestats.ts) as TRUE-LENGTH bars from 0 to full scale
  (65 535 ADU), with the profile's linearity limit and full well marked on every bar;
  a star at the ADC's top code says "clipped", one above the linearity limit "non-linear"
  (a word and an edge, never colour alone). Never an "OK" badge.

  Facts under the bars: pixels at the top code (clipped by the ADC), the sky, and the
  server's metrics of the same frame (HFD, FWHM, stars: frame_metrics, A26, measured by
  the core on the full frame). A value that belongs to another frame is never shown
  unlabelled: the list keeps the last measured peaks, always at the same emphasis, with a
  stamp naming their frame and how far behind the frame on screen it is ("#34 · 1 frame
  behind"); the list keeps its height whatever arrives, so nothing jumps or blinks
  (design review of wave 3). Two or more stars at the top code are one line ("3 brightest
  stars clipped"), drawn as a solid full bar with a hard end cap and the word; the
  unclipped peaks follow with their true lengths.
-->
<script lang="ts">
  import { fixed, int } from '../../format/number';
  import { FULL_SCALE, type ExposureCheck } from './exposure';

  interface Props {
    check: ExposureCheck;
    /** Linearity limit and full well in ADU (for the scale caption). */
    linearityAdu?: number | null;
    fullWellAdu?: number | null;
    /** The frame worker is unavailable in this engine. */
    unsupported?: boolean;
  }

  let { check, linearityAdu = null, fullWellAdu = null, unsupported = false }: Props = $props();

  const WORDS = { ok: '', nonlinear: 'non-linear', clipped: 'clipped' } as const;
  const m = $derived(check.metrics);
  const dash = '—';
  const ROW_H = 14; // one line: 8 px bar, 6 px gap
  const lines = $derived(check.rows.length + (check.clippedGroup ? 1 : 0));
  const stamp = $derived(
    check.peaksSeq === null
      ? null
      : check.lag === 0
        ? `#${int(check.peaksSeq)} · this frame`
        : `#${int(check.peaksSeq)} · ${check.lag} frame${check.lag === 1 ? '' : 's'} behind`,
  );
</script>

<div class="check">
  <div class="list" style:min-height="{check.capacity * ROW_H}px">
  {#if lines}
    <ul aria-label="Brightest stars of frame #{check.peaksSeq}, peak against full scale">
      {#if check.clippedGroup}
        <li class="clipped group">
          <span class="who num">{check.clippedGroup}×</span>
          <span class="meter" role="img" aria-label="{check.clippedGroup} brightest stars at the ADC's top code: clipped">
            <i class="fill" style:width="100%"></i>
          </span>
          <span class="val num">{int(check.topCode ?? FULL_SCALE)}</span>
          <span class="word">clipped</span>
        </li>
      {/if}
      {#each check.rows as r (r.rank)}
        <li class={r.state}>
          <span class="who num">#{r.rank}</span>
          <span class="meter" role="img" aria-label="Star {r.rank}: peak {int(r.peak)} of {int(FULL_SCALE)} ADU{r.state !== 'ok' ? `, ${WORDS[r.state]}` : ''}">
            <i class="fill" style:width="{r.frac * 100}%"></i>
            {#if check.linearity !== null}<i class="tick lin" style:left="{check.linearity * 100}%"></i>{/if}
            {#if check.fullWell !== null}<i class="tick well" style:left="{check.fullWell * 100}%"></i>{/if}
          </span>
          <span class="val num">{r.state === 'clipped' ? 'clipped' : int(r.peak)}</span>
          <span class="word">{r.state === 'nonlinear' ? 'non-lin.' : ''}</span>
        </li>
      {/each}
    </ul>
  {:else}
    <p class="none">
      {#if unsupported}
        Star peaks need a worker thread, which this browser refused.
      {:else if !check.current && check.topCode !== null}
        Measuring the star peaks of this frame…
      {:else}
        No star above 5 σ in this frame: its brightest pixel is the frame maximum.
      {/if}
    </p>
  {/if}
  </div>
  <!-- One line, never wrapped or cut: the frame stamp and the two marks; the bars' scale
       (0 … 65 535 ADU) is the tooltip. -->
  <p class="scale num" title="Bars from 0 to {int(FULL_SCALE)} ADU (full scale)">
    <span class="stamp">{stamp ?? 'measuring…'}</span>
    {#if linearityAdu !== null}<span class="k"><i class="lg lin" aria-hidden="true"></i>lin. {int(linearityAdu)}</span>{/if}
    {#if fullWellAdu !== null}<span class="k"><i class="lg" aria-hidden="true"></i>well {int(fullWellAdu)}</span>{/if}
  </p>
  <dl class="facts num" title={m ? `Server metrics of frame #${m.seq}${check.metricsCurrent ? ' (this frame)' : ', the frame on screen is being measured'}` : undefined}>
    <div>
      <dt>Clipped</dt>
      <dd class:warn={!!check.clipped}>{check.clipped === null ? dash : `${int(check.clipped)} px`}</dd>
    </div>
    <div>
      <dt>Sky</dt>
      <dd>{check.sky === null ? dash : `${int(Math.round(check.sky))} ADU`}</dd>
    </div>
    <div>
      <dt>HFD</dt>
      <dd>{m?.hfd_px != null ? `${fixed(m.hfd_px, 2)} px` : dash}</dd>
    </div>
    <div>
      <dt>FWHM</dt>
      <dd>{m?.fwhm_px != null ? `${fixed(m.fwhm_px, 2)} px` : dash}</dd>
    </div>
    <div>
      <dt>Stars</dt>
      <dd>{m?.star_count != null ? int(m.star_count) : dash}</dd>
    </div>
  </dl>
</div>

<style>
  .check {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  li {
    display: grid;
    grid-template-columns: 22px minmax(0, 1fr) 56px 44px;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-xs);
  }
  .who {
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }
  /* A true-length bar from zero to full scale. */
  .meter {
    position: relative;
    height: 8px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: 1px;
    background: var(--bg);
  }
  .fill {
    position: absolute;
    inset: 0 auto 0 0;
    background: var(--fg-muted);
  }
  .tick {
    position: absolute;
    top: -3px;
    bottom: -3px;
    width: 0;
    border-left: 1px solid var(--fg);
  }
  .tick.lin {
    border-left-style: dashed;
  }
  /* Clipped: a solid full-length bar with a hard end cap, and the word; no amber per row
     and no hatching (hatching means a period or a stale state, D11). */
  .clipped .meter {
    border-color: var(--fg);
  }
  .clipped .fill {
    background: var(--fg-muted);
    border-right: 2px solid var(--fg);
  }
  .val {
    color: var(--fg);
    text-align: right;
    font-size: var(--text-s);
  }
  .clipped .val,
  .word {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .word {
    font-size: var(--text-2xs);
  }
  .scale {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }
  .scale {
    display: flex;
    flex-wrap: nowrap;
    gap: 0 var(--space-3);
    white-space: nowrap;
    overflow: hidden;
  }
  .stamp {
    color: var(--fg);
  }
  .scale .k {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  /* The legend of the marks drawn on the bars: dashed = linearity limit, solid = full well. */
  .lg {
    display: inline-block;
    width: 0;
    height: 10px;
    border-left: 1px solid var(--fg);
  }
  .lg.lin {
    border-left-style: dashed;
  }
  .none {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-relaxed);
  }
  .facts {
    display: grid;
    grid-template-columns: repeat(5, auto);
    justify-content: space-between;
    gap: var(--space-1) var(--space-3);
    margin: auto 0 0;
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .facts div {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  dt {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  dd {
    margin: 0;
    color: var(--fg);
    font-size: var(--readout-s);
    white-space: nowrap;
  }
  /* The list keeps its height (capacity lines): nothing below it moves. */
  .list {
    flex: none;
  }
  dd.warn {
    font-weight: var(--weight-medium);
  }
</style>
