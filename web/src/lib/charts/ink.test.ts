import { afterEach, describe, expect, it, vi } from 'vitest';
import { clearInkCache, Ink, inksFrom, monoFont, parseColor, resolveColor, type ColorEngine } from './ink';
import { drawText, measureText, type TextContext } from './text';

afterEach(() => clearInkCache());

describe('parseColor', () => {
  it('reads hex forms', () => {
    expect(parseColor('#d80000')).toEqual([216, 0, 0, 1]);
    expect(parseColor('#FFF')).toEqual([255, 255, 255, 1]);
    expect(parseColor('#c49a3c80')).toEqual([196, 154, 60, 0.502]);
    expect(parseColor('#0008')).toEqual([0, 0, 0, 0.533]);
  });
  it('reads rgb() and rgba() in comma and space syntax', () => {
    expect(parseColor('rgb(216, 0, 0)')).toEqual([216, 0, 0, 1]);
    expect(parseColor('rgba(18, 20, 23, 0.72)')).toEqual([18, 20, 23, 0.72]);
    expect(parseColor('rgb(216 143 143 / 50%)')).toEqual([216, 143, 143, 0.5]);
    expect(parseColor('rgb(100%, 0%, 50%)')).toEqual([255, 0, 128, 1]);
  });
  it('reads color(srgb …), the serialisation of a computed color-mix()', () => {
    // color-mix(in srgb, #8d6b2b 55%, #191b1f) as Chromium serialises it.
    expect(parseColor('color(srgb 0.3361 0.2557 0.1188)')).toEqual([86, 65, 30, 1]);
    expect(parseColor('color(srgb 1 0 0 / 0.5)')).toEqual([255, 0, 0, 0.5]);
    expect(parseColor('color(srgb 50% none 0%)')).toEqual([128, 0, 0, 1]);
  });
  it('returns null for what needs the engine or is not a colour', () => {
    for (const t of ['red', 'color-mix(in srgb, #000 50%, #fff)', 'oklch(0.7 0.1 80)', '#12', 'rgb(1, 2)', 'var(--fg)', '']) {
      expect(parseColor(t), t).toBeNull();
    }
    expect(parseColor('transparent')).toEqual([0, 0, 0, 0]);
  });
});

describe('resolveColor', () => {
  it('parses without the engine when it can, and caches', () => {
    const engine = vi.fn<ColorEngine>(() => null);
    expect(resolveColor('#e8e5df', engine)).toEqual([232, 229, 223, 1]);
    expect(resolveColor('#e8e5df', engine)).toEqual([232, 229, 223, 1]);
    expect(engine).not.toHaveBeenCalled();
  });
  it('asks the engine for color-mix() and caches the answer', () => {
    const engine = vi.fn<ColorEngine>(() => parseColor('color(srgb 0.3361 0.2557 0.1188)'));
    const mix = 'color-mix(in srgb, #8d6b2b 55%, #191b1f)';
    expect(resolveColor(mix, engine)).toEqual([86, 65, 30, 1]);
    expect(resolveColor(mix, engine)).toEqual([86, 65, 30, 1]);
    expect(engine).toHaveBeenCalledTimes(1);
  });
  it('draws an unknown value in black (no light) and does not cache it', () => {
    const engine = vi.fn<ColorEngine>(() => null);
    expect(resolveColor('not-a-colour', engine)).toEqual([0, 0, 0, 1]);
    expect(resolveColor('not-a-colour', engine)).toEqual([0, 0, 0, 1]);
    expect(engine).toHaveBeenCalledTimes(2);
  });
});

describe('Ink', () => {
  it('builds rgba() strings at any alpha and 0..1 floats', () => {
    const ink = new Ink('#d80000');
    expect(ink.a()).toBe('rgba(216, 0, 0, 1)');
    expect(ink.a(0.16)).toBe('rgba(216, 0, 0, 0.16)');
    expect(String(ink)).toBe('rgba(216, 0, 0, 1)');
    expect(ink.rgb01).toEqual([216 / 255, 0, 0]);
  });
  it('multiplies by the colour own alpha', () => {
    expect(new Ink('rgba(0, 0, 0, 0.5)').a(0.5)).toBe('rgba(0, 0, 0, 0.25)');
  });
});

describe('inksFrom', () => {
  const style = (vars: Record<string, string>) => ({ getPropertyValue: (n: string) => vars[n] ?? '' });

  it('resolves the chart tokens of a theme and its alphas', () => {
    const inks = inksFrom(
      style({
        '--chart-surface': ' #100102',
        '--chart-1': '#df6264',
        '--chart-text': '#bb6667',
        '--chart-band-alpha': '0.2',
        '--chart-twilight-4': '0.2',
        '--font-mono': "'IBM Plex Mono', monospace",
      }),
      () => null,
    );
    expect(inks.surface.a()).toBe('rgba(16, 1, 2, 1)');
    expect(inks.target.a(0.5)).toBe('rgba(223, 98, 100, 0.5)');
    expect(inks.bandAlpha).toBe(0.2);
    expect(inks.twilight).toEqual([0, 0.035, 0.065, 0.1, 0.2]);
    expect(inks.flagAlpha).toBe(0.22);
    expect(inks.clipAlpha).toBe(0.5);
    expect(inks.errorAlpha).toBe(0.55);
    // A token that is not defined draws in black, never in a light colour.
    expect(inks.accent.a()).toBe('rgba(0, 0, 0, 1)');
    expect(monoFont(inks, 10, 500, 2)).toBe("500 20px 'IBM Plex Mono', monospace");
  });
});

describe('drawText', () => {
  function fakeContext(): TextContext & { calls: string[] } {
    const calls: string[] = [];
    return {
      calls,
      font: '',
      fillStyle: '',
      textAlign: 'center', // what uPlot leaves behind
      textBaseline: 'middle',
      fillText(text: string, x: number, y: number) {
        calls.push(`${this.textAlign}/${this.textBaseline}/${String(this.fillStyle)}:${text}@${x},${y}`);
      },
      measureText(text: string) {
        return { width: text.length * 6 } as TextMetrics;
      },
    };
  }

  it('always sets alignment, baseline, font and fill', () => {
    const ctx = fakeContext();
    drawText(ctx, 'B', 10, 20, { font: '10px mono', fill: new Ink('#e8e5df'), align: 'left', baseline: 'top' });
    expect(ctx.calls).toEqual(['left/top/rgba(232, 229, 223, 1):B@10,20']);
    expect(ctx.font).toBe('10px mono');
    expect(measureText(ctx, 'abc', '12px mono')).toBe(18);
  });
});
