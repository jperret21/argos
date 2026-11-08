<!--
  Focuser card (spec 05 §2.3 D, mapping M62-M63; PROPOSAL 3.3 "Focuser card",
  owner D9): the rail card around FocuserControl (instruments/), wired to the
  server (protocol.md "Focuser (A34, A35)", "Autofocus (A36)").

  - Header: the focuser's state in a word (Ready, Moving, Autofocus,
    Returning, Rejected…); folded, the polled position.
  - Body: FocuserControl: polled position on a two-scale gauge, taps queued
    during a move and sent as one (D9), Go to bounded by MaxStep and refused
    in words (H10), Autofocus / Stop AF (Stop AF returns the focuser to its
    start before the camera is released, S23), Halt always available (Esc
    halts a manual move, D21; never the autofocus, Q-O8).
  - The AF frames hint shows the exposure and gain the server will use (S22):
    the capture exposure capped at 10 s and the capture gain (Q-O9 defaults),
    or the parameters of the run in progress.
  - The V-curve sits in the Focus mode's band (D1); the card shows it only
    when that band is not on screen (another mode, or the band hidden).
-->
<script lang="ts">
  import { loadPref, savePref } from '../app/prefs';
  import { useApp } from '../app/state.svelte';
  import VCurvePlot from '../charts/VCurvePlot.svelte';
  import Card from '../components/Card.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { int } from '../format/number';
  import { afFrames } from './capture';
  import { focuserBadge } from './instruments/focuser';
  import FocuserControl from './instruments/FocuserControl.svelte';
  import type { AutofocusView, FocuserView } from './instruments/types';

  interface Props {
    open?: boolean;
    /** The Focus band shows the V-curve now: the card does not repeat it. */
    bandShowsVCurve?: boolean;
  }

  let { open = $bindable(), bandShowsVCurve = false }: Props = $props();
  const app = useApp();

  const OFFLINE: FocuserView = { state: 'disconnected', position: null };
  const focuser = $derived<FocuserView>(app.canFocuser || app.stale ? (app.focuser ?? OFFLINE) : OFFLINE);
  const af = $derived(app.autofocus as AutofocusView | null);
  const badge = $derived(app.stale ? { tone: 'idle' as const, label: 'No link' } : focuserBadge(focuser, af));

  let step = $state(loadPref('argos.focuser.step', (v): v is number => typeof v === 'number' && v > 0, 100));
  $effect(() => {
    savePref('argos.focuser.step', step);
  });

  /** What the next sweep will expose: the run's own parameters, else the capture settings (exposure ≤ 10 s, S22). */
  const frames = $derived(afFrames(af, app.settings));

  const showVCurve = $derived(!bandShowsVCurve && !!af && (af.samples?.length ?? 0) > 0);
</script>

{#snippet plot()}
  <div class="vcurve"><VCurvePlot af={app.autofocus} theme={app.theme} legend={false} /></div>
{/snippet}

<Card title="Focuser" icon="focuser" collapsible bind:open={() => open ?? true, (v) => (open = v)} persist={open === undefined ? 'focuser' : undefined}>
  {#snippet status()}
    <StatusBadge tone={badge.tone} label={badge.label} />
  {/snippet}
  {#snippet summary()}
    {#if focuser.position !== null}{focuser.max_step ? `${int(focuser.position)} / ${int(focuser.max_step)}` : int(focuser.position)}{/if}
  {/snippet}

  <FocuserControl
    {focuser}
    autofocus={af}
    bind:step
    afFrames={frames}
    autofocusReason={app.autofocusRunning ? null : app.autofocusProblem()}
    haltShortcut="Escape"
    onstep={(d) => app.focuserStep(d)}
    onmove={(p) => app.focuserMove(p)}
    onhalt={() => app.focuserHalt()}
    onautofocus={() => app.startAutofocus()}
    onstopautofocus={() => app.stopAutofocus()}
    vcurve={showVCurve ? plot : undefined}
  />
</Card>

<style>
  .vcurve {
    height: 140px;
    min-width: 0;
  }
</style>
