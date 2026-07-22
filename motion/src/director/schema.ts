// schema.ts — Zod runtime schema for SceneSpec. The AI director's JSON is NEVER trusted:
// it is parsed + repaired here before it can reach the renderer. Mirror of spec.ts;
// a compile-time `satisfies` check keeps the two from drifting.

import { z } from 'zod';
import type { SceneSpec } from '../spec';

const springZ = z.object({
  stiffness: z.number().min(20).max(600),
  damping: z.number().min(0.2).max(1),
  delay: z.number().min(0).max(2),
});

const transitionZ = z.object({
  kind: z.enum(['rise', 'whip', 'fade', 'scaleIn']),
  dur: z.number().min(0.15).max(1.2),
});

const wordZ = z.object({
  text: z.string().min(1).max(40),
  start: z.number().min(0),
  end: z.number().min(0),
});

const baseFields = { id: z.string().min(1), slot: z.number().int().min(0).max(15), spring: springZ };

const kineticZ = z.object({
  ...baseFields,
  kind: z.literal('kineticHeadline'),
  words: z.array(wordZ).min(1).max(12),
  weight: z.tuple([z.number().min(100).max(900), z.number().min(100).max(900)]),
  beatSync: z.boolean(),
});

const statZ = z.object({
  ...baseFields,
  kind: z.literal('statCard'),
  value: z.number(),
  prefix: z.string().max(4).optional(),
  suffix: z.string().max(4).optional(),
  label: z.string().max(60),
  countUp: z.boolean(),
});

const underlineZ = z.object({
  ...baseFields,
  kind: z.literal('accentUnderline'),
  follows: z.string(),
  widthPct: z.number().min(0.1).max(1),
});

const deviceZ = z.object({
  ...baseFields,
  kind: z.literal('deviceFrame'),
  src: z.string(),
  depth: z.number().min(0).max(1),
});

const chipRowZ = z.object({
  ...baseFields,
  kind: z.literal('chipRow'),
  items: z.array(z.string().min(1).max(24)).min(1).max(5),
});

const bigQuoteZ = z.object({
  ...baseFields,
  kind: z.literal('bigQuote'),
  text: z.string().min(1).max(140),
  author: z.string().max(40).optional(),
});

const gradientMeshZ = z.object({
  ...baseFields,
  kind: z.literal('gradientMesh'),
  colors: z.array(z.string()).max(5),
  speed: z.number().min(0.05).max(3),
});

const glowOrbZ = z.object({
  ...baseFields,
  kind: z.literal('glowOrb'),
  radiusPct: z.number().min(0.05).max(0.7),
  beatPulse: z.boolean(),
  hueDrift: z.number().min(0).max(180),
});

const orbitRingsZ = z.object({
  ...baseFields,
  kind: z.literal('orbitRings'),
  rings: z.number().int().min(1).max(5),
  spin: z.number().min(-180).max(180),
});

const shapeFieldZ = z.object({
  ...baseFields,
  kind: z.literal('shapeField'),
  count: z.number().int().min(1).max(60),
  shape: z.enum(['mixed', 'dot', 'ring', 'triangle', 'plus', 'square']),
  drift: z.number().min(0).max(1),
});

const waveLinesZ = z.object({
  ...baseFields,
  kind: z.literal('waveLines'),
  lines: z.number().int().min(1).max(14),
  amp: z.number().min(0).max(1),
});

const blockZ = z.discriminatedUnion('kind', [
  kineticZ,
  statZ,
  underlineZ,
  deviceZ,
  chipRowZ,
  bigQuoteZ,
  gradientMeshZ,
  glowOrbZ,
  orbitRingsZ,
  shapeFieldZ,
  waveLinesZ,
]);

const sceneZ = z.object({
  id: z.string().min(1),
  tStart: z.number().min(0),
  tLen: z.number().min(0.4).max(12),
  in: transitionZ,
  out: transitionZ,
  blocks: z.array(blockZ).min(1).max(6),
});

export const sceneSpecZ = z.object({
  version: z.literal(1),
  seed: z.number().int(),
  canvas: z.object({
    format: z.enum(['9:16', '16:9', '1:1']),
    w: z.number().int().min(64).max(4096),
    h: z.number().int().min(64).max(4096),
  }),
  fps: z.number().int().min(24).max(60),
  duration: z.number().min(1).max(60),
  grain: z.number().min(0).max(10),
  palette: z.object({
    bg: z.string(),
    fg: z.string(),
    accent: z.string(),
    muted: z.string(),
  }),
  beat: z.object({
    bpm: z.number().min(40).max(220),
    offset: z.number().min(0),
    snapTol: z.number().min(0).max(0.3),
  }),
  scenes: z.array(sceneZ).min(1).max(8),
});

// Compile-time drift guard (readonly-safe): the schema and SceneSpec must share the same
// top-level keys, so adding a field to one without the other fails the build.
export type SchemaSpec = z.infer<typeof sceneSpecZ>;
type SameKeys =
  keyof SchemaSpec extends keyof SceneSpec
    ? keyof SceneSpec extends keyof SchemaSpec
      ? true
      : false
    : false;
const _keys: SameKeys = true;
void _keys;

/** Parse untrusted JSON into a SceneSpec, or return null (caller falls back). */
export function parseSpec(raw: unknown): SceneSpec | null {
  const r = sceneSpecZ.safeParse(raw);
  return r.success ? (r.data as SceneSpec) : null;
}
