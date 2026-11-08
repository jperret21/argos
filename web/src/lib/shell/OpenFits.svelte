<!--
  Open FITS image (mapping M4 / M49, README D19, D20; rows A25, A27): the
  shared in-app FilePicker on the FITS types, from the Observe toolbar, Mod+O
  in any section and the command palette. The file opens into Observe (the
  Review frame inspector, wave 7, will open any FITS).

  The server takes raw 16-bit camera counts only (S4): a calibrated or
  stacked frame (float data, negative values, RGB cubes) is refused, and the
  dialog stays open with the server's own words so another file can be
  chosen; the frame on screen is left untouched. Live view is stopped first
  (Q-O11), and a toast says so. The dialog starts in the folder last used,
  else the sessions folder.
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import FilePicker from '../components/FilePicker.svelte';
  import { FITS_FILTER, ANY_FILTER } from '../components/filepicker';

  const app = useApp();
  const start = $derived(app.openFitsStart ?? app.appInfo?.paths.sessions ?? null);
</script>

<FilePicker
  bind:open={app.openFitsOpen}
  mode="open-file"
  title="Open FITS image"
  {start}
  list={app.listFiles}
  filters={[FITS_FILTER, ANY_FILTER]}
  onchoose={(path) => app.openFits(path)}
/>
