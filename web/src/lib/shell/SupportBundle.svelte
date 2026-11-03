<!--
  The shell's support bundle (01 2.3.6, D14, M15; A5, A67): the shared
  SupportBundleDialog wired to the server. Opened from the Help menu,
  Settings › Privacy & diagnostics and the command palette.

  - Sessions for the optional metadata come from GET /api/sessions (newest
    first), read each time the dialog opens; off by default (Q-G17).
  - The ZIP is written by the server on this computer (it only listens on
    127.0.0.1): the proposed place is the Desktop (else home), with the
    UTC time in the name; [browse] opens the in-app FilePicker (save mode).
    An existing file asks "Replace?" (409 file_exists).
  - Success: a toast with the file count ("ARGOS did not upload it") and a
    log line from the server.
-->
<script lang="ts">
  import type { SessionSummary } from '../api/types';
  import { useApp } from '../app/state.svelte';
  import SupportBundleDialog from '../components/SupportBundleDialog.svelte';
  import { bundleCreatedText } from '../components/supportbundle';

  const app = useApp();

  let sessions: SessionSummary[] = $state.raw([]);
  let sessionsLoading = $state(false);
  let folder: string | null = $state(null);

  $effect(() => {
    if (!app.supportBundleOpen) return;
    sessionsLoading = true;
    app.client
      .sessions({ limit: 200 })
      .then((p) => (sessions = p.sessions))
      .catch(() => (sessions = []))
      .finally(() => (sessionsLoading = false));
  });

  // Where to propose the ZIP: the Desktop place, else home (the listing's places),
  // read once the server answers, so it is known before the dialog first opens.
  $effect(() => {
    if (!app.linkOpen || folder) return;
    app.client
      .fsList({ path: null, kind: 'dir', ext: null, counts: null, hidden: false })
      .then((l) => {
        const places = l.places.filter((p): p is Exclude<typeof p, string> => typeof p !== 'string');
        const desk = places.find((p) => p.id === 'desktop' && p.exists !== false);
        const home = places.find((p) => p.id === 'home');
        folder = desk?.path ?? home?.path ?? null;
      })
      .catch(() => {});
  });

  const stage = $derived.by(() => {
    const job = app.jobs.latest('support_bundle');
    return job && (job.state === 'queued' || job.state === 'running') ? (job.stage ?? job.message) : null;
  });
</script>

<SupportBundleDialog
  bind:open={app.supportBundleOpen}
  version={app.appInfo?.version ?? app.serverVersion ?? 'unknown'}
  {folder}
  {sessions}
  {sessionsLoading}
  create={(req) => app.createSupportBundle(req)}
  list={app.listFiles}
  {stage}
  oncreated={(r) => app.toast('info', 'Support bundle', bundleCreatedText(r) + (r.path ? ` Saved as ${r.path}` : ''))}
/>
