<!--
  Settings › Observer & site (02 1.7, W3; M28). Observer (name, AAVSO
  code), the default site with the site-against-mount check beside its
  fields, Find a place (online, explicit), Saved sites.
-->
<script lang="ts">
  import type { ConfigValue, KeyMeta } from '../../api/types';
  import { useApp } from '../../app/state.svelte';
  import Control from '../../components/Control.svelte';
  import PlaceSearch from '../PlaceSearch.svelte';
  import SavedSites from '../SavedSites.svelte';
  import SettingsBlock from '../SettingsBlock.svelte';
  import SiteCheckPanel from '../SiteCheckPanel.svelte';
  import SitePosition from '../SitePosition.svelte';

  interface Props {
    query?: string;
  }
  let { query = '' }: Props = $props();

  const app = useApp();
</script>

{#snippet favoritesLink(_key: string, _meta: KeyMeta, _value: ConfigValue | undefined)}
  <Control
    icon="site"
    label="Open the saved sites"
    showLabel
    size="xs"
    variant="ghost"
    onclick={() => app.openSettings('observer_site', 'site.favorites')}
  />
{/snippet}

<div class="page">
  <SettingsBlock title="Observer" keys={['observer.name', 'observer.obscode']} {query} hideEmpty={!!query} />
  {#if query}
    <SettingsBlock
      title="Default site"
      keys={['site.name', 'site.latitude', 'site.longitude', 'site.elevation']}
      {query}
      hideEmpty
    />
  {:else}
    <!-- Name, then the position as one compound row (W3): latitude, longitude, elevation side by side. -->
    <div class="site-block">
      <SettingsBlock title="Default site" caption="Used for the airmass, BJD and visibility." keys={['site.name']} />
      <SitePosition />
    </div>
  {/if}
  {#if !query}
    <SiteCheckPanel />
    <section class="group" aria-labelledby="find-title">
      <h3 class="title" id="find-title">Find a place</h3>
      <PlaceSearch />
    </section>
    <section class="group" aria-labelledby="saved-title">
      <h3 class="title" id="saved-title">Saved sites</h3>
      <SavedSites />
    </section>
  {:else}
    <SettingsBlock
      title="Saved sites"
      keys={['site.favorites']}
      {query}
      hideEmpty
      customKeys={['site.favorites']}
      custom={favoritesLink}
    />
  {/if}
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .group,
  .site-block {
    max-width: var(--page-max-w);
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
</style>
