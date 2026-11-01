<!--
  Bottom drawer of Observe: Log (every section has it, L), Light curve (the
  same component as the Run band, for the other modes), Conditions (the
  timeline: HFD, stars, sky as small multiples sharing the run window and
  one crosshair, D6) and Ensemble. Opening it shrinks the band first, never
  the image (BRAND 11.1).
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import IconButton from '../../../lib/components/IconButton.svelte';
  import LightCurve from '../charts/LightCurve.svelte';
  import Trend from '../charts/Trend.svelte';
  import { DRAWER_TABS } from '../model/layout';
  import { sim, ws } from '../model/app.svelte';
  import { NAMED_STARS } from '../model/field';
  import { utc } from '../model/format';
  import { median, RUN } from '../model/night';
  import { RULES } from '../model/rules';

  const tab = $derived(ws.layout.drawerTab);
  const lines = $derived(sim.log.filter((l) => l.t <= sim.now).slice(-200).reverse());
  const recs = $derived(sim.records);
  const xs = $derived(recs.map((r) => r.t));
  const end = $derived(Number.isFinite(sim.endsAt) ? Math.max(sim.endsAt, sim.now) : RUN.start + 3 * 3600);
  const hfd0 = $derived(recs.length >= 20 ? median(recs.slice(0, 20).map((r) => r.hfd)) : null);
  const stars0 = $derived(recs.length >= 20 ? median(recs.slice(0, 20).map((r) => r.stars)) : null);
  const hfdRule = $derived(sim.attention.find((a) => a.rule === 'HFD rise'));
  const flagged = $derived.by((): [number, number][] => {
    if (!hfdRule?.frame) return [];
    const first = sim.night[hfdRule.frame - 3];
    return first ? [[first.t - 20, sim.now]] : [];
  });
  const check = NAMED_STARS.find((s) => s.role === 'check');
  const comps = NAMED_STARS.filter((s) => s.role === 'comparison');
</script>

<section class="drawer" aria-label="Drawer">
  <header>
    <div class="tabs" role="tablist" aria-label="Drawer tabs">
      {#each DRAWER_TABS as t (t.id)}
        <button
          type="button"
          role="tab"
          aria-selected={tab === t.id}
          class:on={tab === t.id}
          onclick={() => ws.edit((l) => (l.drawerTab = t.id))}
        >
          <Icon name={t.icon} size={16} />{t.label}
        </button>
      {/each}
    </div>
    <span class="grow"></span>
    <IconButton icon="close" label="Close the drawer" shortcut="D" size="s" variant="ghost" onclick={() => ws.toggleDrawer()} />
  </header>
  <div class="content">
    {#if tab === 'log'}
      <ol class="log num">
        {#each lines as l, i (i)}
          <li class="lvl-{l.level.toLowerCase()}">
            <span class="t">{utc(l.t)}</span>
            <span class="lv">{l.level}</span>
            <span class="src">{l.source}</span>
            <span class="txt">{l.text}</span>
          </li>
        {/each}
      </ol>
    {:else if tab === 'curve'}
      {#if recs.length}
        <LightCurve records={recs} start={RUN.start} {end} now={sim.running ? sim.now : null} {flagged} variant="drawer" targetName="RR Lyr" checkName={check?.name ?? null} errors={ws.errorBars} />
      {:else}
        <p class="empty">The light curve appears with the first frame of a run (Plan › Start).</p>
      {/if}
    {:else if tab === 'conditions'}
      {#if recs.length}
        <div class="facets">
          <div><Trend {xs} ys={recs.map((r) => r.hfd)} start={RUN.start} {end} now={sim.running ? sim.now : null} baseline={hfd0} threshold={hfd0 ? { y: RULES.hfdFactor * hfd0, label: `rule ${RULES.hfdFactor}× baseline` } : null} {flagged} timeAxis={false} sync="cond" label="HFD" unit="px" /></div>
          <div><Trend {xs} ys={recs.map((r) => r.stars)} start={RUN.start} {end} now={sim.running ? sim.now : null} baseline={stars0} digits={0} timeAxis={false} sync="cond" label="Stars" unit="count" /></div>
          <div><Trend {xs} ys={recs.map((r) => r.sky)} start={RUN.start} {end} now={sim.running ? sim.now : null} digits={0} sync="cond" label="Sky" unit="ADU" /></div>
        </div>
      {:else}
        <p class="empty">Conditions appear with the first frame of a run.</p>
      {/if}
    {:else}
      <table class="ens">
        <thead><tr><th>Role</th><th>Star</th><th class="n">V</th><th class="n">B−V</th><th class="n">Scatter</th><th class="n">Used</th><th>Status</th></tr></thead>
        <tbody>
          {#each comps as c, i (c.id)}
            <tr><td>comparison</td><td class="m">{c.name}</td><td class="n">{c.v.toFixed(2)}</td><td class="n">{c.bv?.toFixed(2)}</td><td class="n">{(0.019 + i * 0.002).toFixed(3)}</td><td class="n">{recs.length ? `${Math.round(100 - i * 6)} %` : '—'}</td><td>{recs.length >= 10 ? 'stable' : 'waiting'}</td></tr>
          {/each}
          {#if check}<tr><td>check</td><td class="m">{check.name}</td><td class="n">{check.v.toFixed(2)}</td><td class="n">{check.bv?.toFixed(2)}</td><td class="n">0.018</td><td class="n">—</td><td>check</td></tr>{/if}
        </tbody>
      </table>
    {/if}
  </div>
</section>

<style>
  .drawer {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg);
  }
  header {
    display: flex;
    align-items: center;
    height: var(--lab-band-header-h);
    padding: 0 var(--space-1) 0 var(--space-2);
    flex: none;
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .tabs {
    display: flex;
    gap: 2px;
  }
  .tabs button {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 24px;
    padding: 0 var(--space-3) 0 var(--space-2);
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-s);
    cursor: pointer;
  }
  .tabs button :global(.icon) {
    color: var(--fg-muted);
  }
  .tabs button.on {
    background: var(--toggled-bg);
    border-color: var(--border);
    color: var(--fg);
  }
  .grow {
    flex: 1;
  }
  .content {
    flex: 1;
    min-height: 0;
    overflow: auto;
  }
  .log {
    list-style: none;
    margin: 0;
    padding: var(--space-1) 0;
    font-size: var(--text-s);
    background: var(--bg-2);
    min-height: 100%;
  }
  .log li {
    display: grid;
    grid-template-columns: 70px 52px 92px 1fr;
    gap: var(--space-3);
    padding: 1px var(--space-3);
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
    color: var(--fg);
  }
  .t,
  .src {
    color: var(--text-muted);
  }
  .lv {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    line-height: 18px;
  }
  .lvl-cmd .lv {
    color: var(--log-cmd);
  }
  .lvl-info .lv {
    color: var(--log-info);
  }
  .lvl-ok .lv {
    color: var(--log-ok);
  }
  .lvl-warn .lv {
    color: var(--log-warning);
  }
  .lvl-error .lv {
    color: var(--log-error);
  }
  .facets {
    display: grid;
    grid-template-rows: 1fr 1fr 1.25fr;
    height: 100%;
  }
  .facets > div {
    min-height: 0;
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .empty {
    margin: 0;
    padding: var(--space-4);
    color: var(--text-muted);
  }
  .ens {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-s);
  }
  .ens th {
    height: 26px;
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-align: left;
    text-transform: uppercase;
  }
  .ens td {
    height: var(--lab-row-h);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg);
  }
  .ens .n {
    text-align: right;
    font-family: var(--font-mono);
  }
  .ens .m {
    font-family: var(--font-mono);
  }
</style>
