<!--
  Right panel: the mode's cards in the mode's fixed order. Each card is the
  app's Card (collapsible); its open state is the MODE's (folding a card in
  Run does not fold it in Framing). A folded card keeps a one-line summary
  in its header, so folding loses nothing a glance needs. Hidden cards come
  back from Arrange or the palette.
-->
<script lang="ts">
  import Card from '../../../lib/components/Card.svelte';
  import StatusBadge from '../../../lib/components/StatusBadge.svelte';
  import type { Tone } from '../../../lib/app/status';
  import { CARD_LABELS, CARD_ORDER, type CardId } from '../model/layout';
  import { sim, ws } from '../model/app.svelte';
  import { duration, fixed, int } from '../model/format';
  import { RUN } from '../model/night';
  import RunCard from './cards/RunCard.svelte';
  import PhotometryCard from './cards/PhotometryCard.svelte';
  import ConditionsCard from './cards/ConditionsCard.svelte';
  import MountCard from './cards/MountCard.svelte';
  import CameraCard from './cards/CameraCard.svelte';
  import FocuserCard from './cards/FocuserCard.svelte';
  import InspectorCard from './cards/InspectorCard.svelte';
  import FieldCard from './cards/FieldCard.svelte';

  const visible = $derived(CARD_ORDER[ws.mode].filter((id) => ws.layout.cards[id] !== 'hidden'));

  function badge(id: CardId): { tone: Tone; label: string } | null {
    switch (id) {
      case 'run':
        if (!sim.inRun) return { tone: 'idle', label: 'No run' };
        return sim.running
          ? { tone: 'active', label: sim.runState === 'pausing' ? 'Pausing' : 'Running' }
          : { tone: sim.runState === 'complete' ? 'ok' : 'idle', label: sim.runState === 'complete' ? 'Complete' : sim.runState === 'stopped' ? 'Stopped' : 'Paused' };
      case 'mount':
        return sim.parked ? { tone: 'idle', label: 'Parked' } : { tone: 'ok', label: sim.tracking ? 'Tracking' : 'Idle' };
      case 'camera':
        return sim.inRun && sim.running ? { tone: 'busy', label: 'Sequence' } : sim.live ? { tone: 'active', label: 'Live' } : { tone: 'ok', label: 'Ready' };
      case 'focuser':
        return sim.afRunning ? { tone: 'busy', label: 'Autofocus' } : { tone: 'ok', label: 'Idle' };
      case 'photometry':
        if (!sim.solved && !sim.inRun) return { tone: 'idle', label: 'No field' };
        return sim.inRun && sim.delivered >= 10 ? { tone: 'ok', label: 'Consistent' } : { tone: 'busy', label: 'Waiting 7/10' };
      case 'conditions': {
        const flagged = sim.attention.some((a) => a.rule === 'HFD rise' || a.rule === 'Star count drop');
        return flagged ? { tone: 'busy', label: 'Rule holds' } : { tone: 'ok', label: 'Steady' };
      }
      case 'field':
        return sim.solved || sim.inRun ? { tone: 'ok', label: 'Identified' } : { tone: 'idle', label: 'Not identified' };
      default:
        return null;
    }
  }

  function summary(id: CardId): string {
    const l = sim.latest;
    switch (id) {
      case 'run':
        return sim.inRun ? `${sim.delivered}/${RUN.frames} · ${sim.lastAge} s ago · ETA ${duration(sim.endsAt - sim.now)}` : '';
      case 'mount':
        return 'RR Lyr · 0.08° away';
      case 'camera':
        return sim.inRun ? `${fixed(RUN.exposure, 1)} s · gain ${RUN.gain} · ${RUN.filter}` : `2.0 s · gain 80 · IR`;
      case 'focuser':
        return sim.afRunning ? `step ${sim.afStep}/${sim.af.steps.length}` : `${int(1305)} · 12.3 °C`;
      case 'photometry':
        return l ? `${fixed(l.target, 3)} · ${l.compsUsed}/${RUN.comparisons} comps` : '6 comps · 1 check';
      case 'conditions':
        return l ? `HFD ${fixed(l.hfd, 1)} px · ${int(l.stars)} stars` : '';
      case 'field':
        return '2.39″/px · rot 91.2°';
      case 'inspector':
        return ws.selected ? 'star selected' : 'click a star';
      default:
        return '';
    }
  }
</script>

<aside class="panel" aria-label="Right panel">
  {#each visible as id (id)}
    {@const b = badge(id)}
    {@const open = ws.layout.cards[id] === 'open'}
    <Card
      title={CARD_LABELS[id].title}
      icon={id === 'inspector' ? 'metadata' : CARD_LABELS[id].icon}
      collapsible
      dense
      bind:open={() => ws.layout.cards[id] === 'open', (v) => ws.setCard(id, v ? 'open' : 'folded')}
    >
      {#snippet status()}
        {#if !open}<span class="summary num">{summary(id)}</span>{/if}
        {#if b}<StatusBadge tone={b.tone} label={b.label} />{/if}
      {/snippet}
      {#if id === 'run'}
        <RunCard />
      {:else if id === 'photometry'}
        <PhotometryCard />
      {:else if id === 'conditions'}
        <ConditionsCard />
      {:else if id === 'mount'}
        <MountCard />
      {:else if id === 'camera'}
        <CameraCard />
      {:else if id === 'focuser'}
        <FocuserCard />
      {:else if id === 'inspector'}
        <InspectorCard />
      {:else}
        <FieldCard />
      {/if}
    </Card>
  {/each}
  {#if !visible.length}
    <p class="empty">Every card is hidden in this mode. Arrange brings them back.</p>
  {/if}
</aside>

<style>
  .panel {
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-2);
    overflow: auto;
    scrollbar-gutter: stable;
    background: var(--bg-2);
  }
  .summary {
    min-width: 0;
    margin-left: var(--space-3);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .empty {
    color: var(--text-muted);
    font-size: var(--text-s);
    padding: var(--space-4);
  }
</style>
