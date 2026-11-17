/**
 * Alert tones through the Web Audio API: short synthesised sine tones, no
 * sound files, no dependency. Sound emits no light (Night Red) and reaches an
 * observer in another room; it never carries information found nowhere else
 * (BRAND 7): every tone has an attention item on screen.
 *
 * Browsers only start audio after a user gesture (WebKit and Chromium
 * autoplay policy): the context is created by armSound() from a click
 * (Start sequence, Watch, "Test sound").
 */

import type { Level } from './rules';

let ctx: AudioContext | null = null;

export function armAudio(): boolean {
  try {
    ctx ??= new AudioContext();
    void ctx.resume();
    return true;
  } catch {
    return false;
  }
}

function tone(at: number, freq: number, dur: number, gain: number): void {
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const g = ctx.createGain();
  osc.type = 'sine';
  osc.frequency.value = freq;
  // 10 ms attack and release: no click.
  g.gain.setValueAtTime(0, at);
  g.gain.linearRampToValueAtTime(gain, at + 0.01);
  g.gain.setValueAtTime(gain, at + dur - 0.01);
  g.gain.linearRampToValueAtTime(0, at + dur);
  osc.connect(g).connect(ctx.destination);
  osc.start(at);
  osc.stop(at + dur + 0.02);
}

/** Critical: three descending tones; attention: two; info: one soft tone. */
export function alertTone(level: Level, volume: 'soft' | 'normal'): void {
  if (!ctx) return;
  const v = volume === 'soft' ? 0.06 : 0.16;
  const t = ctx.currentTime + 0.02;
  if (level === 'critical') {
    tone(t, 880, 0.18, v);
    tone(t + 0.24, 740, 0.18, v);
    tone(t + 0.48, 587, 0.3, v);
  } else if (level === 'attention') {
    tone(t, 660, 0.16, v);
    tone(t + 0.22, 880, 0.22, v);
  } else {
    tone(t, 523, 0.2, v * 0.6);
  }
}
