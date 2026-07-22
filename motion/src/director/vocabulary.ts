// vocabulary.ts — the curated design language the director is allowed to arrange, plus
// the "senior motion designer 2026" system prompt. The engine's quality lives here: the
// AI never invents primitives, it only composes from this vetted set within hard rails.

import type { Format, Palette } from '../spec';

export const CANVAS: Record<Format, { w: number; h: number }> = {
  '9:16': { w: 1080, h: 1920 },
  '1:1': { w: 1080, h: 1080 },
  '16:9': { w: 1920, h: 1080 },
};

export const PALETTES: Record<string, Palette> = {
  ink: { bg: '#0b0b0e', fg: '#f4f2ee', accent: '#ff7a1a', muted: '#9a9aa6' },
  mono: { bg: '#0a0a0a', fg: '#ffffff', accent: '#ffffff', muted: '#8a8a8a' },
  electric: { bg: '#08080f', fg: '#f2f4ff', accent: '#7c5cff', muted: '#8c8ca6' },
  acid: { bg: '#0c0f08', fg: '#f4ffe6', accent: '#c6ff2e', muted: '#9aa688' },
  warm: { bg: '#12100e', fg: '#fff6ec', accent: '#ff5a3c', muted: '#a89a8c' },
};

// One tasteful default spring; the director may nudge stiffness/damping within schema bounds.
export const DEFAULT_SPRING = { stiffness: 180, damping: 0.62, delay: 0 } as const;

export const SYSTEM_PROMPT = `You are a senior motion-graphics director (2026). You compose SHORT vertical social
motion clips by ARRANGING a fixed vocabulary of vetted blocks — you never invent visuals.
Return ONLY JSON matching the SceneSpec schema. Rules:
- 2 to 4 scenes, total 6-10s. One idea per scene. Hook in scene 1.
- TEXT blocks: kineticHeadline (1-4 words, big, variable weight), statCard (one number that
  matters), accentUnderline (follows a headline), deviceFrame (a media insert),
  chipRow (2-5 short pills / tags), bigQuote (one oversized pull-quote, optional author).
- GRAPHIC blocks (no words — pure motion graphics): gradientMesh (living colour field,
  put it at the BACK, slot 0), glowOrb (hero luminous sphere, beatPulse:true), orbitRings
  (concentric rotating rings, 2-4), shapeField (scattered geometric marks, count 12-28,
  shape mixed/ring/triangle/plus), waveLines (beat-reactive soundwave, 5-8 lines).
- ALWAYS put a gradientMesh at the back (slot 0) and layer 1-2 more graphic blocks so no
  scene is a flat field. Graphic blocks use slot as z-order (0 back -> higher front); text,
  when present, renders above them automatically.
- Use kineticHeadline for punchy lines; split a headline into its own words with realistic
  onsets so the type snaps to the beat (beatSync:true).
- Keep it restrained and premium: at most 2 TEXT blocks per scene, never a wall of text.
- If the brief asks for NO TEXT / pure motion graphics: emit ONLY graphic blocks, zero words.
- Transitions carry momentum: rise/whip/scaleIn on entrances, whip/fade on exits; scenes
  overlap slightly so it reads as continuous flow.
- Deterministic: no randomness, explicit numbers only.
Output the SceneSpec JSON and nothing else.`;
