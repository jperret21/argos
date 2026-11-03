<!--
  Settings › Privacy & diagnostics (02 2.1 "Online services", W8; M31-M32,
  D14, Q-C3, Q-G13, Q-G17). One place to see and stop everything that
  leaves this computer: the online permissions (the same keys as their
  point-of-use toggles: Catalogues, the Planetarium card), then what is
  recorded locally (diagnostic records, log level, log folder, crash
  reports, A6), the support bundle (the shared dialog, A5), and the one
  setting that exposes ARGOS on the network (the Stellarium bridge host,
  with the server's warning, Q-C3).
-->
<script lang="ts">
  import type { CrashReports } from '../../api/types';
  import { useApp } from '../../app/state.svelte';
  import Control from '../../components/Control.svelte';
  import { int } from '../../format/number';
  import { NETWORK_EXPOSURE, PRIVACY_MIRRORS, utcTime } from '../categories';
  import SettingsBlock from '../SettingsBlock.svelte';

  interface Props {
    query?: string;
  }
  let { query = '' }: Props = $props();

  const app = useApp();
  let crashes = $state.raw<CrashReports | null>(null);
  let crashError: string | null = $state(null);
  $effect(() => {
    if (!app.linkOpen) return;
    app.client
      .crashReports()
      .then((c) => (crashes = c))
      .catch((err) => (crashError = err instanceof Error ? err.message : String(err)));
  });
  const newest = $derived(crashes?.reports[0] ?? null);
</script>

<div class="page">
  <!-- In filter mode the catalogue permissions show once, in Catalogues (their home). -->
  <SettingsBlock
    title="Online services"
    caption="Each is used only after an explicit action or a field solve."
    keys={query ? PRIVACY_MIRRORS.filter((k) => !k.startsWith('catalog.')) : PRIVACY_MIRRORS}
    {query}
    hideEmpty={!!query}
  />
  {#if !query}
    <ul class="facts" aria-label="Other network use">
      <li>
        <span class="k">Place search</span>
        <span>OpenStreetMap Nominatim and Open-Meteo, only when you press Search (Observer & site).</span>
      </li>
      <li>
        <span class="k">Reachability</span>
        <span>The Seestar is probed on the local network every 10 s; the internet is checked only when you ask (Connection screen).</span>
      </li>
      <li>
        <span class="k">Documentation</span>
        <span>The Help menu's link opens the website in your browser; nothing else is requested.</span>
      </li>
    </ul>
  {/if}
  <SettingsBlock
    title="Local records"
    caption="Kept on this computer, never sent anywhere."
    keys={['diagnostics.enabled', 'ui.log_level']}
    {query}
    hideEmpty={!!query}
  />
  {#if !query}
    <ul class="facts" aria-label="Logs and crash reports">
      <li>
        <span class="k">Log file</span>
        <span class="mono">{app.appInfo?.paths.log_file ?? 'file logging is off'}</span>
      </li>
      <li>
        <span class="k">Crash reports</span>
        {#if crashError}
          <span>{crashError}</span>
        {:else if !crashes}
          <span>Reading…</span>
        {:else if !crashes.reports.length}
          <span>None.</span>
        {:else}
          <span>
            {int(crashes.reports.length)} {crashes.reports.length === 1 ? 'report' : 'reports'}; newest
            <span class="mono">{utcTime(newest?.t)}</span>
            {newest?.t?.slice(0, 10)}: {newest?.summary}
          </span>
        {/if}
      </li>
    </ul>
    <section class="bundle" aria-labelledby="bundle-title">
      <div class="text">
        <h3 class="title" id="bundle-title">Support bundle</h3>
        <p>A ZIP of redacted logs for a bug report. It stays on this computer until you share it.</p>
      </div>
      <Control
        icon="support-bundle"
        label="Create support bundle…"
        showLabel
        size="s"
        variant="secondary"
        disabledReason={app.linkOpen ? null : 'the ARGOS server is not reachable'}
        onclick={() => (app.supportBundleOpen = true)}
      />
    </section>
  {/if}
  <SettingsBlock
    title="Network exposure"
    caption="127.0.0.1 keeps the Stellarium bridge on this computer."
    keys={NETWORK_EXPOSURE}
    {query}
    hideEmpty={!!query}
  />
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }
  .facts {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    max-width: var(--page-max-w);
    margin: calc(-1 * var(--space-3)) 0 0;
    padding: 0 0 0 var(--space-4);
    list-style: none;
    font-size: var(--text-s);
    color: var(--fg);
  }
  .facts li {
    display: grid;
    grid-template-columns: 112px minmax(0, 1fr);
    gap: var(--space-3);
    line-height: var(--leading-normal);
  }
  .k {
    color: var(--text-muted);
  }
  .mono {
    font-family: var(--font-mono);
    font-size: var(--text-s);
    overflow-wrap: anywhere;
  }
  .bundle {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    max-width: var(--page-max-w);
    padding: var(--space-3) var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .text {
    flex: 1;
    min-width: 0;
  }
  .title {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
  }
  .bundle p {
    margin: 2px 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
