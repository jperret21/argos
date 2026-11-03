<!--
  One per-viewer preference row (Settings › Appearance): the same grid as
  a SettingField (label and help | control | 52 px end column), for the
  choices kept in this browser (theme, density, rotation, layouts) rather
  than in the server configuration.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    label: string;
    help?: string;
    /** Status under the control ("Saved in this browser"). */
    status?: string | null;
    children: Snippet;
    id?: string;
  }
  let { label, help, status = null, children, id }: Props = $props();
</script>

<div class="pref" data-pref={id}>
  <div class="label-col">
    <span class="label">{label}</span>
    {#if help}<p class="help">{help}</p>{/if}
  </div>
  <div class="control-col">
    {@render children()}
    <p class="status">{status ?? ''}</p>
  </div>
  <span></span>
</div>

<style>
  .pref {
    display: grid;
    grid-template-columns: minmax(0, 15fr) minmax(0, 17fr) 52px;
    align-items: start;
    gap: var(--space-1) var(--space-5);
    /* As SettingField: no rule per row (rules separate groups), compact padding. */
    padding: 6px 0 6px var(--space-4);
  }
  .label-col {
    min-width: 0;
    padding-top: 5px;
  }
  .label {
    color: var(--fg);
    font-size: var(--text-m);
    font-weight: var(--weight-medium);
    line-height: var(--leading-tight);
  }
  .help {
    margin: 2px 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
    text-wrap: pretty;
  }
  .control-col {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    min-width: 0;
    min-height: var(--input-h);
    justify-content: center;
  }
  .status {
    min-height: 16px;
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: 16px;
  }
</style>
