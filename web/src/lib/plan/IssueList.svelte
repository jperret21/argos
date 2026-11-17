<!--
  The plan's issues in one list (A59; spec 2.4 "Invalid cell"; the exit criterion's "no
  silent clamp"): errors first (they block Start), then warnings, each with its place
  ("Step 2 · Cadence") and the server's words; a press takes the focus to the field. The
  server's notes on the last change ("Planning metadata dropped: …") follow, muted.
-->
<script lang="ts">
  import type { PlanIssue } from '../api/plan';
  import { issueText, issueTitle } from './model';

  interface Props {
    issues: readonly PlanIssue[];
    notes?: readonly string[];
    onfocus: (i: PlanIssue) => void;
  }

  let { issues, notes = [], onfocus }: Props = $props();

  const sorted = $derived([...issues].sort((a, b) => (a.level === b.level ? 0 : a.level === 'error' ? -1 : 1)));
  const errors = $derived(issues.filter((i) => i.level === 'error').length);
  const warnings = $derived(issues.length - errors);
</script>

{#if sorted.length || notes.length}
  <div class="issues" role="region" aria-label="Plan issues">
    {#if sorted.length}
      <p class="head">
        {#if errors}<span>{errors} to fix before Start</span>{/if}{#if errors && warnings}<span class="sep" aria-hidden="true">·</span><span class="visually-hidden">, </span>{/if}{#if warnings}<span class="muted">{warnings} warning{warnings === 1 ? '' : 's'}</span>{/if}
      </p>
      <ul>
        {#each sorted as i, k (k)}
          <li>
            <button type="button" class="row" onclick={() => onfocus(i)}>
              <span class="mark" class:warn={i.level === 'warning'} aria-hidden="true"></span>
              <span class="where">{issueTitle(i)}</span>
              <span class="what">{issueText(i)}</span>
              <span class="visually-hidden">{i.level === 'error' ? '(blocks Start)' : '(warning)'}</span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
    {#each notes as n (n)}
      <p class="note">{n}</p>
    {/each}
  </div>
{/if}

<style>
  .issues {
    flex: none;
    /* Up to about 40 % of the Steps region (a short plan with many issues shows them all);
       never below 152 px, the list scrolls beyond. */
    max-height: max(152px, 40%);
    overflow-y: auto;
    padding: var(--space-2) var(--space-3);
    border-top: var(--border-w) solid var(--border-soft);
    background: var(--bg);
  }
  .head {
    margin: 0 0 var(--space-1);
    color: var(--fg);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
  }
  .muted,
  .sep {
    color: var(--text-muted);
  }
  .sep {
    margin: 0 var(--space-2);
  }
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .row {
    display: grid;
    grid-template-columns: 10px max-content minmax(0, 1fr);
    align-items: baseline;
    gap: var(--space-2);
    width: 100%;
    padding: 2px var(--space-1);
    border: 0;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font: inherit;
    font-size: var(--text-xs);
    text-align: left;
    cursor: pointer;
  }
  .row:hover {
    background: var(--hover-bg);
  }
  .row:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .mark {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
    background: var(--danger);
  }
  .mark.warn {
    /* The attention mark, a bar over a dot (BRAND 8, run/LevelMark): never a triangle,
       the check star's shape (BRAND 2.6; design review W6a). */
    width: 3px;
    height: 9px;
    border: none;
    border-radius: 0;
    background: linear-gradient(var(--warning) 0 5px, transparent 5px 7px, var(--warning) 7px 9px);
  }
  .where {
    color: var(--text-muted);
    font-family: var(--font-mono);
  }
  .what {
    overflow-wrap: anywhere;
  }
  .note {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
