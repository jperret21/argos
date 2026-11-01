<!--
  Compact star card on the image (functional-spaces P5): identity and the
  role buttons only, so it hides as few stars as possible; the details live
  in the Inspector card. Placed beside the star, flipped to stay inside the
  image. Role buttons are icons (role shapes, BRAND 6) with the role in the
  tooltip; a role change during a run asks for confirmation (spec 3.3).
-->
<script lang="ts">
  import IconButton from '../../../lib/components/IconButton.svelte';
  import { sim, ws } from '../model/app.svelte';
  import type { Star } from '../model/field';
  import { fixed } from '../model/format';

  interface Props {
    star: Star;
    x: number;
    y: number;
    r: number;
    bounds: { w: number; h: number };
  }

  let { star, x, y, r, bounds }: Props = $props();

  const W = 236;
  const H = 66;
  const left = $derived(x + r + 14 + W > bounds.w - 8 ? x - r - 14 - W : x + r + 14);
  const top = $derived(Math.max(8, Math.min(bounds.h - H - 48, y - H / 2)));

  function role(to: string): void {
    const during = sim.running ? ' (during a run the app asks first: it changes the measurement)' : '';
    ws.toast(`${star.name ?? 'Star'} set as ${to}${during}`, 'ok', { label: 'Undo', run: () => ws.toast('Undone', 'info') });
  }
</script>

<div class="card" style:left="{left}px" style:top="{top}px" role="dialog" aria-label="Star {star.name ?? ''}">
  <div class="id">
    <span class="name">{star.name ?? `Gaia star · V ${fixed(star.v, 2)}`}</span>
    <span class="meta num">V {fixed(star.v, 2)}{star.role ? ` · ${star.role}` : ''}</span>
  </div>
  <div class="roles">
    <IconButton icon="target-star" label="Set as target" size="s" variant="ghost" pressed={star.role === 'target'} onclick={() => role('target')} />
    <IconButton icon="comparison-star" label="Set as comparison" size="s" variant="ghost" pressed={star.role === 'comparison'} onclick={() => role('comparison')} />
    <IconButton icon="check-star" label="Set as check star" size="s" variant="ghost" pressed={star.role === 'check'} onclick={() => role('check')} />
    <IconButton icon="remove" label="Remove from the set" size="s" variant="ghost" disabledReason={star.role ? null : 'not in the set'} onclick={() => role('none')} />
    <span class="grow"></span>
    <IconButton icon="close" label="Close" size="s" variant="ghost" tooltip="none" onclick={() => ws.select(null)} />
  </div>
</div>

<style>
  .card {
    position: absolute;
    width: 236px;
    padding: var(--space-2) var(--space-2) var(--space-1) var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--lab-elev-float);
  }
  .id {
    display: flex;
    flex-direction: column;
  }
  .name {
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
    font-family: var(--font-mono);
  }
  .meta {
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-family: var(--font-mono);
  }
  .roles {
    display: flex;
    align-items: center;
    gap: 2px;
    margin-top: 2px;
    margin-left: calc(-1 * var(--space-2));
  }
  .grow {
    flex: 1;
  }
</style>
