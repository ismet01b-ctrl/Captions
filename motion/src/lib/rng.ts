// rng.ts — deterministic PRNG. No Math.random() anywhere in the render path, so a
// spec renders bit-identically on every machine (and every Remotion seek).

/** mulberry32: fast, seedable, good-enough distribution for jitter/scatter. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Stable per-index hash in [0,1) — no state, reproducible, for staggered reveals. */
export function hash01(i: number, salt = 0): number {
  return ((Math.imul(i + salt + 1, 2654435761) >>> 0) & 0x3ff) / 1023;
}
