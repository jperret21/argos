<!--
  Site against mount (web/lab/PROPOSAL.md section 7; protocol.md "Site
  check"; functional-spaces "Site against mount"). The mount reports where
  it points from ITS OWN site and clock (the Seestar takes them from the
  phone); ARGOS computes airmass, BJD and the FITS SITELAT / SITELONG from
  the Settings site. On 2026-09-25 the Settings site was Berkeley while the
  telescope was in France: the mount put RR Lyr at 75.4°, the Settings site
  at 13.8°, and that run's airmass and AAVSO AMASS are wrong.

  The server compares whole directions (never the altitude alone) and
  publishes the record in `status.site_check` and `site_check` events; this
  panel shows it next to the site fields: the verdict in words, both
  altitudes (and azimuths), the angle between them against the 5° limit,
  when and why it was checked, and the mount's own site when the driver
  says it. A mismatch carries the Attention chip (StatusBadge level
  "attention", the one alert vocabulary of the product) and a left bar, with
  the consequence spelled out (it cannot be missed: also the rail mark, the
  Instrument card and the status bar, all with the same mark). [Check now] re-checks from the latest mount reading.
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import Control from '../components/Control.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { siteCheckView } from './categories';

  const app = useApp();
  const view = $derived(siteCheckView(app.siteCheck));
  const checkReason = $derived(
    !app.linkOpen ? 'the ARGOS server is not reachable' : !app.mountReady ? 'connect the mount first (Connection, F1)' : null,
  );
</script>

<section class="site-check tone-{view.tone}" aria-labelledby="site-check-title" role={view.tone === 'mismatch' ? 'alert' : undefined}>
  <div class="head">
    <h4 class="title" id="site-check-title">Site against mount</h4>
    {#if view.tone === 'mismatch'}
      <StatusBadge variant="alert" level="attention" label={view.word} />
    {:else}
      <StatusBadge tone={view.tone === 'ok' ? 'ok' : 'idle'} label={view.word} />
    {/if}
    <span class="spacer"></span>
    <Control
      icon="refresh"
      label="Check now"
      showLabel
      size="xs"
      variant="ghost"
      tooltip="top"
      tooltipText="Compare the Settings site with the mount's latest reading now"
      busy={!!app.busy.siteCheck}
      disabledReason={checkReason}
      onclick={() => void app.checkSite()}
    />
  </div>
  {#if view.tone === 'mismatch'}
    <!-- One paragraph, the verdict first in bold: the chip and the bar already flag it (space, BRAND 11.1). -->
    <p class="consequence">
      <strong class="headline">The Settings site disagrees with where the mount points.</strong>
      Airmass, BJD and the FITS SITELAT / SITELONG of every frame use the Settings site. If the telescope is
      elsewhere, correct the site above; if the site is right, check the location of the Seestar app.
    </p>
  {/if}
  {#if view.tone === 'unknown' || !view.rows.length}
    <!-- The server's line says why nothing was compared; once compared, the rows say it all. -->
    <p class="message">{view.message}</p>
  {/if}
  {#if view.rows.length}
    <dl class="rows">
      {#each view.rows as r (r.label)}
        <dt>{r.label}</dt>
        <dd class="num">{r.value}</dd>
      {/each}
    </dl>
  {/if}
  {#if view.driver || view.when}
    <p class="foot">
      {#if view.when}<span class="num">Checked {view.when}</span>{/if}
      {#if view.driver}<span>{view.driver}</span>{/if}
    </p>
  {/if}
</section>

<style>
  .site-check {
    max-width: var(--page-max-w);
    padding: var(--space-3) var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  /* A mismatch: the neutral edge stays, a 3 px --warning bar on the left (as
     the Connection callout) and the Attention chip are the only warning ink.
     A whole frame in --warning reads as brass in Observatory and Charcoal
     (design review: 2 742 px), i.e. "selected", not "wrong". */
  .tone-mismatch {
    box-shadow: inset 3px 0 0 var(--warning);
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: 26px;
  }
  .title {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
  }
  .spacer {
    flex: 1;
  }
  p {
    margin: 0;
  }
  .headline {
    color: var(--fg);
    font-weight: var(--weight-semibold);
  }
  .consequence {
    margin-top: var(--space-2);
    color: var(--fg);
    font-size: var(--text-s);
    line-height: var(--leading-normal);
  }
  .message {
    margin-top: var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
  }
  .rows {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: 2px var(--space-4);
    margin: var(--space-2) 0 0;
    font-size: var(--text-s);
  }
  dt {
    color: var(--text-muted);
  }
  dd {
    margin: 0;
    color: var(--fg);
  }
  .foot {
    display: flex;
    flex-wrap: wrap;
    gap: 0 var(--space-4);
    margin-top: var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
