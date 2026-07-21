// easing.ts — the small set of curves used across the engine. Everything is pure and
// framerate-independent (input is a normalised 0..1 progress).

export const clamp01 = (x: number): number => (x < 0 ? 0 : x > 1 ? 1 : x);

/** Quintic ease-out: fast settle, no linear tell. The default for entrances/exits. */
export const easeOutQuint = (t: number): number => 1 - Math.pow(1 - clamp01(t), 5);

/** Cubic ease-in-out for camera-like moves. */
export const easeInOutCubic = (t: number): number => {
  const x = clamp01(t);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
};

export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

export const mix = (a: number, b: number, t: number): number => lerp(a, b, clamp01(t));
