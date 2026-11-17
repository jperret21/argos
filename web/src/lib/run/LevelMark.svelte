<!--
  The mark of a preflight level (A64), one shape per level so Night Red (luminance only)
  still tells them apart, and always beside its word (BRAND 4.2, 8):
  ok = small filled dot (--status-ok); note = the attention mark, a bar over a dot
  (--warning); block = a no-entry disc (--danger with a bar knocked out). Never a
  triangle (the check star's shape, BRAND 2.6).
-->
<script lang="ts">
  import type { PreflightLevel } from '../api/sequence';

  let { level }: { level: PreflightLevel | 'unknown' } = $props();
</script>

<span class="mark l-{level}" aria-hidden="true"></span>

<style>
  .mark {
    position: relative;
    display: inline-block;
    flex: none;
    width: 12px;
    height: 12px;
  }
  .mark::before,
  .mark::after {
    content: '';
    position: absolute;
  }
  .l-ok::before {
    inset: 3px;
    border-radius: 50%;
    background: var(--status-ok);
  }
  .l-unknown::before {
    inset: 3px;
    border-radius: 50%;
    box-shadow: inset 0 0 0 1.5px var(--status-idle);
  }
  .l-note::before {
    left: 4.5px;
    top: 0;
    width: 3px;
    height: 7px;
    background: var(--warning);
  }
  .l-note::after {
    left: 4.5px;
    top: 9px;
    width: 3px;
    height: 3px;
    background: var(--warning);
  }
  .l-block::before {
    inset: 0;
    border-radius: 50%;
    background: var(--danger);
  }
  .l-block::after {
    left: 2.5px;
    right: 2.5px;
    top: 5px;
    height: 2px;
    background: var(--bg);
  }
</style>
