<!--
  Support bundle dialog (01 2.3.6, D14; README A5): one modal, opened from
  the Help popover and from Settings › Privacy & diagnostics, instead of the
  four Qt steps (shell.py:478-533).

  - Says what the ZIP holds and what is replaced in it, from the server's
    contract (supportbundle.ts; protocol.md A5), and that ARGOS never
    uploads it. Each part is marked included or not as the boxes change.
  - Session metadata is OFF by default (Q-G17); ticking it enables the
    session chooser (A67 list). Choosing no session keeps the bundle
    without one (fixes 01 P35). Crash reports are in by default; the site
    coordinates are out by default (redacted everywhere).
  - An existing file (409 file_exists) asks "Replace?" inline.
  - Save to: a path (desktop: the server writes it; [browse] opens the
    FilePicker in save mode) or, with `download`, the browser downloads it.
    The proposed name carries the UTC time, so a second bundle never meets
    an overwrite prompt.
  - Busy: "Create bundle" spins, the dialog stays open and cannot be
    dismissed; a failure stays inline with the OS words; success closes it
    and calls `oncreated` (the caller shows the toast with its file count).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import Checkbox from './Checkbox.svelte';
  import { refusalText } from './commit.svelte';
  import Control from './Control.svelte';
  import Dialog from './Dialog.svelte';
  import FilePicker from './FilePicker.svelte';
  import { type FsLister, ZIP_FILTER, baseName, parentOf } from './filepicker';
  import { middlePath } from './pathfield';
  import Select from './Select.svelte';
  import {
    BUNDLE_CONTENTS,
    BUNDLE_REDACTION,
    type BundlePart,
    type BundleRequest,
    type BundleResult,
    type BundleSession,
    bundleProblem,
    bundleRequest,
    defaultBundleName,
    sessionLabel,
  } from './supportbundle';

  interface Props {
    open?: boolean;
    /** ARGOS version (A1), for the proposed file name. */
    version: string;
    /** Folder proposed for the ZIP (the Desktop, else home); ignored with `download`. */
    folder?: string | null;
    /** Browser build: the server keeps the ZIP for a download (destination null). */
    download?: boolean;
    sessions?: readonly BundleSession[];
    /** The sessions list is still loading (A67). */
    sessionsLoading?: boolean;
    create: (req: BundleRequest) => Promise<BundleResult>;
    list?: FsLister | null;
    /** The job's stage while it runs ("writing logs"), when known. */
    stage?: string | null;
    oncreated?: (r: BundleResult) => void;
    preview?: boolean;
    /** Specimen only: freeze a state. */
    pin?: {
      includeSession?: boolean;
      sessionDir?: string | null;
      busy?: boolean;
      error?: string | null;
      exists?: boolean;
    } | null;
  }

  let {
    open = $bindable(false),
    version,
    folder = null,
    download = false,
    sessions = [],
    sessionsLoading = false,
    create,
    list = null,
    stage = null,
    oncreated,
    preview = false,
    pin = null,
  }: Props = $props();

  let includeSession = $state(false);
  let includeCrash = $state(true);
  let includeSite = $state(false);
  let exists = $state(false);
  let sessionDir: string | null = $state(null);
  let destination = $state('');
  let busy = $state(false);
  let error: string | null = $state(null);
  let pickerOpen = $state(false);

  // A fresh proposal each time it opens (the name carries the time).
  $effect(() => {
    if (!open) return;
    untrack(reset);
  });

  function reset(): void {
    includeSession = pin?.includeSession ?? false; // Q-G17: off by default
    includeCrash = true;
    includeSite = false;
    sessionDir = pin?.sessionDir ?? null;
    busy = false;
    error = pin?.error ?? null;
    exists = pin?.exists ?? false;
    const name = defaultBundleName(version);
    destination = folder ? `${folder.replace(/[\\/]$/, '')}/${name}` : `~/${name}`;
  }

  const shownBusy = $derived(pin?.busy ?? busy);
  const form = $derived({
    destination: download ? null : destination,
    includeSession,
    sessionDir,
    includeSite,
    includeCrashReports: includeCrash,
  });
  const included = $derived<Record<BundlePart, boolean>>({
    base: true,
    logs: true,
    crash: includeCrash,
    session: includeSession && !!sessionDir,
  });
  const problem = $derived(bundleProblem(form));
  const sessionOptions = $derived(sessions.map((s) => ({ value: s.path, label: sessionLabel(s) })));

  async function submit(overwrite = false): Promise<void> {
    if (problem || busy) return;
    busy = true;
    error = null;
    exists = false;
    try {
      const r = await create(bundleRequest({ ...form, overwrite }));
      busy = false;
      open = false;
      oncreated?.(r);
    } catch (err) {
      busy = false;
      // 409 file_exists: ask before replacing (never overwrite silently).
      if (err && typeof err === 'object' && (err as { code?: string }).code === 'file_exists') exists = true;
      else error = refusalText(err);
    }
  }
</script>

<Dialog bind:open title="Create a local support bundle" size="m" {preview} dismissible={!shownBusy}>
  <p class="intro">
    A ZIP of redacted ARGOS logs for a bug report. It contains no raw FITS frames and no network
    addresses. ARGOS never uploads it: it stays on this computer until you choose to share it.
  </p>

  <ul class="contents" aria-label="What the ZIP contains">
    {#each BUNDLE_CONTENTS as c (c.part)}
      <li class:off={!included[c.part]}>
        <span class="part">{c.title}{included[c.part] ? '' : ' · not included'}</span>
        <span class="detail">{c.detail}</span>
      </li>
    {/each}
    <li class="redaction"><span class="detail">{BUNDLE_REDACTION}</span></li>
  </ul>

  <div class="options">
    <Checkbox label="Include crash reports" bind:checked={includeCrash} disabledReason={shownBusy ? 'wait until it finishes' : null} />
    <Checkbox
      label="Include the site coordinates"
      detail="Off: latitude, longitude and elevation are replaced everywhere."
      bind:checked={includeSite}
      disabledReason={shownBusy ? 'wait until it finishes' : null}
    />
  </div>

  <div class="session">
    <Checkbox
      label="Include one session's metadata (JSON, JSONL, CSV)"
      bind:checked={includeSession}
      disabledReason={shownBusy ? 'wait until it finishes' : null}
    />
    <div class="session-pick">
      <Select
        label="Session"
        options={sessionOptions}
        bind:value={sessionDir}
        placeholder={sessionsLoading ? 'Loading the sessions…' : sessions.length ? 'Choose a session…' : 'No session found'}
        disabledReason={!includeSession
          ? 'tick “Include one session’s metadata” first'
          : shownBusy
            ? 'wait until it finishes'
            : !sessions.length
              ? 'no session in the sessions folder'
              : null}
      />
    </div>
  </div>

  {#if download}
    <p class="dest-fact">The ZIP is downloaded by the browser once it is ready.</p>
  {:else}
    <div class="dest">
      <label class="key" for="sb-dest">Save to</label>
      <input
        id="sb-dest"
        class="mono"
        type="text"
        autocomplete="off"
        spellcheck="false"
        bind:value={destination}
        use:middlePath={{ value: destination }}
        readonly={shownBusy}
        aria-describedby={problem ? 'sb-problem' : undefined}
      />
      {#if list}
        <Control
          icon="browse"
          label="Choose where to save the ZIP…"
          size="s"
          disabledReason={shownBusy ? 'wait until it finishes' : null}
          onclick={() => (pickerOpen = true)}
        />
      {/if}
    </div>
  {/if}

  {#if exists}
    <p class="replace" role="alert">A file with this name already exists there. Replace it?</p>
  {:else if error}
    <p class="error" role="alert">Could not create the ZIP: {error}</p>
  {:else if shownBusy && stage}
    <p class="stage" aria-live="polite">{stage}</p>
  {/if}
  {#if problem && !shownBusy}
    <span id="sb-problem" class="visually-hidden">{problem}</span>
  {/if}

  {#snippet footer()}
    <Control label="Cancel" size="s" disabledReason={shownBusy ? 'wait until it finishes' : null} onclick={() => (open = false)} />
    {#if exists}
      <Control label="Replace" variant="danger" size="s" busy={shownBusy} onclick={() => void submit(true)} />
    {:else}
      <Control
        label="Create bundle"
        variant="primary"
        size="s"
        busy={shownBusy}
        disabledReason={problem}
        onclick={() => void submit()}
      />
    {/if}
  {/snippet}
</Dialog>

{#if list && !download}
  <FilePicker
    bind:open={pickerOpen}
    mode="save-file"
    title="Save the support bundle"
    start={parentOf(destination) ?? folder}
    defaultName={baseName(destination) || defaultBundleName(version)}
    filters={[ZIP_FILTER]}
    {list}
    onchoose={(p) => (destination = p)}
  />
{/if}

<style>
  .intro {
    margin: 0 0 var(--space-3);
  }
  .contents {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0 0 var(--space-4);
    padding: var(--space-3) var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    list-style: none;
  }
  .contents li {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .part {
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
  }
  .detail {
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
  }
  .off .part {
    color: var(--text-muted);
    font-weight: var(--weight-regular);
  }
  .options {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin-bottom: var(--space-2);
  }
  .redaction {
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .replace {
    display: flex;
    align-items: baseline;
    gap: 6px;
    margin: var(--space-3) 0 0;
    font-size: var(--text-s);
  }
  .replace::before {
    content: '';
    flex: none;
    width: 2px;
    height: 9px;
    margin: 0 2px;
    background: linear-gradient(var(--warning) 0 6px, transparent 6px 7px, var(--warning) 7px 9px);
  }
  .session {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-bottom: var(--space-4);
  }
  .session-pick {
    padding-left: 26px;
  }
  .dest {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-3);
  }
  .key {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .dest input {
    height: var(--input-h);
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-s);
    text-overflow: ellipsis;
  }
  .dest input:hover {
    border-color: var(--fg-muted);
  }
  .dest input:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
  .mono {
    font-family: var(--font-mono);
  }
  .dest-fact,
  .stage {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .error {
    display: flex;
    align-items: baseline;
    gap: 6px;
    margin: var(--space-3) 0 0;
    font-size: var(--text-s);
  }
  .error::before {
    content: '';
    flex: none;
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
    background: var(--danger);
    transform: translateY(-1px);
  }
</style>
