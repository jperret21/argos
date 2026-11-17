<!--
  The mark of an attention level (BRAND §8 "Attention levels"), one SHAPE per level so Night
  Red (luminance only) still tells them apart, always beside its word:
  critical = a filled --danger disc; attention = an upright mark, a bar over a dot, in
  --warning; info = a hollow ring in --fg-muted. Never a triangle (the check star's shape,
  BRAND 2.6). Drawn in CSS at any size (10 px in lists and the status bar, 44 px in Watch),
  so it scales without an icon file. Decorative: the word beside it carries the level.
-->
<script lang="ts">
  import type { AttentionLevel } from '../../api/attention';

  let { level, size = 10 }: { level: AttentionLevel; size?: number } = $props();
</script>

<span class="mark l-{level}" style:--s="{size}px" aria-hidden="true"></span>

<style>
  .mark {
    position: relative;
    display: inline-block;
    flex: none;
    width: var(--s);
    height: var(--s);
  }
  .l-critical {
    border-radius: var(--radius-round);
    background: var(--danger);
  }
  .l-info {
    border-radius: var(--radius-round);
    box-shadow: inset 0 0 0 max(1.5px, calc(var(--s) * 0.15)) var(--fg-muted);
  }
  /* The upright mark: a bar (70 % of the height) over a dot (the bottom 20 %). */
  .l-attention::before,
  .l-attention::after {
    content: '';
    position: absolute;
    left: 35%;
    width: 30%;
    border-radius: max(1px, calc(var(--s) * 0.06));
    background: var(--warning);
  }
  .l-attention::before {
    top: 0;
    height: 66%;
  }
  .l-attention::after {
    bottom: 0;
    height: 24%;
  }
</style>
