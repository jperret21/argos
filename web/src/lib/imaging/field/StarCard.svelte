<!--
  Star card (promoted from src/lab/workspace/observe/StarCard.svelte, web/lab/PROPOSAL.md 3.1
  "compact star card" and 6, W4; web/spec/04 2.3, 03 2.4). Compact on purpose: the star's
  identity (never cut: the card grows from 252 to 340 px and wraps only as a last resort), one
  line of facts built from the fields ("V 7.90 · B−V 0.69 · 27.4′ from target · VSP
  comparison", present.ts `cardText`), the role buttons; the details live in the Inspector
  card, so the card hides as few stars as possible.

  - Placed beside the star, flipped to stay inside the image. Dragged by its head, it follows
    the pointer exactly (no lag) and on release settles into the nearest corner with a spring
    (BRAND 9: orientation only; instant under reduced motion); it then stays docked there for
    the next stars, remembered per viewer. Arrow keys on the head move it between corners,
    Home puts it back beside the star.
  - Identifying: a spinner and "Identifying catalogue source…" (A49 `identifying`); a new
    click replaces the lookup. No match / failed: the server's sentence, the measured star
    kept.
  - Roles are icons (the role shapes, BRAND 6.8) with "Set as target / comparison / check
    star" in the tooltip; the current role is pressed. Before a solve they are unavailable
    with the server's reason ("identify the field first"). Remove is unavailable unless the
    star is in the set. No confirmation: every role change is undoable (03 2.4).
  - Esc or × closes it (the caller clears the selection on the server).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { Spring } from 'svelte/motion';
  import { loadPref, savePref } from '../../app/prefs';
  import Icon from '../../components/Icon.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import { reducedMotion } from '../../components/motion.svelte';
  import Spinner from '../../components/Spinner.svelte';
  import type { Role } from '../../viewer/overlay/layers';
  import { besideStar, cardText, CORNER_NAMES, cornerPos, dockKey, isDock, kindIcon, nearestCorner, type Dock } from './present';
  import RoleGlyph from './RoleGlyph.svelte';
  import type { Selection, SelectionStateName } from './types';

  interface Props {
    selection: Selection;
    phase?: SelectionStateName | null;
    /** The server's sentence for no_match / failed. */
    message?: string | null;
    /** The selected star on the stage (CSS px) and its ring radius. */
    at: { x: number; y: number; r: number } | null;
    /** The stage (the card stays inside it). */
    bounds: { width: number; height: number };
    /** A role call is on the way (that button spins). */
    busyRole?: Role | 'remove' | null;
    onrole?: (role: Role) => void;
    onremove?: () => void;
    onclose?: () => void;
    /** Show the details in the Inspector (Field mode). */
    oninspect?: () => void;
    /** Where the card sits; persisted per viewer unless `persist` is false. */
    dock?: Dock;
    persist?: boolean;
    /** Gallery: draw in flow, not positioned on a stage. */
    still?: boolean;
    /** The set's target (the facts give the separation from it). */
    setTarget?: { ra_hours: number; dec_deg: number } | null;
    /** The same star in another catalogue ("VSP 000-BJW-666"), named beside the title. */
    alias?: string | null;
  }

  let {
    selection,
    phase = null,
    message = null,
    at,
    bounds,
    busyRole = null,
    onrole,
    onremove,
    onclose,
    oninspect,
    dock = $bindable(-1),
    persist = true,
    still = false,
    setTarget = null,
    alias = null,
  }: Props = $props();

  const PREF = 'argos.starcard.dock';
  untrack(() => {
    if (persist) dock = loadPref(PREF, isDock, dock);
  });

  let w = $state(252);
  let h = $state(96);
  const card = $derived({ width: w, height: h });
  const pos = new Spring({ x: 12, y: 44 }, { stiffness: 0.16, damping: 0.72 });
  let dragging = $state(false);
  let grab = { dx: 0, dy: 0 };

  function target(): { x: number; y: number } {
    if (dock === -1) return at ? besideStar(at, card, bounds) : cornerPos(2, card, bounds);
    return cornerPos(dock, card, bounds);
  }

  // A new star, a resize, a pan: the card goes where it belongs at once (data never animates;
  // only a release after a drag springs, BRAND 9).
  $effect(() => {
    void at;
    void bounds.width;
    void bounds.height;
    void h;
    void w;
    void dock;
    untrack(() => {
      if (!dragging) pos.set(target(), { instant: true });
    });
  });

  function setDock(d: Dock, animate: boolean): void {
    dock = d;
    if (persist) savePref(PREF, d);
    pos.set(target(), { instant: !animate || reducedMotion() });
  }

  function down(e: PointerEvent): void {
    if (e.button !== 0 || still) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragging = true;
    grab = { dx: e.clientX - pos.current.x, dy: e.clientY - pos.current.y };
    e.stopPropagation();
  }
  function move(e: PointerEvent): void {
    if (!dragging) return;
    // While held, the card is exactly under the pointer: no spring lag.
    pos.set({ x: e.clientX - grab.dx, y: e.clientY - grab.dy }, { instant: true });
  }
  function up(): void {
    if (!dragging) return;
    dragging = false;
    setDock(nearestCorner(pos.current, card, bounds), true);
  }
  function gripKey(e: KeyboardEvent): void {
    const next = dockKey(dock, e.key);
    if (next === null) return;
    e.preventDefault();
    setDock(next, true);
  }
  function cardKey(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onclose?.();
    }
  }

  const identifying = $derived(selection.identifying || phase === 'identifying');
  const text = $derived(cardText(selection, { target: setTarget, alias }));
  const facts = $derived(text.facts);
  const rolesReason = $derived(selection.roles_enabled ? null : (selection.roles_reason ?? 'Identify the field first'));
  const ROLES: { role: Role; icon: string; label: string }[] = [
    { role: 'target', icon: 'target-star', label: 'Set as target' },
    { role: 'comparison', icon: 'comparison-star', label: 'Set as comparison' },
    { role: 'check', icon: 'check-star', label: 'Set as check star' },
  ];
  const where = $derived(dock === -1 ? 'beside the star' : CORNER_NAMES[dock]);
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
  class="card"
  class:still
  class:dragging
  bind:offsetHeight={h}
  bind:offsetWidth={w}
  style:transform={still ? undefined : `translate(${pos.current.x}px, ${pos.current.y}px)`}
  role="dialog"
  aria-label="Star card: {text.title}"
  tabindex="-1"
  onkeydown={cardKey}
>
  <div class="head">
    <div
      class="grip"
      role="button"
      tabindex="0"
      aria-label="Move the star card, now {where} (arrow keys: corners; Home: beside the star)"
      onpointerdown={down}
      onpointermove={move}
      onpointerup={up}
      onpointercancel={up}
      onkeydown={gripKey}
    >
      <span class="kind" aria-hidden="true">
        {#if selection.role}<RoleGlyph role={selection.role} size={16} />{:else}<Icon name={kindIcon(selection.kind)} size={16} />{/if}
      </span>
      <span class="title">{text.title || 'Identifying catalogue source…'}</span>
    </div>
    <IconButton icon="close" label="Close" shortcut="Esc" size="s" variant="ghost" tooltip="none" onclick={() => onclose?.()} />
  </div>
  <p class="facts num" aria-live="polite">
    {#if identifying}
      <Spinner /><span>Identifying catalogue source…</span>
    {:else if (phase === 'no_match' || phase === 'failed') && message}
      <span class="msg">{message}</span>
    {:else if facts}
      <span>{facts}</span>
    {:else}
      <span class="muted">{selection.role ? `${selection.role} of the set` : 'No catalogue details'}</span>
    {/if}
  </p>
  <div class="actions" role="group" aria-label="Role in the target set">
    {#each ROLES as r (r.role)}
      <IconButton
        icon={r.icon}
        label={r.label}
        size="s"
        variant="ghost"
        pressed={selection.role === r.role}
        layoutToggle
        busy={busyRole === r.role}
        disabledReason={rolesReason}
        onclick={() => onrole?.(r.role)}
      />
    {/each}
    <IconButton
      icon="remove"
      label="Remove from the set"
      size="s"
      variant="ghost"
      busy={busyRole === 'remove'}
      disabledReason={selection.removable ? null : 'Not in the target set'}
      onclick={() => onremove?.()}
    />
    <span class="grow"></span>
    {#if oninspect}
      <IconButton icon="inspector" label="Details in the Inspector" size="s" variant="ghost" onclick={oninspect} />
    {/if}
  </div>
</div>

<style>
  .card {
    position: absolute;
    top: 0;
    left: 0;
    width: max-content;
    min-width: 252px;
    max-width: 340px;
    box-sizing: border-box;
    padding: var(--space-1) var(--space-1) var(--space-1) var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg-2);
    box-shadow: var(--shadow-2);
    pointer-events: auto;
    outline: none;
  }
  .card.still {
    position: relative;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    min-height: 30px;
  }
  .grip {
    display: flex;
    flex: 1;
    min-width: 0;
    align-items: center;
    gap: var(--space-2);
    align-self: stretch;
    border-radius: var(--radius-s);
    cursor: grab;
    touch-action: none;
    outline: none;
  }
  .dragging .grip {
    cursor: grabbing;
  }
  .grip:focus-visible {
    box-shadow: 0 0 0 var(--focus-ring-w) var(--focus-ring);
  }
  .kind {
    display: inline-flex;
    color: var(--fg-muted);
  }
  /* The identity is never cut: it wraps (between words) only past 340 px. */
  .title {
    flex: 1;
    min-width: 0;
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
    overflow-wrap: anywhere;
  }
  .facts {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: 18px;
    max-width: 320px;
    margin: 0 var(--space-2) 2px 0;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .msg {
    color: var(--fg);
    white-space: normal;
  }
  .muted {
    color: var(--text-muted);
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 2px;
    margin-left: calc(-1 * var(--space-2));
  }
  .grow {
    flex: 1;
  }
</style>
