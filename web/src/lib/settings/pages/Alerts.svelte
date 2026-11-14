<!--
  Settings › Alerts (wave 6b; functional-spaces 4.10, BRAND §13): the alert sound and the
  thresholds of the attention rules the server evaluates on every frame of a run. Every
  key comes from the server's config meta (category "alerts"); this page groups them and
  adds "Test sound", which also arms the audio (browsers start sound only after a click).
  Levels: Critical (three tones, repeated every 30 s until acknowledged), Attention (two
  tones, once), Info (one soft tone, only when asked). No OS notification (BRAND 4.3).
-->
<script lang="ts">
  import { useApp } from '../../app/state.svelte';
  import Button from '../../components/Button.svelte';
  import type { AttentionLevel } from '../../api/attention';
  import { ALERT_KEYS, isSoundLevel, LEVEL_WORD } from '../../shell/attention/model';
  import AttentionMark from '../../shell/attention/AttentionMark.svelte';
  import { alertSound } from '../../shell/attention/sound';
  import { keysOf } from '../categories';
  import SettingsBlock from '../SettingsBlock.svelte';

  interface Props {
    query?: string;
  }
  let { query = '' }: Props = $props();

  const app = useApp();
  const SOUND_KEYS: readonly string[] = [ALERT_KEYS.sound, ALERT_KEYS.soundInfo, ALERT_KEYS.repeat];
  const AWAKE_KEYS: readonly string[] = [ALERT_KEYS.keepAwake];
  const ruleKeys = $derived(keysOf(app.configMeta ?? {}, 'alerts').filter((k) => !SOUND_KEYS.includes(k) && !AWAKE_KEYS.includes(k)));
  const level = $derived.by(() => {
    const v = app.configValues?.[ALERT_KEYS.sound];
    return isSoundLevel(v) ? v : 'normal';
  });
  let played = $state<string | null>(null);

  function test(l: AttentionLevel): void {
    alertSound.arm();
    const ok = alertSound.play(l, level === 'off' ? 'normal' : level);
    played = alertSound.unavailable
      ? 'This browser has no Web Audio: no alert sound.'
      : ok
        ? `${LEVEL_WORD[l]} tones played${level === 'off' ? ' at Normal (the sound is Off)' : ''}.`
        : 'Click again: the browser is starting the sound.';
  }
</script>

<div class="page">
  <SettingsBlock title="Sound" caption="Short tones from this computer; sound emits no light. Every tone has its item on screen." keys={SOUND_KEYS} {query} hideEmpty={!!query} />
  {#if !query}
    <div class="test">
      <span class="k">Test sound</span>
      {#each ['critical', 'attention', 'info'] as const as l (l)}
        <Button size="s" onclick={() => test(l)}><span class="tb"><AttentionMark level={l} size={10} />{LEVEL_WORD[l]}</span></Button>
      {/each}
      {#if played}<span class="note" role="status">{played}</span>{/if}
    </div>
  {/if}
  <SettingsBlock title="During a run" keys={AWAKE_KEYS} {query} hideEmpty={!!query} />
  {#if ruleKeys.length}
    <SettingsBlock title="Rules and thresholds" caption="Evaluated by the server on every frame of a run; each item states its rule and the numbers. Changes apply from the next frame." keys={ruleKeys} {query} hideEmpty={!!query} />
  {:else if !query}
    <p class="none">This server does not report attention rules (an older version).</p>
  {/if}
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }
  .test {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .tb {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .k {
    min-width: 120px;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .note,
  .none {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>
