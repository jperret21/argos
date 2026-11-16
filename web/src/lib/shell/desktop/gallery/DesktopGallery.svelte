<!--
  Component gallery, wave 8, the desktop app (development only, part of /?gallery=1): the
  custom title bar (macOS and the others; rest, hover, close, unfocused), the Quit dialog,
  the shutdown scrim, the crash notice, the desktop start-up stages and failure, and Reveal
  in Finder, every state drawn in place with deterministic fixtures. A live row runs the
  real quit flow against a fake server (busy refusal, confirmation, stages, closing) with the real
  layers. Sections are [data-gallery="w8-<name>"] for element screenshots.
-->
<script lang="ts">
  import type { BusyItem, ShutdownAnswer } from '../../../api/desktop';
  import type { StartupStage } from '../../../app/startup';
  import Button from '../../../components/Button.svelte';
  import StartupScreen from '../../StartupScreen.svelte';
  import CrashNotice from '../CrashNotice.svelte';
  import { type CrashView, crashView, type ServerState } from '../desktop.svelte';
  import QuitDialog from '../QuitDialog.svelte';
  import { QuitFlow, type StageRow } from '../quit.svelte';
  import RevealButton from '../RevealButton.svelte';
  import ShutdownScrim from '../ShutdownScrim.svelte';
  import TitleBar from '../TitleBar.svelte';
  import { busySentence, type LocalActivity } from '../words';

  const noop = () => {};

  // -- Fixtures ---------------------------------------------------------------------------
  const ACTIVITY: LocalActivity = {
    sequence: { state: 'running', object: 'SS Cyg', done: 34, total: 120 },
    camera: 'exposing',
    exposureS: 10,
  };
  const RUN_ITEMS: BusyItem[] = [
    { kind: 'sequence', label: null, detail: null },
    { kind: 'exposure', label: null, detail: null },
  ];
  /** As the server words them (protocol.md BusyItem `text`). */
  const SERVER_ITEMS: BusyItem[] = [
    { kind: 'sequence', label: 'A sequence is running: SS Cyg, 34 of 120 frames.', detail: null },
    { kind: 'rerun', label: 'Re-running photometry (12 of 340 frames).', detail: null },
  ];
  const LIVE_ITEMS: BusyItem[] = [
    { kind: 'live', label: null, detail: null },
    { kind: 'rerun', label: null, detail: null },
  ];
  const say = (items: BusyItem[], a: LocalActivity = ACTIVITY) => items.map((i) => busySentence(i, a));

  const T0 = 1_000_000;
  // The server's five stages (protocol.md "Shutdown (A7)").
  const PLAN = [
    { id: 'sequence', label: 'Stopping the sequence' },
    { id: 'services', label: 'Stopping background tasks' },
    { id: 'devices', label: 'Closing the equipment connections' },
    { id: 'files', label: 'Finishing file writes' },
    { id: 'exit', label: 'Stopping the ARGOS server' },
  ];
  const rows = (times: [number | null, number | null][]): StageRow[] => PLAN.map((p, i) => ({ ...p, from: times[i]?.[0] ?? null, to: times[i]?.[1] ?? null }));
  const STOPPING = rows([
    [T0 + 40, T0 + 1_480],
    [T0 + 1_480, T0 + 2_100],
    [T0 + 2_100, null],
  ]);
  const STUCK = rows([
    [T0 + 40, T0 + 900],
    [T0 + 900, null],
  ]);
  const CLOSED = rows([
    [T0 + 40, T0 + 1_480],
    [T0 + 1_480, T0 + 2_100],
    [T0 + 2_100, T0 + 3_050],
    [T0 + 3_050, T0 + 3_120],
    [T0 + 3_120, T0 + 3_120],
  ]);
  const REMOTE: StageRow[] = [
    { id: 'sequence', label: 'Stopping the sequence', from: T0, to: T0 + 900 },
    { id: 'services', label: 'Stopping background tasks', from: T0 + 900, to: null },
  ];

  // Start-up lines first, the cause last: the log box must open at its end (LogTail).
  const TRACE =
    '15:42:59,512 INFO    argos.server.hub: Telescope profile: Seestar S50 (IMX462)\n15:42:59,728 INFO    argos.server: Configuration ~/.argos/config.json; log ~/Library/Logs/Argos/argos-server.log\n15:43:00,104 INFO    argos.server: ARGOS 0.5.0 server on http://127.0.0.1:52418\n15:51:12,880 INFO    argos.server.sequence: SS Cyg: frame 34 of 120 saved\nTraceback (most recent call last):\n  File "argos/server/runtime.py", line 214, in _serve\n    loop.run_until_complete(server.serve())\n  File "argos/server/hub.py", line 512, in _frame_loop\n    raise RuntimeError("frame buffer overrun")\nRuntimeError: frame buffer overrun';
  const shellState = (phase: ServerState['phase'], extra: Partial<ServerState> = {}): ServerState => ({
    phase,
    api: null,
    token: null,
    title: null,
    cause: null,
    details: null,
    logDir: '~/Library/Logs/Argos',
    status: null,
    version: '0.5.0',
    ...extra,
  });
  const CRASH = crashView(shellState('stopped', { status: 'exit status 1', details: TRACE }), false) as CrashView;
  const REQUESTED = crashView(shellState('stopped', { status: 'exit status 0' }), true) as CrashView;
  const RESTARTING = crashView(shellState('starting'), false) as CrashView;
  const FAILED = crashView(shellState('failed', {
      title: 'ARGOS could not start',
      cause: 'The ARGOS server stopped during start-up (exit status 1).',
      details: "Traceback (most recent call last):\n  File \"argos/server/__main__.py\", line 12, in <module>\nModuleNotFoundError: No module named 'astropy'",
    }),
    false,
  ) as CrashView;

  const WAITING: StartupStage[] = [
    { id: 'server', label: 'Starting the ARGOS server…', state: 'active' },
    { id: 'link', label: 'Connecting to the ARGOS server…', state: 'pending' },
  ];
  const SIDECAR_FAILED: StartupStage[] = [
    { id: 'server', label: 'Starting the ARGOS server…', state: 'failed' },
    { id: 'link', label: 'Connecting to the ARGOS server…', state: 'pending' },
  ];
  const SIDECAR_FAILURE = {
    title: 'ARGOS could not start',
    message: 'The ARGOS server did not say where it listens within 60 s.',
    detail:
      'usage: argos-server [-h] [--host HOST] [--port PORT] [--simulator] [--sim-replay DIR]\n                    [--config-dir DIR] [--log-dir DIR] [--desktop] [--exit-on-stdin-eof]\nargos-server: error: argument --port: 99999 is not a valid port (0-65535)',
    logPath: '~/Library/Logs/Argos-observatory-dome-two/server-logs',
  };

  const target = (label: string, fail: string | null = null) => ({
    available: true,
    revealLabel: label,
    reveal: () => (fail ? Promise.reject(new Error(fail)) : new Promise<void>((r) => setTimeout(r, 600))),
  });
  const MAC = target('Reveal in Finder');
  const LINUX = target('Show in folder');
  const MISSING = target('Reveal in Finder', 'No file or folder at ~/Desktop/argos-support-20261115T2104Z.zip');
  const BROWSER = { available: false, revealLabel: 'Reveal in Finder', reveal: () => Promise.resolve() };

  // -- Live: the real flow against a fake server ---------------------------------------------
  let liveMode = $state<'busy' | 'idle'>('busy');
  let exits = $state(0);
  const timers: ReturnType<typeof setTimeout>[] = [];
  const flow: QuitFlow = new QuitFlow({
    desktop: true,
    activity: () => (liveMode === 'busy' ? ACTIVITY : {}),
    exit: () => {
      exits++;
      // The gallery is not a window: come back after a moment.
      timers.push(setTimeout(() => flow.reset(), 2_500));
    },
    shutdown: async (force): Promise<ShutdownAnswer> => {
      await new Promise((r) => setTimeout(r, 300));
      if (!force && liveMode === 'busy') return { outcome: 'busy', items: SERVER_ITEMS, message: 'Quitting now would stop this.' };
      const at = [100, 1_500, 2_300, 3_600, 3_900];
      PLAN.forEach((p, i) => timers.push(setTimeout(() => flow.onShutdownEvent({ stage: p.id, label: p.label, t: null, index: i + 1, count: PLAN.length, done: p.id === 'exit' }), at[i])));
      return { outcome: 'accepted', stages: PLAN, budgetS: 60 };
    },
  });
  $effect(() => () => {
    timers.forEach(clearTimeout);
    flow.dispose();
  });
  function runLive(mode: 'busy' | 'idle'): void {
    liveMode = mode;
    void flow.request();
  }
</script>

<!-- ===================================================================== Title bar -->
<section data-gallery="w8-titlebar" id="w8-titlebar">
  <h2>Title bar <span>Q-G14: drawn from tokens in every theme (decorations off), so Night Red stays red. macOS: the controls where the traffic lights live, rings with glyphs on hover, close fills --danger; others: three cells at the right. The free area drags, a double click zooms; close = Quit (Q-G1).</span></h2>
  <div class="bars">
    <figure><div class="frame"><TitleBar platform="macos" subtitle="Observe" onclose={noop} onminimize={noop} onzoom={noop} ondrag={noop} /></div><figcaption>macOS, at rest</figcaption></figure>
    <figure><div class="frame"><TitleBar platform="macos" subtitle="Observe" pin="controls" onclose={noop} onminimize={noop} onzoom={noop} ondrag={noop} /></div><figcaption>macOS, pointer over the controls</figcaption></figure>
    <figure><div class="frame"><TitleBar platform="macos" subtitle="Plan" pin="close" onclose={noop} onminimize={noop} onzoom={noop} ondrag={noop} /></div><figcaption>macOS, pointer on close (quits; asks when something runs)</figcaption></figure>
    <figure><div class="frame"><TitleBar platform="macos" subtitle="Review" focused={false} onclose={noop} onminimize={noop} onzoom={noop} ondrag={noop} /></div><figcaption>macOS, window not focused</figcaption></figure>
    <figure><div class="frame"><TitleBar platform="linux" subtitle="Observe" onclose={noop} onminimize={noop} onzoom={noop} ondrag={noop} /></div><figcaption>Linux / Windows, at rest</figcaption></figure>
    <figure><div class="frame"><TitleBar platform="linux" subtitle="Observe" pin="controls" onclose={noop} onminimize={noop} onzoom={noop} ondrag={noop} /></div><figcaption>Linux / Windows, pointer on minimise</figcaption></figure>
    <figure><div class="frame"><TitleBar platform="windows" subtitle="Settings" pin="close" onclose={noop} onminimize={noop} onzoom={noop} ondrag={noop} /></div><figcaption>Linux / Windows, pointer on close</figcaption></figure>
    <figure><div class="frame"><TitleBar platform="windows" subtitle="Settings" focused={false} onclose={noop} onminimize={noop} onzoom={noop} ondrag={noop} /></div><figcaption>Linux / Windows, window not focused</figcaption></figure>
  </div>
</section>

<!-- ===================================================================== Quit dialog -->
<section data-gallery="w8-quit" id="w8-quit">
  <h2>Quit dialog <span>01 2.3.7 and 2.4.3, M18: only when something runs (A7's 409 busy). What runs, in words, with what the UI knows; what quitting stops; text buttons (BRAND 7): Cancel has the focus, Quit ARGOS is the destructive one and is busy while the forced request runs.</span></h2>
  <div class="row top">
    <figure class="dlg"><QuitDialog open preview items={SERVER_ITEMS} sentences={say(SERVER_ITEMS)} oncancel={noop} onforce={noop} /><figcaption>a sequence and a re-run, in the server's words (409 busy)</figcaption></figure>
    <figure class="dlg"><QuitDialog open preview items={LIVE_ITEMS} sentences={say(LIVE_ITEMS, {})} oncancel={noop} onforce={noop} /><figcaption>live view and a re-run, worded by the UI</figcaption></figure>
    <figure class="dlg">
      <QuitDialog open preview items={[]} sentences={[]} message="The ARGOS server is busy." error="Internal server error (500): the shutdown could not start." oncancel={noop} onforce={noop} />
      <figcaption>a refusal that is not "busy": its words; Quit ARGOS still quits</figcaption>
    </figure>
    <figure class="dlg"><QuitDialog open preview forcing items={RUN_ITEMS} sentences={say(RUN_ITEMS)} oncancel={noop} onforce={noop} /><figcaption>forcing: the request is in flight (Quit ARGOS busy)</figcaption></figure>
  </div>
</section>

<!-- ===================================================================== Shutdown scrim -->
<section data-gallery="w8-scrim" id="w8-scrim">
  <h2>Shutdown scrim <span>The server's plan of stages (202 ShutdownStarted), each marked as its WS shutdown event arrives, with its time counted up; no estimate; the server's own bound said once. Past 20 s, Quit now; a window that does not close says so.</span></h2>
  <div class="row top">
    <figure class="dlg"><ShutdownScrim preview phase="stopping" stages={STOPPING} startedAt={T0} budgetS={60} now={T0 + 3_350} /><figcaption>stopping: the server's plan; two stages done, the third running</figcaption></figure>
    <figure class="dlg"><ShutdownScrim preview phase="stopping" stages={STUCK} startedAt={T0} budgetS={60} stuck now={T0 + 24_600} /><figcaption>stuck after 20 s: Quit now</figcaption></figure>
    <figure class="dlg"><ShutdownScrim preview phase="closing" stages={CLOSED} startedAt={T0} now={T0 + 3_500} /><figcaption>closing: the server stopped</figcaption></figure>
    <figure class="dlg"><ShutdownScrim preview phase="closing" stages={CLOSED} startedAt={T0} closeStalled now={T0 + 9_000} /><figcaption>the window did not close</figcaption></figure>
    <figure class="dlg"><ShutdownScrim preview phase="remote" stages={REMOTE} startedAt={T0} desktop={false} now={T0 + 1_700} /><figcaption>browser tab: another window shuts the server down</figcaption></figure>
    <figure class="dlg"><ShutdownScrim preview phase="stopped" stages={CLOSED} startedAt={T0} desktop={false} now={T0 + 4_000} /><figcaption>browser tab: the server stopped; Reconnect</figcaption></figure>
  </div>
</section>

<!-- ===================================================================== Crash notice -->
<section data-gallery="w8-crash" id="w8-crash">
  <h2>Crash notice <span>The server ended while the UI ran: said in the UI's theme (the shell's page is not themed), over the last state; exit status, last lines, log folder; Restart server has the focus.</span></h2>
  <div class="row top">
    <figure class="dlg wide"><CrashNotice preview view={CRASH} version="0.5.0" onrestart={noop} onopenlogs={noop} onquit={noop} /><figcaption>crash: exit status, the server's last lines (opened at the end)</figcaption></figure>
    <figure class="dlg wide"><CrashNotice preview view={RESTARTING} onrestart={noop} onopenlogs={noop} onquit={noop} /><figcaption>restarting: the window reloads once it answers</figcaption></figure>
    <figure class="dlg wide"><CrashNotice preview view={FAILED} onrestart={noop} onopenlogs={noop} onquit={noop} /><figcaption>the restart failed: Retry</figcaption></figure>
    <figure class="dlg wide"><CrashNotice preview view={REQUESTED} onrestart={noop} onopenlogs={noop} onquit={noop} /><figcaption>shut down from another window or tab (not a crash: no error mark, no log)</figcaption></figure>
  </div>
</section>

<!-- ===================================================================== Start-up -->
<section data-gallery="w8-startup" id="w8-startup">
  <h2>Desktop start-up <span>01 2.3.8: the UI opens at once, in the observer's theme, and waits for the shell's server state; the shell's own page shows only until the UI has loaded.</span></h2>
  <div class="row top">
    <figure class="startup"><div class="startup-frame"><StartupScreen contained stages={WAITING} version="0.5.0" /></div><figcaption>starting the server (the shell has not said "ready" yet)</figcaption></figure>
    <figure class="startup">
      <div class="startup-frame"><StartupScreen contained stages={SIDECAR_FAILED} version="0.5.0" failure={SIDECAR_FAILURE} onretry={noop} onopenlogs={noop} onquit={noop} /></div>
      <figcaption>the server did not start: columns kept, the path breaks after a slash; Quit ARGOS, Retry</figcaption>
    </figure>
  </div>
</section>

<!-- ===================================================================== Reveal -->
<section data-gallery="w8-reveal" id="w8-reveal">
  <h2>Reveal in Finder <span>A12, desktop only (nothing is drawn in a browser). The label follows the platform; a refusal stays on the button in the server's words.</span></h2>
  <div class="row">
    <figure><div class="cell"><RevealButton path="~/Desktop/argos-support.zip" target={MAC} /></div><figcaption>macOS (press: busy 0.6 s)</figcaption></figure>
    <figure><div class="cell"><RevealButton path="~/Desktop/argos-support.zip" target={LINUX} /></div><figcaption>Linux</figcaption></figure>
    <figure><div class="cell"><RevealButton path="~/Library/Logs/Argos" target={MAC} iconOnly variant="ghost" size="s" /></div><figcaption>icon only (a folder row)</figcaption></figure>
    <figure><div class="cell"><RevealButton path="~/Desktop/argos-support.zip" target={MISSING} error="No file or folder at ~/Desktop/argos-support.zip" /></div><figcaption>refused: the server's words</figcaption></figure>
    <figure><div class="cell"><RevealButton path="~/Desktop/argos-support.zip" target={BROWSER} /><span class="muted">(nothing)</span></div><figcaption>browser tab</figcaption></figure>
  </div>
</section>

<!-- ===================================================================== Live -->
<section data-gallery="w8-live" id="w8-live">
  <h2>Live quit flow <span>The real QuitFlow and layers against a fake server: busy refuses with what runs, Quit ARGOS in the dialog forces it, the stages follow, then the window would close (here it comes back after 2.5 s).</span></h2>
  <div class="live">
    <span class="live-label">live</span>
    <Button label="Quit while a sequence runs" data-testid="w8-quit-busy" onclick={() => runLive('busy')} />
    <Button label="Quit while idle" data-testid="w8-quit-idle" onclick={() => runLive('idle')} />
    <span class="result" data-testid="w8-quit-result">phase {flow.phase} · exits asked {exits}</span>
  </div>
  {#if flow.phase === 'confirm' || flow.phase === 'forcing'}
    <QuitDialog
      open
      items={flow.busy}
      sentences={flow.sentences}
      message={flow.message}
      error={flow.error}
      forcing={flow.phase === 'forcing'}
      oncancel={() => flow.cancel()}
      onforce={() => flow.force()}
    />
  {/if}
  {#if flow.scrim}
    <ShutdownScrim
      phase={flow.phase}
      stages={flow.stages}
      startedAt={flow.startedAt}
      stuck={flow.stuck}
      closeStalled={flow.closeStalled}
      budgetS={flow.budgetS}
      onquitnow={() => flow.quitNow()}
    />
  {/if}
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
  .bars {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(560px, 1fr));
    gap: var(--space-4);
  }
  .frame {
    border: var(--border-w) solid var(--border);
    background: var(--bg);
    padding-bottom: var(--space-6);
  }
  .dlg {
    width: 400px;
  }
  .dlg.wide {
    width: 560px;
  }
  .startup {
    width: 640px;
  }
  .startup-frame {
    height: 420px;
    border: var(--border-w) solid var(--border);
    overflow: hidden;
  }
  .cell {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: 40px;
  }
  .muted {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .live {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
    border: var(--border-w) dashed var(--border);
    border-radius: var(--radius-m);
  }
  .live-label {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .result {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
</style>
