<!--
  Drawer with the global Log tab (D17), on the shared Drawer component: the
  one log store (app.log: server lines, v2 levels when the server sends
  them, client failures), level filter, search, copy, save, clear, follow /
  pause. Opens under the image (the viewer shrinks, nothing is covered).

  Without props it is the Observe screen's log drawer as before (a height
  fixed by ImagingScreen's grid). A section that owns a SectionLayout passes
  its other tabs, the tab content and a bound height to make it resizable.
-->
<script lang="ts" module>
  import { LogFilter } from '../app/log.svelte';

  /** One filter for every Log tab: the level choice follows the observer across sections. */
  let shared: LogFilter | null = null;
  function sharedFilter(): LogFilter {
    shared ??= new LogFilter({ persist: 'argos.log.filter' });
    return shared;
  }
</script>

<script lang="ts">
  import type { Snippet } from 'svelte';
  import { useApp } from '../app/state.svelte';
  import Drawer, { type DrawerTab } from '../components/Drawer.svelte';
  import LogControls from '../components/LogControls.svelte';
  import LogView from '../components/LogView.svelte';

  interface Props {
    /** Tabs before the Log tab (the Log tab is always last, 01 2.3.9). */
    tabs?: readonly DrawerTab[];
    tab?: string;
    /** Content of the other tabs. */
    content?: Snippet<[string]>;
    tools?: Snippet<[string]>;
    height?: number;
    maxHeight?: number;
    resizable?: boolean;
    label?: string;
    ontab?: (id: string) => void;
    onheight?: (px: number) => void;
  }

  let {
    tabs = [],
    tab = $bindable('log'),
    content,
    tools: otherTools,
    height = $bindable(216),
    maxHeight = 480,
    resizable = false,
    label = 'Bottom drawer',
    ontab,
    onheight,
  }: Props = $props();

  const app = useApp();
  const filter = sharedFilter();
  const allTabs = $derived<DrawerTab[]>([
    ...tabs,
    { id: 'log', label: 'Log', icon: 'log', badge: tab === 'log' ? null : app.unseenProblems || null },
  ]);
</script>

<Drawer
  {label}
  tabs={allTabs}
  bind:tab
  bind:height
  {maxHeight}
  {resizable}
  {ontab}
  {onheight}
  closeShortcut="L"
  onclose={() => app.setLogOpen(false)}
>
  {#snippet tools(id: string)}
    {#if id === 'log'}
      <LogControls store={app.log} {filter} />
    {:else if otherTools}
      {@render otherTools(id)}
    {/if}
  {/snippet}
  {#snippet children(id: string)}
    {#if id === 'log'}
      <LogView store={app.log} {filter} markSeen />
    {:else if content}
      {@render content(id)}
    {/if}
  {/snippet}
</Drawer>
