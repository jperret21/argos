<!--
  Settings › About (01 2.3.5, 02 W8; M14, D14, Q-G8, Q-G15): the only About
  of the web UI (the Help menu's "About ARGOS" opens it). The mark comes
  from brand/argos-mark.svg (the generator's output, currentColor), never
  redrawn; the wordmark is "ARGOS" in Plex Sans 600. Version line, what
  ARGOS is, credits (the server's list from GET /api/app/info, then the
  front-end's own: IBM Plex under the OFL, Svelte, uPlot; Tauri in the
  desktop app), copyright and licence, the folders in use. [Copy version
  info] copies a few lines for a bug report (no path, no address);
  [Documentation & website] opens the site in the browser: an explicit
  request, the only network use of this page.
-->
<script lang="ts">
  import mark from '../../../design/brand/argos-mark.svg?raw';
  import { isDesktopApp } from '../../app/shortcuts';
  import { useApp } from '../../app/state.svelte';
  import Control from '../../components/Control.svelte';

  const app = useApp();
  const info = $derived(app.appInfo);
  const desktop = isDesktopApp();

  /** The front-end's own software (Q-G15); the server lists its stack itself. */
  const WEB_CREDITS = [
    { name: 'IBM Plex Sans and Mono', use: 'typefaces, bundled', licence: 'SIL Open Font Licence 1.1' },
    { name: 'Svelte', use: 'user interface', licence: 'MIT' },
    { name: 'uPlot', use: 'plots', licence: 'MIT' },
    ...(desktop ? [{ name: 'Tauri', use: 'desktop application shell', licence: 'MIT or Apache-2.0' }] : []),
  ];

  let copied = $state(false);

  function versionText(): string {
    const lines = [
      `ARGOS ${info?.version ?? app.serverVersion ?? 'unknown'} (API ${info?.api ?? app.serverApi ?? '?'})`,
      `Server: Python ${info?.python ?? '?'} on ${info?.platform ? platformName(info.platform) : '?'}`,
      `Web UI: ${desktop ? 'desktop app' : 'browser'} · ${navigator.userAgent.replace(/\s*\(.*?\)\s*/g, ' ').trim()}`,
      `Telescope profile: ${info?.profile.name ?? '?'}`,
      `Log level: ${info?.log_level ?? '?'} · diagnostics ${info?.diagnostics_enabled ? 'on' : 'off'}`,
    ];
    return lines.join('\n');
  }

  async function copy(): Promise<void> {
    const text = versionText();
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = document.createElement('textarea');
      area.value = text;
      document.body.append(area);
      area.select();
      document.execCommand('copy');
      area.remove();
    }
    copied = true;
    setTimeout(() => (copied = false), 2000);
  }

  /** "macOS-26.5" (platform.platform(terse=True)) -> "macOS 26.5". */
  function platformName(p: string): string {
    return p.replace(/^([A-Za-z]+)-(\d)/, '$1 $2');
  }

  function open(url: string): void {
    window.open(url, '_blank', 'noopener,noreferrer');
  }
</script>

<div class="about">
  <div class="identity">
    <div class="mark" aria-hidden="true">{@html mark}</div>
    <div>
      <p class="wordmark">ARGOS</p>
      <p class="version num">
        {#if info}
          Version {info.version} · API {info.api} · Python {info.python} · {platformName(info.platform)}
        {:else}
          {app.serverVersion ? `Version ${app.serverVersion}` : 'Waiting for the server…'}
        {/if}
      </p>
      <p class="desc">{info?.description ?? 'Scientific acquisition and differential photometry for ZWO Seestar telescopes.'}</p>
    </div>
  </div>

  <div class="actions">
    <Control icon="copy" label={copied ? 'Copied' : 'Copy version info'} showLabel size="s" variant="secondary" onclick={() => void copy()} />
    <Control
      icon="help"
      label="Documentation & website"
      showLabel
      size="s"
      variant="secondary"
      tooltip="top"
      tooltipText="{(info?.docs_url ?? 'https://perretjules.com/argos/').replace(/^https?:\/\//, '')} · opens in your browser"
      onclick={() => open(info?.docs_url ?? 'https://perretjules.com/argos/')}
    />
    <Control
      label="Source code"
      size="s"
      variant="secondary"
      tooltip="top"
      tooltipText="{(info?.project_url ?? 'https://github.com/jperret21/argos').replace(/^https?:\/\//, '')} · opens in your browser"
      onclick={() => open(info?.project_url ?? 'https://github.com/jperret21/argos')}
    />
  </div>

  <section aria-labelledby="credits-title">
    <h3 class="title" id="credits-title">Credits</h3>
    <p class="body">Created and maintained by {info?.author ?? 'Jules Perret'}.</p>
    <table class="credits">
      <tbody>
        {#each [...(info?.credits ?? []), ...WEB_CREDITS] as c (c.name)}
          <tr>
            <td class="name">{c.name}</td>
            <td class="use">{c.use}</td>
            <td class="lic num">{c.licence}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    <p class="body muted">
      {info?.copyright ?? 'Copyright © 2026 ARGOS contributors'} · {info?.licence_name ?? 'GNU GPL v3 or later'}.
    </p>
  </section>

  {#if info}
    <section aria-labelledby="paths-title">
      <h3 class="title" id="paths-title">Folders</h3>
      <dl class="paths">
        <dt>Configuration</dt>
        <dd class="mono">{info.paths.config ?? 'in memory (not saved)'}</dd>
        <dt>Sessions</dt>
        <dd class="mono">{info.paths.sessions}</dd>
        <dt>Logs</dt>
        <dd class="mono">{info.paths.log_file ?? info.paths.diagnostics ?? 'file logging is off'}</dd>
      </dl>
    </section>
  {/if}
</div>

<style>
  .about {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    max-width: 720px;
  }
  .identity {
    display: flex;
    align-items: center;
    gap: var(--space-5);
  }
  .mark {
    flex: none;
    width: 88px;
    height: 88px;
    color: var(--accent);
  }
  .mark :global(svg) {
    width: 100%;
    height: 100%;
  }
  p {
    margin: 0;
  }
  .wordmark {
    color: var(--fg);
    font-family: var(--font-ui);
    font-size: 26px;
    font-weight: var(--weight-semibold);
    letter-spacing: -0.065em;
    line-height: 1.1;
  }
  .version {
    margin-top: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .desc {
    margin-top: var(--space-2);
    color: var(--fg);
    font-size: var(--text-m);
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .title {
    margin: 0 0 var(--space-2);
    padding-bottom: var(--space-2);
    border-bottom: var(--border-w) solid var(--border);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .body {
    color: var(--fg);
    font-size: var(--text-s);
  }
  .muted {
    margin-top: var(--space-2);
    color: var(--text-muted);
  }
  .credits {
    width: 100%;
    margin: var(--space-2) 0 0;
    border-collapse: collapse;
    font-size: var(--text-s);
  }
  .credits td {
    height: var(--row-h);
    padding: 0 var(--space-3) 0 0;
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .name {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .use {
    color: var(--text-muted);
  }
  .lic {
    color: var(--fg);
    text-align: right;
  }
  .paths {
    display: grid;
    grid-template-columns: 112px minmax(0, 1fr);
    gap: var(--space-1) var(--space-3);
    margin: 0;
    font-size: var(--text-s);
  }
  dt {
    color: var(--text-muted);
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .mono {
    font-family: var(--font-mono);
    font-size: var(--text-s);
  }
</style>
