/**
 * Jog model (pure, unit-tested): what each mount axis should do given the
 * keys and pointers held right now, and the dead-man rule.
 *
 * - Two axes, tracked separately (fixes Qt P22: releasing Up while Right is
 *   held stops only the altitude axis; Up + Right jogs diagonally).
 * - On one axis, the most recent press wins; releasing it falls back to the
 *   opposite direction if that is still held (no stuck axis, no surprise).
 * - Sources are named ("key:ArrowUp", "pointer:north") so a key and a
 *   pointer on the same direction release independently.
 * - Dead-man: the client renews every RENEW_MS while an axis moves; the
 *   server stops an axis not renewed within DEADMAN_MS or when the event
 *   socket closes (spec A10). The UI shows the renewal age.
 */

export type Axis = 'primary' | 'secondary';
export type Direction = 'north' | 'south' | 'east' | 'west';

export const RENEW_MS = 250;
export const DEADMAN_MS = 1000;

/** Spec wireframe and Qt pad: N up, S down, W left, E right (mount axes; BRAND 7 note on sky orientation). */
export const DIRECTIONS: Record<Direction, { axis: Axis; sign: 1 | -1; key: string; label: string }> = {
  north: { axis: 'secondary', sign: 1, key: 'ArrowUp', label: 'North' },
  south: { axis: 'secondary', sign: -1, key: 'ArrowDown', label: 'South' },
  east: { axis: 'primary', sign: 1, key: 'ArrowRight', label: 'East' },
  west: { axis: 'primary', sign: -1, key: 'ArrowLeft', label: 'West' },
};

export function directionOfKey(key: string): Direction | null {
  for (const [d, v] of Object.entries(DIRECTIONS)) if (v.key === key) return d as Direction;
  return null;
}

interface Hold {
  source: string;
  direction: Direction;
  at: number;
}

export class JogHolds {
  private holds: Hold[] = [];
  private seq = 0;

  press(source: string, direction: Direction): void {
    this.holds = this.holds.filter((h) => h.source !== source);
    this.holds.push({ source, direction, at: ++this.seq });
  }

  release(source: string): void {
    this.holds = this.holds.filter((h) => h.source !== source);
  }

  releaseAll(): void {
    this.holds = [];
  }

  /** Signed direction of an axis: +1, -1 or 0 (the newest hold on that axis wins). */
  sign(axis: Axis): -1 | 0 | 1 {
    let best: Hold | null = null;
    for (const h of this.holds) {
      if (DIRECTIONS[h.direction].axis !== axis) continue;
      if (!best || h.at > best.at) best = h;
    }
    return best ? DIRECTIONS[best.direction].sign : 0;
  }

  /** The direction an axis is moving in (for the pressed style of the pad). */
  active(axis: Axis): Direction | null {
    const s = this.sign(axis);
    if (s === 0) return null;
    return (Object.keys(DIRECTIONS) as Direction[]).find((d) => DIRECTIONS[d].axis === axis && DIRECTIONS[d].sign === s) ?? null;
  }

  get empty(): boolean {
    return this.holds.length === 0;
  }
}

/** True when the server must stop the axis: no renewal within the dead-man window. */
export function deadmanExpired(lastRenew: number, now: number, limit = DEADMAN_MS): boolean {
  return now - lastRenew > limit;
}
