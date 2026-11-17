<!--
  Devices table (02 2.2 / 2.3 W1 / 2.4, Qt connection_page.py:383-471, M23):
  the four Alpaca devices, always visible, one row each.

  - State: a mark whose shape carries it (filled ready, ring off, half busy,
    cross error; a spinner while connecting) and a word, so it reads in
    Night Red.
  - Detail: the driver's name, what the device does, or the FULL error text
    (never cut, Qt cut it to 48 characters), wrapped on two lines with the
    whole text in the tooltip; the server's warnings (profile mismatch,
    mount clock) under it.
  - Action, icon + label (it moves or releases hardware, BRAND 7): Connect,
    Disconnect, Retry (error), Stop retrying (mount auto-retry, every 10 s),
    Cancel (an attempt in progress). Each request runs on its own: the
    other rows stay usable while one address times out.
  - Disconnecting the camera during an exposure or live view, or the mount
    during a slew, asks first (02 W10b); otherwise no confirmation (Q-C5).
  - Connect all: the server claims every device to connect at once; those
    waiting for their turn read "Queued" (idle ring, one line), the toolbar
    summary says which one is being opened.
  - Rows have no default action, so the table selects nothing (no brass
    edge on an incidental click; an error row keeps its red edge).
  - Server link lost: the rows are the last ones received: ring marks in the
    idle tone, muted words, "Last known" in the header; actions wait.
  - The table copies as TSV (⌘/Ctrl+C on a row): useful for a bug report.
-->
<script lang="ts">
  import type { DeviceId } from '../api/types';
  import { useApp } from '../app/state.svelte';
  import Card from '../components/Card.svelte';
  import ConfirmDialog from '../components/ConfirmDialog.svelte';
  import Icon from '../components/Icon.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Table from '../components/Table.svelte';
  import type { Column } from '../components/table';
  import { tooltip } from '../components/tooltip';
  import DeviceMark from './DeviceMark.svelte';
  import {
    ACTION_ICONS,
    ACTION_LABELS,
    type DeviceView,
    deviceViews,
    disconnectRisk,
    isReleaseAction,
  } from './model';

  const app = useApp();

  /**
   * The server marks the devices of a Connect all "queued" at once; until
   * its first event arrives, a disconnected row of a Connect all in flight
   * reads the same. With the server link lost, every row is a last known
   * state: no state colour, no claim.
   */
  const rows = $derived(
    deviceViews(app.devices).map((v): DeviceView => {
      if (app.stale) return { ...v, tone: 'idle', mark: 'ring', spinning: false, problem: null };
      if (app.busy.connectAll && v.phase === 'disconnected') {
        return { ...v, word: 'Queued', tone: 'idle', mark: 'ring', problem: null, detail: '', action: 'cancel' };
      }
      return v;
    }),
  );

  const columns: Column<DeviceView>[] = [
    { id: 'device', label: 'Device', value: (r) => r.label, sortable: false, width: '124px' },
    { id: 'state', label: 'State', value: (r) => r.word, sortable: false, width: '118px' },
    { id: 'detail', label: 'Detail', value: (r) => [r.detail, ...r.warnings].filter(Boolean).join(' | '), sortable: false, wrap: true },
    // 1 %: the column shrinks to its button, the reason gets the rest.
    { id: 'action', label: 'Action', hideLabel: true, sortable: false, width: '1%', value: (r) => ACTION_LABELS[r.action] },
  ];

  let confirm: { id: DeviceId; risk: string; label: string } | null = $state(null);
  let confirmOpen = $state(false);

  function actionReason(v: DeviceView): string | null {
    if (!app.linkOpen) return 'the ARGOS server is not reachable';
    if (v.action === 'connect' || v.action === 'retry') {
      const problem = app.connectProblem();
      if (problem) return `${problem} in the Link card`;
      if (app.busy.connectAll) return 'Connect all is running';
    }
    return null;
  }

  function act(v: DeviceView): void {
    if (isReleaseAction(v.action)) {
      const risk = v.action === 'disconnect' ? disconnectRisk(app.running, [v.id]) : null;
      if (risk) {
        confirm = { id: v.id, risk, label: v.label };
        confirmOpen = true;
        return;
      }
      void app.disconnectDevice(v.id);
    } else {
      void app.connectDevice(v.id);
    }
  }

  const fullText = (v: DeviceView) => [v.detail, ...v.warnings].filter(Boolean).join('\n');
</script>

<Card title="Devices" icon="network" dense>
  {#snippet status()}
    <span class="mode caption">
      {#if app.stale}
        Last known · server link lost
      {:else if app.connectMode === 'alpaca'}
        <span class="num">{app.alpacaHost ? `${app.alpacaHost}:${app.alpacaPort}` : 'no address'}</span>
      {:else}
        Simulator
      {/if}
    </span>
  {/snippet}
  <div class="table" class:stale={app.stale}>
    <Table
      label="Devices"
      {columns}
      {rows}
      rowKey={(r) => r.id}
      density="comfortable"
      selectable={false}
      problem={(r) => r.problem === 'error'}
      oncopy={(_, n) => app.toast('info', n === 1 ? 'Device row copied' : 'Devices copied')}
    >
      {#snippet cell(row, col)}
        {#if col.id === 'device'}
          <span class="device">
            <Icon name={row.icon} size="s" />
            <span>{row.label}</span>
          </span>
        {:else if col.id === 'state'}
          <span class="state tone-{row.tone}">
            <DeviceMark mark={row.mark} tone={row.tone} spinning={!app.stale && (row.spinning || !!app.busy[`device.${row.id}`])} />
            <span>{row.word}</span>
          </span>
        {:else if col.id === 'detail'}
          {#if row.detail || row.warnings.length}
            <span class="detail" use:tooltip={{ text: fullText(row), placement: 'top', disabled: !fullText(row) }}>
              {#if row.detail}<span class="text" class:error={row.problem === 'error'} class:muted={row.phase !== 'error' && row.phase !== 'connected' && row.phase !== 'busy'}>{row.detail}</span>{/if}
              {#each row.warnings as w (w)}<span class="warn">{w}</span>{/each}
            </span>
          {:else}
            <span class="muted">—</span>
          {/if}
        {:else}
          <span class="action">
            <IconButton
              icon={ACTION_ICONS[row.action]}
              label={ACTION_LABELS[row.action]}
              tooltipText={`${ACTION_LABELS[row.action]}: ${row.label.toLowerCase()}`}
              showLabel
              size="s"
              variant="secondary"
              glyphTone={isReleaseAction(row.action) ? 'danger' : undefined}
              busy={!!app.busy[`${isReleaseAction(row.action) ? 'release' : 'device'}.${row.id}`]}
              disabledReason={actionReason(row)}
              tooltip="left"
              onclick={() => act(row)}
            />
          </span>
        {/if}
      {/snippet}
    </Table>
  </div>
</Card>

<ConfirmDialog
  bind:open={confirmOpen}
  title={confirm ? `Disconnect the ${confirm.label.toLowerCase()}?` : 'Disconnect?'}
  message={confirm?.risk ?? ''}
  confirmLabel="Disconnect"
  destructive
  onconfirm={() => (confirm ? app.disconnectDevice(confirm.id) : undefined)}
/>

<style>
  .table {
    margin: calc(-1 * var(--space-3)) calc(-1 * var(--space-4));
  }
  .table :global(td) {
    padding-top: 2px;
    padding-bottom: 2px;
  }
  /* The table's text starts where the card's content does (its title icon, the cards below). */
  .table :global(td:first-child),
  .table :global(th:first-child) {
    padding-left: var(--space-4);
  }
  .table :global(td:last-child),
  .table :global(th:last-child) {
    padding-right: var(--space-4);
  }

  /* Block-level flex, centred by the cell: name, state and detail share one middle line. */
  .device,
  .state {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    white-space: nowrap;
  }
  .stale .state,
  .stale .text,
  .stale .device {
    color: var(--text-muted);
  }
  .device {
    color: var(--fg);
  }
  .device :global(svg) {
    color: var(--fg-muted);
  }

  .detail {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }
  .text {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    color: var(--fg);
    line-height: var(--leading-normal);
  }
  .text.error {
    color: var(--fg);
  }
  .muted {
    color: var(--text-muted);
  }
  .warn {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    padding-left: var(--space-2);
    border-left: 2px solid var(--warning);
    color: var(--fg);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
  }

  .action {
    display: flex;
    justify-content: flex-end;
  }

  .caption {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
